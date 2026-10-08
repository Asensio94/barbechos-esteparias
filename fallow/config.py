"""Parameters of the fallow-land monitor. Every number that shapes a published figure lives here."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CACHE = DATA / "cache"
HIST_DIR = DATA / "hist"          # per-municipality 2D NDVI histograms, one file per campaign
OFFICIAL_DIR = DATA / "official"  # MAPA yearbook and CAP declarations, already parsed
VALIDATION_DIR = DATA / "validation"
DOCS = ROOT / "docs"

# --- Sentinel-2 -------------------------------------------------------------------------
STAC_URL = "https://earth-search.aws.element84.com/v1"
STAC_COLLECTION = "sentinel-2-l2a"
BANDS = ["red", "nir", "scl"]
MAX_SCENE_CLOUD = 60.0
# SCL classes kept as clear land: 4 vegetation, 5 bare soil. Everything else (cloud, shadow,
# water, snow, saturated, unclassified) is dropped for that date.
SCL_CLEAR = (4, 5)
DASK_THREADS = 8

# --- Grid -------------------------------------------------------------------------------
# Peninsular Spain and the Balearics in ETRS89 / UTM 30N. A 20 km cell at 20 m is 1000 x 1000
# pixels: about one internal block of the Sentinel-2 COG overviews, so a whole cell costs the
# same reads as a small window (measured: 6.7 s for 20 km vs 12.5 s for 4 km, 4 scenes).
WORK_CRS = "EPSG:25830"
RESOLUTION_M = 20
CELL_M = 20_000
PIXEL_HA = RESOLUTION_M * RESOLUTION_M / 10_000

# --- Campaign ---------------------------------------------------------------------------
# A campaign runs from October of the previous year to the end of August; the fallow of a
# campaign is land that grows no crop in it.
CAMPAIGN_START = (10, 1)   # (month, day) of year - 1
CAMPAIGN_END = (8, 31)
SPRING_MONTHS = (3, 4, 5)  # winter cereals peak here
SUMMER_MONTHS = (6, 7, 8)  # sunflower, maize and irrigated crops peak here
MIN_SPRING_OBS = 3
# Spring statistic: percentile of the clear spring dates ("max" for the maximum). Tested on
# the Aragon calibration block 2018-2022, the median beats the maximum on both the level
# error (26.8 % vs 29.1 %) and the year-to-year wobble of the total (10.7 % vs 13.3 %).
SPRING_STAT: int | str = 50
MIN_SUMMER_OBS = 2

# --- Histograms -------------------------------------------------------------------------
# NDVI maxima are binned on [NDVI_LO, NDVI_HI) in steps of NDVI_STEP. A rule of the form
# "spring < a and summer < b" is then exact for any a, b on the bin edges.
NDVI_LO = -0.2
NDVI_HI = 1.0
NDVI_STEP = 0.05
N_BINS = round((NDVI_HI - NDVI_LO) / NDVI_STEP)

# --- Classification ---------------------------------------------------------------------
# Fallow = cropland pixel whose spring median and summer maximum both stay low: no winter
# crop and no spring-sown crop. Fitted on the Aragon CAP declarations (see calibrate.py);
# these are the values the published figures use.
SPRING_MAX_FALLOW = 0.30
SUMMER_MAX_FALLOW = 0.35
# One campaign wobbles with the spring weather (about +-10 % on the calibration block), more
# than the real yearly change of fallow (2-5 %). Trends are read on this moving mean.
ROLLING_YEARS = 3

# --- Cropland mask ----------------------------------------------------------------------
# ESA WorldCover 2021 v200, class 40 (cropland), CC BY 4.0.
WORLDCOVER_URL = ("https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/"
                  "ESA_WorldCover_10m_2021_v200_{tile}_Map.tif")
WORLDCOVER_CROPLAND = 40

# --- Boundaries -------------------------------------------------------------------------
ES_ATLAS_URL = "https://unpkg.com/es-atlas@0.6.0/es/municipalities.json"
COMARCAS_WFS = ("https://wmts.mapama.gob.es/sig/wfs_comun/Comarcas_Agrarias/wfs?service=WFS"
                "&version=2.0.0&request=GetFeature&typeNames=wfs_comun:Comarcas_Agrarias"
                "&outputFormat=application/json&srsName=EPSG:4326")

# Regions processed, by INE autonomous-community code. Aragon is the calibration region
# (CAP declarations by municipality); Castilla y Leon holds the largest steppe-bird areas.
REGIONS = {"02": "Aragón", "07": "Castilla y León"}

# --- Policy events shown on the charts ----------------------------------------------------
POLICY_EVENTS = [
    (2022, "Bruselas permite cultivar el barbecho de la PAC (Decisión 2022/484)"),
    (2023, "Exención del 4 % no productivo (Reglamento 2022/1317)"),
    (2024, "Se suprime la obligación del 4 % (Reglamento 2024/1468)"),
]
