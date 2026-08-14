"""Pruebas unitarias para el cliente helper de Google Cloud Firestore (`src/firestore_client.py`).

Verifica de forma 100% aislada con mocks (`unittest.mock.MagicMock`):
1. Inicialización de cliente (`get_firestore_client`) con ADC, Service Account JSON y variables de entorno.
2. Consulta de catálogo (`get_dwh_catalog` y `list_dwh_catalogs`).
3. Actualización de sincronización (`update_last_refresh`).
4. Registro de auditoría (`log_audit_event`).
5. Telemetría de usuario (`record_ui_event`).
6. Perfiles de usuario (`get_user_profile` y `upsert_user_profile`).
7. Manejo robusto de excepciones y validaciones de tipos.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from src.firestore_client import (
    COLLECTION_AUDIT_LOG,
    COLLECTION_DWH_CATALOG,
    COLLECTION_UI_ANALYTICS,
    COLLECTION_USER_PROFILES,
    get_dwh_catalog,
    get_firestore_client,
    get_user_profile,
    list_dwh_catalogs,
    log_audit_event,
    record_ui_event,
    update_last_refresh,
    upsert_user_profile,
)
from src.firestore_models import DwhCatalog, UserProfile, UserRole


# ==============================================================================
# 1. Pruebas de Inicialización de Cliente (get_firestore_client)
# ==============================================================================
class TestGetFirestoreClient:
    """Verifica los diferentes mecanismos de autenticación e inicialización de Firestore."""

    @patch("src.firestore_client.firestore.Client")
    def test_default_env_initialization(self, mock_client_cls: MagicMock) -> None:
        """Inicializa con valores por defecto cuando no hay variables de entorno."""
        with patch.dict("os.environ", {}, clear=True):
            client = get_firestore_client()
            assert client is not None
            mock_client_cls.assert_called_once_with(database="(default)")

    @patch("src.firestore_client.firestore.Client")
    def test_custom_env_database_and_project(self, mock_client_cls: MagicMock) -> None:
        """Utiliza variables de entorno personalizadas para base de datos y proyecto."""
        env = {
            "FIRESTORE_DATABASE": "analytics-db",
            "GOOGLE_CLOUD_PROJECT": "insight-bolivia-prod",
        }
        with patch.dict("os.environ", env, clear=True):
            client = get_firestore_client()
            assert client is not None
            mock_client_cls.assert_called_once_with(database="analytics-db", project="insight-bolivia-prod")

    @patch("src.firestore_client.firestore.Client")
    def test_explicit_args_override_env(self, mock_client_cls: MagicMock) -> None:
        """Los argumentos explícitos tienen precedencia sobre las variables de entorno."""
        env = {
            "FIRESTORE_DATABASE": "env-db",
            "GOOGLE_CLOUD_PROJECT": "env-project",
        }
        with patch.dict("os.environ", env, clear=True):
            get_firestore_client(database="explicit-db", project="explicit-project")
            mock_client_cls.assert_called_once_with(database="explicit-db", project="explicit-project")

    @patch("src.firestore_client.firestore.Client")
    def test_gcp_project_id_fallback_env(self, mock_client_cls: MagicMock) -> None:
        """Usa GCP_PROJECT_ID si GOOGLE_CLOUD_PROJECT no está definido."""
        env = {"GCP_PROJECT_ID": "gcp-fallback-project"}
        with patch.dict("os.environ", env, clear=True):
            get_firestore_client()
            mock_client_cls.assert_called_once_with(database="(default)", project="gcp-fallback-project")

    @patch("src.firestore_client.service_account.Credentials.from_service_account_file")
    @patch("src.firestore_client.firestore.Client")
    def test_service_account_file_via_arg(
        self,
        mock_client_cls: MagicMock,
        mock_creds_fn: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Carga credenciales desde archivo especificado en credentials_path."""
        key_file = tmp_path / "test_sa_key.json"
        key_file.write_text("{}", encoding="utf-8")

        mock_creds = MagicMock()
        mock_creds.project_id = "key-project-id"
        mock_creds_fn.return_value = mock_creds

        get_firestore_client(credentials_path=key_file)

        mock_creds_fn.assert_called_once_with(str(key_file))
        mock_client_cls.assert_called_once_with(
            database="(default)",
            project="key-project-id",
            credentials=mock_creds,
        )

    @patch("src.firestore_client.service_account.Credentials.from_service_account_file")
    @patch("src.firestore_client.firestore.Client")
    def test_service_account_file_via_env(
        self,
        mock_client_cls: MagicMock,
        mock_creds_fn: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Carga credenciales desde variable de entorno GCP_SA_KEY_PATH."""
        key_file = tmp_path / "env_sa_key.json"
        key_file.write_text("{}", encoding="utf-8")

        mock_creds = MagicMock()
        mock_creds.project_id = None
        mock_creds_fn.return_value = mock_creds

        with patch.dict("os.environ", {"GCP_SA_KEY_PATH": str(key_file)}):
            get_firestore_client(project="explicit-proj")

        mock_creds_fn.assert_called_once_with(str(key_file))
        mock_client_cls.assert_called_once_with(
            database="(default)",
            project="explicit-proj",
            credentials=mock_creds,
        )

    def test_service_account_file_not_found_raises(self) -> None:
        """Lanza FileNotFoundError si el archivo de credenciales no existe."""
        non_existent = Path("non_existent_key_file_xyz.json")
        with pytest.raises(FileNotFoundError, match="No se encontró el archivo de credenciales"):
            get_firestore_client(credentials_path=non_existent)


# ==============================================================================
# 2. Pruebas de Consulta de Catálogo (get_dwh_catalog, list_dwh_catalogs)
# ==============================================================================
class TestGetDwhCatalog:
    """Verifica la consulta unitaria y listado de Data Warehouses."""

    @pytest.fixture
    def mock_catalog_dict(self) -> dict:
        """Datos de prueba válidos para un DwhCatalog."""
        return {
            "id": "comercio_exterior",
            "code": "comercio_exterior",
            "name": "Comercio Exterior de Bolivia",
            "description": "Datos de importaciones y exportaciones del INE.",
            "bq_dataset": "comercio_exterior",
            "bq_project": "insight-bolivia",
            "streamlit_url": "https://insightbolivia.streamlit.app",
            "icon": "📦",
            "status": "active",
            "data_source": "INE",
            "update_frequency": "mensual",
            "last_data_refresh": "2026-08-01T12:00:00Z",
            "record_count": 150000,
            "views": [
                {
                    "view_name": "vw_balanza_comercial_mensual",
                    "display_name": "Balanza Comercial Mensual",
                    "description": "Balanza mensual FOB - CIF",
                    "bq_view_path": "comercio_exterior.vw_balanza_comercial_mensual",
                    "chart_type": "line",
                    "is_public": True,
                    "sort_order": 1,
                }
            ],
        }

    def test_get_existing_dwh_catalog(self, mock_catalog_dict: dict) -> None:
        """Retorna una instancia de DwhCatalog cuando el documento existe."""
        mock_client = MagicMock()
        mock_doc_ref = MagicMock()
        mock_doc_snap = MagicMock()

        mock_doc_snap.exists = True
        mock_doc_snap.to_dict.return_value = mock_catalog_dict
        mock_doc_ref.get.return_value = mock_doc_snap
        mock_client.collection.return_value.document.return_value = mock_doc_ref

        result = get_dwh_catalog("comercio_exterior", client=mock_client)

        assert result is not None
        assert isinstance(result, DwhCatalog)
        assert result.code == "comercio_exterior"
        assert result.record_count == 150000
        assert len(result.views) == 1
        assert result.views[0].view_name == "vw_balanza_comercial_mensual"

        mock_client.collection.assert_called_once_with(COLLECTION_DWH_CATALOG)
        mock_client.collection().document.assert_called_once_with("comercio_exterior")

    def test_get_non_existing_dwh_catalog(self) -> None:
        """Retorna None cuando el documento no existe en Firestore."""
        mock_client = MagicMock()
        mock_doc_ref = MagicMock()
        mock_doc_snap = MagicMock()

        mock_doc_snap.exists = False
        mock_doc_ref.get.return_value = mock_doc_snap
        mock_client.collection.return_value.document.return_value = mock_doc_ref

        result = get_dwh_catalog("non_existent_dwh", client=mock_client)
        assert result is None

    @patch("src.firestore_client.get_firestore_client")
    def test_get_dwh_catalog_auto_inits_client(self, mock_get_client: MagicMock, mock_catalog_dict: dict) -> None:
        """Inicializa automáticamente el cliente si client=None."""
        mock_client = MagicMock()
        mock_doc_ref = MagicMock()
        mock_doc_snap = MagicMock()
        mock_doc_snap.exists = True
        mock_doc_snap.to_dict.return_value = mock_catalog_dict
        mock_doc_ref.get.return_value = mock_doc_snap
        mock_client.collection.return_value.document.return_value = mock_doc_ref
        mock_get_client.return_value = mock_client

        result = get_dwh_catalog("comercio_exterior", client=None)
        assert result is not None
        mock_get_client.assert_called_once()

    @pytest.mark.parametrize("invalid_code", ["", "   ", None, 123])
    def test_get_dwh_catalog_invalid_code_raises_value_error(self, invalid_code: str | None) -> None:
        """Lanza ValueError si el código es inválido o no es cadena."""
        with pytest.raises(ValueError, match="El código del Data Warehouse"):
            get_dwh_catalog(invalid_code)  # type: ignore[arg-type]


class TestListDwhCatalogs:
    """Verifica el listado y filtrado de Data Warehouses."""

    @pytest.fixture
    def mock_catalogs_list(self) -> list[dict]:
        """Lista de diccionarios con catálogos de prueba."""
        return [
            {
                "code": "comercio_exterior",
                "name": "Comercio Exterior",
                "description": "Comercio exterior",
                "bq_dataset": "comercio_exterior",
                "status": "active",
                "data_source": "INE",
            },
            {
                "code": "benchmark_regional",
                "name": "Benchmark Regional",
                "description": "Indicadores BM / CEPAL",
                "bq_dataset": "benchmark_regional",
                "status": "maintenance",
                "data_source": "Banco Mundial",
            },
        ]

    def test_list_all_dwh_catalogs(self, mock_catalogs_list: list[dict]) -> None:
        """Lista todos los catálogos sin filtro."""
        mock_client = MagicMock()
        mock_col_ref = MagicMock()

        snaps = []
        for item in mock_catalogs_list:
            s = MagicMock()
            s.to_dict.return_value = item
            snaps.append(s)

        mock_col_ref.stream.return_value = snaps
        mock_client.collection.return_value = mock_col_ref

        results = list_dwh_catalogs(client=mock_client)
        assert len(results) == 2
        assert results[0].code == "comercio_exterior"
        assert results[1].code == "benchmark_regional"
        mock_col_ref.stream.assert_called_once()

    @patch("src.firestore_client.firestore.FieldFilter")
    def test_list_dwh_catalogs_with_status_filter(
        self,
        mock_filter_cls: MagicMock,
        mock_catalogs_list: list[dict],
    ) -> None:
        """Aplica filtro por status cuando se proporciona."""
        mock_client = MagicMock()
        mock_col_ref = MagicMock()
        mock_query = MagicMock()

        s = MagicMock()
        s.to_dict.return_value = mock_catalogs_list[0]
        mock_query.stream.return_value = [s]
        mock_col_ref.where.return_value = mock_query
        mock_client.collection.return_value = mock_col_ref

        results = list_dwh_catalogs(status="active", client=mock_client)
        assert len(results) == 1
        assert results[0].code == "comercio_exterior"
        mock_col_ref.where.assert_called_once()

    @patch("src.firestore_client.get_firestore_client")
    def test_list_dwh_catalogs_auto_inits_client(self, mock_get_client: MagicMock) -> None:
        """Inicializa automáticamente el cliente cuando es None."""
        mock_client = MagicMock()
        mock_col_ref = MagicMock()
        mock_col_ref.stream.return_value = []
        mock_client.collection.return_value = mock_col_ref
        mock_get_client.return_value = mock_client

        results = list_dwh_catalogs(client=None)
        assert results == []
        mock_get_client.assert_called_once()


# ==============================================================================
# 3. Pruebas de Actualización de Sincronización (update_last_refresh)
# ==============================================================================
class TestUpdateLastRefresh:
    """Verifica la actualización de metadatos de sincronización tras el ETL."""

    def test_update_last_refresh_with_timestamp_and_count(self) -> None:
        """Actualiza exitosamente con timestamp y record_count explícitos."""
        mock_client = MagicMock()
        mock_doc_ref = MagicMock()
        mock_doc_snap = MagicMock()

        mock_doc_snap.exists = True
        mock_doc_ref.get.return_value = mock_doc_snap
        mock_client.collection.return_value.document.return_value = mock_doc_ref

        custom_time = datetime(2026, 8, 15, 10, 30, 0, tzinfo=UTC)
        result = update_last_refresh(
            code="comercio_exterior",
            timestamp=custom_time,
            record_count=200000,
            client=mock_client,
        )

        assert result is True
        mock_doc_ref.update.assert_called_once()
        call_args = mock_doc_ref.update.call_args[0][0]
        assert call_args["last_data_refresh"] == custom_time
        assert call_args["record_count"] == 200000
        assert "updated_at" in call_args

    def test_update_last_refresh_default_timestamp(self) -> None:
        """Usa datetime actual (UTC) si timestamp es None."""
        mock_client = MagicMock()
        mock_doc_ref = MagicMock()
        mock_doc_snap = MagicMock()

        mock_doc_snap.exists = True
        mock_doc_ref.get.return_value = mock_doc_snap
        mock_client.collection.return_value.document.return_value = mock_doc_ref

        result = update_last_refresh("comercio_exterior", client=mock_client)
        assert result is True
        call_args = mock_doc_ref.update.call_args[0][0]
        assert isinstance(call_args["last_data_refresh"], datetime)
        assert "record_count" not in call_args

    def test_update_last_refresh_non_existing_doc_raises_key_error(self) -> None:
        """Lanza KeyError si el Data Warehouse no existe en el catálogo."""
        mock_client = MagicMock()
        mock_doc_ref = MagicMock()
        mock_doc_snap = MagicMock()

        mock_doc_snap.exists = False
        mock_doc_ref.get.return_value = mock_doc_snap
        mock_client.collection.return_value.document.return_value = mock_doc_ref

        with pytest.raises(KeyError, match="No se encontró el Data Warehouse"):
            update_last_refresh("missing_dwh", client=mock_client)

    @pytest.mark.parametrize("invalid_code", ["", "  ", None, 999])
    def test_update_last_refresh_invalid_code_raises_value_error(self, invalid_code: str | None) -> None:
        """Lanza ValueError si el código es inválido."""
        with pytest.raises(ValueError, match="El código del Data Warehouse"):
            update_last_refresh(invalid_code)  # type: ignore[arg-type]

    def test_update_last_refresh_negative_record_count_raises_value_error(self) -> None:
        """Lanza ValueError si record_count es negativo."""
        with pytest.raises(ValueError, match="no puede ser negativo"):
            update_last_refresh("comercio_exterior", record_count=-5)

    @patch("src.firestore_client.get_firestore_client")
    def test_update_last_refresh_auto_inits_client(self, mock_get_client: MagicMock) -> None:
        """Inicializa automáticamente el cliente cuando client=None."""
        mock_client = MagicMock()
        mock_doc_ref = MagicMock()
        mock_doc_snap = MagicMock()
        mock_doc_snap.exists = True
        mock_doc_ref.get.return_value = mock_doc_snap
        mock_client.collection.return_value.document.return_value = mock_doc_ref
        mock_get_client.return_value = mock_client

        result = update_last_refresh("comercio_exterior", client=None)
        assert result is True
        mock_get_client.assert_called_once()


# ==============================================================================
# 4. Pruebas de Registro de Auditoría (log_audit_event)
# ==============================================================================
class TestLogAuditEvent:
    """Verifica la persistencia de logs inmutables de auditoría en audit_log."""

    def test_log_audit_event_success(self) -> None:
        """Registra un evento de auditoría con todos sus parámetros."""
        mock_client = MagicMock()
        mock_col_ref = MagicMock()
        mock_doc_ref = MagicMock()

        mock_doc_ref.id = "audit_doc_12345"
        mock_col_ref.document.return_value = mock_doc_ref
        mock_client.collection.return_value = mock_col_ref

        doc_id = log_audit_event(
            action="etl_load",
            resource_type="dataset",
            resource_id="comercio_exterior.fact_exportaciones",
            metadata={"rows_inserted": 5000, "status": "success"},
            user_id="github-actions-bot",
            ip_address="192.168.1.100",
            user_agent="GitHub-Actions-Runner/2.0",
            client=mock_client,
        )

        assert doc_id == "audit_doc_12345"
        mock_client.collection.assert_called_once_with(COLLECTION_AUDIT_LOG)
        mock_doc_ref.set.assert_called_once()

        payload = mock_doc_ref.set.call_args[0][0]
        assert payload["action"] == "etl_load"
        assert payload["user_id"] == "github-actions-bot"
        assert payload["resource_type"] == "dataset"
        assert payload["metadata"]["rows_inserted"] == 5000
        assert "created_at" in payload

    def test_log_audit_event_default_values(self) -> None:
        """Registra un evento con valores predeterminados (system, general)."""
        mock_client = MagicMock()
        mock_col_ref = MagicMock()
        mock_doc_ref = MagicMock()

        mock_doc_ref.id = "audit_auto_999"
        mock_col_ref.document.return_value = mock_doc_ref
        mock_client.collection.return_value = mock_col_ref

        doc_id = log_audit_event(action="query", client=mock_client)
        assert doc_id == "audit_auto_999"

        payload = mock_doc_ref.set.call_args[0][0]
        assert payload["user_id"] == "system"
        assert payload["resource_type"] == "general"
        assert payload["metadata"] == {}

    def test_log_audit_event_empty_action_raises_validation_error(self) -> None:
        """Lanza ValidationError si action está vacío."""
        with pytest.raises(ValidationError):
            log_audit_event(action="")

    @patch("src.firestore_client.get_firestore_client")
    def test_log_audit_event_auto_inits_client(self, mock_get_client: MagicMock) -> None:
        """Inicializa automáticamente el cliente si client=None."""
        mock_client = MagicMock()
        mock_col_ref = MagicMock()
        mock_doc_ref = MagicMock()
        mock_doc_ref.id = "doc_id_auto"
        mock_col_ref.document.return_value = mock_doc_ref
        mock_client.collection.return_value = mock_col_ref
        mock_get_client.return_value = mock_client

        doc_id = log_audit_event(action="export", client=None)
        assert doc_id == "doc_id_auto"
        mock_get_client.assert_called_once()


# ==============================================================================
# 5. Pruebas de Telemetría UI (record_ui_event)
# ==============================================================================
class TestRecordUiEvent:
    """Verifica la persistencia de eventos de interacción en ui_analytics."""

    def test_record_ui_event_success(self) -> None:
        """Registra exitosamente un evento de telemetría completo."""
        mock_client = MagicMock()
        mock_col_ref = MagicMock()
        mock_doc_ref = MagicMock()

        mock_doc_ref.id = "ui_event_abc123"
        mock_col_ref.document.return_value = mock_doc_ref
        mock_client.collection.return_value = mock_col_ref

        doc_id = record_ui_event(
            session_id="550e8400-e29b-41d4-a716-446655440000",
            page="exportaciones",
            event_type="filter_apply",
            event_data={"year": 2026, "department": "La Paz"},
            duration_ms=120,
            user_id="user_uid_456",
            client=mock_client,
        )

        assert doc_id == "ui_event_abc123"
        mock_client.collection.assert_called_once_with(COLLECTION_UI_ANALYTICS)
        mock_doc_ref.set.assert_called_once()

        payload = mock_doc_ref.set.call_args[0][0]
        assert payload["session_id"] == "550e8400-e29b-41d4-a716-446655440000"
        assert payload["page"] == "exportaciones"
        assert payload["event_type"] == "filter_apply"
        assert payload["duration_ms"] == 120
        assert payload["user_id"] == "user_uid_456"

    def test_record_ui_event_anonymous_and_no_duration(self) -> None:
        """Registra un evento anónimo sin user_id ni duration_ms."""
        mock_client = MagicMock()
        mock_col_ref = MagicMock()
        mock_doc_ref = MagicMock()

        mock_doc_ref.id = "ui_event_anon"
        mock_col_ref.document.return_value = mock_doc_ref
        mock_client.collection.return_value = mock_col_ref

        doc_id = record_ui_event(
            session_id="anon-session-123",
            page="home",
            event_type="page_view",
            client=mock_client,
        )
        assert doc_id == "ui_event_anon"

        payload = mock_doc_ref.set.call_args[0][0]
        assert payload["user_id"] is None
        assert payload["duration_ms"] is None

    def test_record_ui_event_empty_page_raises_validation_error(self) -> None:
        """Lanza ValidationError si page está vacío."""
        with pytest.raises(ValidationError):
            record_ui_event(session_id="sess-1", page="", event_type="click")

    @patch("src.firestore_client.get_firestore_client")
    def test_record_ui_event_auto_inits_client(self, mock_get_client: MagicMock) -> None:
        """Inicializa automáticamente el cliente cuando es None."""
        mock_client = MagicMock()
        mock_col_ref = MagicMock()
        mock_doc_ref = MagicMock()
        mock_doc_ref.id = "auto_init_event"
        mock_col_ref.document.return_value = mock_doc_ref
        mock_client.collection.return_value = mock_col_ref
        mock_get_client.return_value = mock_client

        doc_id = record_ui_event(session_id="s1", page="p1", event_type="view", client=None)
        assert doc_id == "auto_init_event"
        mock_get_client.assert_called_once()


# ==============================================================================
# 6. Pruebas de Perfiles de Usuario (get_user_profile, upsert_user_profile)
# ==============================================================================
class TestUserProfileOperations:
    """Verifica la consulta y actualización de perfiles de usuario en user_profiles."""

    @pytest.fixture
    def mock_user_dict(self) -> dict:
        """Diccionario representativo de un documento en user_profiles."""
        return {
            "display_name": "Paolo Roman",
            "email": "paolo@insightbolivia.org",
            "organization": "InsightBolivia Core Team",
            "role": "admin",
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
        }

    def test_get_user_profile_existing(self, mock_user_dict: dict) -> None:
        """Retorna una instancia de UserProfile cuando el usuario existe."""
        mock_client = MagicMock()
        mock_doc_ref = MagicMock()
        mock_doc_snap = MagicMock()

        mock_doc_snap.exists = True
        mock_doc_snap.to_dict.return_value = mock_user_dict
        mock_doc_ref.get.return_value = mock_doc_snap
        mock_client.collection.return_value.document.return_value = mock_doc_ref

        profile = get_user_profile("firebase_uid_123", client=mock_client)
        assert profile is not None
        assert isinstance(profile, UserProfile)
        assert profile.display_name == "Paolo Roman"
        assert profile.role == UserRole.ADMIN

        mock_client.collection.assert_called_once_with(COLLECTION_USER_PROFILES)
        mock_client.collection().document.assert_called_once_with("firebase_uid_123")

    def test_get_user_profile_not_found(self) -> None:
        """Retorna None si el perfil no existe."""
        mock_client = MagicMock()
        mock_doc_ref = MagicMock()
        mock_doc_snap = MagicMock()

        mock_doc_snap.exists = False
        mock_doc_ref.get.return_value = mock_doc_snap
        mock_client.collection.return_value.document.return_value = mock_doc_ref

        profile = get_user_profile("missing_uid", client=mock_client)
        assert profile is None

    @pytest.mark.parametrize("invalid_uid", ["", "   ", None, 12345])
    def test_get_user_profile_invalid_uid_raises_value_error(self, invalid_uid: str | None) -> None:
        """Lanza ValueError si el user_id está vacío o es inválido."""
        with pytest.raises(ValueError, match="El 'user_id' debe ser una cadena no vacía"):
            get_user_profile(invalid_uid)  # type: ignore[arg-type]

    @patch("src.firestore_client.get_firestore_client")
    def test_get_user_profile_auto_inits_client(self, mock_get_client: MagicMock, mock_user_dict: dict) -> None:
        """Inicializa automáticamente el cliente si client=None."""
        mock_client = MagicMock()
        mock_doc_ref = MagicMock()
        mock_doc_snap = MagicMock()
        mock_doc_snap.exists = True
        mock_doc_snap.to_dict.return_value = mock_user_dict
        mock_doc_ref.get.return_value = mock_doc_snap
        mock_client.collection.return_value.document.return_value = mock_doc_ref
        mock_get_client.return_value = mock_client

        profile = get_user_profile("uid_auto", client=None)
        assert profile is not None
        mock_get_client.assert_called_once()

    def test_upsert_user_profile_with_model_instance(self) -> None:
        """Actualiza perfil pasando una instancia de UserProfile."""
        mock_client = MagicMock()
        mock_doc_ref = MagicMock()
        mock_client.collection.return_value.document.return_value = mock_doc_ref

        profile = UserProfile(
            display_name="Analista INE",
            email="analista@ine.gob.bo",
            organization="INE",
            role=UserRole.ANALYST,
        )

        res_uid = upsert_user_profile("uid_analista_1", profile, client=mock_client)
        assert res_uid == "uid_analista_1"
        mock_doc_ref.set.assert_called_once()
        assert mock_doc_ref.set.call_args[1]["merge"] is True

        payload = mock_doc_ref.set.call_args[0][0]
        assert payload["role"] == "analyst"
        assert payload["display_name"] == "Analista INE"

    def test_upsert_user_profile_with_dict(self) -> None:
        """Actualiza perfil pasando un diccionario válido."""
        mock_client = MagicMock()
        mock_doc_ref = MagicMock()
        mock_client.collection.return_value.document.return_value = mock_doc_ref

        profile_dict = {
            "display_name": "Lector Público",
            "email": "lector@ejemplo.com",
            "role": "viewer",
        }

        res_uid = upsert_user_profile("uid_viewer_2", profile_dict, client=mock_client)
        assert res_uid == "uid_viewer_2"
        mock_doc_ref.set.assert_called_once()
        payload = mock_doc_ref.set.call_args[0][0]
        assert payload["role"] == "viewer"

    @pytest.mark.parametrize("invalid_uid", ["", "  ", None, 123])
    def test_upsert_user_profile_invalid_uid_raises(self, invalid_uid: str | None) -> None:
        """Lanza ValueError si user_id es inválido."""
        with pytest.raises(ValueError, match="El 'user_id' debe ser una cadena no vacía"):
            upsert_user_profile(invalid_uid, {"display_name": "Test", "email": "test@test.com"})  # type: ignore[arg-type]

    def test_upsert_user_profile_invalid_type_raises(self) -> None:
        """Lanza ValueError si profile no es UserProfile ni dict."""
        with pytest.raises(ValueError, match="debe ser una instancia de UserProfile o dict"):
            upsert_user_profile("uid_test", [1, 2, 3])  # type: ignore[arg-type]

    @patch("src.firestore_client.get_firestore_client")
    def test_upsert_user_profile_auto_inits_client(self, mock_get_client: MagicMock) -> None:
        """Inicializa automáticamente el cliente si client=None."""
        mock_client = MagicMock()
        mock_doc_ref = MagicMock()
        mock_client.collection.return_value.document.return_value = mock_doc_ref
        mock_get_client.return_value = mock_client

        profile = UserProfile(display_name="Test", email="test@test.com")
        res_uid = upsert_user_profile("uid_test", profile, client=None)
        assert res_uid == "uid_test"
        mock_get_client.assert_called_once()
