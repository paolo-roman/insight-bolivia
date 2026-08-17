"""Pruebas unitarias para el módulo ``src.transform``.

Valida lectura de formatos heterogéneos (Excel, CSV, DBF), normalización de nombres snake_case,
formato NANDINA, parsing de FLUJO, conversión numérica, cálculo de columnas derivadas,
conversión BOB/USD, deduplicación y transformación hacia Staging y Fact en BigQuery.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.transform import (
    EXPORT_CANONICAL_COLUMNS,
    EXPORT_COLUMN_ALIASES,
    EXPORT_INE_TO_STAGING_MAP,
    EXPORT_NUMERIC_COLUMNS,
    IMPORT_CANONICAL_COLUMNS,
    IMPORT_INE_TO_STAGING_MAP,
    IMPORT_NUMERIC_COLUMNS,
    OFFICIAL_EXCHANGE_RATE_BOB_USD,
    cast_numeric_columns,
    clean_export_dataframe,
    clean_import_dataframe,
    compare_headers_across_files,
    compute_null_report,
    convert_fob_bob,
    deduplicate_records,
    derive_temporal_columns,
    format_nandina,
    normalize_column_names,
    parse_flujo,
    read_raw_file,
    to_snake_case,
    transform_to_fact,
    transform_to_staging,
)

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


# ---------------------------------------------------------------------------
# Tests: read_raw_file
# ---------------------------------------------------------------------------
class TestReadRawFile:
    """Pruebas para ``read_raw_file`` con múltiples formatos."""

    def test_reads_excel_file(self) -> None:
        path = FIXTURES_DIR / "sample_exportaciones.xlsx"
        df = read_raw_file(path)
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 5
        assert "fecha" in df.columns or "VALOR" in df.columns

    def test_reads_excel_all_sheets_dict_return(self) -> None:
        path = FIXTURES_DIR / "sample_exportaciones.xlsx"
        df = read_raw_file(path, sheet_name=None)
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 5

    def test_reads_csv_utf8_file(self) -> None:
        path = FIXTURES_DIR / "sample_importaciones.csv"
        df = read_raw_file(path)
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 5

    def test_reads_csv_latin1_with_autodetection(self) -> None:
        path = FIXTURES_DIR / "sample_bad_encoding.csv"
        df = read_raw_file(path)
        assert isinstance(df, pd.DataFrame)
        descriptions: list[str] = [str(x) for x in df["descripcion_nandina"]]
        text_content = " ".join(descriptions)
        assert "Caf" in text_content or "crust" in text_content

    def test_reads_dbf_mocked(self) -> None:
        fake_records = [{"GESTION": 2021, "MES": 1, "VALOR": 100.0}]
        mock_dbf = MagicMock()
        mock_dbf.__iter__.return_value = fake_records

        with patch("dbfread.DBF", return_value=mock_dbf), patch("pathlib.Path.exists", return_value=True):
            df = read_raw_file("fake_data.dbf")
            assert isinstance(df, pd.DataFrame)
            assert len(df) == 1
            assert df.iloc[0]["VALOR"] == 100.0

    def test_raises_file_not_found(self) -> None:
        with pytest.raises(FileNotFoundError, match="Archivo no encontrado"):
            read_raw_file("non_existent_file_xyz_123.xlsx")

    def test_raises_unsupported_extension(self, tmp_path: Path) -> None:
        bad_file = tmp_path / "test.json"
        bad_file.write_text("{}", encoding="utf-8")
        with pytest.raises(ValueError, match="Extensión de archivo no soportada"):
            read_raw_file(bad_file)


# ---------------------------------------------------------------------------
# Tests: to_snake_case
# ---------------------------------------------------------------------------
class TestToSnakeCase:
    """Pruebas para ``to_snake_case``."""

    def test_converts_spaces_and_caps(self) -> None:
        assert to_snake_case("DESADU") == "desadu"
        assert to_snake_case("Codigo Nandina") == "codigo_nandina"
        assert to_snake_case("valorFobUsd") == "valor_fob_usd"
        assert to_snake_case("  GESTION - MES  ") == "gestion_mes"
        assert to_snake_case("PAIS_ISO_3") == "pais_iso_3"


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
        s = pd.Series(["901110000"])
        result = format_nandina(s)
        assert result.iloc[0] == "0901110000"

    def test_handles_numeric_input(self) -> None:
        s = pd.Series([901110000, 2611110000])
        result = format_nandina(s)
        assert result.iloc[0] == "0901110000"
        assert result.iloc[1] == "2611110000"

    def test_handles_float_with_decimal(self) -> None:
        s = pd.Series([901110000.0])
        result = format_nandina(s)
        assert result.iloc[0] == "0901110000"

    def test_strips_whitespace(self) -> None:
        s = pd.Series(["  0901110000  "])
        result = format_nandina(s)
        assert result.iloc[0] == "0901110000"


# ---------------------------------------------------------------------------
# Tests: parse_flujo
# ---------------------------------------------------------------------------
class TestParseFlujo:
    """Pruebas para ``parse_flujo``."""

    def test_parses_exportaciones(self) -> None:
        s = pd.Series(["1 EXPORTACIONES", "2 REEXPORTACIONES", "3 EFECTOS PRESONALES"])
        result = parse_flujo(s)
        assert result["flujo_codigo"].tolist() == [1, 2, 3]
        assert result["flujo_descripcion"].tolist() == [
            "EXPORTACIONES",
            "REEXPORTACIONES",
            "EFECTOS PRESONALES",
        ]

    def test_single_token_fallback(self) -> None:
        s = pd.Series(["EXPORTACION"])
        result = parse_flujo(s)
        assert pd.isna(result["flujo_codigo"].iloc[0])
        assert result["flujo_descripcion"].iloc[0] == "EXPORTACION"


# ---------------------------------------------------------------------------
# Tests: cast_numeric_columns & compute_null_report & compare_headers
# ---------------------------------------------------------------------------
class TestCastNumericAndReports:
    """Pruebas para utilidades numéricas y reportes de nulos/encabezados."""

    def test_cast_numeric_columns(self) -> None:
        df = pd.DataFrame({"VALOR": ["125000.50", "N/A", "890000"]})
        result = cast_numeric_columns(df, ["VALOR"])
        assert result["VALOR"].dtype == float
        assert result["VALOR"].isna().sum() == 1

    def test_compute_null_report(self) -> None:
        df = pd.DataFrame({"A": [1, None, 3, None], "B": [1, 2, 3, 4]})
        report = compute_null_report(df)
        assert report.iloc[0]["columna"] == "A"
        assert report.iloc[0]["porcentaje_nulos"] == 50.0

    def test_compute_null_report_empty(self) -> None:
        df = pd.DataFrame({"A": pd.Series(dtype=float)})
        report = compute_null_report(df)
        assert len(report) == 1

    def test_compare_headers_across_files(self) -> None:
        headers = {
            "2021.xlsx": ["VIASAL", "DESVIA"],
            "2022.xlsx": ["VIASAL2", "DESVIA"],
        }
        res = compare_headers_across_files(headers)
        assert res["all_consistent"] is False
        assert "VIASAL2" in res["variations"]["2022.xlsx"]["columnas_nuevas"]

    def test_compare_headers_empty(self) -> None:
        res = compare_headers_across_files({})
        assert res["all_consistent"] is True


# ---------------------------------------------------------------------------
# Tests: derive_temporal_columns, convert_fob_bob, deduplicate_records
# ---------------------------------------------------------------------------
class TestDerivedCalculations:
    """Pruebas para cálculos temporales, tipo de cambio y deduplicación."""

    def test_derive_temporal_columns_from_gestion_mes(self) -> None:
        df = pd.DataFrame({
            "gestion": [2021, 2021, 2021, 2021],
            "mes": [2, 5, 8, 11],
        })
        result = derive_temporal_columns(df)
        assert result["anio"].tolist() == [2021, 2021, 2021, 2021]
        assert result["mes"].tolist() == [2, 5, 8, 11]
        assert result["trimestre"].tolist() == [1, 2, 3, 4]
        assert str(result["fecha"].iloc[0]) == "2021-02-01"
        assert str(result["fecha"].iloc[3]) == "2021-11-01"

    def test_derive_temporal_columns_from_fecha(self) -> None:
        df = pd.DataFrame({"fecha": ["2023-07-15", "2024-12-01"]})
        result = derive_temporal_columns(df)
        assert result["anio"].tolist() == [2023, 2024]
        assert result["mes"].tolist() == [7, 12]
        assert result["trimestre"].tolist() == [3, 4]

    def test_convert_fob_bob(self) -> None:
        assert convert_fob_bob(100.0) == 696.00
        assert convert_fob_bob(0.0) == 0.0
        assert convert_fob_bob(None) == 0.0
        series = pd.Series([100.0, 200.0, None])
        res_series = convert_fob_bob(series)
        assert isinstance(res_series, pd.Series)
        assert res_series.iloc[0] == 696.00
        assert res_series.iloc[1] == 1392.00
        assert res_series.iloc[2] == 0.00

    def test_deduplicate_records(self) -> None:
        df = pd.DataFrame({
            "id": [1, 1, 2, 3],
            "val": ["a", "a", "b", "c"],
        })
        dedup = deduplicate_records(df)
        assert len(dedup) == 3
        assert dedup["id"].tolist() == [1, 2, 3]


# ---------------------------------------------------------------------------
# Tests: clean pipelines (clean_export_dataframe / clean_import_dataframe)
# ---------------------------------------------------------------------------
class TestCleanDataframes:
    """Pruebas para pipelines básicos de exportaciones e importaciones."""

    def test_clean_export_dataframe(self) -> None:
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
        assert result["NANDINA"].iloc[0] == "0901110000"
        assert "VIASAL" in result.columns
        assert result["VALOR"].iloc[0] == 125000.50
        assert result["DESVIA"].iloc[0] == "AEREA"

    def test_clean_import_dataframe(self) -> None:
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
        assert result["NANDINA"].iloc[0] == "0406100000"
        assert result["FOB"].iloc[0] == 125.0
        assert result["FRO"].iloc[0] == 187.0


# ---------------------------------------------------------------------------
# Tests: transform_to_staging & transform_to_fact
# ---------------------------------------------------------------------------
class TestTransformToStagingAndFact:
    """Pruebas para la transformación integral a Staging y Modelo Estrella."""

    def test_transform_to_staging_exportaciones(self) -> None:
        raw_df = pd.DataFrame({
            "GESTION": [2021],
            "MES": [2],
            "FLUJO": ["1 EXPORTACIONES"],
            "NANDINA": [901110000],
            "PAIS": [249],
            "DESPAIS": ["ESTADOS UNIDOS"],
            "DEPART": [2],
            "VALOR": [125000.50],
            "KILBRU": [45000],
            "KILNET": [42000],
        })
        stg = transform_to_staging(
            raw_df,
            operation_type="exportaciones",
            filename="export_2021.xlsx",
            file_hash="hash123",
        )
        assert stg["tipo_operacion"].iloc[0] == "EXPORTACION"
        assert stg["codigo_nandina"].iloc[0] == "0901110000"
        assert stg["capitulo_nandina"].iloc[0] == "09"
        assert stg["flujo_codigo"].iloc[0] == 1
        assert stg["flujo_desc"].iloc[0] == "EXPORTACIONES"
        assert str(stg["fecha"].iloc[0]) == "2021-02-01"
        assert stg["nombre_archivo_origen"].iloc[0] == "export_2021.xlsx"
        assert stg["hash_sha256"].iloc[0] == "hash123"
        assert "fecha_ingesta" in stg.columns

    def test_transform_to_staging_importaciones(self) -> None:
        raw_df = pd.DataFrame({
            "GESTION": [2021],
            "MES": [9],
            "ADUANA": [711],
            "PAIS": [63],
            "DESPAI": ["ARGENTINA"],
            "NANDINA": [406100000],
            "FOB": [125.0],
            "FRO": [187.0],
            "ADU": [1300.0],
            "PAG": [130.0],
            "KILOS": [27.0],
        })
        stg = transform_to_staging(
            raw_df,
            operation_type="importaciones",
            filename="import_2021.xlsx",
            file_hash="hash456",
        )
        assert stg["tipo_operacion"].iloc[0] == "IMPORTACION"
        assert stg["codigo_nandina"].iloc[0] == "0406100000"
        assert stg["valor_fob_usd"].iloc[0] == 125.0
        assert stg["valor_cif_frontera_usd"].iloc[0] == 187.0
        assert stg["valor_cif_frontera_bob"].iloc[0] == 1300.0

    def test_transform_to_fact_exportaciones(self) -> None:
        raw_df = pd.DataFrame({
            "GESTION": [2021],
            "MES": [2],
            "NANDINA": [901110000],
            "PAIS": [249],
            "DEPART": [2],
            "VIASAL": [9],
            "ADUDES": [72],
            "VALOR": [1000.0],
            "KILBRU": [500.0],
            "KILNET": [450.0],
            "FINO": [None],
        })
        fact = transform_to_fact(raw_df, operation_type="exportaciones")
        assert len(fact) == 1
        row = fact.iloc[0]
        assert row["id_transaccion"] == 1
        assert str(row["fecha"]) == "2021-02-01"
        assert row["codigo_nandina"] == "0901110000"
        assert row["pais_iso"] == "USA"
        assert row["tipo_operacion"] == "EXPORTACION"
        assert row["valor_fob_usd"] == 1000.0
        assert row["valor_fob_bob"] == 6960.0  # 1000 * 6.96
        assert row["peso_neto_kg"] == 450.0
        assert row["peso_bruto_kg"] == 500.0
        assert row["anio"] == 2021
        assert row["mes"] == 2
        assert row["trimestre"] == 1

    def test_transform_to_fact_importaciones(self) -> None:
        raw_df = pd.DataFrame({
            "GESTION": [2021],
            "MES": [11],
            "NANDINA": [406100000],
            "PAIS": [63],
            "DEPTO": [7],
            "VIA": [9],
            "ADUANA": [711],
            "FOB": [500.0],
            "FRO": [600.0],
            "KILOS": [100.0],
        })
        fact = transform_to_fact(raw_df, operation_type="importaciones")
        assert len(fact) == 1
        assert fact.iloc[0]["tipo_operacion"] == "IMPORTACION"
        assert fact.iloc[0]["pais_iso"] == "ARG"
        assert fact.iloc[0]["valor_fob_usd"] == 500.0
        assert fact.iloc[0]["valor_cif_usd"] == 600.0
        assert fact.iloc[0]["valor_fob_bob"] == 3480.0
        assert fact.iloc[0]["anio"] == 2021
        assert fact.iloc[0]["mes"] == 11
        assert fact.iloc[0]["trimestre"] == 4

    def test_transform_to_fact_country_source_fallbacks(self) -> None:
        # Input with pais_iso directly
        df_iso = pd.DataFrame({"gestion": [2021], "mes": [1], "pais_iso": ["BRA"]})
        fact_iso = transform_to_fact(df_iso, operation_type="exportaciones")
        assert fact_iso["pais_iso"].iloc[0] == "BRA"

        # Input with nombre_pais directly
        df_nombre = pd.DataFrame({"gestion": [2021], "mes": [1], "nombre_pais": ["CHILE"]})
        fact_nombre = transform_to_fact(df_nombre, operation_type="exportaciones")
        assert fact_nombre["pais_iso"].iloc[0] == "CHL"

        # Input without any country column
        df_no_country = pd.DataFrame({"gestion": [2021], "mes": [1]})
        fact_no_country = transform_to_fact(df_no_country, operation_type="exportaciones")
        assert fact_no_country["pais_iso"].iloc[0] == "ZZZ"


# ---------------------------------------------------------------------------
# Tests: Constantes y mapeos
# ---------------------------------------------------------------------------
class TestConstants:
    """Verifica consistencia de constantes de esquema."""

    def test_export_canonical_columns_count(self) -> None:
        assert len(EXPORT_CANONICAL_COLUMNS) == 38

    def test_import_canonical_columns_count(self) -> None:
        assert len(IMPORT_CANONICAL_COLUMNS) == 29

    def test_export_aliases_are_valid(self) -> None:
        for _old, new in EXPORT_COLUMN_ALIASES.items():
            assert new in EXPORT_CANONICAL_COLUMNS

    def test_staging_maps_non_empty(self) -> None:
        assert len(EXPORT_INE_TO_STAGING_MAP) > 30
        assert len(IMPORT_INE_TO_STAGING_MAP) > 20

    def test_numeric_columns_subset(self) -> None:
        for col in EXPORT_NUMERIC_COLUMNS:
            assert col in EXPORT_CANONICAL_COLUMNS
        for col in IMPORT_NUMERIC_COLUMNS:
            assert col in IMPORT_CANONICAL_COLUMNS

    def test_exchange_rate_value(self) -> None:
        assert OFFICIAL_EXCHANGE_RATE_BOB_USD == 6.96
