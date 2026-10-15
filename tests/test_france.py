import io

import openpyxl
import pandas as pd
from shapely.geometry import box

from fallow import config, i18n
from fallow.france import aggregate, saa, units, wfs


def test_french_typography():
    assert i18n.n(46709, "fr") == "46 709"
    assert i18n.n(46709, "es") == "46.709"
    assert i18n.p(2.66, "fr") == "2,7 %"
    assert i18n.p(2.66, "es") == "2,7 %"
    assert i18n.d(1234.5, "fr") == "1 234,5"


def test_classify_groups():
    df = pd.DataFrame({"code_group": ["11", "1", "18", "28", "17"],
                       "surf_parc": [2.0, 10.0, 5.0, 1.0, 3.0]})
    out = aggregate.classify(df)
    assert out.fallow_ha.sum() == 2.0
    assert out.arable_ha.sum() == 12.0      # fallow and wheat; not grassland (18, 17) nor 28
    assert out.declared_ha.sum() == 21.0


def test_rpg_layers_reads_latest_year(monkeypatch):
    cap = ("<Name>RPG.2015:parcelles_graphiques</Name><Title>x</Title>"
           "<Name>RPG.2024:parcelles_graphiques</Name><Title>x</Title>"
           "<Name>RPG.LATEST:parcelles_graphiques</Name>\n  <Title>Registre parcellaire graphique "
           "(RPG) 2025 : Parcelles graphiques</Title>")
    monkeypatch.setattr(wfs, "_capabilities", lambda: cap)
    layers = wfs.rpg_layers()
    assert layers[2025] == "RPG.LATEST:parcelles_graphiques"
    assert layers[2015] == "RPG.2015:parcelles_graphiques"


def test_communes_and_spas(monkeypatch):
    coms = [units.Commune("79001", "A", "79", box(0, 0, 10, 10)),
            units.Commune("2A004", "B", "79", box(10, 0, 20, 10))]
    spa = [{"sitecode": "FR5412013", "name": "Z", "species": ["A128"], "geom": box(5, 0, 15, 10)}]
    monkeypatch.setattr(units, "communes", lambda: coms)
    monkeypatch.setattr(units, "steppe_spas", lambda: spa)
    df = aggregate.classify(pd.DataFrame({
        "code_group": ["11", "1", "11", "1"], "surf_parc": [1.0, 4.0, 2.0, 8.0],
        "x": [2, 7, 12, 50], "y": [5, 5, 5, 5]}))
    with_c = aggregate.with_commune(df)
    assert len(with_c) == 3                          # the parcel at x=50 is outside every commune
    assert set(with_c.insee) == {"79001", "2A004"}   # INSEE codes stay strings (Corsica)
    hits = aggregate.in_spa(with_c.reset_index(drop=True))
    assert sorted(hits.row) == [1, 2] and set(hits.sitecode) == {"FR5412013"}


def test_saa_parse():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "TER"
    ws.append(["Statistique agricole annuelle"])
    ws.append([])
    ws.append(["LIB_REG2", "LIB_DEP", "LIB_SAA", "SURF_2023", "SURF_2024"])
    ws.append(["75 - Nouvelle Aquitaine", "079 - Deux-Sèvres", "01 - Jachères", 3285, 4395])
    ws.append(["75 - Nouvelle Aquitaine", "079 - Deux-Sèvres", "02 - Céréales", 1, 2])
    ws.append(["75 - Nouvelle Aquitaine", "079 - Deux-Sèvres", "21 - TERRES ARABLES (01 + ...)", 344778, 343823])
    ws.append(["11 - Île-de-France", "077 - Seine-et-Marne", "01 - Jachères", 1, 1])
    buf = io.BytesIO()
    wb.save(buf)
    df = saa.parse(buf.getvalue())
    assert set(df.dep) == {"79"}
    row = df[df.year == 2024].iloc[0]
    assert row.fallow_ha == 4395 and row.arable_ha == 343823


def test_study_areas_cover_departments():
    in_areas = {d for _, deps in config.FR_AREAS.values() for d in deps}
    assert in_areas == set(config.FR_DEPARTMENTS)
