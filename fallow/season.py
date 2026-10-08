"""One campaign over one 20 km cell: NDVI maxima per pixel, then histograms per municipality.

Nothing per pixel is kept. Each municipality gets a 2D histogram of (spring NDVI maximum,
summer NDVI maximum) over its cropland pixels, which is all the classification needs.
"""
from __future__ import annotations

import warnings
from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd
import rasterio
from odc.geo.geobox import GeoBox
from odc.stac import configure_rio, load
from pystac import Item
from pystac_client import Client
from rasterio.enums import Resampling
from rasterio.features import rasterize
from rasterio.vrt import WarpedVRT

from . import config, geo

configure_rio(cloud_defaults=True, aws={"aws_unsigned": True})

_client: Client | None = None


def client() -> Client:
    global _client
    if _client is None:
        _client = Client.open(config.STAC_URL)
    return _client


@dataclass
class Cell:
    col: int
    row: int

    @property
    def id(self) -> str:
        return f"{self.col}_{self.row}"

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        x0, y0 = self.col * config.CELL_M, self.row * config.CELL_M
        return x0, y0, x0 + config.CELL_M, y0 + config.CELL_M

    def geobox(self) -> GeoBox:
        return GeoBox.from_bbox(self.bounds, crs=config.WORK_CRS, resolution=config.RESOLUTION_M)


def cells_for(munis: list[geo.Municipality]) -> list[Cell]:
    """Cells of the fixed national grid that touch any of the municipalities."""
    from shapely.geometry import box
    from shapely.strtree import STRtree

    tree = STRtree([m.geom for m in munis])
    x0, y0, x1, y1 = np.array([m.geom.bounds for m in munis]).T
    cmin, rmin = int(x0.min() // config.CELL_M), int(y0.min() // config.CELL_M)
    cmax, rmax = int(x1.max() // config.CELL_M), int(y1.max() // config.CELL_M)
    out = []
    for c in range(cmin, cmax + 1):
        for r in range(rmin, rmax + 1):
            cell = Cell(c, r)
            if len(tree.query(box(*cell.bounds), predicate="intersects")):
                out.append(cell)
    return out


# --- Inputs ---------------------------------------------------------------------------------

def search(cell: Cell, year: int) -> list[Item]:
    """Scenes over the cell from the first spring month to the last summer month."""
    lon0, lat0, lon1, lat1 = geo.cell_bounds_lonlat(cell.bounds)
    start = date(year, min(config.SPRING_MONTHS), 1)
    end = date(year, *config.CAMPAIGN_END)
    s = client().search(
        collections=[config.STAC_COLLECTION], bbox=[lon0, lat0, lon1, lat1],
        datetime=f"{start.isoformat()}T00:00:00Z/{end.isoformat()}T23:59:59Z",
        query={"eo:cloud_cover": {"lt": config.MAX_SCENE_CLOUD}},
    )
    return dedupe(list(s.items()))


def _baseline(item: Item) -> float:
    try:
        return float(item.properties.get("s2:processing_baseline", "0"))
    except ValueError:
        return 0.0


def dedupe(items: list[Item]) -> list[Item]:
    """One item per tile and date, and one processing baseline family per date.

    Earth Search holds many dates twice: the original processing (id ending _0) and the
    2022+ reprocessing (_1, baseline 05.00, with the -1000 DN offset). Reading both doubles the
    cost, and mixing them in one day would break the per-day offset check, so the latest
    version of each tile wins and, if a day still mixes pre- and post-04.00 tiles, only the
    newer family is kept.
    """
    best: dict[tuple, Item] = {}
    for it in items:
        tile = it.properties.get("s2:mgrs_tile") or it.id.split("_")[1]
        key = (tile, it.datetime.date())
        seq = int(it.id.rsplit("_", 2)[-2]) if it.id.rsplit("_", 2)[-2].isdigit() else 0
        if key not in best or seq > int(best[key].id.rsplit("_", 2)[-2] or 0):
            best[key] = it
    by_day: dict = {}
    for it in best.values():
        by_day.setdefault(it.datetime.date(), []).append(it)
    out = []
    for day_items in by_day.values():
        if len({_baseline(i) >= 4 for i in day_items}) > 1:
            day_items = [i for i in day_items if _baseline(i) >= 4]
        out.extend(day_items)
    return out


def cropland_mask(cell: Cell) -> np.ndarray:
    """WorldCover 2021 cropland on the cell grid (mode of the 10 m pixels in each 20 m pixel)."""
    gb = cell.geobox()
    h, w = gb.shape
    out = np.zeros((h, w), dtype=bool)
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", AWS_NO_SIGN_REQUEST="YES"):
        for tile in geo.worldcover_tiles(*geo.cell_bounds_lonlat(cell.bounds)):
            url = config.WORLDCOVER_URL.format(tile=tile)
            try:
                src = rasterio.open(url)
            except rasterio.errors.RasterioIOError:
                continue  # sea-only tiles do not exist
            with src, WarpedVRT(src, crs=config.WORK_CRS, transform=gb.transform, width=w, height=h,
                                resampling=Resampling.mode) as vrt:
                out |= vrt.read(1) == config.WORLDCOVER_CROPLAND
    return out


def municipality_raster(cell: Cell, munis: list[geo.Municipality]) -> np.ndarray:
    """Index + 1 of the municipality holding each pixel centre; 0 outside all of them."""
    gb = cell.geobox()
    from shapely.geometry import box
    cb = box(*cell.bounds)
    shapes = [(m.geom, i + 1) for i, m in enumerate(munis) if m.geom.intersects(cb)]
    if not shapes:
        return np.zeros(gb.shape, dtype=np.int32)
    return rasterize(shapes, out_shape=gb.shape, transform=gb.transform, fill=0, dtype="int32")


# --- NDVI maxima ------------------------------------------------------------------------------

def _offset_applied(red_dn: np.ndarray) -> bool:
    """Whether the -1000 DN offset of processing baseline >= 04.00 is already out of the numbers.

    Earth Search's ``earthsearch:boa_offset_applied`` flag is only reliable when True (see
    vigilancia-humedales, stac.band_scale_offset). With the offset inside, no land pixel goes
    below 1000 DN in red; without it, the 1st percentile of a 20 km cell is a few hundred.
    """
    v = red_dn[red_dn > 0]
    return v.size == 0 or float(np.percentile(v, 1)) < 1000


def ndvi_features(items: list[Item], cell: Cell) -> dict[str, np.ndarray]:
    """Per-pixel spring NDVI median, summer NDVI maximum and their clear-observation counts.

    Spring uses the median of the clear dates, not the maximum: a cereal stays green for
    weeks, while weeds on a fallow flush for a few days after rain. With the maximum, a wet
    spring turned much fallow into "crop" (see config.SPRING_STAT).
    """
    ds = load(items, bands=config.BANDS, geobox=cell.geobox(), groupby="solar_day",
              resampling={"scl": "nearest", "*": "average"}, chunks={"x": 1000, "y": 1000})
    ds = ds.compute(scheduler="threads", num_workers=config.DASK_THREADS)
    shape = ds.red.shape[1:]
    spring_dates = []
    summer = np.full(shape, np.nan, dtype="float32")
    n_summer = np.zeros(shape, dtype="int16")
    for t in range(ds.sizes["time"]):
        month = int(ds.time.values[t].astype("datetime64[M]").astype(int) % 12 + 1)
        red_dn = ds.red.values[t]
        nir_dn = ds.nir.values[t]
        clear = np.isin(ds.scl.values[t], config.SCL_CLEAR) & (red_dn > 0) & (nir_dn > 0)
        if not clear.any():
            continue
        off = 0.0 if _offset_applied(red_dn) else -0.1
        red = np.clip(red_dn.astype("float32") * 1e-4 + off, 1e-4, None)
        nir = np.clip(nir_dn.astype("float32") * 1e-4 + off, 1e-4, None)
        ndvi = np.where(clear, (nir - red) / (nir + red), np.nan).astype("float32")
        if month in config.SPRING_MONTHS:
            spring_dates.append(ndvi)
        elif month in config.SUMMER_MONTHS:
            summer = np.fmax(summer, ndvi)
            n_summer += clear
    stack = np.stack(spring_dates) if spring_dates else np.full((1, *shape), np.nan, "float32")
    n_spring = np.isfinite(stack).sum(0).astype("int16")
    with np.errstate(all="ignore"), warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)  # all-NaN pixels stay NaN
        spring = (np.nanmax(stack, 0) if config.SPRING_STAT == "max"
                  else np.nanpercentile(stack, config.SPRING_STAT, axis=0)).astype("float32")
    return {"spring": spring, "summer": summer, "n_spring": n_spring, "n_summer": n_summer}


def to_bins(v: np.ndarray) -> np.ndarray:
    b = np.floor((v - config.NDVI_LO) / config.NDVI_STEP)
    return np.clip(b, 0, config.N_BINS - 1).astype("int32")


def histograms(maxima: dict[str, np.ndarray], crop: np.ndarray, muni_idx: np.ndarray,
               munis: list[geo.Municipality]) -> pd.DataFrame:
    """Rows (ine, s, u, n): n cropland pixels of a municipality in spring bin s and summer bin u.

    Pixels without enough clear dates go to s = u = -1, so coverage gaps stay visible
    instead of silently shrinking the cropland.
    """
    inside = crop & (muni_idx > 0)
    enough = (maxima["n_spring"] >= config.MIN_SPRING_OBS) & (maxima["n_summer"] >= config.MIN_SUMMER_OBS)
    s = np.where(enough, to_bins(np.nan_to_num(maxima["spring"], nan=config.NDVI_LO)), -1)
    u = np.where(enough, to_bins(np.nan_to_num(maxima["summer"], nan=config.NDVI_LO)), -1)
    nb = config.N_BINS + 1
    key = (muni_idx[inside].astype("int64") * nb + (s[inside] + 1)) * nb + (u[inside] + 1)
    keys, counts = np.unique(key, return_counts=True)
    mi, rest = np.divmod(keys, nb * nb)
    sb, ub = np.divmod(rest, nb)
    return pd.DataFrame({
        "ine": [munis[i - 1].ine for i in mi],
        "s": sb - 1, "u": ub - 1, "n": counts,
    })


def run_cell(cell: Cell, year: int, munis: list[geo.Municipality]) -> tuple[pd.DataFrame, dict]:
    """Histograms of one cell and one campaign, plus a small log record."""
    muni_idx = municipality_raster(cell, munis)
    log = {"cell": cell.id, "year": year, "scenes": 0, "days": 0}
    if not muni_idx.any():
        return pd.DataFrame(columns=["ine", "s", "u", "n"]), log
    crop = cropland_mask(cell)
    log["crop_ha"] = round(float(crop[muni_idx > 0].sum()) * config.PIXEL_HA)
    if not crop.any():
        return pd.DataFrame(columns=["ine", "s", "u", "n"]), log
    items = search(cell, year)
    log["scenes"] = len(items)
    if not items:
        return pd.DataFrame(columns=["ine", "s", "u", "n"]), log
    maxima = ndvi_features(items, cell)
    log["days"] = len({i.datetime.date() for i in items})
    return histograms(maxima, crop, muni_idx, munis), log
