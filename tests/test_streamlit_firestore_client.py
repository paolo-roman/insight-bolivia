"""InsightBolivia — Pruebas unitarias para el cliente Firestore de Streamlit (`firestore_client.py`).

Verifica la inyección de credenciales, lectura de `dwh_catalog` con caching,
gestión de `session_id` y registro no bloqueante en `ui_analytics`.
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest
import streamlit as st

from src.firestore_models import DwhCatalog
from streamlit_app.utils.firestore_client import (
    _get_credentials_from_secrets,
    get_cached_dwh_catalog,
    get_firestore_client,
    get_session_id,
    log_ui_event,
)

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture(autouse=True)
def clear_firestore_cache() -> None:
    """Limpia el caché de funciones de Firestore en Streamlit antes de cada prueba."""
    with contextlib.suppress(Exception):
        get_cached_dwh_catalog.clear()


class TestFirestoreCredentialsAndClient:
    """Pruebas para inicialización y credenciales de Firestore."""

    def test_get_credentials_from_secrets_success(self) -> None:
        mock_secrets = {
            "gcp_service_account": {
                "type": "service_account",
                "project_id": "test-proj",
                "client_email": "test@test-proj.iam.gserviceaccount.com",
                "private_key": "-----BEGIN PRIVATE KEY-----\nMIIEvgIBA\n-----END PRIVATE KEY-----\n",
            }
        }
        with patch.object(st, "secrets", mock_secrets), patch(
            "google.oauth2.service_account.Credentials.from_service_account_info"
        ) as mock_from_info:
            mock_from_info.return_value = MagicMock()
            creds = _get_credentials_from_secrets()
            assert creds is not None
            mock_from_info.assert_called_once()

    def test_get_credentials_from_secrets_absent(self) -> None:
        with patch.object(st, "secrets", {}):
            assert _get_credentials_from_secrets() is None

    @patch("google.cloud.firestore.Client")
    def test_get_firestore_client_with_secrets(self, mock_fs_class: MagicMock) -> None:
        mock_creds = MagicMock(project_id="test-proj")
        with patch("streamlit_app.utils.firestore_client._get_credentials_from_secrets", return_value=mock_creds):
            client = get_firestore_client(database="test-db", project="test-proj")
            assert client is not None
            mock_fs_class.assert_called_once_with(
                database="test-db",
                project="test-proj",
                credentials=mock_creds,
            )

    @patch("google.cloud.firestore.Client")
    def test_get_firestore_client_fallback_file(
        self, mock_fs_class: MagicMock, tmp_path: Path
    ) -> None:
        key_file = tmp_path / "sa_fs.json"
        key_file.write_text('{"project_id": "fs-proj"}', encoding="utf-8")

        with patch("streamlit_app.utils.firestore_client._get_credentials_from_secrets", return_value=None), patch.dict(
            "os.environ", {"GCP_SA_KEY_PATH": str(key_file), "FIRESTORE_DATABASE": "env-db"}
        ), patch("google.oauth2.service_account.Credentials.from_service_account_file") as mock_from_file:
            mock_from_file.return_value = MagicMock(project_id="fs-proj")
            client = get_firestore_client()
            assert client is not None
            mock_fs_class.assert_called_once()


class TestGetCachedDwhCatalog:
    """Pruebas para consulta y caching de DWH catalog."""

    @patch("streamlit_app.utils.firestore_client.get_firestore_client")
    def test_get_cached_dwh_catalog_found(self, mock_get_client: MagicMock) -> None:
        mock_client = MagicMock()
        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = {
            "code": "comercio_exterior",
            "name": "Comercio Exterior de Bolivia",
            "description": "Datos oficiales de exportaciones e importaciones.",
            "bq_dataset": "comercio_exterior",
            "bq_project": "insight-bolivia",
            "status": "active",
            "data_source": "INE",
            "record_count": 2150000,
        }
        mock_client.collection.return_value.document.return_value.get.return_value = mock_doc
        mock_get_client.return_value = mock_client

        catalog = get_cached_dwh_catalog("comercio_exterior")
        assert catalog is not None
        assert isinstance(catalog, DwhCatalog)
        assert catalog.code == "comercio_exterior"
        assert catalog.record_count == 2150000

    @patch("streamlit_app.utils.firestore_client.get_firestore_client")
    def test_get_cached_dwh_catalog_not_found(self, mock_get_client: MagicMock) -> None:
        mock_client = MagicMock()
        mock_doc = MagicMock()
        mock_doc.exists = False
        mock_client.collection.return_value.document.return_value.get.return_value = mock_doc
        mock_get_client.return_value = mock_client

        catalog = get_cached_dwh_catalog("inexistente")
        assert catalog is None

    @patch("streamlit_app.utils.firestore_client.get_firestore_client")
    def test_get_cached_dwh_catalog_exception_handled(self, mock_get_client: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client.collection.side_effect = RuntimeError("Firestore unavailable")
        mock_get_client.return_value = mock_client

        catalog = get_cached_dwh_catalog("comercio_exterior_err")
        assert catalog is None


class TestSessionAndTelemetry:
    """Pruebas para gestión de sesión y telemetría."""

    def test_get_session_id_initializes_state(self) -> None:
        with patch.object(st, "session_state", {}):
            sid1 = get_session_id()
            assert sid1 is not None
            assert len(sid1) > 10
            sid2 = get_session_id()
            assert sid1 == sid2

    @patch("streamlit_app.utils.firestore_client.get_firestore_client")
    def test_log_ui_event_success(self, mock_get_client: MagicMock) -> None:
        mock_client = MagicMock()
        mock_doc_ref = MagicMock()
        mock_doc_ref.id = "analytics-doc-123"
        mock_client.collection.return_value.document.return_value = mock_doc_ref
        mock_get_client.return_value = mock_client

        doc_id = log_ui_event(
            session_id="session-xyz",
            page="home",
            event_type="page_view",
            event_data={"theme": "dark"},
        )
        assert doc_id == "analytics-doc-123"
        mock_doc_ref.set.assert_called_once()

    @patch("streamlit_app.utils.firestore_client.get_firestore_client")
    def test_log_ui_event_defensive_on_error(self, mock_get_client: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client.collection.side_effect = RuntimeError("Network partition")
        mock_get_client.return_value = mock_client

        doc_id = log_ui_event(
            session_id="session-xyz",
            page="01_balanza",
            event_type="filter_apply",
        )
        assert doc_id is None
