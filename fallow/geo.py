"""Boundaries (municipalities, agricultural districts) and the cropland mask."""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from functools import lru_cache

import numpy as np
import requests
from pyproj import Transformer
from shapely.geometry import MultiPolygon, Polygon, shape
from shapely.ops import transform as shp_transform
from shapely.strtree import STRtree

from . import config


# --- TopoJSON -----------------------------------------------------------------------------

def _decode_arcs(topo: dict) -> list[list[tuple[float, float]]]:
    """Quantized, delta-encoded TopoJSON arcs to lon/lat coordinate lists."""
    (sx, sy), (tx, ty) = topo["transform"]["scale"], topo["transform"]["translate"]
    arcs = []
    for arc in topo["arcs"]:
        x = y = 0
        pts = []
        for dx, dy in arc:
            x += dx
            y += dy
            pts.append((x * sx + tx, y * sy + ty))
        arcs.append(pts)
    return arcs


def _ring(arcs: list, idx: list[int]) -> list[tuple[float, float]]:
    pts: list[tuple[float, float]] = []
    for i in idx:
        a = arcs[i] if i >= 0 else arcs[~i][::-1]
        pts.extend(a if not pts else a[1:])
    return pts


def _polygon(arcs: list, rings_idx: list) -> Polygon | None:
    # Quantization collapses some islets and enclaves to fewer than 4 points; they are dropped.
    rings = [r for r in (_ring(arcs, i) for i in rings_idx) if len(r) >= 4]
    if not rings or len(_ring(arcs, rings_idx[0])) < 4:
        return None
    return Polygon(rings[0], rings[1:])


def topo_geometry(arcs: list, g: dict):
    if g["type"] == "Polygon":
        polys = [_polygon(arcs, g["arcs"])]
    elif g["type"] == "MultiPolygon":
        polys = [_polygon(arcs, p) for p in g["arcs"]]
    else:
        return None
    polys = [p for p in polys if p is not None]
    return MultiPolygon(polys).buffer(0) if polys else None


# --- Municipalities -------------------------------------------------------------------------

@dataclass
class Municipality:
    ine: str        # 5-digit INE code
    name: str
    province: str   # 2-digit INE province code
    geom: object    # shapely geometry in WORK_CRS


# INE province code -> autonomous community code (INE), peninsular and Balearic provinces.
PROVINCE_CCAA = {
    "04": "01", "11": "01", "14": "01", "18": "01", "21": "01", "23": "01", "29": "01", "41": "01",
    "22": "02", "44": "02", "50": "02", "33": "03", "07": "04", "39": "06",
    "05": "07", "09": "07", "24": "07", "34": "07", "37": "07", "40": "07", "42": "07", "47": "07", "49": "07",
    "02": "08", "13": "08", "16": "08", "19": "08", "45": "08",
    "08": "09", "17": "09", "25": "09", "43": "09", "03": "10", "12": "10", "46": "10",
    "06": "11", "10": "11", "15": "12", "27": "12", "32": "12", "36": "12",
    "28": "13", "30": "14", "31": "15", "01": "16", "20": "16", "48": "16", "26": "17",
}

PROVINCE_NAMES = {
    "01": "Araba/Álava", "02": "Albacete", "03": "Alicante", "04": "Almería", "05": "Ávila",
    "06": "Badajoz", "07": "Illes Balears", "08": "Barcelona", "09": "Burgos", "10": "Cáceres",
    "11": "Cádiz", "12": "Castellón", "13": "Ciudad Real", "14": "Córdoba", "15": "A Coruña",
    "16": "Cuenca", "17": "Girona", "18": "Granada", "19": "Guadalajara", "20": "Gipuzkoa",
    "21": "Huelva", "22": "Huesca", "23": "Jaén", "24": "León", "25": "Lleida", "26": "La Rioja",
    "27": "Lugo", "28": "Madrid", "29": "Málaga", "30": "Murcia", "31": "Navarra", "32": "Ourense",
    "33": "Asturias", "34": "Palencia", "36": "Pontevedra", "37": "Salamanca", "39": "Cantabria",
    "40": "Segovia", "41": "Sevilla", "42": "Soria", "43": "Tarragona", "44": "Teruel",
    "45": "Toledo", "46": "Valencia", "47": "Valladolid", "48": "Bizkaia", "49": "Zamora",
    "50": "Zaragoza",
}


def _fetch_json(url: str, name: str) -> dict:
    path = config.CACHE / name
    if not path.exists():
        config.CACHE.mkdir(parents=True, exist_ok=True)
        r = requests.get(url, timeout=300)
        r.raise_for_status()
        path.write_bytes(r.content)
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def to_work_crs():
    return Transformer.from_crs("EPSG:4326", config.WORK_CRS, always_xy=True).transform


@lru_cache(maxsize=4)
def municipalities(regions: tuple[str, ...] | None = None) -> list[Municipality]:
    """Municipalities of the given autonomous communities (all processed regions by default)."""
    regions = regions or tuple(config.REGIONS)
    topo = _fetch_json(config.ES_ATLAS_URL, "es-municipalities.json")
    arcs = _decode_arcs(topo)
    out = []
    for g in topo["objects"]["municipalities"]["geometries"]:
        ine = g["id"]
        if PROVINCE_CCAA.get(ine[:2]) not in regions:
            continue
        geom = topo_geometry(arcs, g)
        if geom is None or geom.is_empty:
            continue
        out.append(Municipality(ine, g["properties"]["name"], ine[:2],
                                shp_transform(to_work_crs(), geom)))
    return out


# --- Agricultural districts ----------------------------------------------------------------

@dataclass
class Comarca:
    code: str       # province code + district number, e.g. "49-03"
    name: str
    province: str
    geom: object    # WORK_CRS


@lru_cache(maxsize=1)
def comarcas() -> list[Comarca]:
    fc = _fetch_json(config.COMARCAS_WFS, "comarcas-agrarias.json")
    out = []
    for f in fc["features"]:
        p = f["properties"]
        prov = f"{int(p['co_provinc']):02d}"
        code = f"{prov}-{int(p['co_comarca']):02d}"
        geom = shp_transform(to_work_crs(), shape(f["geometry"]).buffer(0))
        out.append(Comarca(code, str(p["ds_comarca"]).strip().title(), prov, geom))
    return out


def municipality_comarca(munis: list[Municipality]) -> dict[str, str]:
    """INE code -> district code, by the district holding the municipality's interior point."""
    cs = [c for c in comarcas()]
    tree = STRtree([c.geom for c in cs])
    out = {}
    for m in munis:
        pt = m.geom.representative_point()
        hits = [cs[i] for i in tree.query(pt) if cs[i].geom.contains(pt)]
        same = [c for c in hits if c.province == m.province]
        if same or hits:
            out[m.ine] = (same or hits)[0].code
    return out


# --- WorldCover tiles -------------------------------------------------------------------------

def worldcover_tiles(lon_min: float, lat_min: float, lon_max: float, lat_max: float) -> list[str]:
    """Names of the 3x3 degree WorldCover tiles (lower-left corner) touching a lon/lat box."""
    tiles = []
    for lat in range(math.floor(lat_min / 3) * 3, math.ceil(lat_max / 3) * 3, 3):
        for lon in range(math.floor(lon_min / 3) * 3, math.ceil(lon_max / 3) * 3, 3):
            ns = f"N{lat:02d}" if lat >= 0 else f"S{-lat:02d}"
            ew = f"E{lon:03d}" if lon >= 0 else f"W{-lon:03d}"
            tiles.append(ns + ew)
    return tiles


def cell_bounds_lonlat(bounds: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    inv = Transformer.from_crs(config.WORK_CRS, "EPSG:4326", always_xy=True).transform
    x0, y0, x1, y1 = bounds
    xs, ys = inv(np.array([x0, x1, x0, x1]), np.array([y0, y0, y1, y1]))
    return float(min(xs)), float(min(ys)), float(max(xs)), float(max(ys))
