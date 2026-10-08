import numpy as np
import pandas as pd
from shapely.geometry import box

from fallow import calibrate, config, geo, official, season


def test_bins_edges():
    v = np.array([config.NDVI_LO, 0.449, 0.45, 0.99, 5.0, -3.0])
    b = season.to_bins(v)
    assert b[0] == 0 and b[-1] == 0
    assert b[1] == calibrate.edge(0.45) - 1 and b[2] == calibrate.edge(0.45)
    assert b[4] == config.N_BINS - 1


def test_histograms_and_rule():
    munis = [geo.Municipality("50001", "A", "50", box(0, 0, 1, 1)),
             geo.Municipality("50002", "B", "50", box(1, 0, 2, 1))]
    spring = np.array([[0.2, 0.8], [0.3, 0.2]], dtype="float32")
    summer = np.array([[0.1, 0.2], [0.7, 0.1]], dtype="float32")
    maxima = {"spring": spring, "summer": summer,
              "n_spring": np.array([[5, 5], [5, 1]]), "n_summer": np.array([[3, 3], [3, 3]])}
    crop = np.ones((2, 2), bool)
    idx = np.array([[1, 1], [2, 2]])
    h = season.histograms(maxima, crop, idx, munis)
    assert h.n.sum() == 4
    assert ((h.ine == "50002") & (h.s == -1)).sum() == 1  # too few spring dates
    est = calibrate.fallow_ha(h, 0.45, 0.40)
    assert est.loc["50001", "fallow_ha"] == config.PIXEL_HA      # bare in spring and summer
    assert est.loc["50002", "fallow_ha"] == 0                     # summer crop; other pixel no data
    assert est.loc["50002", "nodata_ha"] == config.PIXEL_HA


def test_offset_detection():
    with_offset = np.full((50, 50), 1400, dtype="uint16")
    without = np.full((50, 50), 400, dtype="uint16")
    assert not season._offset_applied(with_offset)
    assert season._offset_applied(without)


def test_province_labels():
    assert official.province_code("  Coruña, A") == "15"
    assert official.province_code("A Coruña") == "15"
    assert official.province_code("  Zaragoza") == "50"
    assert official.province_code("Guipúzcoa") == "20"
    assert official.province_code("   NAVARRA, COMUNIDAD FORAL DE") == "31"
    assert official.province_code("  Ciudad Real") == "13"
    assert official.province_code("  Palmas, Las") is None


def test_worldcover_tiles():
    assert geo.worldcover_tiles(-1.2, 41.1, -0.2, 41.9) == ["N39W003"]
    assert geo.worldcover_tiles(-0.5, 41.0, 0.5, 41.5) == ["N39W003", "N39E000"]


def test_change_scores_sign():
    idx = ["a", "b", "c", "d", "e", "a", "b", "c", "d", "e"]
    p = pd.DataFrame({"year": [2018] * 5 + [2019] * 5,
                      "fallow_ha": [100, 200, 300, 400, 500, 110, 190, 320, 380, 520],
                      "pac_ha": [90, 210, 280, 410, 480, 100, 200, 300, 390, 500]}, index=idx)
    s = calibrate.change_scores(p)
    assert s["n"] == 5 and s["same_sign_pct"] == 100.0
