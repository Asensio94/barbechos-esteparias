"""Official check: Agreste annual agricultural statistics (SAA), fallow and arable land by department.

The SAA is a survey-based estimate of all farmland, not only the land declared to the CAP,
so it reads a little above the RPG. Rows "01 - Jachères" and "21 - TERRES ARABLES" of the
TER sheet are kept for the study departments.
"""
from __future__ import annotations

import io
import logging
import zipfile

import openpyxl
import pandas as pd

from .. import config
from . import wfs

log = logging.getLogger("fallow")
OUT = config.OFFICIAL_DIR / "fr-saa-departements.csv"
ROWS = {"01": "fallow_ha", "21": "arable_ha"}


def parse(xlsx: bytes) -> pd.DataFrame:
    wb = openpyxl.load_workbook(io.BytesIO(xlsx), read_only=True)
    ws = wb["TER"]
    ws.reset_dimensions()  # the sheet declares a wrong size and read-only mode trusts it
    rows = list(ws.iter_rows(values_only=True))
    head = next(i for i, r in enumerate(rows) if r and r[0] == "LIB_REG2")
    cols = rows[head]
    years = {j: int(c.split("_")[1]) for j, c in enumerate(cols) if str(c).startswith("SURF_")}
    out = []
    for r in rows[head + 1:]:
        if not r or not r[1] or not r[2]:
            continue
        dep = str(r[1]).split(" - ")[0].lstrip("0").zfill(2)  # "079 - Deux-Sèvres" -> "79"
        item = str(r[2]).split(" - ")[0]
        if dep in config.FR_DEPARTMENTS and item in ROWS:
            for j, y in years.items():
                if r[j] is not None:
                    out.append({"dep": dep, "year": y, "item": ROWS[item], "ha": float(r[j])})
    df = pd.DataFrame(out).pivot_table(index=["dep", "year"], columns="item", values="ha")
    return df.reset_index()[["dep", "year", "fallow_ha", "arable_ha"]]


def update() -> pd.DataFrame:
    z = zipfile.ZipFile(io.BytesIO(wfs.get(config.FR_SAA_URL, {}).content))
    name = next(n for n in z.namelist() if "departement" in n)
    df = parse(z.read(name))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT, index=False)
    log.info("SAA: %d department-years -> %s", len(df), OUT.name)
    return df


def load() -> pd.DataFrame:
    return pd.read_csv(OUT, dtype={"dep": str}) if OUT.exists() else pd.DataFrame()
