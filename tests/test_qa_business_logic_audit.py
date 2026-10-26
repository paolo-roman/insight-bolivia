"""Auditoría de Control de Calidad (QA) y Lógica de Negocio — InsightBolivia.

Pruebas exhaustivas para verificar cálculos analíticos, reglas de negocio INE,
validaciones de calidad de datos (Great Expectations), indicadores del Banco Mundial
y casos de borde (bisiestos, divisiones por cero, nulos, valores negativos).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.country_iso_mapping import (
    map_country_to_iso3,
)
from src.extract_benchmark import (
    transform_benchmark_data,
)
from src.transform import (
    derive_temporal_columns,
    format_nandina,
    parse_flujo,
)
from src.validate import (
    build_comercio_exterior_suite,
    get_gx_context,
    validate_exchange_rate,
    validate_nandina_format,
    validate_non_negative,
    validate_transformed_data,
    validate_weight_consistency,
)
from streamlit_app.components.balanza_charts import (
    compute_balanza_kpis,
)
from streamlit_app.components.benchmark_charts import (
    compute_benchmark_kpis,
)


# ==============================================================================
# 1. Auditoría: Balanza Comercial y Signos (Exportaciones FOB - Importaciones CIF)
# ==============================================================================
class TestTradeBalanceBusinessLogic:
    """Verifica el cálculo de balanza comercial y convenciones de signo."""

    def test_trade_balance_surplus_and_deficit_calculation(self) -> None:
        """Verifica que balanza = FOB - CIF y determine superávit vs déficit."""
        df_surplus = pd.DataFrame({
            "fecha": ["2023-01-01"],
            "total_exportaciones_usd": [1500.0],
            "total_importaciones_usd": [1000.0],
            "total_peso_neto_exportaciones_kg": [5000.0],
            "total_peso_bruto_importaciones_kg": [6000.0],
        })
        kpis_surplus = compute_balanza_kpis(df_surplus)
        assert kpis_surplus["saldo_balanza_usd"] == 500.0
        assert kpis_surplus["es_superavit"] is True
        assert kpis_surplus["tasa_cobertura_pct"] == 150.0

        df_deficit = pd.DataFrame({
            "fecha": ["2023-01-01"],
            "total_exportaciones_usd": [800.0],
            "total_importaciones_usd": [1200.0],
            "total_peso_neto_exportaciones_kg": [4000.0],
            "total_peso_bruto_importaciones_kg": [5000.0],
        })
        kpis_deficit = compute_balanza_kpis(df_deficit)
        assert kpis_deficit["saldo_balanza_usd"] == -400.0
        assert kpis_deficit["es_superavit"] is False
        assert pytest.approx(kpis_deficit["tasa_cobertura_pct"], 0.01) == 66.67

    def test_trade_balance_zero_equilibrium(self) -> None:
        """Verifica el comportamiento cuando exportaciones == importaciones."""
        df_eq = pd.DataFrame({
            "fecha": ["2023-01-01"],
            "total_exportaciones_usd": [1000.0],
            "total_importaciones_usd": [1000.0],
            "total_peso_neto_exportaciones_kg": [1000.0],
            "total_peso_bruto_importaciones_kg": [1000.0],
        })
        kpis = compute_balanza_kpis(df_eq)
        assert kpis["saldo_balanza_usd"] == 0.0
        assert kpis["tasa_cobertura_pct"] == 100.0
        # Convención del código actual: saldo >= 0 se clasifica como True
        assert kpis["es_superavit"] is True

    def test_trade_balance_division_by_zero_handling(self) -> None:
        """Verifica que tasa de cobertura maneje división por cero cuando importaciones = 0."""
        df_zero_imp = pd.DataFrame({
            "fecha": ["2023-01-01"],
            "total_exportaciones_usd": [5000.0],
            "total_importaciones_usd": [0.0],
            "total_peso_neto_exportaciones_kg": [2000.0],
            "total_peso_bruto_importaciones_kg": [0.0],
        })
        kpis = compute_balanza_kpis(df_zero_imp)
        assert kpis["saldo_balanza_usd"] == 5000.0
        assert kpis["tasa_cobertura_pct"] == 0.0  # Protegido contra ZeroDivisionError

    def test_trade_balance_empty_dataframe(self) -> None:
        """Verifica que un DataFrame vacío no cause excepciones y retorne ceros."""
        kpis = compute_balanza_kpis(pd.DataFrame())
        assert kpis["total_exportaciones_usd"] == 0.0
        assert kpis["total_importaciones_usd"] == 0.0
        assert kpis["saldo_balanza_usd"] == 0.0
        assert kpis["tasa_cobertura_pct"] == 0.0


# ==============================================================================
# 2. Auditoría: NANDINA 10 Dígitos y Regex
# ==============================================================================
class TestNandinaBusinessLogic:
    """Verifica reglas RN-001 a RN-006 de codificación NANDINA."""

    def test_nandina_zero_padding_and_length(self) -> None:
        """Verifica que códigos numéricos o cortos se rellenen a exactamente 10 dígitos."""
        raw = pd.Series([901110000, "901110000", "0901110000", "901110000.0"])
        formatted = format_nandina(raw)
        assert all(len(code) == 10 for code in formatted)
        assert all(code == "0901110000" for code in formatted)

    def test_nandina_validation_numeric_regex(self) -> None:
        """Verifica que validate_nandina_format detecte cadenas inválidas."""
        valid_series = pd.Series(["0901110000", "2611110000", "0801220000"])
        assert validate_nandina_format(valid_series).passed is True

        invalid_len = pd.Series(["09011100", "2611110000"])
        res_len = validate_nandina_format(invalid_len)
        assert res_len.passed is False
        assert res_len.details["longitud_incorrecta"] == 1

        non_digits = pd.Series(["090111000A", "2611110000"])
        res_digits = validate_nandina_format(non_digits)
        assert res_digits.passed is False
        assert res_digits.details["no_numericos"] == 1

    def test_nandina_empty_and_null_edge_cases(self) -> None:
        """Verifica el comportamiento de format_nandina ante cadenas vacías y nulos."""
        s_empty = pd.Series([""])
        formatted_empty = format_nandina(s_empty)
        # Nota de hallazgo QA: Cadena vacía '' se rellena a 10 ceros ('0000000000')
        assert formatted_empty.iloc[0] == "0000000000"

        s_null = pd.Series([None, np.nan])
        formatted_null = format_nandina(s_null)
        assert pd.isna(formatted_null.iloc[0]) or formatted_null.iloc[0] == "0000000000"


# ==============================================================================
# 3. Auditoría: Diccionarios y Mapeos (Departamentos, Aduanas, Países)
# ==============================================================================
class TestDictionaryAlignments:
    """Verifica la alineación de dimensiones territoriales y aduaneras."""

    def test_country_mapping_ine_codes_and_defaults(self) -> None:
        """Verifica que los códigos INE de países principales se mapeen a ISO-3."""
        assert map_country_to_iso3(249) == "USA"
        assert map_country_to_iso3(23) == "DEU"
        assert map_country_to_iso3(63) == "ARG"
        assert map_country_to_iso3(105) == "BRA"
        assert map_country_to_iso3(215) == "CHN"
        assert map_country_to_iso3(589) == "PER"
        assert map_country_to_iso3(211) == "CHL"
        # Desconocidos deben retornar default 'ZZZ'
        assert map_country_to_iso3(99999) == "ZZZ"
        assert map_country_to_iso3(None) == "ZZZ"

    def test_country_mapping_substring_collision_risk(self) -> None:
        """Audita el riesgo de coincidencia por subcadena en map_country_to_iso3."""
        # Palabras comunes coinciden por subcadena: 'REPUBLICA' in 'CAMERUN REPUBLICA UNIDA DEL' -> CMR
        res = map_country_to_iso3("REPUBLICA")
        assert res in ("CMR", "CZE", "DOM", "KOR")

    def test_parse_flujo_exportaciones(self) -> None:
        """Verifica que FLUJO separe código numérico y descripción respetando RF-001/002."""
        s = pd.Series(["1 EXPORTACIONES", "2 REEXPORTACIONES", "3 EFECTOS PRESONALES"])
        res = parse_flujo(s)
        assert res["flujo_codigo"].tolist() == [1, 2, 3]
        assert res["flujo_descripcion"].iloc[2] == "EFECTOS PRESONALES"


# ==============================================================================
# 4. Auditoría: Coherencia Física y Valores No Negativos
# ==============================================================================
class TestPhysicalConsistencyAndNonNegativity:
    """Verifica coherencia física de pesos (RP-003) y no negatividad (RV-006)."""

    def test_weight_consistency_physical_law(self) -> None:
        """Verifica que peso bruto >= peso neto."""
        bruto_ok = pd.Series([100.0, 200.0, 300.0])
        neto_ok = pd.Series([90.0, 200.0, 250.0])
        assert validate_weight_consistency(bruto_ok, neto_ok).passed is True

        bruto_bad = pd.Series([80.0, 200.0])
        neto_bad = pd.Series([100.0, 200.0])
        res_bad = validate_weight_consistency(bruto_bad, neto_bad)
        assert res_bad.passed is False
        assert res_bad.details["violaciones"] == 1

    def test_monetary_values_non_negative(self) -> None:
        """Verifica que valores FOB y CIF rechacen números negativos."""
        valid_vals = pd.Series([0.0, 1500.50, 200000.0])
        assert validate_non_negative(valid_vals, column_name="FOB").passed is True

        negative_vals = pd.Series([100.0, -25.0, 50.0])
        res_neg = validate_non_negative(negative_vals, column_name="FOB")
        assert res_neg.passed is False
        assert res_neg.details["negativos"] == 1

    def test_exchange_rate_official_tolerance(self) -> None:
        """Verifica la relación de tipo de cambio BOB/USD con tolerancia."""
        cif_usd = pd.Series([100.0, 200.0])
        cif_bob_exact = pd.Series([696.0, 1392.0])
        assert validate_exchange_rate(cif_bob_exact, cif_usd).passed is True

        cif_bob_deviant = pd.Series([750.0, 1392.0])  # 7.50 excede 6.96 +- 0.10
        res_dev = validate_exchange_rate(cif_bob_deviant, cif_usd)
        assert res_dev.passed is False
        assert res_dev.details["outliers"] == 1

    def test_exchange_rate_handles_zeros_and_negatives(self) -> None:
        """Verifica que validate_exchange_rate maneje USD cero sin crash."""
        cif_usd = pd.Series([0.0, 0.0])
        cif_bob = pd.Series([100.0, 200.0])
        res = validate_exchange_rate(cif_bob, cif_usd)
        # Con usd=0, comparable es 0 y retorna passed=True con details vacío
        assert res.passed is True
        assert res.details == {}


# ==============================================================================
# 5. Auditoría: Great Expectations Suite (GX 1.x)
# ==============================================================================
class TestGreatExpectationsSuiteAudit:
    """Verifica la suite de validación GX y su cobertura de expectativas."""

    def test_suite_construction_and_rules_count(self) -> None:
        """Verifica que la suite construya las expectativas reglamentarias."""
        suite = build_comercio_exterior_suite("test_audit_suite")
        assert suite.name == "test_audit_suite"
        exp_names = [type(e).__name__ for e in suite.expectations]
        assert "ExpectColumnValuesToNotBeNull" in exp_names
        assert "ExpectColumnValuesToBeBetween" in exp_names
        assert "ExpectColumnValuesToMatchRegex" in exp_names
        assert "ExpectColumnPairValuesAToBeGreaterThanB" in exp_names

    def test_gx_detects_invalid_nandina_and_negative_fob(self) -> None:
        """Verifica que GX capture fallos en NANDINA y valores FOB negativos."""
        df_invalid = pd.DataFrame({
            "id_transaccion": [1],
            "fecha": ["2023-01-01"],
            "codigo_nandina": ["123"],  # Inválido: 3 dígitos
            "pais_iso": ["USA"],
            "id_departamento": [2],
            "id_via_transporte": [1],
            "id_aduana": [101],
            "tipo_operacion": ["EXPORTACION"],
            "valor_fob_usd": [-500.0],  # Inválido: negativo
            "valor_cif_usd": [0.0],
            "valor_fob_bob": [-3480.0],
            "peso_neto_kg": [100.0],
            "peso_bruto_kg": [120.0],
            "contenido_fino": [0.0],
            "anio": [2023],
            "mes": [1],
            "trimestre": [1],
        })
        ctx = get_gx_context(mode="ephemeral")
        report = validate_transformed_data(df_invalid, suite_name="test_audit_suite", context=ctx)
        assert report.success is False
        assert report.failed_expectations >= 2


# ==============================================================================
# 6. Auditoría: Banco Mundial y Casos Borde
# ==============================================================================
class TestWorldBankBenchmarkAudit:
    """Verifica la transformación y resiliencia del módulo extract_benchmark."""

    def test_benchmark_data_transformation_valid_and_missing(self) -> None:
        """Verifica que registros nulos se descarten y válidos se normalicen."""
        raw = [
            {"value": 43000000000.0, "series": "NY.GDP.MKTP.CD", "economy": "BOL", "time": "YR2022"},
            {"value": None, "series": "FP.CPI.TOTL.ZG", "economy": "PER", "time": "YR2022"},  # Missing
            {"value": 3.2, "series": "NY.GDP.MKTP.KD.ZG", "economy": "CHL", "time": "YR2021"},
        ]
        df = transform_benchmark_data(raw)
        assert len(df) == 2
        assert "BOL" in df["pais_iso"].values
        assert "CHL" in df["pais_iso"].values
        assert df["id_indicador_bm"].nunique() == 2

    def test_benchmark_kpis_calculation(self) -> None:
        """Verifica cálculo de KPIs de benchmark, rankings y diferenciales."""
        df = pd.DataFrame({
            "anio": [2023, 2023, 2022],
            "codigo_indicador": ["NY.GDP.MKTP.KD.ZG", "NY.GDP.MKTP.KD.ZG", "NY.GDP.MKTP.KD.ZG"],
            "pais_iso": ["BOL", "PER", "BOL"],
            "pais_nombre": ["Bolivia", "Perú", "Bolivia"],
            "valor": [3.1, 2.7, 3.5],
        })
        kpis = compute_benchmark_kpis(df, indicator_code="NY.GDP.MKTP.KD.ZG", target_year=2023)
        assert kpis["bolivia_value"] == 3.1
        assert pytest.approx(kpis["regional_avg"], 0.01) == 2.9
        assert kpis["bolivia_rank"] == 1
        assert pytest.approx(kpis["bolivia_yoy_delta"], 0.01) == -0.4

    def test_temporal_derivation_leap_year(self) -> None:
        """Verifica derivación temporal en años bisiestos (ej: 2024-02-29)."""
        df_leap = pd.DataFrame({"fecha": ["2024-02-29", "2020-02-29"]})
        derived = derive_temporal_columns(df_leap)
        assert derived["anio"].tolist() == [2024, 2020]
        assert derived["mes"].tolist() == [2, 2]
        assert str(derived["fecha"].iloc[0]) == "2024-02-01"
        assert str(derived["fecha"].iloc[1]) == "2020-02-01"
