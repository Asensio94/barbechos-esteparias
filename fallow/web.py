"""docs/index.html: map of districts, series per district, official check and the method."""
from __future__ import annotations

import json
from html import escape
from pathlib import Path

import pandas as pd
from shapely.ops import unary_union

from . import aggregate, config, geo
from .logo import LOGO_SVG, favicon_link

COMMON_CSS = Path(__file__).with_name("common.css").read_text(encoding="utf-8").strip()
ACCENT, ACCENT_DARK = "#7c4a2d", "#d9a07a"
MAP_WIDTH = 1000
SIMPLIFY_M = 400


def _es(x: float, decimales: int = 0) -> str:
    """Número a la española: 1.500 y 0,15."""
    s = f"{x:,.{decimales}f}"
    return s.replace(",", "_").replace(".", ",").replace("_", ".")


# --- Map geometry --------------------------------------------------------------------------

def _path(geom, tf) -> str:
    polys = getattr(geom, "geoms", [geom])
    out = []
    for p in polys:
        for ring in [p.exterior, *p.interiors]:
            pts = [tf(x, y) for x, y in ring.coords]
            out.append("M" + "L".join(f"{a},{b}" for a, b in pts) + "Z")
    return "".join(out)


def map_shapes(comarca_codes: set[str]) -> dict:
    """SVG paths of the districts and of the region outlines, in a 0..MAP_WIDTH box."""
    cs = [c for c in geo.comarcas() if c.code in comarca_codes]
    munis = geo.municipalities(tuple(config.REGIONS))
    regions = {}
    for m in munis:
        regions.setdefault(geo.PROVINCE_CCAA[m.province], []).append(m.geom)
    outlines = {k: unary_union(v).simplify(SIMPLIFY_M) for k, v in regions.items()}
    x0, y0, x1, y1 = unary_union(list(outlines.values())).bounds
    k = MAP_WIDTH / (x1 - x0)
    height = round((y1 - y0) * k)

    def tf(x, y):
        return round((x - x0) * k), round((y1 - y) * k)

    return {
        "height": height,
        "comarcas": {c.code: _path(c.geom.simplify(SIMPLIFY_M), tf) for c in cs},
        "regions": [_path(g, tf) for g in outlines.values()],
    }


# --- Data ----------------------------------------------------------------------------------

def _series(df: pd.DataFrame, key: str) -> dict:
    out: dict = {}
    for r in df.itertuples():
        out.setdefault(getattr(r, key), {})[int(r.year)] = [round(r.fallow_ha), round(r.cropland_ha)]
    return out


def build_data() -> dict:
    mun = aggregate.municipal()
    if mun.empty:
        raise SystemExit("no histograms yet; run `fallow hist` first")
    com = aggregate.by(mun, "comarca")
    prov = aggregate.by(mun, "province")
    reg = aggregate.by(mun, "ccaa")
    names = {c.code: c.name for c in geo.comarcas()}
    official = pd.read_csv(config.OFFICIAL_DIR / "anuario-provincias.csv", dtype={"province": str})
    pac = pd.read_csv(config.OFFICIAL_DIR / "aragon-pac-municipios.csv", dtype={"ine": str})
    pac_prov = (pac.assign(province=pac.ine.str[:2]).groupby(["year", "province"])
                [["rainfed_ha", "irrigated_ha"]].sum().sum(axis=1).round())
    prov_codes = sorted(set(prov.province) if not prov.empty else set())
    cal_path = config.VALIDATION_DIR / "calibration.json"
    return {
        "years": aggregate.years_available(),
        "rolling": config.ROLLING_YEARS,
        "comarcas": {c: {"name": names.get(c, c), "province": c[:2], "province_name": geo.PROVINCE_NAMES.get(c[:2], ""), "y": s}
                     for c, s in _series(com, "comarca").items()} if not com.empty else {},
        "provinces": {p: {"name": geo.PROVINCE_NAMES[p], "y": s.get(p, {}),
                          "anuario": {int(r.year): int(r.total_ha) for r in official[official.province == p].itertuples()},
                          "pac": {int(y): int(v) for (y, pp), v in pac_prov.items() if pp == p}}
                      for p, s in [(p, _series(prov, "province")) for p in prov_codes]},
        "regions": {r: {"name": config.REGIONS[r], "y": s} for r, s in _series(reg, "ccaa").items()}
        if not reg.empty else {},
        "spain": {int(r.year): int(r.total_ha) for r in official[official.province == "ES"].itertuples()},
        "policy": [{"year": y, "text": t} for y, t in config.POLICY_EVENTS],
        "calibration": json.loads(cal_path.read_text(encoding="utf-8")) if cal_path.exists() else {},
        "_com": com, "_mun": mun,
    }


# --- Page ----------------------------------------------------------------------------------

def _parametros(cal: dict) -> str:
    filas = [
        ("Imágenes", f"Sentinel-2 nivel 2A (reflectancia de superficie) vía Earth Search, a {config.RESOLUTION_M} m; "
                     f"escenas con menos del {config.MAX_SCENE_CLOUD:g} % de nubes"),
        ("Píxel válido", "suelo desnudo o vegetación según la clasificación de escena (SCL); fuera nubes, sombras, agua y nieve"),
        ("Primavera", f"marzo a mayo, mediana del NDVI de las fechas despejadas; al menos {config.MIN_SPRING_OBS} fechas despejadas"),
        ("Verano", f"junio a agosto, máximo del NDVI; al menos {config.MIN_SUMMER_OBS} fechas despejadas"),
        ("Barbecho", f"NDVI de primavera por debajo de {_es(config.SPRING_MAX_FALLOW, 2)} y de verano por debajo de "
                     f"{_es(config.SUMMER_MAX_FALLOW, 2)}"),
        ("Tierra de cultivo", "clase «cultivos» de ESA WorldCover 2021 (10 m, agregada a 20 m por moda)"),
        ("Unidades", "municipios (es-atlas, IGN) agregados a comarcas agrarias del MAPA"),
        ("Tendencia", f"media móvil de {config.ROLLING_YEARS} campañas; una campaña sola oscila con la lluvia de primavera"),
        ("Calibración", f"declaraciones de la PAC de Aragón por municipio, {', '.join(map(str, cal.get('fit_years', [])))}"
         if cal else "pendiente"),
    ]
    return '<table class="params">' + "".join(
        f"<tr><th>{escape(a)}</th><td>{escape(b)}</td></tr>" for a, b in filas) + "</table>"


def _validacion(cal: dict) -> str:
    if not cal or not cal.get("fit"):
        return '<p class="note">La validación se publicará con la primera campaña completa.</p>'
    filas = []
    for clave, nombre in (("fit", "Ajuste"), ("test", "Prueba")):
        s = cal.get(clave) or {}
        if not s:
            continue
        anios = ", ".join(map(str, cal.get(f"{clave}_years", [])))
        filas.append(f"<tr><td>{nombre} ({anios})</td><td class='num'>{s['n']}</td><td class='num'>{_es(s['r'], 2)}</td>"
                     f"<td class='num'>{'+' if s['bias_pct'] > 0 else ''}{_es(s['bias_pct'], 1)} %</td>"
                     f"<td class='num'>{_es(s['mae_pct'], 1)} %</td></tr>")
    tabla = ('<table class="params valid"><tr><th>Campañas</th><th class="num">Municipio-año</th>'
             '<th class="num">Correlación</th><th class="num">Sesgo</th><th class="num">Error absoluto</th></tr>'
             + "".join(filas) + "</table>")
    ch = cal.get("all_change") or {}
    cambio = (f"<p>Para las tendencias importa más el cambio que el nivel. De un año a otro, la variación del barbecho "
              f"estimado y la del declarado van en el mismo sentido en el {_es(ch['same_sign_pct'])} % de "
              f"{ch['n']} pares municipio-año (correlación {_es(ch['r'], 2)}).</p>") if ch else ""
    prov = cal.get("provinces") or {}
    provs = (f"<p>Por provincias, frente al Anuario de Estadística del MAPA, la estimación queda un "
             f"{_es(abs(prov['bias_pct']), 1)} % {'por encima' if prov['bias_pct'] > 0 else 'por debajo'} "
             f"en {prov['n']} provincia-año.</p>") if prov.get("n") else ""
    ratios = cal.get("ratio_by_year") or {}
    oscila = (f"<p>Lo que no se puede leer es el cambio de un solo año. Sumando un mismo grupo de municipios, el cociente "
              f"entre estimado y declarado varía un {_es(cal['wobble_pct'], 1)} % de una campaña a otra ("
              + ", ".join(f"{y}: {_es(float(r), 2)}" for y, r in sorted(ratios.items()))
              + "), mientras que lo declarado cambia un 2 a 5 % al año. La primavera lluviosa de 2020 en el Ebro, con "
              "más hierba en los barbechos, se nota en todas las variantes probadas. Por eso las tendencias del mapa "
              f"y de las gráficas usan la media de {config.ROLLING_YEARS} campañas. Para el efecto de un cambio de la PAC "
              "en un año concreto, la fuente buena es la propia declaración de la PAC.</p>") if cal.get("wobble_pct") else ""
    return tabla + cambio + oscila + provs


PLANTILLA = r"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
__FAVICON__
<title>Barbechos y aves esteparias</title>
<meta name="description" content="Superficie de barbecho por comarca agraria en Aragón y Castilla y León, medida cada campaña con Sentinel-2 y contrastada con la PAC y el Anuario del MAPA.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@500;600;700&family=Source+Serif+4:opsz,wght@8..60,400;8..60,600&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
__COMMON_CSS__
:root{--accent:__ACCENT__;--accent-dark:__ACCENT_DARK__}
:root{--q0:#efe6d8;--q1:#dcc3a1;--q2:#c4976a;--q3:#a0683f;--q4:#6e3f22;--nd:transparent;
  --sube:#2f7a55;--baja:#9f1d35;--oficial:#6b625c}
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){--q0:#3a2e25;--q1:#5c4330;--q2:#8a5d3b;--q3:#c08458;--q4:#efb98a;
    --sube:#62b88a;--baja:#f0708a;--oficial:#a69a91}
}
:root[data-theme="dark"]{--q0:#3a2e25;--q1:#5c4330;--q2:#8a5d3b;--q3:#c08458;--q4:#efb98a;
  --sube:#62b88a;--baja:#f0708a;--oficial:#a69a91}
.marca{display:flex;align-items:baseline;gap:14px;flex-wrap:wrap}
.marca .label{color:var(--muted);font-size:14px}
main{max-width:1440px;margin:0 auto;padding:0 16px;display:grid;grid-template-columns:minmax(0,1.3fr) minmax(320px,1fr);gap:20px;align-items:start}
.controles{display:flex;flex-wrap:wrap;gap:8px 16px;align-items:center;padding:10px 0;font-size:14px;color:var(--muted)}
.controles select{font:14px var(--font-text);background:var(--paper);color:var(--ink);border:1px solid var(--line);padding:4px 6px}
.mapa{background:var(--paper);border:1px solid var(--line);padding:8px}
.mapa svg{display:block;width:100%;height:auto}
.mapa path.c{stroke:var(--paper);stroke-width:.8;cursor:pointer}
.mapa path.c:hover,.mapa path.c.sel{stroke:var(--ink);stroke-width:2}
.mapa path.c.nd{fill:url(#rayas)}
.mapa path.r{fill:none;stroke:var(--ink);stroke-width:1.3;pointer-events:none}
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
.dos{display:grid;grid-template-columns:1fr 1fr;gap:28px}
.dos p{margin:0 0 10px;max-width:72ch}
.method{border-top:1.5px solid var(--ink);display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:28px;margin-top:24px}
.method p{margin:0 0 10px} .method ol{margin:0 0 10px;padding-left:1.4em} .method ol li{margin-bottom:8px}
.method > div > h3:first-child{margin-top:0}
.method table.params th{white-space:normal;width:30%}
.method table.valid th{width:auto}
.aviso{border-left:3px solid var(--accent);padding:2px 0 2px 12px}
.site-footer p{margin:0}
@media (max-width:900px){main,.method,.dos{grid-template-columns:1fr}}
</style>
</head>
<body>
<header class="site-header">
  <div class="marca">
    <h1>__LOGO__Barbechos <span>y aves esteparias</span></h1>
    <span class="label">Aragón y Castilla y León · Sentinel-2 · una cifra por campaña</span>
  </div>
  <p class="lede">El barbecho es la casa de la ganga, la ortega, el sisón y la avutarda: tierra de cultivo que un año descansa sin sembrar. Aquí se mide cuánto queda, comarca a comarca y campaña a campaña, con imágenes de satélite y reglas fijas, y se pone al lado de los cambios de la PAC que lo empujan arriba o abajo.</p>
  <div class="figures">
    <div><b>__ULTIMO__</b><span>hectáreas de barbecho al año, media __VENT__</span></div>
    <div><b>__CAMBIO__</b><span>frente a la media __VENT0__</span></div>
    <div><b>__CUOTA__</b><span>de la tierra de cultivo</span></div>
    <div><b>__NCOM__</b><span>comarcas agrarias</span></div>
  </div>
</header>

<main>
  <div>
    <div class="controles">
      <label>Campaña <select id="f-anio"></select></label>
      <label>Mostrar <select id="f-modo"><option value="cuota">Parte en barbecho</option><option value="cambio">Cambio de la media de 3 campañas</option></select></label>
    </div>
    <div class="mapa"><svg id="mapa" viewBox="0 0 __MAPW__ __MAPH__" role="img" aria-label="Mapa de comarcas agrarias coloreadas según el barbecho">
      <defs><pattern id="rayas" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="6" stroke="var(--line)" stroke-width="2"/></pattern></defs>
      <g id="comarcas"></g><g id="regiones"></g></svg></div>
    <div class="leyenda" id="leyenda" aria-label="Leyenda"></div>
  </div>
  <div class="panel card" id="panel" aria-live="polite"></div>
</main>

<section class="bloque" id="oficial">
  <h2>Frente a las cifras oficiales</h2>
  <p class="note">Barbecho estimado por provincia (línea de color) y el que da el Anuario de Estadística del MAPA (discontinua), en hectáreas. En Aragón, también lo declarado en la PAC (puntos grises). Las tres cifras no miden exactamente lo mismo: el Anuario incluye «otras tierras no ocupadas» y la PAC solo lo que se declara.</p>
  <div class="provincias" id="provincias"></div>
</section>

<section class="bloque" id="por-que">
  <h2>Por qué importa</h2>
  <div class="dos">
    <div>
      <p>Las aves esteparias son el grupo de aves que más rápido cae en España. Traba y Morales (2019, <a href="https://doi.org/10.1038/s41598-019-45854-0">Scientific Reports 9: 9473</a>) relacionaron sus índices de población del programa SACRE de SEO/BirdLife con la superficie de barbecho de 2002 a 2017. En esos años se perdió cerca de un millón cien mil hectáreas de barbecho, y esa superficie explica dos tercios de la variación de los índices de aves de campiña; en el sisón, tres cuartas partes.</p>
      <p>En el censo nacional de 2019, SEO/BirdLife estimó unas 7.500 gangas ibéricas y unas 7.000 ortegas (2.200 de ellas en Fuerteventura). En 2005 eran unas 9.500 y 10.500. El barbecho les da alimento, refugio y suelo para criar. Los cultivos tempranos y los herbicidas les quitan las tres cosas.</p>
      <p class="aviso">Esta página no publica la ubicación de ninguna especie. Las cifras son de superficie agraria por comarca; los datos de censo siguen siendo de quien los produce.</p>
    </div>
    <div>
      <h3 class="label">La PAC y el barbecho</h3>
      <ol class="politica" id="politica"></ol>
      <p class="note">Desde 2023 la PAC española paga un ecorrégimen por dejar «espacios de biodiversidad» (Real Decreto 1048/2022). Desde 2024 ya no es obligatorio dejar el 4 % de la tierra arable sin producir.</p>
    </div>
  </div>
</section>

<section class="method" id="metodo">
  <div>
    <h2>Cómo se calcula</h2>
    <ol>
      <li>Cada campaña se leen todas las imágenes de Sentinel-2 de marzo a agosto con menos nubes, a 20 metros. Se descarta cada píxel con nube, sombra, agua o nieve en esa fecha.</li>
      <li>Con el rojo y el infrarrojo cercano se calcula el NDVI, que sube con la vegetación verde. Para cada píxel se guarda el valor típico de la primavera (la mediana de marzo a mayo), cuando crecen los cereales de invierno, y el más alto del verano (junio a agosto), cuando verdean el girasol, el maíz y el regadío. La mediana aguanta mejor que el máximo una sola fecha con hierba tras la lluvia.</li>
      <li>Solo cuenta la tierra de cultivo según ESA WorldCover. Un píxel es barbecho si no verdea ni en primavera ni en verano: ni cereal ni cultivo de siembra tardía. El rastrojo de la cosecha anterior, las hierbas espontáneas y el suelo labrado quedan por debajo de los dos umbrales.</li>
      <li>Para cada municipio se guarda cuántos píxeles caen en cada combinación de valores de primavera y verano. Los umbrales se ajustaron con lo declarado como barbecho en la PAC de Aragón y se pueden cambiar sin volver a leer imágenes.</li>
      <li>Los municipios se suman en comarcas agrarias del Ministerio de Agricultura. Una comarca solo tiene cifra si todos sus municipios están completos.</li>
    </ol>
    <h3>Parámetros</h3>
    __PARAMETROS__
  </div>
  <div>
    <h3>Contraste con la PAC de Aragón</h3>
    <p>Gobierno de Aragón publica la superficie declarada en la PAC por municipio y cultivo. Se compara el barbecho estimado con el declarado («barbecho tradicional», «sin producción», «para especies melíferas» y «medioambiental») en municipios con al menos 50 hectáreas declaradas. Los umbrales se eligen en unas campañas y se prueban en otras.</p>
    __VALIDACION__
    <h3>Lo que hay que saber antes de citarlo</h3>
    <p class="aviso">Es una estimación por satélite, no una estadística oficial. Un año muy seco puede dejar el cereal tan bajo que pase por barbecho, y un barbecho con mucha hierba en primavera puede no contarse. Por eso cada campaña se contrasta con el Anuario.</p>
    <p class="aviso">Una campaña sola sube o baja un 10 % o más según haya llovido en primavera. Las tendencias se leen en la media de varias campañas (la línea de las gráficas), no en los puntos de cada año.</p>
    <p>La máscara de cultivo es de 2021. Las tierras que se roturaron o abandonaron después no cambian de clase, y los pastos que se labran de vez en cuando pueden quedar dentro o fuera. Los límites municipales están simplificados a unos 200 metros, lo que mueve unas decenas de hectáreas entre municipios vecinos pero no cambia los totales de comarca.</p>
    <h3>Datos abiertos</h3>
    <p><a href="barbecho-comarcas.csv">barbecho-comarcas.csv</a> y <a href="barbecho-municipios.csv">barbecho-municipios.csv</a> con las cifras por campaña · histogramas por municipio en el <a href="https://github.com/Asensio94/barbechos-esteparias/tree/main/data/hist">repositorio</a> · <a href="https://github.com/Asensio94/barbechos-esteparias">código</a>.</p>
  </div>
</section>

<footer class="site-footer">
  <p class="principle">Datos públicos, reglas a la vista y cada cifra enlazada a su fuente. Indicios, no veredictos.</p>
  <p>Imágenes Sentinel-2: Copernicus, © Unión Europea, vía Earth Search (Element 84) · Tierra de cultivo: ESA WorldCover 2021 v200, © ESA, CC BY 4.0 · Municipios: es-atlas, a partir de datos del Instituto Geográfico Nacional · Comarcas agrarias y Anuario de Estadística: Ministerio de Agricultura, Pesca y Alimentación · Superficie declarada en la PAC: Gobierno de Aragón.</p>
  <nav aria-label="Proyectos hermanos"><ul class="siblings">
    <li><a href="https://asensio94.github.io/observatorio-alegaciones/">Observatorio de alegaciones</a></li>
    <li><a href="https://asensio94.github.io/vigia-incendios/">Vigía de incendios</a></li>
    <li><a href="https://asensio94.github.io/centinela-natura/">Centinela Natura</a></li>
    <li><a href="https://asensio94.github.io/vigilancia-humedales/">Vigilancia de humedales</a></li>
    <li><a href="https://asensio94.github.io/sub-nocte/">Sub Nocte</a></li>
    <li><a href="https://asensio94.github.io/riesgo-tendidos-aves/">Riesgo de tendidos para aves</a></li>
    <li><a href="https://asensio94.github.io/grafo-promotores/">Grafo de promotores</a></li>
    <li><a href="https://asensio94.github.io/cartera-cotizadas/">Cartera de las cotizadas</a></li>
    <li><a href="https://asensio94.github.io/cuaderno-campo/">Cuaderno de campo</a></li>
    <li><a href="https://asensio94.github.io/acuiferos-francia/">Acuíferos de Francia</a></li>
    <li aria-current="page"><a href="https://asensio94.github.io/barbechos-esteparias/">Barbechos y aves esteparias</a></li>
  </ul></nav>
</footer>

<script>
const D = __DATOS__;
const num = (x,d=0) => x==null ? "—" : x.toLocaleString("es-ES",{minimumFractionDigits:d,maximumFractionDigits:d});
const pct = (a,b) => b ? 100*a/b : null;
const Y = D.years, Y0 = Y[0];
const selA = document.getElementById("f-anio"), selM = document.getElementById("f-modo");
for (const y of [...Y].reverse()) selA.add(new Option(`${y - 1}–${String(y).slice(2)}`, y));
let sel = null;

const ESC_CUOTA = [10,20,30,40], ESC_CAMBIO = [-25,-10,10,25];
function color(v, modo){
  if (v == null) return null;
  if (modo === "cuota") { const i = ESC_CUOTA.findIndex(t => v < t); return `var(--q${i < 0 ? 4 : i})`; }
  return v < ESC_CAMBIO[0] ? "var(--baja)" : v < ESC_CAMBIO[1] ? "color-mix(in srgb,var(--baja) 45%,var(--paper))"
       : v < ESC_CAMBIO[2] ? "var(--q0)" : v < ESC_CAMBIO[3] ? "color-mix(in srgb,var(--sube) 45%,var(--paper))" : "var(--sube)";
}
// Moving mean of the last D.rolling campaigns ending in y; null unless all of them exist.
function media(s, y){
  let f = 0, c = 0;
  for (let k = y - D.rolling + 1; k <= y; k++) { const v = s.y[k]; if (!v) return null; f += v[0]; c += v[1]; }
  return [f / D.rolling, c / D.rolling];
}
const YM = Y.filter(y => y - D.rolling + 1 >= Y0);  // campaigns with a full window
function valor(s, y, modo){
  if (modo === "cuota") { const v = s.y[y]; return v ? pct(v[0], v[1]) : null; }
  const m = media(s, y), m0 = YM.length ? media(s, YM[0]) : null;
  return m && m0 && m0[0] && y !== YM[0] ? 100*(m[0]/m0[0]-1) : null;
}

const gC = document.getElementById("comarcas");
gC.innerHTML = Object.entries(D.map.comarcas).map(([c,p]) => `<path class="c" data-c="${c}" d="${p}" tabindex="0"><title></title></path>`).join("");
document.getElementById("regiones").innerHTML = D.map.regions.map(p => `<path class="r" d="${p}"/>`).join("");

function pintar(){
  const y = +selA.value, modo = selM.value;
  for (const el of gC.children) {
    const s = D.comarcas[el.dataset.c], v = s ? valor(s, y, modo) : null, col = color(v, modo);
    el.classList.toggle("nd", col == null); el.style.fill = col || "";
    el.classList.toggle("sel", el.dataset.c === sel);
    el.firstChild.textContent = s ? `${s.name}: ${v == null ? "sin datos" : num(v,0) + " %"}` : "sin datos";
  }
  const lab = modo === "cuota" ? ["< 10 %","10–20 %","20–30 %","30–40 %","≥ 40 %"] : ["< −25 %","−25 a −10 %","±10 %","10 a 25 %","> 25 %"];
  const vals = modo === "cuota" ? [5,15,25,35,45] : [-30,-15,0,15,30];
  const ventana = y => `${y - D.rolling + 1}–${y}`;
  document.getElementById("leyenda").innerHTML = (modo === "cuota" ? `Parte de la tierra de cultivo en barbecho en ${y}: `
      : YM.length > 1 && y > YM[0] ? `Barbecho medio de ${ventana(y)} frente al de ${ventana(YM[0])}: `
      : `Hace falta la campaña ${(YM[0] || Y0 + D.rolling - 1) + 1} o posterior para comparar medias de ${D.rolling} campañas · `)
    + vals.map((v,i) => `<span><i style="background:${color(v, modo)}"></i>${lab[i]}</span>`).join("")
    + `<span><i style="background:url(#rayas);border:1px solid var(--line)"></i>sin datos</span>`;
}

function grafica(serie, extra){
  const W = 340, H = 150, L = 46, R = 8, T = 18, B = 22;
  const ys = Y.filter(y => serie[y] != null);
  const todos = [...ys.map(y => serie[y]), ...(extra||[]).flatMap(e => Object.values(e.d))];
  if (!todos.length) return "";
  const max = Math.max(...todos) * 1.1, min = 0;
  const x = y => L + (Y.length < 2 ? 0 : (y - Y[0]) / (Y[Y.length-1] - Y[0]) * (W - L - R));
  const yy = v => T + (1 - (v - min) / (max - min)) * (H - T - B);
  let s = `<svg viewBox="0 0 ${W} ${H}" role="img">`;
  for (const t of [0, .5, 1]) { const v = max/1.1*t; s += `<line class="eje" x1="${L}" x2="${W-R}" y1="${yy(v)}" y2="${yy(v)}"/><text x="${L-4}" y="${yy(v)+4}" text-anchor="end">${num(v/1000,0)} mil</text>`; }
  for (const p of D.policy) if (p.year >= Y[0] && p.year <= Y[Y.length-1]) s += `<line class="pol" x1="${x(p.year)}" x2="${x(p.year)}" y1="${T-6}" y2="${H-B}"/><text class="pol-n" x="${x(p.year)}" y="${T-8}" text-anchor="middle">${D.policy.indexOf(p)+1}</text>`;
  for (const y of Y) s += `<text x="${x(y)}" y="${H-6}" text-anchor="middle">${y}</text>`;
  for (const e of (extra||[])) {
    const ks = Object.keys(e.d).map(Number).filter(k => k >= Y[0] && k <= Y[Y.length-1]).sort();
    if (e.puntos) s += ks.map(k => `<circle cx="${x(k)}" cy="${yy(e.d[k])}" r="3" fill="var(--oficial)"><title>${e.n} ${k}: ${num(e.d[k])} ha</title></circle>`).join("");
    else if (ks.length > 1) s += `<polyline class="of" points="${ks.map(k => `${x(k)},${yy(e.d[k])}`).join(" ")}"><title>${e.n}</title></polyline>`;
  }
  // Single campaigns as faint dots; the moving mean as the line a trend is read on.
  s += ys.map(y => `<circle class="punto" cx="${x(y)}" cy="${yy(serie[y])}" r="2.6" opacity=".45"><title>Campaña ${y}: ${num(serie[y])} ha</title></circle>`).join("");
  const ms = Y.map(y => { let t = 0; for (let k = y - D.rolling + 1; k <= y; k++) { if (serie[k] == null) return null; t += serie[k]; } return [y, t / D.rolling]; }).filter(Boolean);
  if (ms.length > 1) s += `<polyline class="linea" points="${ms.map(([y, v]) => `${x(y)},${yy(v)}`).join(" ")}"/>`;
  s += ms.map(([y, v]) => `<circle class="punto" cx="${x(y)}" cy="${yy(v)}" r="3.4"><title>Media ${y - D.rolling + 1}–${y}: ${num(v)} ha</title></circle>`).join("");
  return s + "</svg>";
}

function panel(){
  const y = +selA.value, p = document.getElementById("panel");
  let s, titulo, sub;
  if (sel && D.comarcas[sel]) { s = D.comarcas[sel]; titulo = s.name; sub = `Comarca agraria · ${s.province_name}`; }
  else {
    const t = {}; for (const r of Object.values(D.regions)) for (const [yy, v] of Object.entries(r.y)) { t[yy] = t[yy] || [0,0]; t[yy][0] += v[0]; t[yy][1] += v[1]; }
    s = {y: t}; titulo = Object.values(D.regions).map(r => r.name).join(" y ") || "Sin datos todavía"; sub = "Pulse una comarca del mapa para ver la suya";
  }
  const v = s.y[y], m = media(s, y), m0 = YM.length ? media(s, YM[0]) : null;
  const serie = Object.fromEntries(Object.entries(s.y).map(([k, a]) => [k, a[0]]));
  p.innerHTML = `<div><h2>${titulo}</h2><p class="sub">${sub}</p></div>
    <dl class="cifras">
      <div><dt>Barbecho en ${y}</dt><dd>${v ? num(v[0]) + " ha" : "—"}</dd></div>
      <div><dt>Media ${y - D.rolling + 1}–${y}</dt><dd>${m ? num(m[0]) + " ha" : "—"}</dd></div>
      <div><dt>Parte del cultivo</dt><dd>${v ? num(pct(v[0], v[1]), 1) + " %" : "—"}</dd></div>
      <div><dt>Media frente a ${YM[0] ? (YM[0] - D.rolling + 1) + "–" + YM[0] : "—"}</dt><dd>${m && m0 && m0[0] && y !== YM[0] ? (m[0] >= m0[0] ? "+" : "") + num(100*(m[0]/m0[0]-1), 0).replace("-", "−") + " %" : "—"}</dd></div>
    </dl>
    <figure class="serie" style="margin:0">${grafica(serie)}<figcaption class="note">Hectáreas de barbecho. Puntos claros: cada campaña, que sube o baja con la lluvia de la primavera. Línea: media de ${D.rolling} campañas, la que vale para ver tendencias. Las líneas verticales numeradas son los cambios de la PAC de abajo.</figcaption></figure>
    <ol class="politica">${D.policy.map((p,i) => `<li><b>${i+1} · ${p.year}</b><span>${p.text}</span></li>`).join("")}</ol>
    ${sel ? '<button type="button" id="todo" class="badge" style="background:none;cursor:pointer">Ver el total</button>' : ""}`;
  document.getElementById("todo")?.addEventListener("click", () => { sel = null; pintar(); panel(); });
}

document.getElementById("politica").innerHTML = D.policy.map(p => `<li><b>${p.year}</b><span>${p.text}</span></li>`).join("");
document.getElementById("provincias").innerHTML = Object.values(D.provinces).filter(p => Object.keys(p.y).length).map(p => {
  const serie = Object.fromEntries(Object.entries(p.y).map(([k, a]) => [k, a[0]]));
  const extra = [{n: "Anuario", d: p.anuario}]; if (Object.keys(p.pac).length) extra.push({n: "PAC", d: p.pac, puntos: true});
  return `<div class="card"><h3>${p.name}</h3>${grafica(serie, extra)}</div>`;
}).join("") || '<p class="note">Aún no hay ninguna provincia completa.</p>';

function elegir(c){ sel = c; pintar(); panel(); }
gC.addEventListener("click", e => { const c = e.target.closest("path.c"); if (c) elegir(c.dataset.c); });
gC.addEventListener("keydown", e => { const c = e.target.closest("path.c"); if (c && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); elegir(c.dataset.c); } });
selA.addEventListener("change", () => { pintar(); panel(); });
selM.addEventListener("change", pintar);
pintar(); panel();
</script>
</body>
</html>
"""


def build() -> Path:
    d = build_data()
    com, mun = d.pop("_com"), d.pop("_mun")
    d["map"] = map_shapes(set(c.code for c in geo.comarcas() if c.province in
                              {p for p, cc in geo.PROVINCE_CCAA.items() if cc in config.REGIONS}))
    years = d["years"]
    last, first = years[-1], years[0]
    tot = {}
    for r in d["regions"].values():
        for y, (f, c) in r["y"].items():
            t = tot.setdefault(y, [0, 0])
            t[0] += f
            t[1] += c
    k = config.ROLLING_YEARS

    def media(y):  # mean of the k campaigns ending in y, only if all of them exist
        w = [tot.get(i) for i in range(y - k + 1, y + 1)]
        return None if None in w else [sum(v[0] for v in w) / k, sum(v[1] for v in w) / k]

    ult, pri = media(last), media(first + k - 1)
    cambio = f"{'+' if ult[0] >= pri[0] else '−'}{_es(abs(100 * (ult[0] / pri[0] - 1)))} %" \
        if ult and pri and pri[0] and last > first + k - 1 else "—"
    cal = d["calibration"]
    html = (PLANTILLA
            .replace("__LOGO__", LOGO_SVG)
            .replace("__FAVICON__", favicon_link(ACCENT, ACCENT_DARK))
            .replace("__COMMON_CSS__", COMMON_CSS)
            .replace("__ACCENT__", ACCENT).replace("__ACCENT_DARK__", ACCENT_DARK)
            .replace("__ULTIMO__", _es(ult[0]) if ult else "—")
            .replace("__VENT__", f"{last - k + 1}–{last}").replace("__VENT0__", f"{first}–{first + k - 1}")
            .replace("__CAMBIO__", cambio)
            .replace("__CUOTA__", f"{_es(100 * ult[0] / ult[1])} %" if ult and ult[1] else "—")
            .replace("__NCOM__", str(len(d["comarcas"])))
            .replace("__MAPW__", str(MAP_WIDTH)).replace("__MAPH__", str(d["map"]["height"]))
            .replace("__PARAMETROS__", _parametros(cal))
            .replace("__VALIDACION__", _validacion(cal))
            .replace("__DATOS__", json.dumps(d, ensure_ascii=False, separators=(",", ":"))))
    config.DOCS.mkdir(parents=True, exist_ok=True)
    out = config.DOCS / "index.html"
    out.write_text(html, encoding="utf-8")
    names = {c.code: c.name for c in geo.comarcas()}
    if not com.empty:
        com.assign(name=com.comarca.map(names)).round(0)[
            ["year", "comarca", "name", "fallow_ha", "cropland_ha", "nodata_ha"]].to_csv(
            config.DOCS / "barbecho-comarcas.csv", index=False)
    mun[mun.complete].round(0)[["year", "ine", "comarca", "fallow_ha", "cropland_ha", "nodata_ha"]].to_csv(
        config.DOCS / "barbecho-municipios.csv", index=False)
    return out
