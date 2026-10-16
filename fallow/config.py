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

# --- France -------------------------------------------------------------------------------
# France is a second value of ``country`` ("ES" | "FR"). Its fallow is not estimated from
# satellite images: it is read parcel by parcel from the CAP declarations (RPG, Registre
# parcellaire graphique), which IGN serves openly by WFS for every campaign since 2015.
COUNTRIES = ("ES", "FR")
FR_DIR = DATA / "fr"              # per-commune and per-ZPS aggregates, one file per campaign
FR_DOCS = DOCS / "fr"
FR_WORK_CRS = "EPSG:2154"         # RGF93 / Lambert-93
FR_WFS = "https://data.geopf.fr/wfs/ows"
FR_FIRST_YEAR = 2015              # the first RPG with parcels and crop codes (2007-2014: blocks only)
FR_PAGE = 5000                    # features per WFS request
FR_TILE_M = 25_000                # download tiles, aligned to multiples of this in Lambert-93

# Study departments, by area: the plains of Poitou-Charentes and southern Vendée (little
# bustard SPAs), the Crau and the Costières and Hérault plains, and the chalk Champagne.
FR_DEPARTMENTS = {
    "16": "Charente", "17": "Charente-Maritime", "79": "Deux-Sèvres", "86": "Vienne",
    "85": "Vendée", "13": "Bouches-du-Rhône", "30": "Gard", "34": "Hérault",
    "51": "Marne", "10": "Aube",
}
FR_AREAS = {
    "poitou": ("Plaines du Centre-Ouest", ("16", "17", "79", "86", "85")),
    "midi": ("Crau et plaines du Languedoc", ("13", "30", "34")),
    "champagne": ("Champagne crayeuse", ("51", "10")),
}

# RPG crop groups. Group 11 (« Gel, surfaces gelées sans production ») is fallow: codes J5M,
# J6P, J6S and JNO until 2022, JAC and JNO from 2023 on. Arable land is the set of groups the
# 2024 RPG labels « TA » (terres arables); group 28 (« Divers ») is mixed and left out.
FR_FALLOW_GROUP = "11"
FR_ARABLE_GROUPS = frozenset({"1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11",
                              "14", "15", "16", "19", "24", "25"})

# Communes: IGN ADMIN EXPRESS. One fixed geography (COG_YEAR) for every campaign keeps the
# series comparable; petites régions agricoles (PRA) come from the Agreste 2017 reference,
# keyed on the 2017 communes, and are carried to today's communes by their interior point.
FR_COG_YEAR = 2025
FR_PRA_URL = ("https://agreste.agriculture.gouv.fr/agreste-web/download/methode/Z_PRA_2017/"
              "Referentiel_CommuneRA_PRA_2017.xls")

# Steppe-bird SPAs: Birds Directive sites (EEA Natura 2000) in the study departments whose
# standard data form lists the little bustard (A128 Tetrax tetrax) or the pin-tailed
# sandgrouse (A205 Pterocles alchata, Crau). Site level only: no record locations.
FR_N2K_SITES = ("https://bio.discomap.eea.europa.eu/arcgis/rest/services/ProtectedSites/"
                "Natura2000Sites/MapServer/1/query")
FR_N2K_SPECIES = ("https://bio.discomap.eea.europa.eu/arcgis/rest/services/Bio/"
                  "Natura2000_Dyna_WGS84/MapServer/11/query")
FR_STEPPE_SPECIES = {"A128": "Outarde canepetière", "A205": "Ganga cata"}

# Official check: Agreste annual agricultural statistics (SAA), fallow by department.
FR_SAA_URL = ("https://agreste.agriculture.gouv.fr/agreste-web/download/publication/publie/"
              "SAA-SeriesLongues/SAA-SeriesLongues-2010-2025_DonneesProvisoires-"
              "DepartementalesRegionales.zip")

