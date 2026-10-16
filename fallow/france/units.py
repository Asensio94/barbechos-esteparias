"""French units: study departments, communes (ADMIN EXPRESS), PRA and steppe-bird SPAs."""
from __future__ import annotations

import gzip
import io
import json
import logging
from dataclasses import dataclass
from functools import lru_cache

import pandas as pd
from pyproj import Transformer
from shapely.geometry import shape
from shapely.ops import transform as shp_transform, unary_union
from shapely.strtree import STRtree

from .. import config
from . import wfs

log = logging.getLogger("fallow")
CACHE = config.CACHE / "fr"


def _cached_json(name: str, fetch) -> dict | list:
    path = CACHE / f"{name}.json.gz"
    if path.exists():
        return json.loads(gzip.decompress(path.read_bytes()))
    data = fetch()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(gzip.compress(json.dumps(data).encode()))
    return data


def _in_list(field: str, values) -> str:
    return f"{field} IN ({','.join(repr(v) for v in sorted(values))})"


# --- Departments and communes ---------------------------------------------------------------

@lru_cache(maxsize=1)
def departments() -> dict[str, object]:
    """Study department code -> polygon in Lambert-93."""
    layer = f"ADMINEXPRESS-COG.{config.FR_COG_YEAR}:departement"
    feats = _cached_json(f"departements-{config.FR_COG_YEAR}", lambda: wfs.features(
        layer, properties="code_insee,geometrie", cql=_in_list("code_insee", config.FR_DEPARTMENTS)))
    return {f["properties"]["code_insee"]: shape(f["geometry"]) for f in feats}


@lru_cache(maxsize=1)
def study_area():
    return unary_union(list(departments().values()))


@dataclass
class Commune:
    insee: str   # INSEE code, 5 characters (2A004 in Corsica)
    name: str
    dep: str
    geom: object


@lru_cache(maxsize=1)
def communes() -> list[Commune]:
    layer = f"ADMINEXPRESS-COG.{config.FR_COG_YEAR}:commune"
    feats = _cached_json(f"communes-{config.FR_COG_YEAR}", lambda: wfs.features(
        layer, properties="code_insee,nom_officiel,code_insee_du_departement,geometrie",
        cql=_in_list("code_insee_du_departement", config.FR_DEPARTMENTS), sort_by="code_insee"))
    return [Commune(p["code_insee"], p["nom_officiel"], p["code_insee_du_departement"],
                    shape(f["geometry"])) for f in feats for p in [f["properties"]]]


# --- Petites régions agricoles --------------------------------------------------------------

@lru_cache(maxsize=1)
def pra_2017() -> pd.DataFrame:
    """Agreste reference: 2017 commune -> PRA code and name."""
    path = CACHE / "pra-2017.xls"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(wfs.get(config.FR_PRA_URL, {}).content)
    raw = pd.read_excel(path, sheet_name="COM", header=None, dtype=str)
    head = raw.index[raw.iloc[:, 0] == "CODGEO"][0]  # a title block and French labels come first
    com = raw.iloc[head + 1:].set_axis(raw.iloc[head].tolist(), axis=1)
    out = com[["CODGEO", "PRA_Code", "PRA_Lib"]].dropna().set_axis(["insee", "pra", "pra_name"], axis=1)
    out = out.apply(lambda c: c.str.strip())
    out["pra_name"] = out["pra_name"].str.replace(r"\s+-\s+\w+$", "", regex=True)  # "PLAINE DE NIORT - 79"
    return out.reset_index(drop=True)


def communes_2017() -> list[tuple[str, object]]:
    layer = "ADMINEXPRESS-COG.2017:commune"
    feats = _cached_json("communes-2017", lambda: wfs.features(
        layer, properties="insee_com,geom", bbox=study_area().bounds))
    return [(f["properties"]["insee_com"], shape(f["geometry"])) for f in feats if f["geometry"]]


@lru_cache(maxsize=1)
def commune_table() -> pd.DataFrame:
    """Today's communes with their department, area (study area) and PRA.

    The PRA reference is keyed on the 2017 communes; a commune created later by merger takes
    the PRA of the 2017 commune holding its interior point (mergers rarely cross PRA lines)."""
    coms = communes()
    old = communes_2017()
    tree = STRtree([g for _, g in old])
    pra = pra_2017().set_index("insee")
    rows = []
    area_of = {d: k for k, (_, deps) in config.FR_AREAS.items() for d in deps}
    for c in coms:
        code = c.insee if c.insee in pra.index else None
        if code is None:
            pt = c.geom.representative_point()
            hit = [old[i][0] for i in tree.query(pt, predicate="within")]
            code = hit[0] if hit and hit[0] in pra.index else None
        rows.append({"insee": c.insee, "name": c.name, "dep": c.dep, "area": area_of[c.dep],
                     "pra": pra.at[code, "pra"] if code else None,
                     "pra_name": pra.at[code, "pra_name"] if code else None})
    return pd.DataFrame(rows)


# --- Steppe-bird SPAs -------------------------------------------------------------------------

def _arcgis(url: str, params: dict) -> dict:
    return wfs.get(url, {"f": "json", **params}).json()


@lru_cache(maxsize=1)
def steppe_spas() -> list[dict]:
    """Birds Directive sites in the study area whose standard data form lists a steppe species.

    Each item: sitecode, name, species (codes), geom (Lambert-93)."""
    def fetch():
        species: dict[str, set[str]] = {}
        for code in config.FR_STEPPE_SPECIES:
            off = 0
            while True:
                d = _arcgis(config.FR_N2K_SPECIES, {
                    "where": f"SPECIESCODE='{code}' AND SITECODE LIKE 'FR%'", "outFields": "*",
                    "returnGeometry": "false", "resultOffset": off, "resultRecordCount": 1000})
                feats = d.get("features", [])
                for f in feats:
                    species.setdefault(f["attributes"]["SITECODE"], set()).add(code)
                if not d.get("exceededTransferLimit") or not feats:
                    break
                off += len(feats)
        codes = sorted(species)
        sites = []
        for i in range(0, len(codes), 50):
            chunk = codes[i:i + 50]
            d = _arcgis(config.FR_N2K_SITES, {
                "where": "SITECODE IN (" + ",".join(f"'{c}'" for c in chunk) + ")",
                "outFields": "SITECODE,SITENAME", "returnGeometry": "true", "outSR": 4326,
                "f": "geojson"})
            for f in d["features"]:
                p = f["properties"]
                sites.append({"sitecode": p["SITECODE"], "name": p["SITENAME"],
                              "species": sorted(species[p["SITECODE"]]), "geometry": f["geometry"]})
        return sites

    to_l93 = Transformer.from_crs("EPSG:4326", config.FR_WORK_CRS, always_xy=True).transform
    area = study_area()
    out = []
    for s in _cached_json("zps-steppe", fetch):
        g = shp_transform(to_l93, shape(s["geometry"])).buffer(0)
        if g.intersects(area):
            out.append({**{k: v for k, v in s.items() if k != "geometry"}, "geom": g})
    return sorted(out, key=lambda s: s["sitecode"])
