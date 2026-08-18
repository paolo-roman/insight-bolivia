"""InsightBolivia — Pruebas unitarias para el cliente BigQuery de Streamlit (`bq_client.py`).

Verifica la inyección segura de credenciales desde `st.secrets`, ejecución de
consultas parametrizadas, caching con `@st.cache_data` y manejo defensivo de errores.
"""

from __future__ import annotations

import contextlib
from datetime import date
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
import streamlit as st
from google.cloud import bigquery

from streamlit_app.utils.bq_client import (
    _get_credentials_from_secrets,
    get_available_date_range,
    get_balanza_comercial,
    get_bigquery_client,
    get_socios_comerciales,
    get_top_productos,
    run_query,
)

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture(autouse=True)
def clear_streamlit_cache() -> None:
    """Limpia el caché de Streamlit antes de cada prueba."""
    with contextlib.suppress(Exception):
        run_query.clear()
        get_balanza_comercial.clear()
        get_top_productos.clear()
        get_socios_comerciales.clear()
        get_available_date_range.clear()


class TestGetCredentialsFromSecrets:
    """Pruebas para extracción de credenciales desde st.secrets."""

    def test_returns_credentials_when_secrets_present(self) -> None:
        mock_secrets = {
            "gcp_service_account": {
                "type": "service_account",
                "project_id": "test-proj",
                "client_email": "test@test-proj.iam.gserviceaccount.com",
                "private_key": "-----BEGIN PRIVATE KEY-----\nMIIEvgIBA\n-----END PRIVATE KEY-----\n",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        }
        with patch.object(st, "secrets", mock_secrets), patch(
            "google.oauth2.service_account.Credentials.from_service_account_info"
        ) as mock_from_info:
            mock_from_info.return_value = MagicMock(project_id="test-proj")
            creds = _get_credentials_from_secrets()
            assert creds is not None
            mock_from_info.assert_called_once()

    def test_returns_none_when_secrets_absent_or_empty(self) -> None:
        with patch.object(st, "secrets", {}):
            assert _get_credentials_from_secrets() is None

    def test_returns_none_on_exception(self) -> None:
        with patch.object(st, "secrets", {"gcp_service_account": "invalid_structure"}):
            assert _get_credentials_from_secrets() is None


class TestGetBigQueryClient:
    """Pruebas para inicialización de bigquery.Client."""

    @patch("google.cloud.bigquery.Client")
    def test_client_init_with_secrets(self, mock_bq_class: MagicMock) -> None:
        mock_creds = MagicMock(project_id="test-proj")
        with patch("streamlit_app.utils.bq_client._get_credentials_from_secrets", return_value=mock_creds):
            client = get_bigquery_client(project="custom-proj", location="EU")
            assert client is not None
            mock_bq_class.assert_called_once_with(
                project="custom-proj",
                location="EU",
                credentials=mock_creds,
            )

    @patch("google.cloud.bigquery.Client")
    def test_client_init_fallback_to_file_path(self, mock_bq_class: MagicMock, tmp_path: Path) -> None:
        key_file = tmp_path / "sa.json"
        key_file.write_text('{"project_id": "file-proj"}', encoding="utf-8")

        with patch("streamlit_app.utils.bq_client._get_credentials_from_secrets", return_value=None), patch.dict(
            "os.environ", {"GCP_SA_KEY_PATH": str(key_file), "BQ_PROJECT_ID": "env-proj"}
        ), patch("google.oauth2.service_account.Credentials.from_service_account_file") as mock_from_file:
            mock_from_file.return_value = MagicMock(project_id="file-proj")
            client = get_bigquery_client()
            assert client is not None
            mock_bq_class.assert_called_once()


class TestRunQuery:
    """Pruebas para ejecución de consultas SQL."""

    @patch("streamlit_app.utils.bq_client.get_bigquery_client")
    def test_run_query_success(self, mock_get_client: MagicMock) -> None:
        mock_client = MagicMock()
        mock_job = MagicMock()
        expected_df = pd.DataFrame({"anio": [2024, 2025], "fob": [1000.0, 2000.0]})
        mock_job.to_dataframe.return_value = expected_df
        mock_client.query.return_value = mock_job
        mock_get_client.return_value = mock_client

        df = run_query("SELECT 1", _params=[bigquery.ScalarQueryParameter("test", "STRING", "val")])
        assert not df.empty
        assert len(df) == 2
        mock_client.query.assert_called_once()

    @patch("streamlit_app.utils.bq_client.get_bigquery_client")
    def test_run_query_handles_exception(self, mock_get_client: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client.query.side_effect = RuntimeError("BigQuery connection error")
        mock_get_client.return_value = mock_client

        df = run_query("SELECT 1")
        assert df.empty
        assert isinstance(df, pd.DataFrame)


class TestBqViewsQueries:
    """Pruebas para las funciones de consulta a vistas analíticas."""

    @patch("streamlit_app.utils.bq_client.run_query")
    def test_get_balanza_comercial_with_dates(self, mock_run_query: MagicMock) -> None:
        mock_run_query.return_value = pd.DataFrame({"fecha": ["2024-01-01"], "saldo_balanza_usd": [500000.0]})
        start = date(2024, 1, 1)
        end = date(2024, 12, 31)

        df = get_balanza_comercial(start_date=start, end_date=end)
        assert not df.empty
        mock_run_query.assert_called_once()
        call_args = mock_run_query.call_args
        query_sql = call_args[0][0]
        params = call_args[1]["_params"]

        assert "vw_balanza_comercial_mensual" in query_sql
        assert "fecha >= @start_date" in query_sql
        assert "fecha <= @end_date" in query_sql
        assert len(params) == 2

    @patch("streamlit_app.utils.bq_client.run_query")
    def test_get_top_productos(self, mock_run_query: MagicMock) -> None:
        mock_run_query.return_value = pd.DataFrame({"ranking": [1, 2], "codigo_nandina": ["2711110000", "1201900000"]})

        df = get_top_productos(year=2024, limit=5)
        assert not df.empty
        mock_run_query.assert_called_once()
        call_args = mock_run_query.call_args
        query_sql = call_args[0][0]
        params = call_args[1]["_params"]

        assert "vw_top_productos_exportados" in query_sql
        assert "anio = @year" in query_sql
        assert any(p.name == "limit" and p.value == 5 for p in params)
        assert any(p.name == "year" and p.value == 2024 for p in params)

    @patch("streamlit_app.utils.bq_client.run_query")
    def test_get_socios_comerciales(self, mock_run_query: MagicMock) -> None:
        mock_run_query.return_value = pd.DataFrame({"pais_iso": ["BRA", "ARG"], "total_valor_usd": [10000.0, 5000.0]})

        df = get_socios_comerciales(flow="EXPORTACION", year=2025, limit=10)
        assert not df.empty
        mock_run_query.assert_called_once()
        call_args = mock_run_query.call_args
        query_sql = call_args[0][0]
        params = call_args[1]["_params"]

        assert "vw_socios_comerciales" in query_sql
        assert "tipo_operacion = @flow" in query_sql
        assert "LIMIT 10" in query_sql
        assert any(p.name == "flow" and p.value == "EXPORTACION" for p in params)

    @patch("streamlit_app.utils.bq_client.run_query")
    def test_get_available_date_range_success(self, mock_run_query: MagicMock) -> None:
        mock_run_query.return_value = pd.DataFrame({"min_date": [date(2021, 1, 1)], "max_date": [date(2026, 6, 30)]})

        d_min, d_max = get_available_date_range()
        assert d_min == date(2021, 1, 1)
        assert d_max == date(2026, 6, 30)

    @patch("streamlit_app.utils.bq_client.run_query")
    def test_get_available_date_range_fallback_on_empty(self, mock_run_query: MagicMock) -> None:
        mock_run_query.return_value = pd.DataFrame()

        d_min, d_max = get_available_date_range(dataset="empty_ds")
        assert d_min == date(2020, 1, 1)
        assert d_max == date.today()
