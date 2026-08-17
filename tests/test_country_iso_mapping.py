"""Pruebas unitarias para el módulo ``src.country_iso_mapping``.

Valida el mapeo de códigos INE numéricos, códigos ISO alpha-2, nombres de país en español,
códigos ISO alpha-3 existentes y manejo de casos borde (nulos, valores desconocidos).
"""

from __future__ import annotations

from src.country_iso_mapping import (
    INE_CODE_TO_ISO3,
    ISO2_TO_ISO3,
    NAME_TO_ISO3,
    map_country_to_iso3,
)


class TestCountryIsoMapping:
    """Pruebas de mapeo de países a ISO 3166-1 alpha-3."""

    def test_numeric_ine_codes(self) -> None:
        assert map_country_to_iso3(249) == "USA"
        assert map_country_to_iso3(23) == "DEU"
        assert map_country_to_iso3(63) == "ARG"
        assert map_country_to_iso3(105) == "BRA"
        assert map_country_to_iso3(215) == "CHN"
        assert map_country_to_iso3(399) == "JPN"
        assert map_country_to_iso3(589) == "PER"
        assert map_country_to_iso3(169) == "COL"
        assert map_country_to_iso3(211) == "CHL"
        assert map_country_to_iso3(573) == "NLD"

    def test_numeric_ine_codes_as_string_and_float(self) -> None:
        assert map_country_to_iso3("249") == "USA"
        assert map_country_to_iso3("249.0") == "USA"
        assert map_country_to_iso3(249.0) == "USA"
        assert map_country_to_iso3("  23  ") == "DEU"

    def test_iso2_codes(self) -> None:
        assert map_country_to_iso3("US") == "USA"
        assert map_country_to_iso3("DE") == "DEU"
        assert map_country_to_iso3("AR") == "ARG"
        assert map_country_to_iso3("BR") == "BRA"
        assert map_country_to_iso3("CN") == "CHN"
        assert map_country_to_iso3("JP") == "JPN"
        assert map_country_to_iso3("PE") == "PER"
        assert map_country_to_iso3("FR") == "FRA"
        assert map_country_to_iso3("es") == "ESP"

    def test_country_names_spanish(self) -> None:
        assert map_country_to_iso3("ESTADOS UNIDOS") == "USA"
        assert map_country_to_iso3("Alemania") == "DEU"
        assert map_country_to_iso3("ARGENTINA") == "ARG"
        assert map_country_to_iso3("Brasil") == "BRA"
        assert map_country_to_iso3("China") == "CHN"
        assert map_country_to_iso3("Japón") == "JPN"
        assert map_country_to_iso3("JAPON") == "JPN"
        assert map_country_to_iso3("Perú") == "PER"
        assert map_country_to_iso3("España") == "ESP"
        assert map_country_to_iso3("ESPANA") == "ESP"
        assert map_country_to_iso3("Reino Unido") == "GBR"

    def test_complex_names_and_partial_match(self) -> None:
        assert map_country_to_iso3("CAMERUN, REPUBLICA UNIDA DEL") == "CMR"
        assert map_country_to_iso3("COREA (SUR), REPUBLICA DE") == "KOR"
        assert map_country_to_iso3("ESTADOS UNIDOS DE AMERICA") == "USA"

    def test_iso3_passthrough(self) -> None:
        assert map_country_to_iso3("USA") == "USA"
        assert map_country_to_iso3("DEU") == "DEU"
        assert map_country_to_iso3("ARG") == "ARG"
        assert map_country_to_iso3("BOL") == "BOL"

    def test_null_nan_and_unmapped(self) -> None:
        assert map_country_to_iso3(None) == "ZZZ"
        assert map_country_to_iso3(float("nan")) == "ZZZ"
        assert map_country_to_iso3("NaN") == "ZZZ"
        assert map_country_to_iso3("NULL") == "ZZZ"
        assert map_country_to_iso3("") == "ZZZ"
        assert map_country_to_iso3("XYZZY_UNKNOWN_COUNTRY") == "ZZZ"
        assert map_country_to_iso3(99999) == "ZZZ"
        assert map_country_to_iso3("UNKNOWN", default="OTR") == "OTR"

    def test_mapping_dictionaries_integrity(self) -> None:
        assert len(INE_CODE_TO_ISO3) > 50
        assert len(ISO2_TO_ISO3) > 40
        assert len(NAME_TO_ISO3) > 40
        for code, iso3 in INE_CODE_TO_ISO3.items():
            assert isinstance(code, int)
            assert len(iso3) == 3
            assert iso3.isupper()
