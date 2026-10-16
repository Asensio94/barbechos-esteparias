"""Command line: python -m fallow <command>."""
from __future__ import annotations

import argparse
import json
import logging
import time
from concurrent.futures import ProcessPoolExecutor, as_completed

import pandas as pd

from . import config, geo, official, season

log = logging.getLogger("fallow")


def _parts_dir(year: int):
    return config.CACHE / "parts" / str(year)


def _run_one(args: tuple[int, int, int, tuple[str, ...]]) -> dict:
    col, row, year, regions = args
    cell = season.Cell(col, row)
    out = _parts_dir(year) / f"{cell.id}.csv"
    if out.exists():
        return {"cell": cell.id, "cached": True}
    t = time.time()
    df, rec = season.run_cell(cell, year, geo.municipalities(regions))
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out.with_suffix(".tmp"), index=False)
    out.with_suffix(".tmp").replace(out)  # a killed run never leaves a half-written part
    rec["seconds"] = round(time.time() - t, 1)
    return rec


def hist(year: int, regions: tuple[str, ...], workers: int, bbox: list[float] | None = None) -> None:
    """Histograms for every cell of the regions, then merged into data/hist/{year}.csv.gz.

    Each cell is saved as soon as it finishes, so an interrupted run resumes where it stopped.
    ``bbox`` (lon_min lat_min lon_max lat_max) limits the run to a block, for calibration.
    """
    munis = geo.municipalities(regions)
    cells = season.cells_for(munis)
    if bbox:
        from shapely.geometry import box
        from shapely.ops import transform
        area = transform(geo.to_work_crs(), box(*bbox))
        cells = [c for c in cells if box(*c.bounds).intersects(area)]
    log.info("%d cells, campaign %d, %d workers", len(cells), year, workers)
    done = 0
    with ProcessPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(_run_one, (c.col, c.row, year, regions)) for c in cells]
        for f in as_completed(futs):
            done += 1
            log.info("[%d/%d] %s", done, len(cells), json.dumps(f.result()))
    merge(year)


def merge(year: int) -> None:
    parts = sorted(_parts_dir(year).glob("*.csv"))
    frames = [pd.read_csv(p, dtype={"ine": str}) for p in parts]
    frames = [f for f in frames if len(f)]
    if not frames:
        return
    # A municipality split by cell edges gets one row per cell; sum them.
    df = pd.concat(frames).groupby(["ine", "s", "u"], as_index=False).n.sum()
    config.HIST_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(config.HIST_DIR / f"{year}.csv.gz", index=False)
    log.info("merged %d cells into %s (%d rows)", len(parts), f"hist/{year}.csv.gz", len(df))


def fr_rpg(years: list[int] | None, workers: int, refresh: bool) -> None:
    """France: download the RPG of the study departments and aggregate it by commune and SPA.

    Without --year, every published campaign not yet in data/fr, plus the newest one, which
    IGN may still correct (its tile cache is then dropped and read again)."""
    import shutil

    from .france import aggregate as fr_aggregate, rpg, wfs
    published = sorted(wfs.rpg_layers())
    if not years:
        years = [y for y in published if not (config.FR_DIR / f"communes-{y}.csv").exists()]
        if published and published[-1] not in years:
            years.append(published[-1])
            refresh = True
    for y in years:
        if refresh:
            shutil.rmtree(config.CACHE / "rpg" / str(y), ignore_errors=True)
        rpg.download(y, workers)
        fr_aggregate.run(y)


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="fallow")
    sub = p.add_subparsers(dest="cmd", required=True)
    h = sub.add_parser("hist", help="NDVI histograms per municipality for one campaign")
    h.add_argument("--year", type=int, required=True)
    h.add_argument("--region", action="append", choices=sorted(config.REGIONS),
                   help="INE community code (repeatable); all configured regions by default")
    h.add_argument("--workers", type=int, default=2)
    h.add_argument("--bbox", type=float, nargs=4, metavar=("LON0", "LAT0", "LON1", "LAT1"))
    m = sub.add_parser("merge", help="merge the saved cells of one campaign")
    m.add_argument("--year", type=int, required=True)
    sub.add_parser("official", help="download and parse the official figures")
    sub.add_parser("calibrate", help="fit the thresholds on the Aragon CAP declarations")
    sub.add_parser("web", help="build docs/index.html")
    f = sub.add_parser("fr-rpg", help="France: RPG campaigns -> data/fr (missing ones by default)")
    f.add_argument("--year", type=int, action="append")
    f.add_argument("--workers", type=int, default=4)
    f.add_argument("--refresh", action="store_true", help="download again even if cached")
    sub.add_parser("fr-official", help="France: Agreste SAA fallow by department")
    sub.add_parser("fr-web", help="France: build docs/fr/index.html")
    a = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")

    if a.cmd == "hist":
        hist(a.year, tuple(a.region or config.REGIONS), a.workers, a.bbox)
    elif a.cmd == "merge":
        merge(a.year)
    elif a.cmd == "official":
        log.info(official.update())
    elif a.cmd == "calibrate":
        from . import calibrate
        log.info(calibrate.run())
    elif a.cmd == "web":
        from . import web
        web.build()
    elif a.cmd == "fr-rpg":
        fr_rpg(a.year, a.workers, a.refresh)
    elif a.cmd == "fr-official":
        from .france import saa
        saa.update()
    elif a.cmd == "fr-web":
        from .france import web as fr_web
        log.info(fr_web.build())


if __name__ == "__main__":
    main()
