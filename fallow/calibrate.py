"""Fit the two NDVI thresholds on the Aragon CAP declarations and test them out of sample.

Fit: campaigns 2018-2020. Test: 2021-2022 by municipality and, for every year with
histograms, the MAPA yearbook by province. Everything is read from the saved histograms,
so no image is read again.
"""
from __future__ import annotations

import json
from functools import lru_cache, reduce

import numpy as np
import pandas as pd
from shapely.geometry import box

from . import config, geo, season

FIT_YEARS = (2018, 2019, 2020)
TEST_YEARS = (2021, 2022)
SPRING_GRID = np.round(np.arange(0.25, 0.701, config.NDVI_STEP), 2)
SUMMER_GRID = np.round(np.arange(0.25, 0.651, config.NDVI_STEP), 2)
# Municipalities with less declared fallow than this are left out: a few hectares of
# difference there is noise, not skill.
MIN_PAC_FALLOW_HA = 50


def load_hist(year: int) -> pd.DataFrame | None:
    path = config.HIST_DIR / f"{year}.csv.gz"
    return pd.read_csv(path, dtype={"ine": str}) if path.exists() else None


def edge(v: float) -> int:
    """Bin index whose lower edge is v: 'NDVI < v' is 'bin < edge(v)'."""
    return int(round((v - config.NDVI_LO) / config.NDVI_STEP))


def fallow_ha(hist: pd.DataFrame, spring_max: float, summer_max: float) -> pd.DataFrame:
    """Per municipality: estimated fallow, observed cropland and cropland without enough dates."""
    ok = hist[hist.s >= 0]
    is_fallow = (ok.s < edge(spring_max)) & (ok.u < edge(summer_max))
    out = pd.DataFrame({
        "fallow_ha": ok[is_fallow].groupby("ine").n.sum(),
        "cropland_ha": hist.groupby("ine").n.sum(),
        "nodata_ha": hist[hist.s < 0].groupby("ine").n.sum(),
    }).fillna(0) * config.PIXEL_HA
    return out


@lru_cache(maxsize=32)
def covered_municipalities(year: int, regions: tuple[str, ...]) -> set[str]:
    """Municipalities lying wholly inside the cells processed for a campaign."""
    parts = (config.CACHE / "parts" / str(year)).glob("*.csv")
    boxes = [box(*season.Cell(*map(int, p.stem.split("_"))).bounds) for p in parts]
    if not boxes:
        return set()
    area = reduce(lambda a, b: a.union(b), boxes).buffer(1)
    return {m.ine for m in geo.municipalities(regions) if area.contains(m.geom)}


def _pairs(years, pac: pd.DataFrame, hists: dict, a: float, b: float) -> pd.DataFrame:
    rows = []
    for y in years:
        if y not in hists:
            continue
        h, cov = hists[y]
        est = fallow_ha(h, a, b)
        truth = pac[pac.year == y].set_index("ine")
        truth = truth[truth.index.isin(cov)]
        j = est.join(truth[["rainfed_ha", "irrigated_ha"]], how="inner")
        j["pac_ha"] = j.rainfed_ha + j.irrigated_ha
        j["year"] = y
        rows.append(j[j.pac_ha >= MIN_PAC_FALLOW_HA])
    return pd.concat(rows) if rows else pd.DataFrame()


def scores(p: pd.DataFrame) -> dict:
    if p.empty:
        return {}
    e, t = p.fallow_ha, p.pac_ha
    return {
        "n": int(len(p)),
        "r": round(float(np.corrcoef(e, t)[0, 1]), 3),
        "bias_pct": round(float((e.sum() - t.sum()) / t.sum() * 100), 1),
        "rmse_ha": round(float(np.sqrt(((e - t) ** 2).mean())), 0),
        "mae_pct": round(float((e - t).abs().sum() / t.sum() * 100), 1),
    }


def wobble(p: pd.DataFrame) -> float | None:
    """Coefficient of variation (%) of the yearly ratio estimate/declared on a fixed set.

    The ratio should not move from year to year; when it does, the estimate is following the
    weather rather than the land.
    """
    n = p.groupby(level=0).year.nunique()
    fixed = p[p.index.isin(n[n == p.year.nunique()].index)]
    if fixed.year.nunique() < 2:
        return None
    tot = fixed.groupby("year")[["fallow_ha", "pac_ha"]].sum()
    ratio = tot.fallow_ha / tot.pac_ha
    return round(float(ratio.std() / ratio.mean() * 100), 1)


def change_scores(p: pd.DataFrame) -> dict:
    """Agreement of year-to-year changes per municipality (what a trend relies on)."""
    if p.empty or p.year.nunique() < 2:
        return {}
    w = p.pivot_table(index=p.index, columns="year", values=["fallow_ha", "pac_ha"])
    years = sorted(p.year.unique())
    d = []
    for y0, y1 in zip(years, years[1:]):
        x = (w["fallow_ha"][y1] - w["fallow_ha"][y0]).dropna()
        t = (w["pac_ha"][y1] - w["pac_ha"][y0]).reindex(x.index).dropna()
        d.append(pd.DataFrame({"est": x.reindex(t.index), "pac": t}))
    d = pd.concat(d)
    if len(d) < 5:
        return {}
    return {"n": int(len(d)), "r": round(float(np.corrcoef(d.est, d.pac)[0, 1]), 3),
            "same_sign_pct": round(float((np.sign(d.est) == np.sign(d.pac)).mean() * 100), 1)}


def province_check(a: float, b: float) -> pd.DataFrame:
    """Satellite fallow by province vs the yearbook, for provinces fully processed."""
    path = config.OFFICIAL_DIR / "anuario-provincias.csv"
    if not path.exists():
        return pd.DataFrame()
    an = pd.read_csv(path, dtype={"province": str})
    rows = []
    munis = {m.ine: m for m in geo.municipalities(tuple(config.REGIONS))}
    for y in sorted(an.year.unique()):
        h = load_hist(int(y))
        if h is None:
            continue
        cov = covered_municipalities(int(y), tuple(config.REGIONS))
        est = fallow_ha(h, a, b)
        est["province"] = est.index.str[:2]
        for prov, g in est.groupby("province"):
            allm = [i for i in munis if i[:2] == prov]
            if not allm or not all(i in cov for i in allm):
                continue
            off = an[(an.year == y) & (an.province == prov)]
            if off.empty:
                continue
            rows.append({"year": int(y), "province": prov, "satellite_ha": round(g.fallow_ha.sum()),
                         "anuario_ha": int(off.total_ha.iloc[0])})
    return pd.DataFrame(rows)


def run() -> dict:
    pac = pd.read_csv(config.OFFICIAL_DIR / "aragon-pac-municipios.csv", dtype={"ine": str})
    hists = {}
    for y in FIT_YEARS + TEST_YEARS:
        h = load_hist(y)
        if h is not None:
            hists[y] = (h, covered_municipalities(y, ("02",)))
    if not any(y in hists for y in FIT_YEARS):
        raise SystemExit("no histograms for the fit years; run `fallow hist` first")

    grid = []
    for a in SPRING_GRID:
        for b in SUMMER_GRID:
            p = _pairs(FIT_YEARS, pac, hists, a, b)
            grid.append({"spring_max": float(a), "summer_max": float(b), **scores(p), "wobble_pct": wobble(p)})
    grid = pd.DataFrame(grid)
    # Level error plus the yearly wobble: a trend needs both to be small.
    grid["objective"] = grid.mae_pct + grid.wobble_pct.fillna(0)
    best = grid.sort_values("objective").iloc[0]
    a, b = float(best.spring_max), float(best.summer_max)

    fit = _pairs(FIT_YEARS, pac, hists, a, b)
    test = _pairs(TEST_YEARS, pac, hists, a, b)
    result = {
        "spring_max": a, "summer_max": b,
        "fit_years": [y for y in FIT_YEARS if y in hists],
        "test_years": [y for y in TEST_YEARS if y in hists],
        "fit": scores(fit), "test": scores(test),
        "fit_change": change_scores(fit), "test_change": change_scores(test),
        "all_change": change_scores(pd.concat([fit, test])),
        "wobble_pct": wobble(pd.concat([fit, test])),
        "ratio_by_year": {int(y): round(float(g.fallow_ha.sum() / g.pac_ha.sum()), 3)
                          for y, g in pd.concat([fit, test]).groupby("year")},
        "spring_stat": config.SPRING_STAT,
    }
    config.VALIDATION_DIR.mkdir(parents=True, exist_ok=True)
    grid.to_csv(config.VALIDATION_DIR / "grid.csv", index=False)
    out = pd.concat([fit.assign(set="fit"), test.assign(set="test")]).reset_index(names="ine")
    out[["ine", "year", "set", "fallow_ha", "pac_ha", "cropland_ha", "nodata_ha"]].round(1).to_csv(
        config.VALIDATION_DIR / "aragon-municipios.csv", index=False)
    prov = province_check(a, b)
    if not prov.empty:
        prov.to_csv(config.VALIDATION_DIR / "provincias.csv", index=False)
        result["provinces"] = {"n": len(prov), "r": round(float(np.corrcoef(prov.satellite_ha, prov.anuario_ha)[0, 1]), 3)
                               if len(prov) > 2 else None,
                               "bias_pct": round(float((prov.satellite_ha.sum() / prov.anuario_ha.sum() - 1) * 100), 1)}
    (config.VALIDATION_DIR / "calibration.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    return result
