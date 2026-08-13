"""Pruebas unitarias para el módulo ``src.transform``.

Valida normalización de columnas, formato NANDINA, parsing de FLUJO,
conversión numérica, reporte de nulos y comparación de encabezados.
"""

from __future__ import annotations

import pandas as pd
import pytest

from src.transform import (
    EXPORT_CANONICAL_COLUMNS,
    EXPORT_COLUMN_ALIASES,
    EXPORT_NUMERIC_COLUMNS,
    IMPORT_CANONICAL_COLUMNS,
    IMPORT_NUMERIC_COLUMNS,
    cast_numeric_columns,
    clean_export_dataframe,
    clean_import_dataframe,
    compare_headers_across_files,
    compute_null_report,
    format_nandina,
    normalize_column_names,
    parse_flujo,
)

# ---------------------------------------------------------------------------
# Tests: normalize_column_names
# ---------------------------------------------------------------------------

class TestNormalizeColumnNames:
    """Pruebas para ``normalize_column_names``."""

    def test_renames_viasal2_to_viasal(self) -> None:
        df = pd.DataFrame({"VIASAL2": [1], "DESVIA2": ["AEREA"], "GESTION": [2022]})
        result = normalize_column_names(df, operation_type="exportaciones")
        assert "VIASAL" in result.columns
        assert "DESVIA" in result.columns
        assert "VIASAL2" not in result.columns

    def test_renames_2026_variants(self) -> None:
        df = pd.DataFrame({"CUCIR3": ["0711"], "GCE": ["111"], "CIIU3": ["0113"]})
        result = normalize_column_names(df, operation_type="exportaciones")
        assert "CUCI3" in result.columns
        assert "GCE3" in result.columns
        assert "CIIUR3" in result.columns

    def test_strips_column_name_spaces(self) -> None:
        df = pd.DataFrame({"FLUJO ": ["1 EXPORTACIONES"], " PAIS ": [23]})
        result = normalize_column_names(df, operation_type="exportaciones")
        assert "FLUJO" in result.columns
        assert "PAIS" in result.columns

    def test_importaciones_unchanged(self) -> None:
        """Importaciones no tienen alias; las columnas no deben cambiar."""
        cols = ["GESTION", "MES", "NANDINA", "FOB"]
        df = pd.DataFrame({c: [1] for c in cols})
        result = normalize_column_names(df, operation_type="importaciones")
        assert list(result.columns) == cols

    def test_raises_for_invalid_operation_type(self) -> None:
        df = pd.DataFrame({"A": [1]})
        with pytest.raises(ValueError, match="operation_type"):
            normalize_column_names(df, operation_type="invalid")


# ---------------------------------------------------------------------------
# Tests: format_nandina
# ---------------------------------------------------------------------------

class TestFormatNandina:
    """Pruebas para ``format_nandina``."""

    def test_preserves_10_digit_string(self) -> None:
        s = pd.Series(["0901110000", "2611110000"])
        result = format_nandina(s)
        assert result.tolist() == ["0901110000", "2611110000"]

    def test_pads_short_values_with_zeros(self) -> None:
        s = pd.Series(["901110000"])  # 9 dígitos
        result = format_nandina(s)
        assert result.iloc[0] == "0901110000"

    def test_handles_numeric_input(self) -> None:
        """Cuando NANDINA viene como numérico (int o float)."""
        s = pd.Series([901110000, 2611110000])
        result = format_nandina(s)
        assert result.iloc[0] == "0901110000"
        assert result.iloc[1] == "2611110000"

    def test_handles_float_with_decimal(self) -> None:
        """Cuando NANDINA viene como float con .0."""
        s = pd.Series([901110000.0])
        result = format_nandina(s)
        assert result.iloc[0] == "0901110000"

    def test_strips_whitespace(self) -> None:
        s = pd.Series(["  0901110000  "])
        result = format_nandina(s)
        assert result.iloc[0] == "0901110000"

    def test_all_results_have_length_10(self) -> None:
        s = pd.Series(["0901110000", "27", "12345", "2611110000"])
        result = format_nandina(s)
        assert all(len(v) == 10 for v in result)


# ---------------------------------------------------------------------------
# Tests: parse_flujo
# ---------------------------------------------------------------------------

class TestParseFlujo:
    """Pruebas para ``parse_flujo``."""

    def test_parses_exportaciones(self) -> None:
        s = pd.Series(["1 EXPORTACIONES"])
        result = parse_flujo(s)
        assert result["flujo_codigo"].iloc[0] == 1
        assert result["flujo_descripcion"].iloc[0] == "EXPORTACIONES"

    def test_parses_all_three_values(self) -> None:
        s = pd.Series(["1 EXPORTACIONES", "2 REEXPORTACIONES", "3 EFECTOS PRESONALES"])
        result = parse_flujo(s)
        assert result["flujo_codigo"].tolist() == [1, 2, 3]
        assert result["flujo_descripcion"].tolist() == [
            "EXPORTACIONES",
            "REEXPORTACIONES",
            "EFECTOS PRESONALES",
        ]

    def test_returns_two_columns(self) -> None:
        s = pd.Series(["1 EXPORTACIONES"])
        result = parse_flujo(s)
        assert list(result.columns) == ["flujo_codigo", "flujo_descripcion"]


# ---------------------------------------------------------------------------
# Tests: cast_numeric_columns
# ---------------------------------------------------------------------------

class TestCastNumericColumns:
    """Pruebas para ``cast_numeric_columns``."""

    def test_converts_string_to_float(self) -> None:
        df = pd.DataFrame({"VALOR": ["125000.50", "890000"]})
        result = cast_numeric_columns(df, ["VALOR"])
        assert result["VALOR"].dtype == float

    def test_handles_non_numeric_as_nan(self) -> None:
        df = pd.DataFrame({"VALOR": ["125000", "N/A", "890000"]})
        result = cast_numeric_columns(df, ["VALOR"])
        assert result["VALOR"].isna().sum() == 1

    def test_skips_missing_columns(self) -> None:
        df = pd.DataFrame({"A": [1, 2]})
        result = cast_numeric_columns(df, ["NONEXISTENT"])
        assert list(result.columns) == ["A"]

    def test_does_not_modify_original(self) -> None:
        df = pd.DataFrame({"VALOR": ["100", "200"]})
        _ = cast_numeric_columns(df, ["VALOR"])
        assert pd.api.types.is_string_dtype(df["VALOR"])
        assert df["VALOR"].iloc[0] == "100"


# ---------------------------------------------------------------------------
# Tests: compute_null_report
# ---------------------------------------------------------------------------

class TestComputeNullReport:
    """Pruebas para ``compute_null_report``."""

    def test_reports_correct_percentages(self) -> None:
        df = pd.DataFrame({"A": [1, None, 3, None], "B": [1, 2, 3, 4]})
        report = compute_null_report(df)
        a_row = report[report["columna"] == "A"].iloc[0]
        assert a_row["nulos"] == 2
        assert a_row["porcentaje_nulos"] == 50.0

    def test_sorted_descending(self) -> None:
        df = pd.DataFrame({"A": [1, None], "B": [None, None], "C": [1, 2]})
        report = compute_null_report(df)
        assert report.iloc[0]["columna"] == "B"

    def test_empty_dataframe(self) -> None:
        df = pd.DataFrame({"A": pd.Series(dtype=float)})
        report = compute_null_report(df)
        assert len(report) == 1


# ---------------------------------------------------------------------------
# Tests: compare_headers_across_files
# ---------------------------------------------------------------------------

class TestCompareHeadersAcrossFiles:
    """Pruebas para ``compare_headers_across_files``."""

    def test_consistent_headers(self) -> None:
        headers = {
            "file1.xlsx": ["A", "B", "C"],
            "file2.xlsx": ["A", "B", "C"],
        }
        result = compare_headers_across_files(headers)
        assert result["all_consistent"] is True
        assert result["variations"] == {}

    def test_detects_differences(self) -> None:
        headers = {
            "2021.xlsx": ["VIASAL", "DESVIA", "NANDINA"],
            "2022.xlsx": ["VIASAL2", "DESVIA2", "NANDINA"],
        }
        result = compare_headers_across_files(headers)
        assert result["all_consistent"] is False
        assert "2022.xlsx" in result["variations"]
        assert "VIASAL2" in result["variations"]["2022.xlsx"]["columnas_nuevas"]
        assert "VIASAL" in result["variations"]["2022.xlsx"]["columnas_faltantes"]

    def test_empty_input(self) -> None:
        result = compare_headers_across_files({})
        assert result["all_consistent"] is True


# ---------------------------------------------------------------------------
# Tests: clean pipelines
# ---------------------------------------------------------------------------

class TestCleanExportDataframe:
    """Pruebas para ``clean_export_dataframe``."""

    def test_normalizes_and_formats(self) -> None:
        df = pd.DataFrame({
            "GESTION": ["2021"],
            "MES": ["1"],
            "NANDINA": ["901110000"],
            "VALOR": ["125000.50"],
            "KILBRU": ["45000"],
            "KILNET": ["42000"],
            "VIASAL2": ["9"],
            "DESVIA2": ["AEREA "],
        })
        result = clean_export_dataframe(df)
        # NANDINA padded
        assert result["NANDINA"].iloc[0] == "0901110000"
        # Columns renamed
        assert "VIASAL" in result.columns
        assert "DESVIA" in result.columns
        # Numeric conversion
        assert result["VALOR"].iloc[0] == 125000.50
        # Strip applied
        assert result["DESVIA"].iloc[0] == "AEREA"


class TestCleanImportDataframe:
    """Pruebas para ``clean_import_dataframe``."""

    def test_normalizes_and_formats(self) -> None:
        df = pd.DataFrame({
            "GESTION": ["2021"],
            "MES": ["9"],
            "NANDINA": ["406100000"],
            "FOB": ["125"],
            "FRO": ["187"],
            "ADU": ["1300"],
            "PAG": ["130"],
            "KILOS": ["27"],
        })
        result = clean_import_dataframe(df)
        # NANDINA padded
        assert result["NANDINA"].iloc[0] == "0406100000"
        # Numeric conversion
        assert result["FOB"].iloc[0] == 125.0
        assert result["FRO"].iloc[0] == 187.0


# ---------------------------------------------------------------------------
# Tests: constantes
# ---------------------------------------------------------------------------

class TestConstants:
    """Verifica que las constantes de esquema están bien definidas."""

    def test_export_canonical_columns_count(self) -> None:
        assert len(EXPORT_CANONICAL_COLUMNS) == 38

    def test_import_canonical_columns_count(self) -> None:
        assert len(IMPORT_CANONICAL_COLUMNS) == 29

    def test_nandina_in_both_schemas(self) -> None:
        assert "NANDINA" in EXPORT_CANONICAL_COLUMNS
        assert "NANDINA" in IMPORT_CANONICAL_COLUMNS

    def test_export_aliases_are_valid(self) -> None:
        """Los alias deben apuntar a columnas canónicas existentes."""
        for _old, new in EXPORT_COLUMN_ALIASES.items():
            assert new in EXPORT_CANONICAL_COLUMNS, f"Alias target {new!r} not in canonical"

    def test_export_numeric_columns_subset(self) -> None:
        for col in EXPORT_NUMERIC_COLUMNS:
            assert col in EXPORT_CANONICAL_COLUMNS, f"{col!r} not in canonical"

    def test_import_numeric_columns_subset(self) -> None:
        for col in IMPORT_NUMERIC_COLUMNS:
            assert col in IMPORT_CANONICAL_COLUMNS, f"{col!r} not in canonical"
