"""From histograms to hectares: fallow per municipality, agricultural district and province."""
from __future__ import annotations

import pandas as pd

from . import calibrate, config, geo

LEVELS = ("ine", "comarca", "province", "ccaa")


def years_available() -> list[int]:
    return sorted(int(p.name.split(".")[0]) for p in config.HIST_DIR.glob("*.csv.gz"))


def municipal() -> pd.DataFrame:
    """Rows (year, ine, comarca, province, ccaa, fallow_ha, cropland_ha, nodata_ha, complete).

    ``complete`` is False when the municipality was only partly inside the processed cells
    (calibration blocks); such rows never enter a district or province total.
    """
    regions = tuple(config.REGIONS)
    munis = geo.municipalities(regions)
    to_comarca = geo.municipality_comarca(munis)
    frames = []
    for y in years_available():
        h = calibrate.load_hist(y)
        est = calibrate.fallow_ha(h, config.SPRING_MAX_FALLOW, config.SUMMER_MAX_FALLOW)
        cov = calibrate.covered_municipalities(y, regions)
        est = est.reset_index(names="ine")
        est["year"] = y
        est["complete"] = est.ine.isin(cov)
        frames.append(est)
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    df["comarca"] = df.ine.map(to_comarca)
    df["province"] = df.ine.str[:2]
    df["ccaa"] = df.province.map(geo.PROVINCE_CCAA)
    return df


def by(df: pd.DataFrame, level: str) -> pd.DataFrame:
    """Totals per unit and year, only for units whose every municipality is complete that year."""
    regions = tuple(config.REGIONS)
    munis = geo.municipalities(regions)
    to_comarca = geo.municipality_comarca(munis)
    members: dict[str, set[str]] = {}
    for m in munis:
        key = {"ine": m.ine, "comarca": to_comarca.get(m.ine), "province": m.province,
               "ccaa": geo.PROVINCE_CCAA[m.province]}[level]
        if key:
            members.setdefault(key, set()).add(m.ine)
    out = []
    for (y, unit), g in df.dropna(subset=[level]).groupby(["year", level]):
        done = set(g[g.complete].ine)
        # Municipalities with no cropland at all have no histogram rows; they are not missing.
        missing = members.get(unit, set()) - set(g.ine)
        if not done >= set(g.ine) or any(_has_cropland_cell(i, y) for i in missing):
            continue
        out.append({"year": y, level: unit, "fallow_ha": g.fallow_ha.sum(),
                    "cropland_ha": g.cropland_ha.sum(), "nodata_ha": g.nodata_ha.sum()})
    return pd.DataFrame(out)


def _has_cropland_cell(ine: str, year: int) -> bool:
    """A municipality absent from the histograms is missing only if its cells were not run."""
    return ine not in calibrate.covered_municipalities(year, tuple(config.REGIONS))
