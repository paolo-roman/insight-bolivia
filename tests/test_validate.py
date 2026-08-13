"""Pruebas unitarias para el módulo ``src.validate``.

Valida las funciones de validación de calidad de datos: formato NANDINA,
valores no negativos, coherencia de pesos, umbral de nulos y tipo de cambio.
"""

from __future__ import annotations

import pandas as pd

from src.validate import (
    ValidationResult,
    run_export_validations,
    run_import_validations,
    validate_exchange_rate,
    validate_nandina_format,
    validate_non_negative,
    validate_null_threshold,
    validate_weight_consistency,
)

# ---------------------------------------------------------------------------
# Tests: ValidationResult
# ---------------------------------------------------------------------------

class TestValidationResult:
    """Pruebas para el dataclass ``ValidationResult``."""

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


# ---------------------------------------------------------------------------
# Tests: validate_nandina_format
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


# ---------------------------------------------------------------------------
# Tests: validate_non_negative
# ---------------------------------------------------------------------------

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
        assert result.passed is True  # No numeric values to validate


# ---------------------------------------------------------------------------
# Tests: validate_weight_consistency
# ---------------------------------------------------------------------------

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
        neto = pd.Series([90, 80, 290])  # 50 < 80
        result = validate_weight_consistency(bruto, neto)
        assert result.passed is False
        assert result.details["violaciones"] == 1

    def test_handles_nulls(self) -> None:
        bruto = pd.Series([100, None, 300])
        neto = pd.Series([90, 200, None])
        result = validate_weight_consistency(bruto, neto)
        assert result.passed is True  # Only 1 comparable pair (100 >= 90)
        assert result.details["pares_comparados"] == 1

    def test_all_null_passes(self) -> None:
        bruto = pd.Series([None, None])
        neto = pd.Series([None, None])
        result = validate_weight_consistency(bruto, neto)
        assert result.passed is True


# ---------------------------------------------------------------------------
# Tests: validate_null_threshold
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Tests: validate_exchange_rate
# ---------------------------------------------------------------------------

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
        usd = pd.Series([1000])  # ratio = 10.0
        result = validate_exchange_rate(bob, usd)
        assert result.passed is False
        assert result.details["outliers"] == 1

    def test_handles_zero_usd(self) -> None:
        """USD = 0 debe excluirse del cálculo (evitar div by zero)."""
        bob = pd.Series([6960, 0])
        usd = pd.Series([1000, 0])
        result = validate_exchange_rate(bob, usd)
        assert result.passed is True
        assert result.details["pares_comparados"] == 1

    def test_custom_tolerance(self) -> None:
        bob = pd.Series([7100])
        usd = pd.Series([1000])  # ratio = 7.1
        # Default tolerance 0.10: would fail (7.1 > 7.06)
        result_default = validate_exchange_rate(bob, usd)
        assert result_default.passed is False
        # Wider tolerance: should pass
        result_wide = validate_exchange_rate(bob, usd, tolerance=0.20)
        assert result_wide.passed is True

    def test_all_null_passes(self) -> None:
        bob = pd.Series([None, None])
        usd = pd.Series([None, None])
        result = validate_exchange_rate(bob, usd)
        assert result.passed is True


# ---------------------------------------------------------------------------
# Tests: pipeline functions
# ---------------------------------------------------------------------------

class TestRunExportValidations:
    """Pruebas para ``run_export_validations``."""

    def test_returns_list_of_results(self) -> None:
        df = pd.DataFrame({
            "GESTION": [2021, 2021],
            "MES": [1, 2],
            "NANDINA": ["0901110000", "2611110000"],
            "PAIS": [23, 105],
            "VALOR": [125000, 890000],
            "KILBRU": [45000, 150000],
            "KILNET": [42000, 148000],
        })
        results = run_export_validations(df)
        assert isinstance(results, list)
        assert all(isinstance(r, ValidationResult) for r in results)
        assert len(results) >= 3  # nandina + valor + weight + null_threshold

    def test_detects_invalid_nandina(self) -> None:
        df = pd.DataFrame({
            "NANDINA": ["090111", "ABC"],
            "VALOR": [100, 200],
        })
        results = run_export_validations(df)
        nandina_results = [r for r in results if r.rule_name == "nandina_format"]
        assert len(nandina_results) == 1
        assert nandina_results[0].passed is False


class TestRunImportValidations:
    """Pruebas para ``run_import_validations``."""

    def test_returns_list_of_results(self) -> None:
        df = pd.DataFrame({
            "GESTION": [2021],
            "MES": [9],
            "NANDINA": ["0406100000"],
            "PAIS": [63],
            "FOB": [125],
            "FRO": [187],
            "ADU": [1301],
            "PAG": [130],
        })
        results = run_import_validations(df)
        assert isinstance(results, list)
        assert all(isinstance(r, ValidationResult) for r in results)
        # Should include: nandina + fob + cif + exchange_rate + null_threshold
        assert len(results) >= 4

    def test_validates_exchange_rate(self) -> None:
        df = pd.DataFrame({
            "NANDINA": ["0406100000"],
            "FOB": [125],
            "FRO": [187],
            "ADU": [1301],  # 1301/187 ≈ 6.96
        })
        results = run_import_validations(df)
        rate_results = [r for r in results if r.rule_name == "exchange_rate"]
        assert len(rate_results) == 1
