"""Módulo de mapeo de códigos y nombres de país a la norma ISO 3166-1 alpha-3.

Proporciona diccionarios y funciones para estandarizar códigos numéricos del INE,
códigos ISO alpha-2 y nombres comunes en español al formato internacional
ISO 3166-1 alpha-3 (3 letras mayúsculas).
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

# ---------------------------------------------------------------------------
# Mapeo de códigos numéricos del INE a ISO 3166-1 alpha-3
# ---------------------------------------------------------------------------
INE_CODE_TO_ISO3: dict[int, str] = {
    23: "DEU",   # ALEMANIA
    29: "BIH",   # BOSNIA Y HERZEGOVINA
    37: "AND",   # ANDORRA
    40: "AGO",   # ANGOLA
    53: "SAU",   # ARABIA SAUDITA
    59: "DZA",   # ARGELIA
    63: "ARG",   # ARGENTINA
    69: "AUS",   # AUSTRALIA
    72: "AUT",   # AUSTRIA
    74: "AZE",   # AZERBAIYAN
    77: "BHS",   # BAHAMAS
    80: "BHR",   # BAHREIN
    81: "BGD",   # BANGLADESH
    87: "BEL",   # BELGICA
    88: "BLZ",   # BELICE
    91: "BLR",   # BIELORRUSIA
    93: "MMR",   # MYANMAR
    97: "BOL",   # BOLIVIA
    105: "BRA",  # BRASIL
    108: "BRN",  # BRUNEI DARUSSALAM
    111: "BGR",  # BULGARIA
    127: "CPV",  # CABO VERDE
    141: "KHM",  # CAMBOYA
    145: "CMR",  # CAMERUN
    149: "CAN",  # CANADA
    169: "COL",  # COLOMBIA
    177: "COG",  # CONGO
    190: "KOR",  # COREA DEL SUR
    193: "CIV",  # COSTA DE MARFIL
    196: "CRI",  # COSTA RICA
    198: "HRV",  # CROACIA
    199: "CUB",  # CUBA
    211: "CHL",  # CHILE
    215: "CHN",  # CHINA
    218: "ECU",  # ECUADOR
    221: "EGY",  # EGIPTO
    232: "DNK",  # DINAMARCA
    239: "SLV",  # EL SALVADOR
    240: "ARE",  # EMIRATOS ARABES UNIDOS
    245: "ESP",  # ESPAÑA
    249: "USA",  # ESTADOS UNIDOS
    267: "PHL",  # FILIPINAS
    271: "FIN",  # FINLANDIA
    275: "FRA",  # FRANCIA
    301: "GRC",  # GRECIA
    317: "GTM",  # GUATEMALA
    345: "HND",  # HONDURAS
    351: "HKG",  # HONG KONG
    355: "HUN",  # HUNGRIA
    361: "IND",  # INDIA
    365: "IDN",  # INDONESIA
    372: "IRL",  # IRLANDA
    376: "ISR",  # ISRAEL
    386: "ITA",  # ITALIA
    392: "JPN",  # JAPON (código alternativo)
    399: "JPN",  # JAPON (código INE frecuente)
    493: "MEX",  # MEXICO
    528: "NZL",  # NUEVA ZELANDA
    573: "NLD",  # PAISES BAJOS (HOLANDA)
    576: "PAK",  # PAKISTAN
    580: "PAN",  # PANAMA
    586: "PRY",  # PARAGUAY
    589: "PER",  # PERU
    603: "POL",  # POLONIA
    605: "PRT",  # PORTUGAL
    611: "PRI",  # PUERTO RICO
    628: "GBR",  # REINO UNIDO
    644: "CZE",  # REPUBLICA CHECA
    647: "DOM",  # REPUBLICA DOMINICANA
    665: "RUS",  # RUSIA
    741: "SGP",  # SINGAPUR
    748: "ZAF",  # SUDAFRICA
    756: "SWE",  # SUECIA
    757: "CHE",  # SUIZA
    764: "TWN",  # TAIWAN
    767: "THA",  # TAILANDIA
    776: "TUR",  # TURQUIA
    800: "UKR",  # UCRANIA
    845: "URY",  # URUGUAY
    850: "VEN",  # VENEZUELA
    863: "VNM",  # VIETNAM
}

# ---------------------------------------------------------------------------
# Mapeo de códigos ISO alpha-2 a ISO 3166-1 alpha-3
# ---------------------------------------------------------------------------
ISO2_TO_ISO3: dict[str, str] = {
    "AE": "ARE", "AR": "ARG", "AT": "AUT", "AU": "AUS", "BE": "BEL",
    "BO": "BOL", "BR": "BRA", "CA": "CAN", "CH": "CHE", "CL": "CHL",
    "CN": "CHN", "CO": "COL", "CR": "CRI", "CU": "CUB", "CZ": "CZE",
    "DE": "DEU", "DK": "DNK", "DO": "DOM", "EC": "ECU", "ES": "ESP",
    "FI": "FIN", "FR": "FRA", "GB": "GBR", "GT": "GTM", "HK": "HKG",
    "HN": "HND", "ID": "IDN", "IE": "IRL", "IL": "ISR", "IN": "IND",
    "IT": "ITA", "JP": "JPN", "KR": "KOR", "MX": "MEX", "MY": "MYS",
    "NL": "NLD", "NO": "NOR", "NZ": "NZL", "PA": "PAN", "PE": "PER",
    "PH": "PHL", "PL": "POL", "PR": "PRI", "PT": "PRT", "PY": "PRY",
    "RU": "RUS", "SA": "SAU", "SE": "SWE", "SG": "SGP", "SV": "SLV",
    "TH": "THA", "TR": "TUR", "TW": "TWN", "UA": "UKR", "US": "USA",
    "UY": "URY", "VE": "VEN", "VN": "VNM", "ZA": "ZAF",
}

# ---------------------------------------------------------------------------
# Mapeo de nombres en español a ISO 3166-1 alpha-3 (claves normalizadas sin acentos)
# ---------------------------------------------------------------------------
NAME_TO_ISO3: dict[str, str] = {
    "ALEMANIA": "DEU",
    "ANDORRA": "AND",
    "ANGOLA": "AGO",
    "ARABIA SAUDITA": "SAU",
    "ARGELIA": "DZA",
    "ARGENTINA": "ARG",
    "AUSTRALIA": "AUS",
    "AUSTRIA": "AUT",
    "AZERBAIYAN": "AZE",
    "BAHAMAS": "BHS",
    "BAHREIN": "BHR",
    "BANGLADESH": "BGD",
    "BELGICA": "BEL",
    "BELICE": "BLZ",
    "BIELORRUSIA": "BLR",
    "BOLIVIA": "BOL",
    "BOSNIA Y HERZEGOVINA": "BIH",
    "BRASIL": "BRA",
    "BRUNEI": "BRN",
    "BULGARIA": "BGR",
    "CABO VERDE": "CPV",
    "CAMBOYA": "KHM",
    "CAMERUN": "CMR",
    "CAMERUN REPUBLICA UNIDA DEL": "CMR",
    "CANADA": "CAN",
    "CHILE": "CHL",
    "CHINA": "CHN",
    "COLOMBIA": "COL",
    "CONGO": "COG",
    "COREA": "KOR",
    "COREA SUR": "KOR",
    "COREA DEL SUR": "KOR",
    "COREA SUR REPUBLICA DE": "KOR",
    "COSTA DE MARFIL": "CIV",
    "COSTA RICA": "CRI",
    "CROACIA": "HRV",
    "CUBA": "CUB",
    "DINAMARCA": "DNK",
    "ECUADOR": "ECU",
    "EGIPTO": "EGY",
    "EL SALVADOR": "SLV",
    "EMIRATOS ARABES UNIDOS": "ARE",
    "ESPANA": "ESP",
    "ESTADOS UNIDOS": "USA",
    "FILIPINAS": "PHL",
    "FINLANDIA": "FIN",
    "FRANCIA": "FRA",
    "GRECIA": "GRC",
    "GUATEMALA": "GTM",
    "HOLANDA": "NLD",
    "HONDURAS": "HND",
    "HONG KONG": "HKG",
    "HUNGRIA": "HUN",
    "INDIA": "IND",
    "INDONESIA": "IDN",
    "IRLANDA": "IRL",
    "ISRAEL": "ISR",
    "ITALIA": "ITA",
    "JAPON": "JPN",
    "MEXICO": "MEX",
    "MYANMAR": "MMR",
    "NUEVA ZELANDA": "NZL",
    "PAISES BAJOS": "NLD",
    "PAKISTAN": "PAK",
    "PANAMA": "PAN",
    "PARAGUAY": "PRY",
    "PERU": "PER",
    "POLONIA": "POL",
    "PORTUGAL": "PRT",
    "PUERTO RICO": "PRI",
    "REINO UNIDO": "GBR",
    "REPUBLICA CHECA": "CZE",
    "REPUBLICA DOMINICANA": "DOM",
    "RUSIA": "RUS",
    "SINGAPUR": "SGP",
    "SUDAFRICA": "ZAF",
    "SUECIA": "SWE",
    "SUIZA": "CHE",
    "TAIWAN": "TWN",
    "TAILANDIA": "THA",
    "TURQUIA": "TUR",
    "UCRANIA": "UKR",
    "URUGUAY": "URY",
    "VENEZUELA": "VEN",
    "VIETNAM": "VNM",
}


def _clean_text_key(text: str) -> str:
    """Normaliza un texto eliminando acentos, puntuación y espacios extras."""
    nfkd = unicodedata.normalize("NFKD", text)
    without_accents = "".join(c for c in nfkd if not unicodedata.combining(c))
    normalized = without_accents.upper().replace("Ñ", "N")
    cleaned = re.sub(r"[^A-Z0-9\s]", " ", normalized)
    return re.sub(r"\s+", " ", cleaned).strip()


def map_country_to_iso3(
    val: Any,
    default: str = "ZZZ",
) -> str:
    """Mapea un código INE, código ISO-2 o nombre de país a ISO 3166-1 alpha-3.

    Parameters
    ----------
    val:
        Código numérico INE (int/str), código ISO-2, código ISO-3 o nombre del país.
    default:
        Valor retornado cuando no se encuentra coincidencia (por defecto ``"ZZZ"``).

    Returns
    -------
    str
        Código de país ISO 3166-1 alpha-3 de 3 caracteres en mayúsculas.
    """
    if val is None:
        return default

    # 1. Si es numérico o float que no sea NaN
    if isinstance(val, (int, float)) and not (isinstance(val, float) and (val != val)):
        int_val = int(val)
        if int_val in INE_CODE_TO_ISO3:
            return INE_CODE_TO_ISO3[int_val]

    str_val = str(val).strip()
    if not str_val or str_val.upper() in {"NAN", "NONE", "NULL", "<NA>"}:
        return default

    # Verificar si es string puramente numérico (posible float con .0)
    cleaned_num = re.sub(r"\.0$", "", str_val)
    if cleaned_num.isdigit():
        int_val = int(cleaned_num)
        if int_val in INE_CODE_TO_ISO3:
            return INE_CODE_TO_ISO3[int_val]

    clean_str = _clean_text_key(str_val)

    # 2. Si ya es un código ISO-3 de 3 letras
    if len(clean_str) == 3 and clean_str.isalpha():
        return clean_str

    # 3. Si es un código ISO-2 de 2 letras
    if len(clean_str) == 2 and clean_str in ISO2_TO_ISO3:
        return ISO2_TO_ISO3[clean_str]

    # 4. Búsqueda por nombre de país en español
    if clean_str in NAME_TO_ISO3:
        return NAME_TO_ISO3[clean_str]

    # Búsqueda parcial o por subcadena
    for name_key, iso3 in NAME_TO_ISO3.items():
        if name_key in clean_str or clean_str in name_key:
            return iso3

    return default
