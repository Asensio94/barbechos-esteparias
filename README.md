# Barbechos y aves esteparias

Superficie de barbecho por comarca agraria en Aragón y Castilla y León, campaña a campaña, medida con imágenes Sentinel-2 y contrastada con la PAC y con el Anuario del Ministerio de Agricultura. El barbecho es el hábitat de la ganga, la ortega, el sisón y la avutarda, y su caída explica buena parte de la de estas aves.

> **Estado: aparcado (octubre de 2026).** La calibración con la PAC de Aragón muestra que el satélite acierta el nivel de barbecho y su reparto, pero no el cambio de un año a otro (ver *Contraste*). Para el efecto de la PAC año a año, la declaración es mejor fuente. El método se retomaría donde no hay dato oficial fino: comarcas de Castilla y León, ZEPA esteparias y tendencias de varios años. Solo está procesado el bloque de calibración del valle del Ebro (2018-2022). El flujo de Actions no tiene ejecución programada.
>
> **Francia (desde octubre de 2026): activo.** En las llanuras del sisón francés (outarde canepetière) el barbecho no se estima: se lee de la declaración de la PAC, parcela a parcela, en el Registro Parcelario Gráfico (RPG). Página en francés en [`docs/fr/`](https://asensio94.github.io/barbechos-esteparias/fr/), campañas 2015 en adelante, actualizada cada año por `francia.yml`. Ver la sección *Francia*.

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

## Francia

Francia es un segundo valor de país (`country = "FR"`), con el mismo repositorio y otra fuente. Lo español no cambia.

**Fuente distinta, a propósito.** En España no hay declaración de la PAC por parcela en datos abiertos para todo el país, y por eso el barbecho se estima con satélite. En Francia el IGN publica cada año el RPG: cada parcela declarada, con su cultivo, su grupo de cultivo y su superficie, anonimizada y con Licencia Abierta 2.0. Es mejor que cualquier estimación por satélite. Las dos cifras no miden lo mismo: la española cuenta toda tierra que no se siembra, también el barbecho de «año y vez»; la francesa cuenta lo declarado como barbecho, incluido el de seis años o más. Se comparan tendencias de cada país, no niveles entre países. La web lo explica en una caja que aparece en las dos versiones.

**Zonas.** Diez departamentos en tres zonas de estudio (`config.FR_AREAS`):

- Llanuras del Centro-Oeste: Charente, Charente-Maritime, Deux-Sèvres, Vienne y Vendée (llanuras de Niort, Mirebalais, Villefagnan y el sur de Vendée).
- Crau y llanuras del Languedoc: Bouches-du-Rhône, Gard y Hérault (Crau, Costières nîmoises y llanuras de Béziers y Fabrègues).
- Champaña cretácica: Marne y Aube.

**Cómo se calcula.**

1. `fallow fr-rpg` baja del WFS de la Géoplateforme (`data.geopf.fr`) las capas `RPG.{año}:parcelles_graphiques`, y `RPG.LATEST` para la última campaña, cuyo año se lee del título de la capa. Lo hace por teselas de 25 km en Lambert-93, a páginas de 5000 parcelas, y guarda cada tesela en `data/cache/rpg/` (reanudable). De cada parcela solo se quedan el grupo y el código de cultivo, la superficie y su punto interior.
2. Cada parcela va a la comuna (ADMIN EXPRESS COG 2025, una sola geografía para todas las campañas) que contiene su punto interior.
3. Barbecho = grupo de cultivo 11 («gel»): códigos J5M, J6P, J6S y JNO hasta 2022; JAC y JNO desde 2023. Tierra arable = los grupos que el RPG de 2024 marca como `TA`: 1 a 11, 14, 15, 16, 19, 24 y 25. El grupo 28 («divers») es mixto y se deja fuera.
4. Las comunas se suman en pequeñas regiones agrícolas (PRA) de Agreste, el equivalente de las comarcas agrarias. La tabla de 2017 se lleva a las comunas de hoy por el punto interior de cada comuna nueva.
5. ZPS: las de la directiva Aves (Natura 2000, AEMA) cuyo formulario cita el sisón (A128) o la ganga ibérica (A205), 28 en los diez departamentos. Se compara su parte de barbecho con la del resto de comunas de sus departamentos, fuera de toda ZPS esteparia. Solo a nivel de sitio: no se usan censos ni localizaciones.
6. Contraste por departamento con la Estadística Agrícola Anual (SAA) de Agreste, filas «jachères» y «terres arables».

**Contraste (2024).** Tierra arable del RPG frente a la SAA: entre −9 % (Hérault) y −1 % (Charente-Maritime, Deux-Sèvres y Vienne). Barbecho: muy cerca en el Centro-Oeste (Deux-Sèvres 4.678 frente a 4.395 ha, Vienne 20.775 frente a 21.230) y más alto en el Aube (10.626 frente a 7.500).

**Límites.**

- El RPG solo ve lo declarado a la PAC. La SAA, que lo cubre todo, sirve de control.
- La definición de barbecho la pone la norma de la PAC de cada año: superficie de interés ecológico desde 2015, cultivo permitido de esos barbechos en 2022 y nomenclatura nueva en 2023. Un salto de un año puede venir de una regla.
- La alfalfa, las praderas temporales y las cubiertas de las medidas agroambientales importan mucho al sisón, pero no son barbecho.
- Los *coussouls* de la Crau son pasto, no tierra arable. En la Crau, la parte de barbecho solo habla de las tierras cultivadas de alrededor.
- La última campaña (`RPG.LATEST`) aún puede corregirse, y por eso se relee cada año.

## Uso

```bash
pip install -r requirements.txt
python -m fallow official                      # Anuario por provincia y PAC de Aragón por municipio
python -m fallow hist --year 2024 --workers 3  # histogramas de una campaña (reanudable)
python -m fallow hist --year 2020 --region 02 --bbox -1.3 41.2 -0.1 41.95   # solo un bloque
python -m fallow calibrate                     # ajusta y contrasta los umbrales
python -m fallow web                           # docs/index.html y los CSV abiertos
python -m fallow fr-official                   # Francia: SAA de Agreste por departamento
python -m fallow fr-rpg                        # Francia: campañas del RPG que falten (y la última)
python -m fallow fr-rpg --year 2019 --refresh  # Francia: rehacer una campaña
python -m fallow fr-web                        # Francia: docs/fr/index.html y sus CSV
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
| `data/fr/communes-{año}.csv` | Francia: barbecho, tierra arable y superficie declarada (ha) por comuna (código INSEE), total y fuera de las ZPS esteparias |
| `data/fr/zps-{año}.csv` | Francia: lo mismo por ZPS (código de sitio Natura 2000) |
| `data/official/fr-saa-departements.csv` | Francia: barbecho y tierra arable por departamento, SAA de Agreste |
| `docs/index.html` | La web |
| `docs/fr/` | La web en francés y sus CSV (`jacheres-pra.csv`, `jacheres-communes.csv`, `jacheres-zps.csv`) |
| `docs/barbecho-comarcas.csv`, `docs/barbecho-municipios.csv` | Barbecho estimado, tierra de cultivo y superficie sin datos por campaña |

## Fuentes y licencias

- Sentinel-2 L2A: Copernicus, © Unión Europea, vía [Earth Search](https://earth-search.aws.element84.com/v1) (Element 84).
- [ESA WorldCover 2021 v200](https://esa-worldcover.org/), © ESA, CC BY 4.0.
- Municipios: [es-atlas](https://github.com/martgnz/es-atlas), a partir de datos del Instituto Geográfico Nacional.
- Comarcas agrarias y [Anuario de Estadística](https://www.mapa.gob.es/es/estadistica/temas/publicaciones/anuario-de-estadistica/): Ministerio de Agricultura, Pesca y Alimentación.
- [Superficie declarada en la PAC por municipio](https://www.aragon.es/-/estadisticas-agricolas): Gobierno de Aragón.
- Francia: [Registre parcellaire graphique](https://geoservices.ign.fr/rpg) (IGN y ASP) y [ADMIN EXPRESS](https://geoservices.ign.fr/adminexpress) (IGN), Licencia Abierta 2.0; [pequeñas regiones agrícolas y Estadística Agrícola Anual](https://agreste.agriculture.gouv.fr/) (Agreste); sitios Natura 2000 de la [Agencia Europea de Medio Ambiente](https://www.eea.europa.eu/).
- Contexto: Traba, J. y Morales, M. B. (2019). The decline of farmland birds in Spain is strongly associated to the loss of fallowland. *Scientific Reports* 9: 9473. <https://doi.org/10.1038/s41598-019-45854-0>

Código bajo licencia MIT. Las cifras propias (histogramas, estimaciones y validación), CC BY 4.0.

Forma parte de un conjunto de proyectos hermanos:
[Observatorio de alegaciones](https://asensio94.github.io/observatorio-alegaciones/) ·
[Vigía de incendios](https://asensio94.github.io/vigia-incendios/) ·
[Centinela Natura](https://asensio94.github.io/centinela-natura/) ·
[Vigilancia de humedales](https://asensio94.github.io/vigilancia-humedales/) ·
[Sub Nocte](https://asensio94.github.io/sub-nocte/) ·
[Riesgo de tendidos para aves](https://asensio94.github.io/riesgo-tendidos-aves/) ·
[Grafo de promotores](https://asensio94.github.io/grafo-promotores/) ·
[Cartera de las cotizadas](https://asensio94.github.io/cartera-cotizadas/) ·
[Cuaderno de campo](https://asensio94.github.io/cuaderno-campo/).
- Contexto en Francia: Bretagnolle, V. *et al.* (2011). Rapid recovery of a depleted population of Little Bustards *Tetrax tetrax* following provision of alfalfa through an agri-environment scheme. *Ibis* 153: 4-13. <https://doi.org/10.1111/j.1474-919X.2010.01092.x>
