"""Small client for the IGN Géoplateforme WFS (RPG, ADMIN EXPRESS)."""
from __future__ import annotations

import logging
import re
import time
from functools import lru_cache

import requests

from .. import config

log = logging.getLogger("fallow")
UA = {"User-Agent": "barbechos-esteparias (+https://github.com/Asensio94/barbechos-esteparias)"}


def get(url: str, params: dict, tries: int = 8, timeout: int = 300) -> requests.Response:
    """GET with retries: the Géoplateforme answers 5xx or times out now and then under load."""
    for k in range(tries):
        try:
            r = requests.get(url, params=params, headers=UA, timeout=timeout)
            if r.status_code < 500:
                r.raise_for_status()
                return r
            err = f"HTTP {r.status_code}"
        except requests.RequestException as e:
            if isinstance(e, requests.HTTPError):
                raise
            err = str(e)
        wait = min(5 * 2 ** k, 120)
        log.warning("%s (try %d/%d), again in %d s", err, k + 1, tries, wait)
        time.sleep(wait)
    raise RuntimeError(f"{url} failed {tries} times")


def features(type_name: str, *, bbox: tuple[float, float, float, float] | None = None,
             srs: str = config.FR_WORK_CRS, properties: str | None = None,
             cql: str | None = None, sort_by: str | None = None) -> list[dict]:
    """Every feature of a layer (paged), optionally inside a bbox given in ``srs``."""
    base = {"service": "WFS", "version": "2.0.0", "request": "GetFeature",
            "outputFormat": "application/json", "typeNames": type_name,
            "srsName": srs, "count": config.FR_PAGE}
    if bbox:
        base["bbox"] = ",".join(f"{v:.0f}" for v in bbox) + f",urn:ogc:def:crs:{srs.replace(':', '::')}"
    if properties:
        base["propertyName"] = properties
    if cql:
        base["CQL_FILTER"] = cql
    if sort_by:  # stable paging: without it the server may repeat or skip features across pages
        base["sortBy"] = sort_by
    out: list[dict] = []
    start = 0
    while True:
        d = get(config.FR_WFS, {**base, "startIndex": start}).json()
        out.extend(d["features"])
        start += config.FR_PAGE
        if start >= d.get("numberMatched", 0) or not d["features"]:
            return out


@lru_cache(maxsize=1)
def _capabilities() -> str:
    return get(config.FR_WFS, {"service": "WFS", "version": "2.0.0", "request": "GetCapabilities"}).text


def rpg_layers() -> dict[int, str]:
    """Campaign -> RPG parcel layer. RPG.LATEST is the newest campaign, which has no named
    layer yet; its year is read from the layer title."""
    cap = _capabilities()
    out = {int(y): f"RPG.{y}:parcelles_graphiques"
           for y in re.findall(r"<Name>RPG\.(\d{4}):parcelles_graphiques</Name>", cap)}
    m = re.search(r"<Name>RPG\.LATEST:parcelles_graphiques</Name>\s*<Title>[^<]*?(\d{4})", cap)
    if m and int(m.group(1)) not in out:
        out[int(m.group(1))] = "RPG.LATEST:parcelles_graphiques"
    return {y: t for y, t in sorted(out.items()) if y >= config.FR_FIRST_YEAR}
