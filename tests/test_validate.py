"""Pruebas unitarias para el módulo ``src.validate``.

Valida las funciones de calidad de datos tanto ligeras (Pandas) como basadas
en Great Expectations (GX 1.x), cubriendo escenarios válidos, inválidos,
tolerancia de nulos, excepciones DataQualityError y generación de Data Docs.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

import pandas as pd
import pytest

from src.transform import transform_to_fact
from src.validate import (
    DataQualityError,
    GXValidationReport,
    ValidationResult,
    build_comercio_exterior_suite,
    get_gx_context,
    run_export_validations,
    run_import_validations,
    save_comercio_exterior_suite,
    validate_exchange_rate,
    validate_nandina_format,
    validate_non_negative,
    validate_null_threshold,
    validate_transformed_data,
    validate_weight_consistency,
)

if TYPE_CHECKING:
    from pathlib import Path


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def valid_fact_df() -> pd.DataFrame:
    """Genera un DataFrame válido con el esquema analítico de la Tabla de Hechos."""
    return pd.DataFrame(
        {
            "id_transaccion": [1, 2, 3],
            "fecha": ["2023-01-01", "2023-02-01", "2023-03-01"],
            "codigo_nandina": ["0901110000", "2611110000", "0801220000"],
            "pais_iso": ["USA", "BRA", "ARG"],
            "id_departamento": [2, 3, 4],
            "id_via_transporte": [1, 2, 1],
            "id_aduana": [101, 201, 301],
            "tipo_operacion": ["EXPORTACION", "EXPORTACION", "IMPORTACION"],
            "valor_fob_usd": [15000.0, 32000.0, 500.0],
            "valor_cif_usd": [0.0, 0.0, 600.0],
            "valor_fob_bob": [104400.0, 222720.0, 3480.0],
            "peso_neto_kg": [1000.0, 2500.0, 50.0],
            "peso_bruto_kg": [1050.0, 2600.0, 55.0],
            "contenido_fino": [0.0, 120.0, 0.0],
            "anio": [2023, 2023, 2023],
            "mes": [1, 2, 3],
            "trimestre": [1, 1, 1],
        }
    )


# ---------------------------------------------------------------------------
# Tests: ValidationResult y DataQualityError
# ---------------------------------------------------------------------------


class TestValidationDataClasses:
    """Pruebas para los modelos de datos de validación."""

    def test_default_details_is_empty_dict(self) -> None:
        vr = ValidationResult(rule_name="test", passed=True, message="ok")
        assert vr.details == {}

    def test_stores_all_fields(self) -> None:
        vr = ValidationResult(
            rule_name="nandina_format",
            passed=False,
            message="error",
            details={"count": 5},
        )
        assert vr.rule_name == "nandina_format"
        assert vr.passed is False
        assert vr.details["count"] == 5

    def test_data_quality_error_is_exception(self) -> None:
        with pytest.raises(DataQualityError, match="Error crítico"):
            raise DataQualityError("Error crítico de calidad de datos")


# ---------------------------------------------------------------------------
# Tests: Validaciones Ligeras en Pandas
# ---------------------------------------------------------------------------


class TestValidateNandinaFormat:
    """Pruebas para ``validate_nandina_format``."""

    def test_valid_nandina_passes(self) -> None:
        s = pd.Series(["0901110000", "2611110000", "0801220000"])
        result = validate_nandina_format(s)
        assert result.passed is True

    def test_wrong_length_fails(self) -> None:
        s = pd.Series(["090111", "2611110000"])
        result = validate_nandina_format(s)
        assert result.passed is False
        assert result.details["longitud_incorrecta"] == 1

    def test_non_numeric_fails(self) -> None:
        s = pd.Series(["090111ABCD"])
        result = validate_nandina_format(s)
        assert result.passed is False
        assert result.details["no_numericos"] == 1

    def test_all_null_fails(self) -> None:
        s = pd.Series([None, None, None])
        result = validate_nandina_format(s)
        assert result.passed is False

    def test_custom_expected_length(self) -> None:
        s = pd.Series(["0901"])
        result = validate_nandina_format(s, expected_length=4)
        assert result.passed is True


class TestValidateNonNegative:
    """Pruebas para ``validate_non_negative``."""

    def test_all_positive_passes(self) -> None:
        s = pd.Series([100, 200, 0, 500])
        result = validate_non_negative(s, column_name="VALOR")
        assert result.passed is True

    def test_negative_value_fails(self) -> None:
        s = pd.Series([100, -50, 200])
        result = validate_non_negative(s, column_name="VALOR")
        assert result.passed is False
        assert result.details["negativos"] == 1

    def test_handles_string_input(self) -> None:
        s = pd.Series(["100", "200", "300"])
        result = validate_non_negative(s, column_name="VALOR")
        assert result.passed is True

    def test_empty_numeric_passes(self) -> None:
        s = pd.Series(["N/A", "invalid"])
        result = validate_non_negative(s, column_name="VALOR")
        assert result.passed is True


class TestValidateWeightConsistency:
    """Pruebas para ``validate_weight_consistency``."""

    def test_bruto_gte_neto_passes(self) -> None:
        bruto = pd.Series([100, 200, 300])
        neto = pd.Series([90, 180, 290])
        result = validate_weight_consistency(bruto, neto)
        assert result.passed is True

    def test_equal_weights_passes(self) -> None:
        bruto = pd.Series([100, 200])
        neto = pd.Series([100, 200])
        result = validate_weight_consistency(bruto, neto)
        assert result.passed is True

    def test_bruto_lt_neto_fails(self) -> None:
        bruto = pd.Series([100, 50, 300])
        neto = pd.Series([90, 80, 290])
        result = validate_weight_consistency(bruto, neto)
        assert result.passed is False
        assert result.details["violaciones"] == 1

    def test_handles_nulls(self) -> None:
        bruto = pd.Series([100, None, 300])
        neto = pd.Series([90, 200, None])
        result = validate_weight_consistency(bruto, neto)
        assert result.passed is True
        assert result.details["pares_comparados"] == 1

    def test_all_null_passes(self) -> None:
        bruto = pd.Series([None, None])
        neto = pd.Series([None, None])
        result = validate_weight_consistency(bruto, neto)
        assert result.passed is True


class TestValidateNullThreshold:
    """Pruebas para ``validate_null_threshold``."""

    def test_within_threshold_passes(self) -> None:
        df = pd.DataFrame({"A": [1, 2, 3, 4, 5], "B": [1, 2, 3, 4, None]})
        results = validate_null_threshold(df, max_null_percentage=25.0)
        assert all(r.passed for r in results)

    def test_exceeds_threshold_fails(self) -> None:
        df = pd.DataFrame({"A": [1, None, None, None, None]})
        results = validate_null_threshold(df, max_null_percentage=5.0)
        failed = [r for r in results if not r.passed]
        assert len(failed) >= 1

    def test_mandatory_column_with_nulls_fails(self) -> None:
        df = pd.DataFrame({"NANDINA": ["0901", None, "2611"]})
        results = validate_null_threshold(df, mandatory_columns=["NANDINA"])
        failed = [r for r in results if not r.passed]
        assert len(failed) >= 1
        assert any("obligatoria" in r.message for r in failed)

    def test_empty_dataframe_fails(self) -> None:
        df = pd.DataFrame({"A": pd.Series(dtype=float)})
        results = validate_null_threshold(df)
        assert any(not r.passed for r in results)


class TestValidateExchangeRate:
    """Pruebas para ``validate_exchange_rate``."""

    def test_correct_rate_passes(self) -> None:
        bob = pd.Series([6960, 13920, 34800])
        usd = pd.Series([1000, 2000, 5000])
        result = validate_exchange_rate(bob, usd)
        assert result.passed is True
        assert abs(result.details["ratio_media"] - 6.96) < 0.01

    def test_wrong_rate_fails(self) -> None:
        bob = pd.Series([10000])
        usd = pd.Series([1000])
        result = validate_exchange_rate(bob, usd)
        assert result.passed is False
        assert result.details["outliers"] == 1

    def test_handles_zero_usd(self) -> None:
        bob = pd.Series([6960, 0])
        usd = pd.Series([1000, 0])
        result = validate_exchange_rate(bob, usd)
        assert result.passed is True
        assert result.details["pares_comparados"] == 1

    def test_custom_tolerance(self) -> None:
        bob = pd.Series([7100])
        usd = pd.Series([1000])
        result_default = validate_exchange_rate(bob, usd)
        assert result_default.passed is False
        result_wide = validate_exchange_rate(bob, usd, tolerance=0.20)
        assert result_wide.passed is True

    def test_all_null_passes(self) -> None:
        bob = pd.Series([None, None])
        usd = pd.Series([None, None])
        result = validate_exchange_rate(bob, usd)
        assert result.passed is True


class TestPipelineLightweightValidations:
    """Pruebas para funciones combinadas de exportación e importación."""

    def test_run_export_validations(self) -> None:
        df = pd.DataFrame(
            {
                "GESTION": [2021, 2021],
                "MES": [1, 2],
                "NANDINA": ["0901110000", "2611110000"],
                "PAIS": [23, 105],
                "VALOR": [125000, 890000],
                "KILBRU": [45000, 150000],
                "KILNET": [42000, 148000],
            }
        )
        results = run_export_validations(df)
        assert isinstance(results, list)
        assert all(isinstance(r, ValidationResult) for r in results)
        assert len(results) >= 3

    def test_run_import_validations(self) -> None:
        df = pd.DataFrame(
            {
                "GESTION": [2021],
                "MES": [9],
                "NANDINA": ["0406100000"],
                "PAIS": [63],
                "FOB": [125],
                "FRO": [187],
                "ADU": [1301],
                "PAG": [130],
            }
        )
        results = run_import_validations(df)
        assert isinstance(results, list)
        assert all(isinstance(r, ValidationResult) for r in results)
        assert len(results) >= 4


# ---------------------------------------------------------------------------
# Tests: Great Expectations (GX 1.x)
# ---------------------------------------------------------------------------


class TestGreatExpectationsSuiteAndContext:
    """Pruebas para construcción de suites y resolución del DataContext."""

    def test_build_comercio_exterior_suite(self) -> None:
        suite = build_comercio_exterior_suite("test_suite")
        assert suite.name == "test_suite"
        assert len(suite.expectations) >= 15

    def test_get_gx_context_ephemeral(self) -> None:
        ctx = get_gx_context(mode="ephemeral")
        assert ctx is not None

    def test_get_gx_context_file_mode(self) -> None:
        ctx = get_gx_context()
        assert ctx is not None

    def test_get_gx_context_parent_resolution(self, tmp_path: Path) -> None:
        # Si la carpeta actual está dentro de un subdirectorio sin gx/, busca en el padre
        (tmp_path / "gx").mkdir()
        sub_dir = tmp_path / "src"
        sub_dir.mkdir()
        ctx = get_gx_context(project_root_dir=sub_dir, mode="file")
        assert ctx is not None

    def test_get_gx_context_fallback(self, tmp_path: Path) -> None:
        # Directorio sin carpeta gx/ fuerza fallback a ephemeral
        ctx = get_gx_context(project_root_dir=tmp_path / "non_existent")
        assert ctx is not None

    def test_save_comercio_exterior_suite(self) -> None:
        ctx = get_gx_context(mode="ephemeral")
        suite1 = save_comercio_exterior_suite(context=ctx, suite_name="custom_suite")
        assert suite1.name == "custom_suite"
        # Segunda llamada cubre branch si ya existe
        suite2 = save_comercio_exterior_suite(context=ctx, suite=suite1, suite_name="custom_suite")
        assert suite2.name == "custom_suite"


class TestValidateTransformedDataGX:
    """Pruebas para ``validate_transformed_data`` usando Great Expectations."""

    def test_valid_dataframe_passes_gx(self, valid_fact_df: pd.DataFrame) -> None:
        ctx = get_gx_context(mode="ephemeral")
        report = validate_transformed_data(valid_fact_df, context=ctx)
        assert isinstance(report, GXValidationReport)
        assert report.success is True
        assert report.failed_expectations == 0
        assert report.total_expectations >= 15
        assert "EXITOSA" in report.summary_message

    def test_repeated_validation_reuses_existing_definitions(self, valid_fact_df: pd.DataFrame) -> None:
        ctx = get_gx_context(mode="ephemeral")
        r1 = validate_transformed_data(valid_fact_df, context=ctx, suite_name="reuse_suite")
        assert r1.success is True
        # Segunda ejecución reutiliza las definiciones registradas
        r2 = validate_transformed_data(valid_fact_df, context=ctx, suite_name="reuse_suite")
        assert r2.success is True

    def test_null_in_primary_key_fails(self, valid_fact_df: pd.DataFrame) -> None:
        invalid_df = valid_fact_df.copy()
        invalid_df.loc[0, "fecha"] = None  # Clave primaria no tolera nulos
        ctx = get_gx_context(mode="ephemeral")
        report = validate_transformed_data(invalid_df, context=ctx)
        assert report.success is False
        assert report.failed_expectations >= 1
        assert len(report.failed_details) >= 1

    def test_negative_fob_fails(self, valid_fact_df: pd.DataFrame) -> None:
        invalid_df = valid_fact_df.copy()
        invalid_df.loc[0, "valor_fob_usd"] = -150.0
        ctx = get_gx_context(mode="ephemeral")
        report = validate_transformed_data(invalid_df, context=ctx)
        assert report.success is False
        assert any("valor_fob_usd" in str(d) for d in report.failed_details)

    def test_invalid_month_fails(self, valid_fact_df: pd.DataFrame) -> None:
        invalid_df = valid_fact_df.copy()
        invalid_df.loc[0, "mes"] = 13  # Fuera de rango 1-12
        ctx = get_gx_context(mode="ephemeral")
        report = validate_transformed_data(invalid_df, context=ctx)
        assert report.success is False
        assert any("mes" in str(d) for d in report.failed_details)

    def test_invalid_weight_consistency_fails(self, valid_fact_df: pd.DataFrame) -> None:
        invalid_df = valid_fact_df.copy()
        invalid_df.loc[0, "peso_bruto_kg"] = 50.0
        invalid_df.loc[0, "peso_neto_kg"] = 100.0  # bruto < neto
        ctx = get_gx_context(mode="ephemeral")
        report = validate_transformed_data(invalid_df, context=ctx)
        assert report.success is False
        assert any("peso_bruto_kg" in str(d) for d in report.failed_details)

    def test_invalid_nandina_regex_fails(self, valid_fact_df: pd.DataFrame) -> None:
        invalid_df = valid_fact_df.copy()
        invalid_df.loc[0, "codigo_nandina"] = "0901ABC"  # no numérico / longitud incorrecta
        ctx = get_gx_context(mode="ephemeral")
        report = validate_transformed_data(invalid_df, context=ctx)
        assert report.success is False

    def test_invalid_tipo_operacion_fails(self, valid_fact_df: pd.DataFrame) -> None:
        invalid_df = valid_fact_df.copy()
        invalid_df.loc[0, "tipo_operacion"] = "REEXPORTACION"  # no permitido en el set
        ctx = get_gx_context(mode="ephemeral")
        report = validate_transformed_data(invalid_df, context=ctx)
        assert report.success is False

    def test_raise_on_error_triggers_exception(self, valid_fact_df: pd.DataFrame) -> None:
        invalid_df = valid_fact_df.copy()
        invalid_df.loc[0, "valor_fob_usd"] = -10.0
        ctx = get_gx_context(mode="ephemeral")
        with pytest.raises(DataQualityError, match="Validación de Calidad GX FALLIDA"):
            validate_transformed_data(invalid_df, context=ctx, raise_on_error=True)

    def test_build_data_docs_invocation(self, valid_fact_df: pd.DataFrame) -> None:
        ctx = get_gx_context()
        report = validate_transformed_data(valid_fact_df, context=ctx, build_docs=True)
        assert report.data_docs_url is not None
        assert "data_docs" in str(report.data_docs_url).lower() or "http" in str(report.data_docs_url)

    def test_build_data_docs_error_handled_gracefully(self, valid_fact_df: pd.DataFrame) -> None:
        ctx = get_gx_context(mode="ephemeral")
        with patch.object(ctx, "build_data_docs", side_effect=RuntimeError("Data docs build failed")):
            report = validate_transformed_data(valid_fact_df, context=ctx, build_docs=True)
            assert report.data_docs_url is None

    def test_mostly_null_threshold_tolerance(self) -> None:
        records = []
        for i in range(20):
            records.append(
                {
                    "id_transaccion": i + 1,
                    "fecha": "2023-01-01",
                    "codigo_nandina": "0901110000",
                    "pais_iso": "USA",
                    "id_departamento": 2,
                    "id_via_transporte": 1,
                    "id_aduana": None if i == 0 else 101,  # 1/20 = 5% nulo (aprobado con mostly=0.95)
                    "tipo_operacion": "EXPORTACION",
                    "valor_fob_usd": 100.0,
                    "valor_cif_usd": 0.0,
                    "valor_fob_bob": 696.0,
                    "peso_neto_kg": 50.0,
                    "peso_bruto_kg": 60.0,
                    "contenido_fino": 0.0,
                    "anio": 2023,
                    "mes": 1,
                    "trimestre": 1,
                }
            )
        df_5_percent = pd.DataFrame(records)
        ctx = get_gx_context(mode="ephemeral")
        report = validate_transformed_data(df_5_percent, context=ctx)
        assert report.success is True

    def test_end_to_end_with_transform_to_fact(self) -> None:
        raw_export_df = pd.DataFrame(
            {
                "GESTION": [2023, 2023],
                "MES": [5, 5],
                "ADUDES": [101, 201],
                "DESADU": ["LA PAZ", "SANTA CRUZ"],
                "FLUJO": ["1 - EXPORTACIONES TRADICIONALES", "2 - EXPORTACIONES NO TRADICIONALES"],
                "NANDINA": ["0901110000", "2611110000"],
                "DESNAN": ["CAFÉ", "ESTAÑO"],
                "PAIS": [23, 105],
                "DESPAIS": ["ESTADOS UNIDOS", "BRASIL"],
                "DEPART": [2, 7],
                "VIASAL": [1, 2],
                "VALOR": [250000, 890000],
                "KILBRU": [45000, 150000],
                "KILNET": [42000, 148000],
            }
        )
        fact_df = transform_to_fact(raw_export_df, operation_type="exportaciones")
        ctx = get_gx_context(mode="ephemeral")
        report = validate_transformed_data(fact_df, context=ctx)
        assert report.success is True
