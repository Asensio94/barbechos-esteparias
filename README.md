# Barbechos y aves esteparias

Superficie de barbecho por comarca agraria en Aragón y Castilla y León, campaña a campaña, medida con imágenes Sentinel-2 y contrastada con la PAC y con el Anuario del Ministerio de Agricultura. El barbecho es el hábitat de la ganga, la ortega, el sisón y la avutarda, y su caída explica buena parte de la de estas aves.

> **Estado: aparcado (octubre de 2026).** La calibración con la PAC de Aragón muestra que el satélite acierta el nivel de barbecho y su reparto, pero no el cambio de un año a otro (ver *Contraste*). Para el efecto de la PAC año a año, la declaración es mejor fuente. El método se retomaría donde no hay dato oficial fino: comarcas de Castilla y León, ZEPA esteparias y tendencias de varios años. Solo está procesado el bloque de calibración del valle del Ebro (2018-2022). El flujo de Actions no tiene ejecución programada.

## Cómo funciona

1. Para cada campaña se leen las escenas Sentinel-2 L2A de marzo a agosto (Earth Search, menos del 60 % de nubes) en celdas de 20 × 20 km a 20 m. Cada fecha se queda solo con los píxeles despejados según la clasificación de escena (vegetación o suelo desnudo).
2. Si una fecha está dos veces en el catálogo (procesado original y reprocesado de 2022), se usa solo la versión más reciente. A las fechas con *baseline* 04.00 o posterior se les resta el desfase de 1000 que traen los números.
3. Por píxel se guardan la mediana del NDVI de primavera (marzo a mayo) y el máximo de verano (junio a agosto). Solo cuenta la tierra de cultivo de ESA WorldCover 2021.
4. Por municipio se guarda un histograma bidimensional: cuántos píxeles caen en cada par de intervalos de 0,05 de NDVI de primavera y de verano. Los píxeles con menos de 3 fechas despejadas en primavera o 2 en verano van aparte, como «sin datos».
5. Barbecho = NDVI de primavera por debajo de un umbral y de verano por debajo de otro: ni cereal de invierno ni cultivo de siembra tardía. Los umbrales se ajustan con lo declarado como barbecho en la PAC de Aragón. Como todo sale de los histogramas, cambiarlos no obliga a volver a leer imágenes.
6. Los municipios se suman en comarcas agrarias (MAPA) y en provincias. Una comarca o provincia solo tiene cifra en una campaña si todos sus municipios están completos.
7. Las tendencias de la web usan la media móvil de 3 campañas (`config.ROLLING_YEARS`). Cada campaña sola se muestra como punto, con aviso.

## Contraste

Se calibró sobre un bloque de 30 celdas del centro del valle del Ebro (entre Zaragoza, Monegros y Belchite), con 123 municipios enteros. La comparación es con el barbecho declarado en la PAC de Aragón por municipio («barbecho tradicional», «sin producción», «para especies melíferas» y «medioambiental»), solo en municipios con al menos 50 ha declaradas. Los umbrales se eligieron con 2018-2020 y se probaron con 2021-2022.

| Campañas | Municipio-año | Correlación | Sesgo | Error absoluto |
|---|---:|---:|---:|---:|
| Ajuste (2018-2020) | 293 | 0,89 | −8,2 % | 31,4 % |
| Prueba (2021-2022) | 206 | 0,94 | −3,4 % | 26,3 % |

**El nivel y el reparto en el territorio son fiables. El cambio de un año suelto no lo es.** En un mismo grupo de 84 municipios, el cociente entre estimado y declarado fue 0,94 en 2018, 1,07 en 2019, 0,77 en 2020, 0,92 en 2021 y 1,01 en 2022: oscila un 9,9 %. Lo declarado, en cambio, cambia un 2 a 5 % al año. De una campaña a la siguiente, estimado y declarado van en el mismo sentido en el 52 % de los municipios, lo mismo que si se echara a cara o cruz. La primavera lluviosa de 2020, con mucha hierba en los barbechos, deja esa campaña un 23 % por debajo con cualquier umbral.

Se probaron tres resúmenes de la primavera: máximo, percentil 75 y mediana. La mediana fue la mejor en nivel (26,8 % de error frente a 29,1 %) y en oscilación (10,7 % frente a 13,3 %), porque una sola fecha verde tras la lluvia no la mueve. También se probó un umbral que se adaptara a cada año buscando el valle entre barbecho y cereal; se descartó porque el valle salta entre 0,35 y 0,65. Con la oscilación que queda, la web publica como tendencia la **media de 3 campañas**. Para el efecto de un cambio de la PAC en un año concreto, la mejor fuente en Aragón es la propia declaración.

El resumen completo está en `data/validation/calibration.json`, y los pares municipio-año en `data/validation/aragon-municipios.csv`. Falta el contraste por provincia con el Anuario, que necesita provincias completas.

## Límites

- Una campaña sola oscila un 10 % o más con la lluvia de primavera. Para leer tendencias, medias de 3 campañas.
- La calibración es de un bloque de secano del valle del Ebro. En el páramo de Castilla y León, con otra fenología, no se ha comprobado municipio a municipio, solo por provincia con el Anuario.
- Es una estimación por satélite, no una estadística oficial. En un año muy seco el cereal puede quedarse tan bajo que pase por barbecho, y un barbecho con mucha hierba en primavera puede no contarse.
- La PAC, el Anuario y el satélite no miden lo mismo. El Anuario suma «otras tierras no ocupadas», y la PAC solo recoge lo declarado. La máscara de cultivo de WorldCover también tiene sus errores.
- La máscara de cultivo es de 2021: lo roturado o abandonado después no cambia de clase.
- Los límites municipales (es-atlas) están cuantizados a unos 190 m. Eso mueve unas decenas de hectáreas entre municipios vecinos, pero no los totales de comarca.
- Solo Aragón y Castilla y León. Añadir otra comunidad es añadir su código en `config.REGIONS`.

## Pendiente

- Primera pasada completa de las campañas 2018-2025 en las dos comunidades y contraste por provincia con el Anuario.
- Extremadura, Castilla-La Mancha y Andalucía, con contraste solo por provincia.
- Cruzar con las zonas de especial protección para las aves (ZEPA) esteparias, a nivel de comarca y sin localizaciones de censos.

## Uso

```bash
pip install -r requirements.txt
python -m fallow official                      # Anuario por provincia y PAC de Aragón por municipio
python -m fallow hist --year 2024 --workers 3  # histogramas de una campaña (reanudable)
python -m fallow hist --year 2020 --region 02 --bbox -1.3 41.2 -0.1 41.95   # solo un bloque
python -m fallow calibrate                     # ajusta y contrasta los umbrales
python -m fallow web                           # docs/index.html y los CSV abiertos
pytest
```

El flujo `campana.yml` hace todo esto cada 15 de septiembre, cuando ya ha terminado la campaña. También se puede lanzar a mano con el año y la comunidad. Si se corta por tiempo, al relanzarlo sigue desde la última celda guardada.

## Datos que se guardan

| Fichero | Contenido |
|---|---|
| `data/hist/{año}.csv.gz` | Histogramas por municipio: `ine`, intervalo de primavera `s`, de verano `u` (−1 = sin datos) y píxeles `n` de 20 m |
| `data/official/anuario-provincias.csv` | Barbecho y otras tierras no ocupadas por provincia (secano, regadío, total), Anuario MAPA, tabla 3.4 |
| `data/official/aragon-pac-municipios.csv` | Barbecho declarado en la PAC por municipio de Aragón (secano, regadío) y superficie total declarada |
| `data/validation/` | Rejilla de umbrales, pares municipio-año y resumen de la calibración |
| `docs/index.html` | La web |
| `docs/barbecho-comarcas.csv`, `docs/barbecho-municipios.csv` | Barbecho estimado, tierra de cultivo y superficie sin datos por campaña |

## Fuentes y licencias

- Sentinel-2 L2A: Copernicus, © Unión Europea, vía [Earth Search](https://earth-search.aws.element84.com/v1) (Element 84).
- [ESA WorldCover 2021 v200](https://esa-worldcover.org/), © ESA, CC BY 4.0.
- Municipios: [es-atlas](https://github.com/martgnz/es-atlas), a partir de datos del Instituto Geográfico Nacional.
- Comarcas agrarias y [Anuario de Estadística](https://www.mapa.gob.es/es/estadistica/temas/publicaciones/anuario-de-estadistica/): Ministerio de Agricultura, Pesca y Alimentación.
- [Superficie declarada en la PAC por municipio](https://www.aragon.es/-/estadisticas-agricolas): Gobierno de Aragón.
- Contexto: Traba, J. y Morales, M. B. (2019). The decline of farmland birds in Spain is strongly associated to the loss of fallowland. *Scientific Reports* 9: 9473. <https://doi.org/10.1038/s41598-019-45854-0>

Código bajo licencia MIT. Las cifras propias (histogramas, estimaciones y validación), CC BY 4.0.

Forma parte de [Terra Aperta](https://asensio94.github.io/terra-aperta/), un conjunto de proyectos hermanos de datos abiertos sobre naturaleza:
[Sub Nocte](https://github.com/Asensio94/sub-nocte) ·
[Vigía de incendios](https://github.com/Asensio94/vigia-incendios) ·
[Centinela Natura](https://github.com/Asensio94/centinela-natura) ·
[Estado de las IBA](https://github.com/Asensio94/estado-iba) ·
[Riesgo de tendidos para aves](https://github.com/Asensio94/riesgo-tendidos-aves) ·
[Observatorio de alegaciones](https://github.com/Asensio94/observatorio-alegaciones) ·
[Grafo de promotores](https://github.com/Asensio94/grafo-promotores) ·
[Vigilancia de humedales](https://github.com/Asensio94/vigilancia-humedales) ·
[Caudal ecológico](https://github.com/Asensio94/caudal-ecologico) ·
[Acuíferos de Francia](https://github.com/Asensio94/acuiferos-francia) ·
[Depuración y baño](https://github.com/Asensio94/depuracion-y-bano) ·
[Construir en zona inundable](https://github.com/Asensio94/zona-inundable).
