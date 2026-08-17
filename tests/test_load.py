"""Pruebas unitarias para el módulo base de carga ``src.load``.

Valida la inicialización de clientes BigQuery, verificación de idempotencia,
carga a Staging, registro en `etl_control_log`, sincronización con Firestore,
el dataclass `LoadResult` y la re-exportación de funciones especializadas.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.load import (
    LoadError,
    LoadResult,
    get_bigquery_client,
    is_already_processed,
    load_comercio_exterior,
    load_to_staging,
    log_etl_execution,
    merge_into_fact_comercio_exterior,
    sync_dim_producto_scd2,
    sync_firestore_metadata,
)


@pytest.fixture
def sample_staging_df() -> pd.DataFrame:
    """Retorna un DataFrame sintético con el esquema de staging."""
    return pd.DataFrame(
        {
            "gestion": [2023, 2023],
            "mes": [1, 2],
            "fecha": ["2023-01-01", "2023-02-01"],
            "codigo_nandina": ["0901110000", "2611110000"],
            "tipo_operacion": ["EXPORTACION", "EXPORTACION"],
            "valor_fob_usd": [15000.0, 32000.0],
            "hash_sha256": ["test_hash_123", "test_hash_123"],
            "fecha_ingesta": ["2023-01-01T00:00:00Z", "2023-02-01T00:00:00Z"],
        }
    )


class TestBigQueryClientInitialization:
    """Pruebas de inicialización y autenticación de BigQuery Client."""

    @patch("google.cloud.bigquery.Client")
    def test_default_initialization(self, mock_client: MagicMock) -> None:
        mock_client.return_value.project = "insight-bolivia"
        client = get_bigquery_client()
        assert client is not None
        mock_client.assert_called_once()

    @patch("google.cloud.bigquery.Client")
    def test_custom_project_and_location(self, mock_client: MagicMock) -> None:
        get_bigquery_client(project="custom-project", location="EU")
        mock_client.assert_called_with(project="custom-project", location="EU")

    @patch("src.load.Path.is_file", return_value=True)
    @patch("google.oauth2.service_account.Credentials.from_service_account_file")
    @patch("google.cloud.bigquery.Client")
    def test_service_account_credentials(
        self,
        mock_client: MagicMock,
        mock_creds: MagicMock,
        mock_is_file: MagicMock,
    ) -> None:
        mock_creds_instance = MagicMock()
        mock_creds_instance.project_id = "sa-project"
        mock_creds.return_value = mock_creds_instance

        key_path = str(Path("/path/to/key.json"))
        get_bigquery_client(credentials_path="/path/to/key.json")
        mock_creds.assert_called_once_with(key_path)
        mock_client.assert_called_once()

    @patch("src.load.Path.is_file", return_value=True)
    @patch("google.oauth2.service_account.Credentials.from_service_account_file")
    @patch("google.cloud.bigquery.Client")
    def test_service_account_credentials_infers_project(
        self,
        mock_client: MagicMock,
        mock_creds: MagicMock,
        mock_is_file: MagicMock,
    ) -> None:
        mock_creds_instance = MagicMock()
        mock_creds_instance.project_id = "inferred-project"
        mock_creds.return_value = mock_creds_instance

        with patch.dict("os.environ", {}, clear=True), patch("src.load.get_settings") as mock_settings:
            mock_settings.return_value.bigquery.project_id = ""
            mock_settings.return_value.bigquery.location = "US"
            get_bigquery_client(credentials_path="/path/to/key.json")
            mock_client.assert_called_with(
                location="US",
                project="inferred-project",
                credentials=mock_creds_instance,
            )

    def test_missing_credentials_file_raises(self) -> None:
        with pytest.raises(FileNotFoundError, match="No se encontró el archivo"):
            get_bigquery_client(credentials_path="/non/existent/path.json")


class TestIsAlreadyProcessed:
    """Pruebas para verificar idempotencia mediante etl_control_log."""

    def test_empty_hash_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="El hash SHA-256 no puede estar vacío"):
            is_already_processed("")

    def test_hash_found_returns_true(self) -> None:
        mock_bq = MagicMock()
        mock_query_job = MagicMock()
        mock_query_job.result.return_value = [{"total": 1}]
        mock_bq.query.return_value = mock_query_job
        mock_bq.project = "insight-bolivia"

        assert is_already_processed("hash123", client=mock_bq) is True
        mock_bq.query.assert_called_once()

    def test_hash_not_found_returns_false(self) -> None:
        mock_bq = MagicMock()
        mock_query_job = MagicMock()
        mock_query_job.result.return_value = [{"total": 0}]
        mock_bq.query.return_value = mock_query_job
        mock_bq.project = "insight-bolivia"

        assert is_already_processed("hash456", client=mock_bq) is False

    def test_empty_results_returns_false(self) -> None:
        mock_bq = MagicMock()
        mock_query_job = MagicMock()
        mock_query_job.result.return_value = []
        mock_bq.query.return_value = mock_query_job
        mock_bq.project = "insight-bolivia"

        assert is_already_processed("hash789", client=mock_bq) is False


class TestLoadToStaging:
    """Pruebas para la función `load_to_staging`."""

    def test_empty_dataframe_returns_zero(self) -> None:
        mock_bq = MagicMock()
        assert load_to_staging(pd.DataFrame(), client=mock_bq) == 0
        mock_bq.load_table_from_dataframe.assert_not_called()

    def test_loads_dataframe_with_date_casting(self, sample_staging_df: pd.DataFrame) -> None:
        mock_bq = MagicMock()
        mock_job = MagicMock()
        mock_job.output_rows = 2
        mock_bq.load_table_from_dataframe.return_value = mock_job
        mock_bq.project = "insight-bolivia"

        rows = load_to_staging(sample_staging_df, client=mock_bq)
        assert rows == 2
        mock_bq.load_table_from_dataframe.assert_called_once()
        mock_job.result.assert_called_once()


class TestLogEtlExecution:
    """Pruebas para el registro en `etl_control_log`."""

    def test_successful_log_insertion_with_various_date_types(self) -> None:
        mock_bq = MagicMock()
        mock_bq.insert_rows_json.return_value = []
        mock_bq.project = "insight-bolivia"

        id1 = log_etl_execution(
            nombre_archivo="boletin.xlsx",
            hash_sha256="hash123",
            estado="SUCCESS",
            registros_procesados=100,
            fecha_publicacion=datetime(2023, 1, 15, tzinfo=UTC),
            client=mock_bq,
        )
        assert id1 is not None

        id2 = log_etl_execution(
            nombre_archivo="boletin.xlsx",
            hash_sha256="hash123",
            estado="SUCCESS",
            fecha_publicacion=date(2023, 1, 15),
            client=mock_bq,
        )
        assert id2 is not None

        id3 = log_etl_execution(
            nombre_archivo="boletin.xlsx",
            hash_sha256="hash123",
            estado="SUCCESS",
            fecha_publicacion="2023-01-15",
            client=mock_bq,
        )
        assert id3 is not None
        assert mock_bq.insert_rows_json.call_count == 3

    def test_insert_errors_raises_load_error(self) -> None:
        mock_bq = MagicMock()
        mock_bq.insert_rows_json.return_value = [{"error": "Invalid schema"}]
        mock_bq.project = "insight-bolivia"

        with pytest.raises(LoadError, match="Error insertando log"):
            log_etl_execution(
                nombre_archivo="archivo.xlsx",
                hash_sha256="hash_err",
                estado="FAILED",
                client=mock_bq,
            )


class TestSyncFirestoreMetadata:
    """Pruebas de integración operacional con Cloud Firestore."""

    @patch("src.load.update_last_refresh", return_value=True)
    @patch("src.load.log_audit_event", return_value="audit_123")
    def test_sync_firestore_metadata_calls_helpers(
        self,
        mock_audit: MagicMock,
        mock_update: MagicMock,
    ) -> None:
        mock_fs = MagicMock()
        result = sync_firestore_metadata(code="comercio_exterior", record_count=500, client=mock_fs)
        assert result is True
        mock_update.assert_called_once()
        mock_audit.assert_called_once()


class TestLoadResult:
    """Pruebas sobre el dataclass LoadResult."""

    def test_is_success_states(self) -> None:
        success_res = LoadResult("SUCCESS", 10, 10, "h1", "id1", 1.2)
        skipped_res = LoadResult("SKIPPED", 0, 0, "h2", "id2", 0.1)
        failed_res = LoadResult("FAILED", 0, 0, "h3", "id3", 0.5, "error")

        assert success_res.is_success is True
        assert skipped_res.is_success is True
        assert failed_res.is_success is False


class TestReExports:
    """Verifica que las funciones de comercio exterior estén re-exportadas en src.load."""

    def test_reexported_functions_exist(self) -> None:
        assert callable(sync_dim_producto_scd2)
        assert callable(merge_into_fact_comercio_exterior)
        assert callable(load_comercio_exterior)
