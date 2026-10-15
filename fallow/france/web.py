"""docs/fr/index.html: fallow by petite région agricole from the RPG, the steppe-bird SPAs
against the land around them, the official check and the method, in French."""
from __future__ import annotations

import json
from html import escape
from pathlib import Path

import pandas as pd
from shapely.ops import unary_union

from .. import config, i18n
from ..logo import LOGO_SVG, favicon_link
from ..web import ACCENT, ACCENT_DARK, COMMON_CSS, _path
from . import aggregate, saa, units

LANG = "fr"
MAP_WIDTH = 600
SIMPLIFY_M = 250
# A PRA is coloured only with enough arable land for its share to mean something.
MIN_ARABLE_HA = 500


def _n(v: float) -> str:
    return i18n.n(v, LANG)


def _p(v: float, nd: int = 1) -> str:
    return i18n.p(v, LANG, nd)


def _series(df: pd.DataFrame, key: str, cols=("fallow_ha", "arable_ha")) -> dict:
    out: dict = {}
    for r in df.itertuples():
        out.setdefault(str(getattr(r, key)), {})[int(r.year)] = [round(getattr(r, c)) for c in cols]
    return out


def tables() -> tuple[pd.DataFrame, pd.DataFrame]:
    """(commune-year rows with their PRA and department, SPA-year rows)."""
    com = aggregate.load("communes")
    if com.empty:
        raise SystemExit("no French campaign yet; run `fallow fr-rpg` and `fallow fr-aggregate` first")
    com = com.merge(units.commune_table(), on="insee", how="left")
    return com, aggregate.load("zps")


def map_shapes(com: pd.DataFrame) -> dict:
    """One small map per study area: PRA, department outlines and steppe SPAs."""
    geoms = {c.insee: c.geom for c in units.communes()}
    table = units.commune_table()
    deps = units.departments()
    spas = units.steppe_spas()
    out = {}
    for key, (name, dep_codes) in config.FR_AREAS.items():
        outline = unary_union([deps[d] for d in dep_codes])
        x0, y0, x1, y1 = outline.bounds
        k = MAP_WIDTH / (x1 - x0)

        def tf(x, y, x0=x0, y1=y1, k=k):
            return round((x - x0) * k, 1), round((y1 - y) * k, 1)

        pra = {}
        for code, g in table[table.dep.isin(dep_codes)].groupby("pra"):
            pra[code] = _path(unary_union([geoms[i] for i in g.insee]).simplify(SIMPLIFY_M), tf)
        out[key] = {
            "name": name, "height": round((y1 - y0) * k),
            "pra": pra,
            "deps": [_path(deps[d].simplify(SIMPLIFY_M), tf) for d in dep_codes],
            "spas": {s["sitecode"]: _path(s["geom"].intersection(outline).simplify(SIMPLIFY_M), tf)
                     for s in spas if s["geom"].intersects(outline)},
        }
    return out


def build_data() -> dict:
    com, zps = tables()
    years = sorted(com.year.unique().tolist())
    s = aggregate.SUMS
    pra = com.groupby(["pra", "year"])[s].sum().reset_index()
    pra_meta = com.drop_duplicates("pra").set_index("pra")
    dep = com.groupby(["dep", "year"])[s].sum().reset_index()
    area = com.groupby(["area", "year"])[s].sum().reset_index()
    off = saa.load()
    # Reference for each SPA: the study communes of the departments it touches, outside every
    # steppe SPA. Same soils and farming as far as departments go, no SPA measures.
    out_cols = [f"{c}_out_spa" for c in ("fallow_ha", "arable_ha")]
    dep_out = com.groupby(["dep", "year"])[out_cols].sum()
    deps = units.departments()
    spas = []
    for sp in units.steppe_spas():
        touched = sorted(d for d, g in deps.items() if g.intersects(sp["geom"]))
        ref = dep_out.loc[dep_out.index.get_level_values(0).isin(touched)].groupby(level=1).sum()
        z = zps[zps.sitecode == sp["sitecode"]]
        spas.append({
            "code": sp["sitecode"], "name": sp["name"], "species": sp["species"], "deps": touched,
            "area": next(k for k, (_, dd) in config.FR_AREAS.items() if touched and touched[0] in dd),
            "y": {int(r.year): [round(r.fallow_ha), round(r.arable_ha)] for r in z.itertuples()},
            "ref": {int(y): [round(r[out_cols[0]]), round(r[out_cols[1]])] for y, r in ref.iterrows()},
        })
    return {
        "years": years,
        "pra": {p: {"name": pra_meta.at[p, "pra_name"].title(), "dep": pra_meta.at[p, "dep"],
                    "area": pra_meta.at[p, "area"], "y": v}
                for p, v in _series(pra, "pra").items()},
        "deps": {d: {"name": config.FR_DEPARTMENTS[d], "y": v,
                     "saa": {int(r.year): round(r.fallow_ha) for r in off[off.dep == d].itertuples()}
                     if not off.empty else {}}
                 for d, v in _series(dep, "dep").items()},
        "areas": {a: {"name": config.FR_AREAS[a][0], "y": v} for a, v in _series(area, "area").items()},
        "spas": spas,
        "species": config.FR_STEPPE_SPECIES,
        "policy": [{"year": y, "text": t} for y, t in i18n.POLICY[LANG]],
        "min_arable": MIN_ARABLE_HA,
        "_com": com, "_pra": pra, "_zps": zps,
    }


def _sources() -> str:
    rows = [
        ("Jachère et terres arables", "Registre parcellaire graphique (RPG), « parcelles graphiques », "
         f"campagnes {config.FR_FIRST_YEAR} et suivantes, IGN / ASP, Licence Ouverte 2.0, par le service WFS de la Géoplateforme"),
        ("Jachère", f"groupe de cultures {config.FR_FALLOW_GROUP} « gel (surfaces gelées sans production) » : "
         "codes J5M, J6P, J6S et JNO jusqu’en 2022, JAC et JNO depuis 2023"),
        ("Terres arables", "groupes de cultures que le RPG 2024 range en « terres arables » (TA) : céréales, "
         "oléagineux, protéagineux, fourrages annuels, prairies temporaires, légumes, gel… ; "
         "le groupe 28 « divers », mixte, est laissé de côté"),
        ("Communes", f"ADMIN EXPRESS COG {config.FR_COG_YEAR}, IGN : une seule géographie pour toutes les campagnes"),
        ("Petites régions agricoles", "référentiel Agreste 2017 commune → PRA ; les communes nouvelles prennent "
         "la PRA de la commune de 2017 qui contient leur point intérieur"),
        ("ZPS", "sites de la directive Oiseaux (Natura 2000, base de l’Agence européenne pour l’environnement) "
         "dont le formulaire standard cite l’outarde canepetière (A128) ou le ganga cata (A205)"),
        ("Contrôle", "Statistique agricole annuelle (SAA), Agreste, séries longues 2010-2025 par département, "
         "lignes « jachères » et « terres arables »"),
    ]
    return '<table class="params">' + "".join(
        f"<tr><th>{escape(a)}</th><td>{escape(b)}</td></tr>" for a, b in rows) + "</table>"


PLANTILLA = r"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
__FAVICON__
<title>Jachères et oiseaux de plaine</title>
<meta name="description" content="Surface en jachère par petite région agricole dans les plaines de l’outarde canepetière (Centre-Ouest, Crau et Languedoc, Champagne), lue chaque campagne dans le Registre parcellaire graphique.">
<link rel="alternate" hreflang="es" href="../">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@500;600;700&family=Source+Serif+4:opsz,wght@8..60,400;8..60,600&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
__COMMON_CSS__
:root{--accent:__ACCENT__;--accent-dark:__ACCENT_DARK__}
:root{--q0:#efe6d8;--q1:#dcc3a1;--q2:#c4976a;--q3:#a0683f;--q4:#6e3f22;--zps:#2f5e7a;--oficial:#6b625c}
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){--q0:#3a2e25;--q1:#5c4330;--q2:#8a5d3b;--q3:#c08458;--q4:#efb98a;--zps:#8ec3e0;--oficial:#a69a91}
}
:root[data-theme="dark"]{--q0:#3a2e25;--q1:#5c4330;--q2:#8a5d3b;--q3:#c08458;--q4:#efb98a;--zps:#8ec3e0;--oficial:#a69a91}
.marca{display:flex;align-items:baseline;gap:14px;flex-wrap:wrap}
.marca .label{color:var(--muted);font-size:14px}
main{max-width:1440px;margin:0 auto;padding:0 16px;display:grid;grid-template-columns:minmax(0,1.3fr) minmax(320px,1fr);gap:20px;align-items:start}
.controles{display:flex;flex-wrap:wrap;gap:8px 16px;align-items:center;padding:10px 0;font-size:14px;color:var(--muted)}
.controles select{font:14px var(--font-text);background:var(--paper);color:var(--ink);border:1px solid var(--line);padding:4px 6px}
.cartes{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px}
.mapa{background:var(--paper);border:1px solid var(--line);padding:8px;margin:0}
.mapa figcaption{font:600 15px/1.1 var(--font-title);text-transform:uppercase;letter-spacing:.05em;margin-bottom:4px}
.mapa svg{display:block;width:100%;height:auto}
.mapa path.c{stroke:var(--paper);stroke-width:.8;cursor:pointer}
.mapa path.c:hover,.mapa path.c.sel{stroke:var(--ink);stroke-width:2}
.mapa path.c.nd{fill:url(#rayas)}
.mapa path.d{fill:none;stroke:var(--ink);stroke-width:1.2;pointer-events:none}
.mapa path.z{fill:none;stroke:var(--zps);stroke-width:1.6;stroke-dasharray:4 2;pointer-events:none}
.leyenda{display:flex;flex-wrap:wrap;gap:4px 12px;font-size:12.5px;color:var(--muted);align-items:center;margin-top:6px}
.leyenda i{display:inline-block;width:14px;height:10px;margin-right:4px;vertical-align:-1px}
.panel{display:grid;gap:14px}
.panel h2{margin:0;font:600 26px/1.1 var(--font-title);text-wrap:balance}
.panel .sub{margin:0;color:var(--muted);font-size:14.5px}
.serie svg{width:100%;height:auto;display:block;overflow:visible}
.serie .eje{stroke:var(--line)} .serie text{font:11px var(--font-data);fill:var(--muted)}
.serie .linea{fill:none;stroke:var(--accent);stroke-width:2.2}
.serie .punto{fill:var(--accent)}
.serie .of{fill:none;stroke:var(--oficial);stroke-width:1.5;stroke-dasharray:4 3}
.serie .ref{fill:none;stroke:var(--zps);stroke-width:1.8;stroke-dasharray:5 3}
.serie .pol{stroke:var(--ink);stroke-width:1;stroke-dasharray:2 3;opacity:.55}
.serie .pol-n{font:600 11px var(--font-title);fill:var(--ink)}
dl.cifras{margin:0;display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:8px 12px}
dl.cifras div{display:grid;gap:1px} dl.cifras dt{font-size:12px;color:var(--muted)}
dl.cifras dd{margin:0;font:500 16px var(--font-data);font-variant-numeric:tabular-nums}
ol.politica{margin:0;padding:0;list-style:none;display:grid;gap:6px;font-size:14.5px}
ol.politica li{display:grid;grid-template-columns:3.2em 1fr;gap:8px}
ol.politica b{font-family:var(--font-data);color:var(--accent)}
.bloque{max-width:1440px;margin:0 auto;padding:24px 16px 0}
.bloque > h2{margin:0 0 8px;font:700 28px/1 var(--font-title);text-transform:uppercase;letter-spacing:.03em}
.provincias{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:14px}
.provincias .card h3{margin:0 0 4px;font:600 18px/1.1 var(--font-title);text-transform:uppercase;letter-spacing:.05em}
.tabla-zps{overflow-x:auto}
.tabla-zps table{width:100%}
.tabla-zps td.num,.tabla-zps th.num{text-align:right;font-variant-numeric:tabular-nums}
.dos{display:grid;grid-template-columns:1fr 1fr;gap:28px}
.dos p{margin:0 0 10px;max-width:72ch}
.fuentes{border:1.5px solid var(--accent);padding:14px 16px;background:var(--paper)}
.fuentes h2{margin:0 0 8px;font:700 22px/1.1 var(--font-title);text-transform:uppercase;letter-spacing:.03em}
.fuentes p{margin:0 0 10px;max-width:90ch}
.method{border-top:1.5px solid var(--ink);display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:28px;margin-top:24px}
.method p{margin:0 0 10px} .method ol,.method ul{margin:0 0 10px;padding-left:1.4em} .method li{margin-bottom:8px}
.method > div > h3:first-child{margin-top:0}
.method table.params th{white-space:normal;width:30%}
.aviso{border-left:3px solid var(--accent);padding:2px 0 2px 12px}
.site-footer p{margin:0}
@media (max-width:900px){main,.method,.dos{grid-template-columns:1fr}}
</style>
</head>
<body>
<header class="site-header">
  <div class="marca">
    <h1>__LOGO__Jachères <span>et oiseaux de plaine</span></h1>
    <span class="label">Centre-Ouest, Crau et Languedoc, Champagne · RPG · un chiffre par campagne · <a href="../" hreflang="es" lang="es">Versión en español</a></span>
  </div>
  <p class="lede">La jachère est l’un des couverts où l’outarde canepetière trouve insectes, abri et place pour nicher au milieu des céréales. Cette page compte, campagne après campagne et petite région agricole par petite région agricole, la surface que les exploitants déclarent en jachère à la PAC, et la met en regard des changements de la PAC qui la font monter ou baisser.</p>
  <div class="figures">
    <div><b>__ULTIMO__</b><span>hectares de jachère déclarés en __ANIO__</span></div>
    <div><b>__CUOTA__</b><span>des terres arables</span></div>
    <div><b>__CAMBIO__</b><span>de jachère par rapport à __ANIO0__</span></div>
    <div><b>__NPRA__</b><span>petites régions agricoles</span></div>
  </div>
</header>

<main>
  <div>
    <div class="controles">
      <label>Campagne <select id="f-anio"></select></label>
      <span>Cliquez sur une petite région agricole pour voir sa série.</span>
    </div>
    <svg width="0" height="0" style="position:absolute" aria-hidden="true"><defs><pattern id="rayas" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="6" stroke="var(--line)" stroke-width="2"/></pattern></defs></svg>
    <div class="cartes" id="cartes"></div>
    <div class="leyenda" id="leyenda" aria-label="Légende"></div>
  </div>
  <div class="panel card" id="panel" aria-live="polite"></div>
</main>

<section class="bloque" id="zps">
  <h2>Dans les ZPS de l’outarde</h2>
  <p class="note">Part des terres arables en jachère dans chaque zone de protection spéciale (ZPS) dont le formulaire Natura 2000 cite l’outarde canepetière ou le ganga cata, et la même part dans le reste des communes étudiées des départements qu’elle touche, hors de toute ZPS de plaine. Une parcelle compte dans la ZPS si son point intérieur y tombe. Les ZPS de moins de __MINZPS__ ha de terres arables (marais, garrigues, étangs) sont grisées : leur part ne dit pas grand-chose.</p>
  <div class="tabla-zps"><table id="t-zps"></table></div>
</section>

<section class="bloque" id="officiel">
  <h2>Face aux chiffres officiels</h2>
  <p class="note">Jachère déclarée dans le RPG par département (ligne de couleur) et celle de la Statistique agricole annuelle d’Agreste (tirets), en hectares. La SAA estime toute la surface agricole, y compris celle qui n’est pas déclarée à la PAC, à partir d’enquêtes et de l’avis des services départementaux ; le RPG compte ce que les exploitants déclarent sous le code jachère. Les deux ne tombent donc pas sur le même chiffre, et l’écart n’a pas le même signe partout. __ECART_SAA__ Ce qui compte ici, c’est que les deux courbes bougent ensemble.</p>
  <div class="provincias" id="provincias"></div>
</section>

<section class="bloque" id="sources-es">
  <div class="fuentes">
    <h2>__BOX_TITLE__</h2>
    __BOX_BODY__
    <p>__BOX_LINK__</p>
  </div>
</section>

<section class="bloque" id="pourquoi">
  <h2>Pourquoi c’est important</h2>
  <div class="dos">
    <div>
      <p>L’outarde canepetière a presque disparu des plaines céréalières de l’Ouest. Les comptages nationaux de la LPO et de ses partenaires sont passés d’environ 6&#8239;800 mâles chanteurs en 1978 à quelque 320 en 2012 dans le Centre-Ouest, dernier noyau de la population migratrice d’Europe de l’Ouest ; le comptage de 2024 en donne encore environ 330. Autour de la Méditerranée, la population, en grande partie sédentaire, compte plus de 2&#8239;000 mâles, dont une grande partie en Crau, dans les Costières et les plaines de l’Hérault (<a href="https://cen-paca.org/wp-content/uploads/2025/02/Rapport_activite_2024_Outarde.pdf">CEN PACA, rapport d’activité 2024 du plan national d’actions</a>).</p>
      <p>Dans la plaine de Niort, Bretagnolle et ses collègues (2011, <a href="https://doi.org/10.1111/j.1474-919X.2010.01092.x">Ibis 153 : 4-13</a>) ont relié l’effondrement local (de 65 mâles en 1995 à 6 en 2003) au manque de jeunes, puis la remontée à une trentaine de mâles en 2009 aux mesures agro-environnementales ciblées : plus de 1&#8239;300 ha, surtout de luzerne, fauchés après la nidification. La jachère n’est qu’un de ces couverts, mais c’est celui que la PAC fait varier le plus d’une année à l’autre.</p>
      <p class="aviso">Cette page ne publie l’emplacement d’aucune espèce. Les chiffres sont des surfaces agricoles par commune, petite région ou ZPS ; les données de comptage appartiennent à ceux qui les produisent.</p>
    </div>
    <div>
      <h3 class="label">La PAC et la jachère</h3>
      <ol class="politica" id="politica"></ol>
      <p class="note">Depuis 2023, l’éco-régime de la PAC française récompense aussi les « infrastructures agroécologiques », dont la jachère. Depuis 2024, il n’est plus obligatoire de laisser 4&#8239;% des terres arables non productives.</p>
    </div>
  </div>
</section>

<section class="method" id="methode">
  <div>
    <h2>Comment c’est calculé</h2>
    <ol>
      <li>Pour chaque campagne depuis __ANIO0__, on télécharge du service WFS de l’IGN toutes les parcelles du Registre parcellaire graphique (RPG) des dix départements étudiés : la culture principale déclarée à la PAC, son groupe et la surface déclarée. Le RPG est publié en données ouvertes et anonymisé : il ne contient pas le nom des exploitants.</li>
      <li>Chaque parcelle est placée dans une commune par son point intérieur (un point toujours à l’intérieur du polygone). Une parcelle à cheval sur deux communes compte entièrement dans celle qui contient ce point.</li>
      <li>Une parcelle est en jachère si sa culture appartient au groupe « gel, surfaces gelées sans production ». Les terres arables sont les groupes de terres labourables ; les prairies permanentes, les vignes, les vergers et les surfaces pastorales n’en font pas partie.</li>
      <li>Les communes sont additionnées en petites régions agricoles (PRA) d’Agreste, les zones que la statistique agricole française juge homogènes, l’équivalent des « comarcas agrarias » espagnoles. Le même calcul se fait dans chaque ZPS de plaine et, pour comparer, dans le reste des communes des départements qu’elle touche.</li>
      <li>Chaque département est comparé à la Statistique agricole annuelle (SAA) d’Agreste. Aucun seuil n’est ajusté : c’est la déclaration elle-même qui est comptée.</li>
    </ol>
    <h3>Sources et définitions</h3>
    __FUENTES__
  </div>
  <div>
    <h3>Ce qui reste en dehors, et pourquoi</h3>
    <ul>
      <li><b>Le reste de la France.</b> Seuls les dix départements des plaines à outarde sont traités : Charente, Charente-Maritime, Deux-Sèvres, Vienne et Vendée ; Bouches-du-Rhône, Gard et Hérault ; Marne et Aube. Le même code marche pour d’autres départements, il suffit de les ajouter à la configuration.</li>
      <li><b>Les terres non déclarées à la PAC.</b> Le RPG ne voit que ce que les exploitants déclarent pour toucher les aides. La SAA, qui couvre tout, sert de contrôle.</li>
      <li><b>Les couverts favorables autres que la jachère.</b> La luzerne, les prairies temporaires et les couverts des mesures agro-environnementales comptent beaucoup pour l’outarde, mais ce ne sont pas des jachères : ils sont dans les terres arables, pas dans la jachère.</li>
      <li><b>Les coussouls de la Crau.</b> La steppe de la Crau, où vivent l’outarde et le ganga cata, est un parcours pastoral, pas une terre arable : elle n’entre pas dans le calcul. Dans la Crau, la part de jachère ne parle que des terres cultivées autour.</li>
      <li><b>Les oiseaux eux-mêmes.</b> Aucune donnée de comptage ni de localisation n’est utilisée ou publiée. Les ZPS servent de cadre, pas de carte de l’espèce.</li>
    </ul>
    <h3>Ce qu’il faut savoir avant de le citer</h3>
    <p class="aviso">Le RPG dit ce qui a été déclaré, pas ce qui pousse. Il n’y a pas d’erreur de mesure comme avec un satellite, mais la définition de la jachère suit les règles de la PAC : en 2015 elle comptait comme surface d’intérêt écologique, en 2022 on a pu cultiver les jachères SIE, et depuis 2023 la nomenclature a changé (codes JAC et JNO). Un saut d’une année peut venir d’une règle autant que des champs.</p>
    <p class="aviso">La dernière campagne publiée par l’IGN (couche « RPG.LATEST ») peut encore être corrigée ; elle est reprise chaque année.</p>
    <p>Les ZPS de marais, d’étangs ou de garrigues ont peu de terres arables ; leur part de jachère est calculée mais grisée. Les limites de la carte sont simplifiées à environ 250 mètres ; les chiffres, eux, sont calculés avec les limites complètes.</p>
    <h3>Données ouvertes</h3>
    <p><a href="jacheres-pra.csv">jacheres-pra.csv</a>, <a href="jacheres-communes.csv">jacheres-communes.csv</a> (code INSEE) et <a href="jacheres-zps.csv">jacheres-zps.csv</a> (code de site Natura 2000) par campagne · agrégats par commune dans le <a href="https://github.com/Asensio94/barbechos-esteparias/tree/main/data/fr">dépôt</a> · <a href="https://github.com/Asensio94/barbechos-esteparias">code</a>.</p>
  </div>
</section>

<footer class="site-footer">
  <p class="principle">Données publiques, règles en vue et chaque chiffre relié à sa source. Des indices, pas des verdicts.</p>
  <p>Registre parcellaire graphique : IGN / Agence de services et de paiement, Licence Ouverte 2.0 · Communes et départements : ADMIN EXPRESS, IGN, Licence Ouverte 2.0 · Petites régions agricoles et Statistique agricole annuelle : Agreste, ministère de l’Agriculture et de la Souveraineté alimentaire · Sites Natura 2000 : Agence européenne pour l’environnement.</p>
  <nav aria-label="Projets frères"><ul class="siblings">
    <li><a href="https://asensio94.github.io/observatorio-alegaciones/">Observatorio de alegaciones</a></li>
    <li><a href="https://asensio94.github.io/vigia-incendios/">Vigía de incendios</a></li>
    <li><a href="https://asensio94.github.io/centinela-natura/">Centinela Natura</a></li>
    <li><a href="https://asensio94.github.io/vigilancia-humedales/">Vigilancia de humedales</a></li>
    <li><a href="https://asensio94.github.io/sub-nocte/">Sub Nocte</a></li>
    <li><a href="https://asensio94.github.io/riesgo-tendidos-aves/">Riesgo de tendidos para aves</a></li>
    <li><a href="https://asensio94.github.io/grafo-promotores/">Grafo de promotores</a></li>
    <li><a href="https://asensio94.github.io/cartera-cotizadas/">Cartera de las cotizadas</a></li>
    <li><a href="https://asensio94.github.io/cuaderno-campo/">Cuaderno de campo</a></li>
    <li aria-current="page"><a href="https://asensio94.github.io/barbechos-esteparias/">Barbechos y aves esteparias</a></li>
  </ul></nav>
</footer>

<script>
const D = __DATOS__;
const NB = " ";
const num = (x,d=0) => x==null ? "—" : x.toLocaleString("fr-FR",{minimumFractionDigits:d,maximumFractionDigits:d});
const pc = (x,d=1) => x==null ? "—" : num(x,d) + NB + "%";
const pct = (a,b) => b ? 100*a/b : null;
const Y = D.years, Y0 = Y[0];
const selA = document.getElementById("f-anio");
for (const y of [...Y].reverse()) selA.add(new Option(y, y));
let sel = null;

const ESC = [2,4,8,15];
function color(v){ if (v == null) return null; const i = ESC.findIndex(t => v < t); return `var(--q${i < 0 ? 4 : i})`; }
function cuota(s, y){ const v = s.y[y]; return v && v[1] >= D.min_arable ? pct(v[0], v[1]) : null; }

document.getElementById("cartes").innerHTML = Object.entries(D.map).map(([k, m]) =>
  `<figure class="mapa"><figcaption>${m.name}</figcaption><svg viewBox="0 0 ${D.mapw} ${m.height}" role="img" aria-label="Carte des petites régions agricoles : ${m.name}">
    <g class="g-pra">${Object.entries(m.pra).map(([c,p]) => `<path class="c" data-c="${c}" d="${p}" tabindex="0"><title></title></path>`).join("")}</g>
    <g>${Object.entries(m.spas).map(([c,p]) => `<path class="z" d="${p}"/>`).join("")}</g>
    <g>${m.deps.map(p => `<path class="d" d="${p}"/>`).join("")}</g></svg></figure>`).join("");
const celdas = [...document.querySelectorAll("path.c")];

function pintar(){
  const y = +selA.value;
  for (const el of celdas) {
    const s = D.pra[el.dataset.c], v = s ? cuota(s, y) : null, col = color(v);
    el.classList.toggle("nd", col == null); el.style.fill = col || "";
    el.classList.toggle("sel", el.dataset.c === sel);
    el.firstChild.textContent = s ? `${s.name} : ${v == null ? "peu de terres arables" : pc(v)}` : "hors étude";
  }
  const lab = ["< 2" + NB + "%","2–4" + NB + "%","4–8" + NB + "%","8–15" + NB + "%","≥ 15" + NB + "%"];
  document.getElementById("leyenda").innerHTML = `Part des terres arables en jachère en ${y} : `
    + [1,3,6,10,20].map((v,i) => `<span><i style="background:${color(v)}"></i>${lab[i]}</span>`).join("")
    + `<span><i style="background:url(#rayas);border:1px solid var(--line)"></i>moins de ${num(D.min_arable)} ha de terres arables</span>`
    + `<span><i style="border:1.6px dashed var(--zps);height:8px"></i>ZPS outarde ou ganga</span>`;
}

function grafica(serie, extra, unidad){
  const W = 340, H = 150, L = 46, R = 8, T = 18, B = 22;
  const ys = Y.filter(y => serie[y] != null);
  const todos = [...ys.map(y => serie[y]), ...(extra||[]).flatMap(e => Object.values(e.d))].filter(v => v != null);
  if (!todos.length) return "";
  const max = Math.max(...todos) * 1.1 || 1, min = 0;
  const x = y => L + (Y.length < 2 ? 0 : (y - Y[0]) / (Y[Y.length-1] - Y[0]) * (W - L - R));
  const yy = v => T + (1 - (v - min) / (max - min)) * (H - T - B);
  const et = v => unidad === "%" ? pc(v, max < 5 ? 1 : 0) : max >= 3000 ? num(v/1000, max >= 30000 ? 0 : 1) + NB + "k" : num(v);
  let s = `<svg viewBox="0 0 ${W} ${H}" role="img">`;
  for (const t of [0, .5, 1]) { const v = max/1.1*t; s += `<line class="eje" x1="${L}" x2="${W-R}" y1="${yy(v)}" y2="${yy(v)}"/><text x="${L-4}" y="${yy(v)+4}" text-anchor="end">${et(v)}</text>`; }
  for (const p of D.policy) if (p.year >= Y[0] && p.year <= Y[Y.length-1]) s += `<line class="pol" x1="${x(p.year)}" x2="${x(p.year)}" y1="${T-6}" y2="${H-B}"/><text class="pol-n" x="${x(p.year)}" y="${T-8}" text-anchor="middle">${D.policy.indexOf(p)+1}</text>`;
  for (const y of Y) if (Y.length < 8 || (y - Y0) % 2 === 0 || y === Y[Y.length-1]) s += `<text x="${x(y)}" y="${H-6}" text-anchor="middle">${y}</text>`;
  for (const e of (extra||[])) {
    const ks = Object.keys(e.d).map(Number).filter(k => k >= Y[0] && k <= Y[Y.length-1] && e.d[k] != null).sort();
    if (ks.length > 1) s += `<polyline class="${e.cls || "of"}" points="${ks.map(k => `${x(k)},${yy(e.d[k])}`).join(" ")}"><title>${e.n}</title></polyline>`;
  }
  if (ys.length > 1) s += `<polyline class="linea" points="${ys.map(y => `${x(y)},${yy(serie[y])}`).join(" ")}"/>`;
  s += ys.map(y => `<circle class="punto" cx="${x(y)}" cy="${yy(serie[y])}" r="3"><title>${y} : ${unidad === "%" ? pc(serie[y]) : num(serie[y]) + " ha"}</title></circle>`).join("");
  return s + "</svg>";
}

function total(){
  const t = {}; for (const a of Object.values(D.areas)) for (const [y, v] of Object.entries(a.y)) { t[y] = t[y] || [0,0]; t[y][0] += v[0]; t[y][1] += v[1]; }
  return t;
}
function panel(){
  const y = +selA.value, p = document.getElementById("panel");
  let s, titulo, sub;
  if (sel && D.pra[sel]) { s = D.pra[sel]; titulo = s.name; sub = `Petite région agricole · ${D.deps[s.dep] ? D.deps[s.dep].name : s.dep} (${s.dep})`; }
  else { s = {y: total()}; titulo = "Les trois zones d’étude"; sub = "Cliquez sur une petite région agricole pour voir la sienne"; }
  const v = s.y[y], v0 = s.y[Y0];
  const ha = Object.fromEntries(Object.entries(s.y).map(([k, a]) => [k, a[0]]));
  const sh = Object.fromEntries(Object.entries(s.y).map(([k, a]) => [k, a[1] ? pct(a[0], a[1]) : null]));
  p.innerHTML = `<div><h2>${titulo}</h2><p class="sub">${sub}</p></div>
    <dl class="cifras">
      <div><dt>Jachère en ${y}</dt><dd>${v ? num(v[0]) + " ha" : "—"}</dd></div>
      <div><dt>Part des terres arables</dt><dd>${v ? pc(pct(v[0], v[1])) : "—"}</dd></div>
      <div><dt>Terres arables</dt><dd>${v ? num(v[1]) + " ha" : "—"}</dd></div>
      <div><dt>Par rapport à ${Y0}</dt><dd>${v && v0 && v0[0] && y !== Y0 ? (v[0] >= v0[0] ? "+" : "−") + pc(Math.abs(100*(v[0]/v0[0]-1)), 0) : "—"}</dd></div>
    </dl>
    <figure class="serie" style="margin:0">${grafica(ha)}<figcaption class="note">Hectares déclarés en jachère, campagne par campagne. Les lignes verticales numérotées sont les changements de la PAC ci-dessous.</figcaption></figure>
    <figure class="serie" style="margin:0">${grafica(sh, null, "%")}<figcaption class="note">Part des terres arables en jachère.</figcaption></figure>
    <ol class="politica">${D.policy.map((p,i) => `<li><b>${i+1} · ${p.year}</b><span>${p.text}</span></li>`).join("")}</ol>
    ${sel ? '<button type="button" id="todo" class="badge" style="background:none;cursor:pointer">Voir le total</button>' : ""}`;
  document.getElementById("todo")?.addEventListener("click", () => { sel = null; pintar(); panel(); });
}

function tablaZps(){
  const y = +selA.value;
  const filas = D.spas.map(z => {
    const v = z.y[y], r = z.ref[y], ok = v && v[1] >= D.min_arable;
    const a = v && v[1] ? pct(v[0], v[1]) : null, b = r && r[1] ? pct(r[0], r[1]) : null;
    const sp = z.species.map(c => D.species[c]).join(", ");
    const sh = Object.fromEntries(Y.map(k => [k, z.y[k] && z.y[k][1] ? pct(z.y[k][0], z.y[k][1]) : null]));
    const sr = Object.fromEntries(Y.map(k => [k, z.ref[k] && z.ref[k][1] ? pct(z.ref[k][0], z.ref[k][1]) : null]));
    return {z, v, ok, a, b, sp, sh, sr};
  }).sort((p, q) => (q.ok - p.ok) || ((q.v ? q.v[1] : 0) - (p.v ? p.v[1] : 0)));
  document.getElementById("t-zps").innerHTML = `<tr><th>Site</th><th>Espèces citées</th><th class="num">Terres arables ${y}</th><th class="num">Jachère ${y}</th><th class="num">Part dans la ZPS</th><th class="num">Part autour (mêmes départements)</th></tr>`
    + filas.map(f => `<tr${f.ok ? "" : ' style="color:var(--muted)"'}><td><b>${f.z.name}</b><br><span class="note">${f.z.code} · ${f.z.deps.map(d => D.deps[d] ? D.deps[d].name : d).join(", ")}</span></td><td>${f.sp}</td>
      <td class="num">${f.v ? num(f.v[1]) + " ha" : "—"}</td><td class="num">${f.v ? num(f.v[0]) + " ha" : "—"}</td>
      <td class="num"><b>${f.ok ? pc(f.a) : "—"}</b></td><td class="num">${pc(f.b)}</td></tr>`
      + (f.ok ? `<tr><td colspan="6" style="border-top:0"><figure class="serie" style="margin:0;max-width:420px">${grafica(f.sh, [{n: "Autour, hors ZPS", d: f.sr, cls: "ref"}], "%")}<figcaption class="note">Part en jachère dans la ZPS (ligne pleine) et autour (tirets bleus).</figcaption></figure></td></tr>` : "")).join("");
}

document.getElementById("politica").innerHTML = D.policy.map(p => `<li><b>${p.year}</b><span>${p.text}</span></li>`).join("");
document.getElementById("provincias").innerHTML = Object.entries(D.deps).map(([c, d]) => {
  const serie = Object.fromEntries(Object.entries(d.y).map(([k, a]) => [k, a[0]]));
  return `<div class="card"><h3>${d.name} (${c})</h3>${grafica(serie, [{n: "SAA (Agreste)", d: d.saa}])}</div>`;
}).join("");

function elegir(c){ sel = c; pintar(); panel(); }
document.getElementById("cartes").addEventListener("click", e => { const c = e.target.closest("path.c"); if (c) elegir(c.dataset.c); });
document.getElementById("cartes").addEventListener("keydown", e => { const c = e.target.closest("path.c"); if (c && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); elegir(c.dataset.c); } });
selA.addEventListener("change", () => { pintar(); panel(); tablaZps(); });
pintar(); panel(); tablaZps();
</script>
</body>
</html>
"""


def _saa_gap(deps: dict, year: int) -> str:
    """One sentence on how far the RPG sits from the SAA, by department, in the given year."""
    gaps = {d: 100 * (v["y"][year][0] / v["saa"][year] - 1) for d, v in deps.items()
            if year in v["y"] and v["saa"].get(year)}
    if not gaps:
        return ""
    lo, hi = min(gaps, key=gaps.get), max(gaps, key=gaps.get)
    near = sum(1 for g in gaps.values() if abs(g) <= 11)

    def sg(g: float) -> str:
        return ("+" if g >= 0 else "−") + _p(abs(g), 0)

    return (f"En {year}, la jachère du RPG va de {sg(gaps[lo])} ({deps[lo]['name']}) à {sg(gaps[hi])} "
            f"({deps[hi]['name']}) par rapport à la SAA ; {near} départements sur {len(gaps)} restent "
            f"à {_p(11, 0)} près.")


def build() -> Path:
    d = build_data()
    com, pra, zps = d.pop("_com"), d.pop("_pra"), d.pop("_zps")
    d["map"] = map_shapes(com)
    d["mapw"] = MAP_WIDTH
    years = d["years"]
    last, first = years[-1], years[0]
    tot = com.groupby("year")[["fallow_ha", "arable_ha"]].sum()
    f1, a1 = tot.loc[last]
    f0 = tot.loc[first, "fallow_ha"]
    change = 100 * (f1 / f0 - 1) if f0 and last > first else None
    box = i18n.SOURCES_BOX[LANG]
    html = (PLANTILLA
            .replace("__LOGO__", LOGO_SVG)
            .replace("__FAVICON__", favicon_link(ACCENT, ACCENT_DARK))
            .replace("__COMMON_CSS__", COMMON_CSS)
            .replace("__ACCENT__", ACCENT).replace("__ACCENT_DARK__", ACCENT_DARK)
            .replace("__ULTIMO__", _n(f1)).replace("__ANIO__", str(last)).replace("__ANIO0__", str(first))
            .replace("__CUOTA__", _p(100 * f1 / a1) if a1 else "—")
            .replace("__CAMBIO__", ("+" if change >= 0 else "−") + _p(abs(change), 0) if change is not None else "—")
            .replace("__NPRA__", str(sum(1 for p in d["pra"].values()
                                         if (p["y"].get(last) or [0, 0])[1] >= MIN_ARABLE_HA)))
            .replace("__MINZPS__", _n(MIN_ARABLE_HA))
            .replace("__ECART_SAA__", _saa_gap(d["deps"], last))
            .replace("__FUENTES__", _sources())
            .replace("__BOX_TITLE__", box["title"]).replace("__BOX_BODY__", box["body"])
            .replace("__BOX_LINK__", box["link"])
            .replace("__DATOS__", json.dumps(d, ensure_ascii=False, separators=(",", ":"))))
    config.FR_DOCS.mkdir(parents=True, exist_ok=True)
    out = config.FR_DOCS / "index.html"
    out.write_text(html, encoding="utf-8")
    meta = units.commune_table().set_index("insee")
    cols = ["fallow_ha", "arable_ha", "declared_ha"]
    pra.assign(name=pra.pra.map(meta.drop_duplicates("pra").set_index("pra").pra_name),
               dep=pra.pra.str[:2]).round(0)[["year", "pra", "name", "dep", *cols]].to_csv(
        config.FR_DOCS / "jacheres-pra.csv", index=False)
    com.round(0)[["year", "insee", "name", "dep", "pra", *cols]].to_csv(
        config.FR_DOCS / "jacheres-communes.csv", index=False)
    names = {s["sitecode"]: s["name"] for s in units.steppe_spas()}
    zps.assign(name=zps.sitecode.map(names)).round(0)[["year", "sitecode", "name", *cols]].to_csv(
        config.FR_DOCS / "jacheres-zps.csv", index=False)
    return out
