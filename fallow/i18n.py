"""Interface strings and number formats, one dictionary per language.

Each country's page is written in that country's language: the Spanish one in Spanish, the
French one in French. Data files (CSV, the JSON inside the page) stay in canonical,
language-independent values; only what a reader sees goes through here. Same pattern as
humedales/i18n.py in vigilancia-humedales.
"""
from __future__ import annotations

LANG_BY_COUNTRY = {"ES": "es", "FR": "fr"}

# French typography: a narrow no-break space as thousands separator and before «%».
NNBSP = " "


def lang_of(country: str) -> str:
    return LANG_BY_COUNTRY.get(country, "es")


def n(v: float, lang: str) -> str:
    """Integer with the thousands separator of the language: 46.709 / 46 709."""
    s = f"{v:,.0f}"
    return s.replace(",", "." if lang == "es" else NNBSP)


def d(v: float, lang: str, nd: int = 1) -> str:
    """Decimal with comma, in both languages: 2,7. Format the number, never the sentence."""
    s = f"{v:,.{nd}f}".replace(",", "_").replace(".", ",")
    return s.replace("_", "." if lang == "es" else NNBSP)


def p(pct: float, lang: str, nd: int = 1) -> str:
    """A value already in percent: 2,7 % / 2,7 %."""
    return d(pct, lang, nd) + (" %" if lang == "es" else NNBSP + "%")


# CAP changes drawn on the charts, by language. The years are campaigns (harvest years).
POLICY: dict[str, list[tuple[int, str]]] = {
    "es": [
        (2022, "Bruselas permite cultivar el barbecho de la PAC (Decisión 2022/484)"),
        (2023, "Exención del 4 % no productivo (Reglamento 2022/1317)"),
        (2024, "Se suprime la obligación del 4 % (Reglamento 2024/1468)"),
    ],
    "fr": [
        (2015, "Verdissement : la jachère compte comme surface d’intérêt écologique (SIE)"),
        (2022, "Bruxelles autorise la mise en culture des jachères SIE (décision 2022/484)"),
        (2023, "Nouvelle PAC : BCAE 8 (4 % non productif), suspendue pour 2023 (règlement 2022/1317)"),
        (2024, "Fin de l’obligation des 4 % non productifs (règlement 2024/1468)"),
    ],
}

# The box that sets the two countries side by side, on both pages.
SOURCES_BOX: dict[str, dict[str, str]] = {
    "es": {
        "title": "España y Francia: dos fuentes distintas",
        "body": (
            "<p>En España el barbecho se <b>estima con satélite</b>: es la tierra de cultivo que no "
            "verdea ni en primavera ni en verano, contada con reglas fijas sobre Sentinel-2. En "
            "Francia se <b>lee de la declaración de la PAC</b>: el Registro Parcelario Gráfico (RPG) "
            "publica cada año cada parcela con el cultivo que declaró el agricultor, y se suman las "
            "declaradas como barbecho («jachère»).</p>"
            "<p>Las dos cifras no son intercambiables. La española cuenta toda tierra que no se "
            "siembra en la campaña, se declare como se declare: también el barbecho de «año y vez» "
            "de los secanos. La francesa cuenta lo que se declara como barbecho, incluido el de "
            "larga duración (seis años o más), y no ve un rastrojo que se deja sin sembrar si se "
            "declara con otro cultivo. La francesa no tiene error de medida, pero depende de lo que "
            "la norma de la PAC llama barbecho cada año; la española no depende de la declaración, "
            "pero oscila con la lluvia. Compárense las tendencias de cada país, no los niveles "
            "entre países.</p>"),
        "link": '<a href="fr/" hreflang="fr" lang="fr">Version française : jachères et outarde canepetière en France</a>',
    },
    "fr": {
        "title": "France et Espagne : deux sources différentes",
        "body": (
            "<p>En France, la jachère se <b>lit dans la déclaration PAC</b> : le Registre parcellaire "
            "graphique (RPG) publie chaque année chaque parcelle avec la culture déclarée par "
            "l’exploitant, et l’on additionne celles déclarées en jachère. En Espagne, la même page "
            "l’<b>estime par satellite</b> : c’est la terre cultivée qui ne verdit ni au printemps "
            "ni en été, comptée avec des règles fixes sur les images Sentinel-2, faute de déclaration "
            "parcellaire publiée en données ouvertes pour tout le pays.</p>"
            "<p>Les deux chiffres ne sont pas interchangeables. L’espagnol compte toute terre "
            "cultivable qui n’est pas semée dans la campagne, quelle que soit sa déclaration, y "
            "compris la jachère traditionnelle d’« año y vez » (un an sur deux) des céréales en sec. "
            "Le français compte ce qui est déclaré en jachère, y compris la jachère longue (six ans "
            "ou plus), et ne voit pas un chaume laissé sans semis s’il est déclaré sous une autre "
            "culture. Le chiffre français n’a pas d’erreur de mesure, mais il dépend de ce que la "
            "PAC appelle jachère chaque année ; l’espagnol ne dépend pas de la déclaration, mais "
            "oscille avec la pluie. Comparez les tendances de chaque pays, pas les niveaux d’un pays "
            "à l’autre.</p>"),
        "link": '<a href="../" hreflang="es" lang="es">Versión en español: barbechos en Aragón y Castilla y León</a>',
    },
}
