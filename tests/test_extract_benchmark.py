"""Pruebas unitarias para el módulo de extracción y carga de benchmark internacional.

Cubre:
- Validación del script DDL `sql/ddl/create_fact_indicadores_bm.sql`.
- Extracción de datos con `wbgapi` (`fetch_world_bank_data`).
- Transformación y normalización tabular (`transform_benchmark_data`).
- Cálculo de hash SHA-256 determinista (`calculate_benchmark_hash`).
- Carga e idempotencia con BigQuery MERGE (`load_benchmark_to_bigquery`).
- Orquestación del pipeline ETL (`run_benchmark_etl`).
- Punto de entrada CLI (`main`).
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.extract_benchmark import (
    COUNTRY_NAMES_ES,
    DEFAULT_COUNTRIES,
    DEFAULT_INDICATORS,
    BenchmarkETLResult,
    ExtractBenchmarkError,
    calculate_benchmark_hash,
    fetch_world_bank_data,
    load_benchmark_to_bigquery,
    main,
    run_benchmark_etl,
    transform_benchmark_data,
)
from src.load import LoadError


def get_ddl_path() -> Path:
    """Helper para ubicar el archivo DDL create_fact_indicadores_bm.sql."""
    candidates = [
        Path.cwd() / "sql" / "ddl" / "create_fact_indicadores_bm.sql",
        Path.cwd() / "insight-bolivia" / "sql" / "ddl" / "create_fact_indicadores_bm.sql",
        Path(__file__).resolve().parent.parent / "sql" / "ddl" / "create_fact_indicadores_bm.sql",
    ]
    for p in candidates:
        if p.exists():
            return p.resolve()
    raise FileNotFoundError("No se encontró sql/ddl/create_fact_indicadores_bm.sql")


class TestBenchmarkConstants:
    """Verifica las constantes y diccionarios de configuración de benchmark."""

    def test_default_countries_and_names(self) -> None:
        assert "BOL" in DEFAULT_COUNTRIES
        assert "PER" in DEFAULT_COUNTRIES
        assert "CHL" in DEFAULT_COUNTRIES
        assert "COL" in DEFAULT_COUNTRIES
        assert "PRY" in DEFAULT_COUNTRIES
        assert COUNTRY_NAMES_ES["BOL"] == "Bolivia"
        assert COUNTRY_NAMES_ES["PER"] == "Perú"

    def test_default_indicators_contains_macro_keys(self) -> None:
        assert "NY.GDP.MKTP.CD" in DEFAULT_INDICATORS
        assert "FP.CPI.TOTL.ZG" in DEFAULT_INDICATORS
        assert "NE.EXP.GNFS.KD.ZG" in DEFAULT_INDICATORS
        assert DEFAULT_INDICATORS["NY.GDP.MKTP.CD"]["unidad"] == "USD"


class TestDDLFactIndicadoresBM:
    """Verifica la sintaxis, restricciones y estructura del DDL create_fact_indicadores_bm.sql."""

    def test_ddl_file_exists_and_is_not_empty(self) -> None:
        path = get_ddl_path()
        assert path.is_file()
        content = path.read_text(encoding="utf-8")
        assert len(content.strip()) > 200

    def test_ddl_contains_required_table_and_columns(self) -> None:
        content = get_ddl_path().read_text(encoding="utf-8")
        assert "CREATE TABLE IF NOT EXISTS `insight-bolivia.benchmark_regional.fact_indicadores_bm`" in content
        expected_cols = [
            "id_indicador_bm STRING NOT NULL",
            "fecha DATE NOT NULL",
            "anio INT64 NOT NULL",
            "pais_iso STRING NOT NULL",
            "pais_nombre STRING NOT NULL",
            "codigo_indicador STRING NOT NULL",
            "nombre_indicador STRING NOT NULL",
            "valor NUMERIC",
            "unidad_medida STRING NOT NULL",
            "fuente STRING NOT NULL",
            "fecha_extraccion TIMESTAMP NOT NULL",
        ]
        for col in expected_cols:
            assert col in content, f"Falta la columna o tipo: {col}"

    def test_ddl_contains_partitioning_and_clustering(self) -> None:
        content = get_ddl_path().read_text(encoding="utf-8")
        assert "PARTITION BY DATE_TRUNC(fecha, YEAR)" in content
        assert "CLUSTER BY pais_iso, codigo_indicador" in content
        assert "benchmark_regional" in content


class TestFetchWorldBankData:
    """Pruebas para la función de extracción con wbgapi."""

    @patch("wbgapi.data.fetch")
    def test_fetch_world_bank_data_success(self, mock_fetch: MagicMock) -> None:
        mock_fetch.return_value = iter([
            {"value": 40000000000.0, "series": "NY.GDP.MKTP.CD", "economy": "BOL", "time": "YR2022"},
            {"value": 3.5, "series": "NY.GDP.MKTP.KD.ZG", "economy": "PER", "time": "YR2022"},
        ])
        records = fetch_world_bank_data(start_year=2020, end_year=2022)
        assert len(records) == 2
        assert records[0]["economy"] == "BOL"
        mock_fetch.assert_called_once()

    def test_fetch_invalid_years_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="start_year .* no puede ser mayor que end_year"):
            fetch_world_bank_data(start_year=2025, end_year=2020)

    def test_fetch_empty_indicators_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="La lista de indicadores no puede estar vacía"):
            fetch_world_bank_data(indicators=[])

    def test_fetch_empty_countries_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="La lista de países no puede estar vacía"):
            fetch_world_bank_data(countries=[])

    @patch("wbgapi.data.fetch", side_effect=RuntimeError("API Connection Timeout"))
    def test_fetch_api_error_raises_extract_benchmark_error(self, mock_fetch: MagicMock) -> None:
        with pytest.raises(ExtractBenchmarkError, match="Error consultando la API del Banco Mundial"):
            fetch_world_bank_data(start_year=2020, end_year=2021)


class TestTransformBenchmarkData:
    """Pruebas para la normalización tabular y cálculos de hash."""

    def test_transform_empty_records_returns_empty_dataframe(self) -> None:
        df = transform_benchmark_data([])
        assert isinstance(df, pd.DataFrame)
        assert df.empty
        assert "id_indicador_bm" in df.columns
        assert "fecha" in df.columns

    def test_transform_valid_records(self) -> None:
        raw = [
            {"value": 43000000000.0, "series": "NY.GDP.MKTP.CD", "economy": "BOL", "time": "YR2022"},
            {"value": 2.8, "series": "FP.CPI.TOTL.ZG", "economy": "CHL", "time": "YR2021"},
            {"value": None, "series": "FP.CPI.TOTL.ZG", "economy": "PER", "time": "YR2020"},  # Ignorado
            {"value": 1.5, "series": "NE.EXP.GNFS.KD.ZG", "economy": "COL", "time": "INVALID"},  # Ignorado
        ]
        fixed_now = datetime(2026, 8, 18, 12, 0, 0, tzinfo=UTC)
        df = transform_benchmark_data(raw, extraction_timestamp=fixed_now)

        assert len(df) == 2
        bol_row = df[df["pais_iso"] == "BOL"].iloc[0]
        assert bol_row["pais_nombre"] == "Bolivia"
        assert bol_row["anio"] == 2022
        assert bol_row["fecha"] == date(2022, 1, 1)
        assert bol_row["codigo_indicador"] == "NY.GDP.MKTP.CD"
        assert bol_row["nombre_indicador"] == "PIB a precios actuales"
        assert bol_row["unidad_medida"] == "USD"
        assert bol_row["valor"] == 43000000000.0
        assert bol_row["fuente"] == "Banco Mundial - WDI"
        assert len(bol_row["id_indicador_bm"]) == 16

        chl_row = df[df["pais_iso"] == "CHL"].iloc[0]
        assert chl_row["pais_nombre"] == "Chile"
        assert chl_row["anio"] == 2021
        assert chl_row["valor"] == 2.8

    def test_transform_all_nulls_returns_empty_dataframe(self) -> None:
        raw = [{"value": None, "series": "NY.GDP.MKTP.CD", "economy": "BOL", "time": "YR2022"}]
        df = transform_benchmark_data(raw)
        assert df.empty

    def test_calculate_benchmark_hash_empty_and_deterministic(self) -> None:
        empty_hash = calculate_benchmark_hash(pd.DataFrame())
        assert len(empty_hash) == 64

        df1 = pd.DataFrame([
            {"pais_iso": "BOL", "codigo_indicador": "NY.GDP.MKTP.CD", "anio": 2022, "valor": 40.0},
            {"pais_iso": "PER", "codigo_indicador": "NY.GDP.MKTP.CD", "anio": 2022, "valor": 200.0},
        ])
        df2 = pd.DataFrame([
            {"pais_iso": "PER", "codigo_indicador": "NY.GDP.MKTP.CD", "anio": 2022, "valor": 200.0},
            {"pais_iso": "BOL", "codigo_indicador": "NY.GDP.MKTP.CD", "anio": 2022, "valor": 40.0},
        ])
        h1 = calculate_benchmark_hash(df1)
        h2 = calculate_benchmark_hash(df2)
        assert h1 == h2
        assert len(h1) == 64


class TestLoadBenchmarkToBigQuery:
    """Pruebas para la carga en Staging y sentencia MERGE en BigQuery."""

    def test_load_empty_dataframe_returns_zero(self) -> None:
        mock_bq = MagicMock()
        rows = load_benchmark_to_bigquery(pd.DataFrame(), client=mock_bq)
        assert rows == 0
        mock_bq.load_table_from_dataframe.assert_not_called()

    def test_load_success_with_staging_and_merge(self) -> None:
        mock_bq = MagicMock()
        mock_load_job = MagicMock()
        mock_load_job.result.return_value = None
        mock_bq.load_table_from_dataframe.return_value = mock_load_job

        mock_merge_job = MagicMock()
        mock_merge_job.num_dml_affected_rows = 15
        mock_merge_job.result.return_value = None
        mock_bq.query.return_value = mock_merge_job

        df = pd.DataFrame([
            {
                "id_indicador_bm": "abc1234567890def",
                "fecha": date(2022, 1, 1),
                "anio": 2022,
                "pais_iso": "BOL",
                "pais_nombre": "Bolivia",
                "codigo_indicador": "NY.GDP.MKTP.CD",
                "nombre_indicador": "PIB",
                "valor": 43000000000.0,
                "unidad_medida": "USD",
                "fuente": "Banco Mundial - WDI",
                "fecha_extraccion": datetime.now(UTC),
            }
        ])

        affected = load_benchmark_to_bigquery(df, client=mock_bq, project_id="test-proj")
        assert affected == 15
        mock_bq.load_table_from_dataframe.assert_called_once()
        mock_bq.query.assert_called_once()

    def test_load_staging_error_raises_load_error(self) -> None:
        mock_bq = MagicMock()
        mock_bq.load_table_from_dataframe.side_effect = RuntimeError("Staging Load Failed")

        df = pd.DataFrame([{"fecha": date(2022, 1, 1), "pais_iso": "BOL", "valor": 10.0}])
        with pytest.raises(LoadError, match="Error cargando datos en Staging"):
            load_benchmark_to_bigquery(df, client=mock_bq)

    def test_load_merge_error_raises_load_error(self) -> None:
        mock_bq = MagicMock()
        mock_load_job = MagicMock()
        mock_load_job.result.return_value = None
        mock_bq.load_table_from_dataframe.return_value = mock_load_job
        mock_bq.query.side_effect = RuntimeError("MERGE Syntax Error")

        df = pd.DataFrame([{"fecha": date(2022, 1, 1), "pais_iso": "BOL", "valor": 10.0}])
        with pytest.raises(LoadError, match="Error ejecutando MERGE en tabla destino"):
            load_benchmark_to_bigquery(df, client=mock_bq)


class TestRunBenchmarkETL:
    """Pruebas del orquestador run_benchmark_etl."""

    @patch("src.extract_benchmark.sync_firestore_metadata")
    @patch("src.extract_benchmark.log_etl_execution", return_value="exec-12345")
    @patch("src.extract_benchmark.load_benchmark_to_bigquery", return_value=10)
    @patch("src.extract_benchmark.is_already_processed", return_value=False)
    @patch("src.extract_benchmark.fetch_world_bank_data")
    def test_run_benchmark_etl_success(
        self,
        mock_fetch: MagicMock,
        mock_is_proc: MagicMock,
        mock_load: MagicMock,
        mock_log: MagicMock,
        mock_sync_fs: MagicMock,
    ) -> None:
        mock_fetch.return_value = [
            {"value": 43000000000.0, "series": "NY.GDP.MKTP.CD", "economy": "BOL", "time": "YR2022"},
        ]
        result = run_benchmark_etl(start_year=2022, end_year=2022)

        assert isinstance(result, BenchmarkETLResult)
        assert result.status == "SUCCESS"
        assert result.is_success is True
        assert result.records_extracted == 1
        assert result.records_loaded == 10
        assert result.execution_id == "exec-12345"
        mock_load.assert_called_once()
        mock_log.assert_called_once()
        mock_sync_fs.assert_called_once()

    @patch("src.extract_benchmark.fetch_world_bank_data", return_value=[])
    def test_run_benchmark_etl_empty_records(self, mock_fetch: MagicMock) -> None:
        result = run_benchmark_etl(start_year=2022, end_year=2022)
        assert result.status == "SUCCESS"
        assert result.records_extracted == 0
        assert result.records_loaded == 0

    @patch("src.extract_benchmark.is_already_processed", return_value=True)
    @patch("src.extract_benchmark.fetch_world_bank_data")
    def test_run_benchmark_etl_idempotency_skip(
        self,
        mock_fetch: MagicMock,
        mock_is_proc: MagicMock,
    ) -> None:
        mock_fetch.return_value = [
            {"value": 43000000000.0, "series": "NY.GDP.MKTP.CD", "economy": "BOL", "time": "YR2022"},
        ]
        result = run_benchmark_etl(start_year=2022, end_year=2022, force=False)
        assert result.status == "SKIPPED"
        assert result.is_success is True
        assert result.records_loaded == 0

    @patch("src.extract_benchmark.sync_firestore_metadata", side_effect=RuntimeError("Firestore connection down"))
    @patch("src.extract_benchmark.log_etl_execution", return_value="exec-789")
    @patch("src.extract_benchmark.load_benchmark_to_bigquery", return_value=5)
    @patch("src.extract_benchmark.is_already_processed", return_value=False)
    @patch("src.extract_benchmark.fetch_world_bank_data")
    def test_run_benchmark_etl_firestore_error_non_fatal(
        self,
        mock_fetch: MagicMock,
        mock_is_proc: MagicMock,
        mock_load: MagicMock,
        mock_log: MagicMock,
        mock_sync_fs: MagicMock,
    ) -> None:
        mock_fetch.return_value = [
            {"value": 43000000000.0, "series": "NY.GDP.MKTP.CD", "economy": "BOL", "time": "YR2022"},
        ]
        result = run_benchmark_etl(start_year=2022, end_year=2022)
        assert result.status == "SUCCESS"
        assert result.records_loaded == 5

    @patch("src.extract_benchmark.log_etl_execution")
    @patch("src.extract_benchmark.fetch_world_bank_data", side_effect=RuntimeError("Fatal WB Error"))
    def test_run_benchmark_etl_failure(
        self,
        mock_fetch: MagicMock,
        mock_log: MagicMock,
    ) -> None:
        result = run_benchmark_etl(start_year=2022, end_year=2022)
        assert result.status == "FAILED"
        assert result.is_success is False
        assert "Fatal WB Error" in str(result.error_details)
        mock_log.assert_called_once()

    @patch("src.extract_benchmark.log_etl_execution", side_effect=RuntimeError("Log failed"))
    @patch("src.extract_benchmark.fetch_world_bank_data", side_effect=RuntimeError("Fatal WB Error"))
    def test_run_benchmark_etl_failure_with_log_error(
        self,
        mock_fetch: MagicMock,
        mock_log: MagicMock,
    ) -> None:
        result = run_benchmark_etl(start_year=2022, end_year=2022)
        assert result.status == "FAILED"
        assert result.is_success is False


class TestBenchmarkCLI:
    """Pruebas para el CLI (main)."""

    @patch("src.extract_benchmark.run_benchmark_etl")
    def test_main_cli_success(self, mock_run: MagicMock) -> None:
        mock_run.return_value = BenchmarkETLResult(
            status="SUCCESS",
            records_extracted=10,
            records_loaded=10,
            sha256="abc",
            execution_id="1",
            duration_seconds=1.0,
        )
        exit_code = main(["--start-year", "2015", "--end-year", "2023", "--force", "-v"])
        assert exit_code == 0
        mock_run.assert_called_once_with(
            start_year=2015,
            end_year=2023,
            countries=None,
            indicators=None,
            force=True,
        )

    @patch("src.extract_benchmark.run_benchmark_etl")
    def test_main_cli_failure(self, mock_run: MagicMock) -> None:
        mock_run.return_value = BenchmarkETLResult(
            status="FAILED",
            records_extracted=0,
            records_loaded=0,
            sha256="none",
            execution_id="none",
            duration_seconds=1.0,
            error_details="Error",
        )
        exit_code = main(["--countries", "BOL", "PER"])
        assert exit_code == 1

    def test_extract_benchmark_module_main_execution(self) -> None:
        """Valida la ejecución del script con __name__ == '__main__'."""
        import runpy

        import src.extract_benchmark as eb_mod

        file_path = str(Path(eb_mod.__file__).resolve())
        with (
            patch("sys.argv", ["extract_benchmark.py", "--start-year", "2022"]),
            patch("wbgapi.data.fetch", return_value=[]),
            pytest.raises(SystemExit) as exc_info,
        ):
            runpy.run_path(file_path, run_name="__main__")
        assert exc_info.value.code == 0
