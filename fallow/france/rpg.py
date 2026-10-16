"""RPG parcels of the study departments, one campaign at a time.

The WFS serves each campaign as one layer. The study area is cut into tiles aligned on a
FR_TILE_M grid in Lambert-93; every tile is paged, reduced to one row per parcel (crop
group, code, declared area and an interior point) and cached, so an interrupted run resumes
at the first missing tile. Geometry is used only to place the parcel and then dropped.
"""
from __future__ import annotations

import logging
import math
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
from shapely.geometry import box, shape

from .. import config
from . import units, wfs

log = logging.getLogger("fallow")
COLUMNS = ["id_parcel", "code_group", "code_cultu", "surf_parc", "x", "y"]


def tiles() -> list[tuple[int, int, int, int]]:
    """Grid tiles (xmin, ymin, xmax, ymax) that touch a study department."""
    area = units.study_area()
    t = config.FR_TILE_M
    x0, y0, x1, y1 = area.bounds
    out = []
    for i in range(math.floor(x0 / t), math.ceil(x1 / t)):
        for j in range(math.floor(y0 / t), math.ceil(y1 / t)):
            b = (i * t, j * t, (i + 1) * t, (j + 1) * t)
            if area.intersects(box(*b)):
                out.append(b)
    return out


def _tile_path(year: int, b: tuple[int, int, int, int]):
    return config.CACHE / "rpg" / str(year) / f"{b[0] // 1000}_{b[1] // 1000}.csv.gz"


def fields(layer: str) -> tuple[str, str]:
    """(parcel id field, geometry field) of a campaign layer."""
    sch = wfs.schema(layer)
    geom = next(k for k, t in sch.items() if t.startswith("gml:") and "Surface" in t)
    ident = next(k for k in ("id_parcel", "num_parcel") if k in sch)
    return ident, geom


def _parcels(feats: list[dict], ident: str) -> pd.DataFrame:
    rows = []
    for f in feats:
        if not f.get("geometry"):
            continue
        p = f["properties"]
        pt = shape(f["geometry"]).representative_point()
        rows.append((str(p[ident]), p["code_group"], p["code_cultu"], p["surf_parc"],
                     round(pt.x), round(pt.y)))
    return pd.DataFrame(rows, columns=COLUMNS)


def fetch_tile(year: int, layer: str, b: tuple[int, int, int, int]) -> int:
    path = _tile_path(year, b)
    if path.exists():
        return -1
    ident, geom = fields(layer)
    feats = wfs.features(layer, bbox=b, properties=f"{ident},surf_parc,code_cultu,code_group,{geom}",
                         sort_by=ident)
    df = _parcels(feats, ident)
    # The bbox filter returns every parcel that touches the tile: keep only those whose
    # interior point falls inside it, so each parcel belongs to exactly one tile.
    df = df[(df.x >= b[0]) & (df.x < b[2]) & (df.y >= b[1]) & (df.y < b[3])]
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    df.to_csv(tmp, index=False, compression="gzip")
    tmp.replace(path)  # a killed run never leaves a half-written tile
    return len(df)


def download(year: int, workers: int = 4) -> None:
    layers = wfs.rpg_layers()
    if year not in layers:
        raise SystemExit(f"RPG {year} is not published yet (available: {min(layers)}-{max(layers)})")
    todo = tiles()
    log.info("RPG %d: %d tiles (%s)", year, len(todo), layers[year])
    t = time.time()
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(fetch_tile, year, layers[year], b): b for b in todo}
        for k, f in enumerate(as_completed(futs), 1):
            n = f.result()
            if n >= 0:
                log.info("[%d/%d] %s: %d parcels", k, len(todo), _tile_path(year, futs[f]).name, n)
    log.info("RPG %d downloaded in %.0f s", year, time.time() - t)


def parcels(year: int) -> pd.DataFrame:
    """Every cached parcel of a campaign (download first)."""
    parts = [pd.read_csv(_tile_path(year, b), dtype={"id_parcel": str, "code_group": str,
                                                      "code_cultu": str}) for b in tiles()]
    df = pd.concat(parts, ignore_index=True)
    return df.drop_duplicates(["id_parcel", "x", "y"])
