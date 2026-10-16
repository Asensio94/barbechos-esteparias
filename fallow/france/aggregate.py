"""Parcels of a campaign -> fallow and arable hectares by commune and by steppe-bird SPA."""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd
import shapely
from shapely.strtree import STRtree

from .. import config
from . import rpg, units

log = logging.getLogger("fallow")
SUMS = ["fallow_ha", "arable_ha", "declared_ha"]


def classify(df: pd.DataFrame) -> pd.DataFrame:
    """Adds the hectare columns: fallow (group 11), arable (TA groups) and all declared land."""
    g = df["code_group"].astype(str)
    area = df["surf_parc"].astype(float)
    return df.assign(fallow_ha=np.where(g == config.FR_FALLOW_GROUP, area, 0.0),
                     arable_ha=np.where(g.isin(config.FR_ARABLE_GROUPS), area, 0.0),
                     declared_ha=area)


def _point_in(polys: list, x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(point index, polygon index) pairs for points inside polygons."""
    pts = shapely.points(np.asarray(x, float), np.asarray(y, float))
    return STRtree(polys).query(pts, predicate="within")


def with_commune(df: pd.DataFrame) -> pd.DataFrame:
    """Parcels whose interior point lies in a study commune, with its INSEE code."""
    coms = units.communes()
    ip, ic = _point_in([c.geom for c in coms], df["x"].to_numpy(), df["y"].to_numpy())
    # A point exactly on a shared border may fall in two communes: keep the first.
    first = pd.Series(ic, index=ip).groupby(level=0).first()
    out = df.iloc[first.index].assign(insee=[coms[i].insee for i in first.to_numpy()])
    log.info("%.1f %% of the downloaded area lies in a study commune",
             100 * out.declared_ha.sum() / df.declared_ha.sum())
    return out


def in_spa(df: pd.DataFrame) -> pd.DataFrame:
    """(parcel row, sitecode) for parcels inside a steppe-bird SPA; SPAs may overlap."""
    spas = units.steppe_spas()
    ip, isp = _point_in([s["geom"] for s in spas], df["x"].to_numpy(), df["y"].to_numpy())
    return pd.DataFrame({"row": ip, "sitecode": [spas[i]["sitecode"] for i in isp]})


def run(year: int) -> None:
    """Writes data/fr/communes-{year}.csv and data/fr/zps-{year}.csv.

    Communes carry their totals and the part outside every steppe SPA, the reference the
    SPAs are read against."""
    df = with_commune(classify(rpg.parcels(year))).reset_index(drop=True)
    log.info("RPG %d: %d parcels, %.0f ha declared, %.0f ha fallow", year, len(df),
             df.declared_ha.sum(), df.fallow_ha.sum())
    hits = in_spa(df)
    spa = (df.iloc[hits.row][SUMS].assign(sitecode=hits.sitecode.to_numpy())
           .groupby("sitecode")[SUMS].sum()
           .reindex([s["sitecode"] for s in units.steppe_spas()], fill_value=0.0).reset_index())
    outside = df.drop(index=hits.row.unique())
    com = (df.groupby("insee")[SUMS].sum()
           .join(outside.groupby("insee")[SUMS].sum().add_suffix("_out_spa")).fillna(0.0))
    config.FR_DIR.mkdir(parents=True, exist_ok=True)
    com.round(2).reset_index().to_csv(config.FR_DIR / f"communes-{year}.csv", index=False)
    spa.round(2).to_csv(config.FR_DIR / f"zps-{year}.csv", index=False)


def load(kind: str) -> pd.DataFrame:
    """Every saved campaign of 'communes' or 'zps', with a year column."""
    parts = []
    for p in sorted(config.FR_DIR.glob(f"{kind}-*.csv")):
        parts.append(pd.read_csv(p, dtype={"insee": str}).assign(year=int(p.stem.split("-")[1])))
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
