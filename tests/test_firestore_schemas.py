"""Pruebas unitarias para esquemas Pydantic e índices de Google Cloud Firestore.

Valida:
1. Conformidad del archivo `firestore/indexes/firestore.indexes.json` con la especificación de Firebase.
2. Modelos Pydantic (`UserProfile`, `CatalogView`, `DwhCatalog`, `AuditLog`, `UiAnalytics`).
3. Validaciones de tipos, campos obligatorios, restricciones RBAC y métodos de serialización Firestore.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.firestore_models import (
    AuditLog,
    CatalogView,
    DwhCatalog,
    FirestoreBaseModel,
    UiAnalytics,
    UserProfile,
    UserRole,
)


# ==============================================================================
# 1. Pruebas de Configuración de Índices (firestore.indexes.json)
# ==============================================================================
class TestFirestoreIndexesFile:
    """Verifica que el archivo de índices compuestos exista y cumpla la especificación."""

    @pytest.fixture
    def indexes_file_path(self) -> Path:
        """Ruta al archivo firestore.indexes.json."""
        project_root = Path(__file__).resolve().parent.parent
        return project_root / "firestore" / "indexes" / "firestore.indexes.json"

    def test_indexes_file_exists(self, indexes_file_path: Path):
        """Verifica que el archivo exista en la ruta especificada."""
        assert indexes_file_path.is_file(), f"No se encontró el archivo {indexes_file_path}"

    def test_indexes_file_is_valid_json(self, indexes_file_path: Path):
        """Verifica que el archivo sea JSON sintácticamente válido."""
        content = indexes_file_path.read_text(encoding="utf-8")
        data = json.loads(content)
        assert isinstance(data, dict)
        assert "indexes" in data
        assert "fieldOverrides" in data
        assert isinstance(data["indexes"], list)
        assert isinstance(data["fieldOverrides"], list)

    def test_indexes_definitions_match_architecture(self, indexes_file_path: Path):
        """Verifica que los índices compuestos requeridos estén exactamente definidos."""
        data = json.loads(indexes_file_path.read_text(encoding="utf-8"))
        indexes = data["indexes"]
        assert len(indexes) == 4

        # 1. audit_log: (user_id ASC, created_at DESC)
        idx_audit_user = next(
            (
                idx
                for idx in indexes
                if idx["collectionGroup"] == "audit_log"
                and idx["fields"]
                == [
                    {"fieldPath": "user_id", "order": "ASCENDING"},
                    {"fieldPath": "created_at", "order": "DESCENDING"},
                ]
            ),
            None,
        )
        assert idx_audit_user is not None
        assert idx_audit_user["queryScope"] == "COLLECTION"

        # 2. audit_log: (action ASC, created_at DESC)
        idx_audit_action = next(
            (
                idx
                for idx in indexes
                if idx["collectionGroup"] == "audit_log"
                and idx["fields"]
                == [
                    {"fieldPath": "action", "order": "ASCENDING"},
                    {"fieldPath": "created_at", "order": "DESCENDING"},
                ]
            ),
            None,
        )
        assert idx_audit_action is not None
        assert idx_audit_action["queryScope"] == "COLLECTION"

        # 3. ui_analytics: (session_id ASC, created_at ASC)
        idx_ui_session = next(
            (
                idx
                for idx in indexes
                if idx["collectionGroup"] == "ui_analytics"
                and idx["fields"]
                == [
                    {"fieldPath": "session_id", "order": "ASCENDING"},
                    {"fieldPath": "created_at", "order": "ASCENDING"},
                ]
            ),
            None,
        )
        assert idx_ui_session is not None
        assert idx_ui_session["queryScope"] == "COLLECTION"

        # 4. ui_analytics: (page ASC, created_at DESC)
        idx_ui_page = next(
            (
                idx
                for idx in indexes
                if idx["collectionGroup"] == "ui_analytics"
                and idx["fields"]
                == [
                    {"fieldPath": "page", "order": "ASCENDING"},
                    {"fieldPath": "created_at", "order": "DESCENDING"},
                ]
            ),
            None,
        )
        assert idx_ui_page is not None
        assert idx_ui_page["queryScope"] == "COLLECTION"


# ==============================================================================
# 2. Pruebas de UserRole y UserProfile
# ==============================================================================
class TestUserProfileSchema:
    """Pruebas del modelo UserProfile."""

    def test_valid_user_profile_creation(self):
        """Valida la creación correcta de un perfil con datos completos."""
        now = datetime.now(UTC)
        profile = UserProfile(
            display_name="Paolo Roman",
            email="paolo@ejemplo.com",
            organization="InsightBolivia Core Team",
            role=UserRole.ADMIN,
            created_at=now,
            updated_at=now,
        )
        assert profile.display_name == "Paolo Roman"
        assert profile.email == "paolo@ejemplo.com"
        assert profile.role == "admin"
        assert profile.organization == "InsightBolivia Core Team"
        assert profile.created_at == now

    def test_user_profile_defaults(self):
        """Valida los valores por defecto de UserProfile."""
        profile = UserProfile(
            display_name="Analista INE",
            email="analista@ine.gob.bo",
        )
        assert profile.role == UserRole.VIEWER
        assert profile.organization == ""
        assert isinstance(profile.created_at, datetime)
        assert isinstance(profile.updated_at, datetime)

    def test_user_profile_string_role_coercion(self):
        """Valida que los roles pasados como string válido se conviertan al Enum/valor."""
        profile = UserProfile(
            display_name="Investigador",
            email="inv@udape.gob.bo",
            role="analyst",  # type: ignore[arg-type]
        )
        assert profile.role == "analyst"
        assert profile.role == UserRole.ANALYST

    @pytest.mark.parametrize(
        "invalid_email",
        [
            "not-an-email",
            "@domain.com",
            "user@",
            "user@domain",
            "user@.com",
            "   ",
        ],
    )
    def test_invalid_email_raises_validation_error(self, invalid_email: str):
        """Verifica que correos con formato inválido lancen error."""
        with pytest.raises(ValidationError):
            UserProfile(
                display_name="Usuario Invalido",
                email=invalid_email,
            )

    def test_blank_display_name_raises_error(self):
        """Verifica que display_name vacío o con puros espacios falle."""
        with pytest.raises(ValidationError):
            UserProfile(
                display_name="   ",
                email="user@test.com",
            )

    def test_invalid_role_raises_error(self):
        """Verifica que roles no contemplados en RBAC lancen error."""
        with pytest.raises(ValidationError):
            UserProfile(
                display_name="Hacker",
                email="hacker@test.com",
                role="superadmin",  # type: ignore[arg-type]
            )

    def test_extra_fields_forbidden(self):
        """Verifica que campos no declarados sean rechazados."""
        with pytest.raises(ValidationError):
            UserProfile(
                display_name="User",
                email="user@test.com",
                unknown_field="injected",  # type: ignore[call-arg]
            )

    def test_serialization_and_deserialization(self):
        """Valida el ciclo de serialización to_firestore_dict y from_firestore_dict."""
        data = {
            "display_name": "Maria Perez",
            "email": "maria@ine.gob.bo",
            "organization": "INE",
            "role": "analyst",
            "created_at": datetime(2026, 1, 15, 12, 0, tzinfo=UTC),
            "updated_at": datetime(2026, 1, 15, 12, 0, tzinfo=UTC),
        }
        profile = UserProfile.from_firestore_dict(data)
        assert isinstance(profile, UserProfile)
        assert profile.email == "maria@ine.gob.bo"

        serialized = profile.to_firestore_dict()
        assert serialized["role"] == "analyst"
        assert serialized["display_name"] == "Maria Perez"


# ==============================================================================
# 3. Pruebas de CatalogView y DwhCatalog
# ==============================================================================
class TestDwhCatalogSchema:
    """Pruebas de los esquemas CatalogView y DwhCatalog."""

    def test_valid_catalog_view(self):
        """Valida instanciación de vista de catálogo con valores válidos."""
        view = CatalogView(
            view_name="vw_balanza_comercial_mensual",
            display_name="Balanza Comercial Mensual",
            description="Exportaciones vs Importaciones",
            bq_view_path="comercio_exterior.vw_balanza_comercial_mensual",
            chart_type="line",
            is_public=True,
            sort_order=1,
        )
        assert view.view_name == "vw_balanza_comercial_mensual"
        assert view.sort_order == 1
        assert view.is_public is True

    def test_catalog_view_invalid_sort_order(self):
        """Valida que sort_order < 1 lance ValidationError."""
        with pytest.raises(ValidationError):
            CatalogView(
                view_name="vw_test",
                display_name="Test",
                bq_view_path="dataset.vw_test",
                sort_order=0,  # type: ignore[arg-type]
            )

    def test_valid_dwh_catalog_creation(self):
        """Valida la creación de un catálogo completo con vistas anidadas."""
        now = datetime.now(UTC)
        catalog = DwhCatalog(
            code="comercio_exterior",
            name="Comercio Exterior de Bolivia",
            description="Datos del INE de exportaciones e importaciones.",
            bq_dataset="comercio_exterior",
            bq_project="insightbolivia-dwh",
            streamlit_url="https://insightbolivia.streamlit.app",
            icon="📦",
            status="active",
            data_source="INE - Instituto Nacional de Estadística",
            update_frequency="mensual",
            last_data_refresh=now,
            record_count=2150000,
            views=[
                CatalogView(
                    view_name="vw_balanza_comercial_mensual",
                    display_name="Balanza Comercial Mensual",
                    bq_view_path="comercio_exterior.vw_balanza_comercial_mensual",
                    chart_type="line",
                    sort_order=1,
                ),
                CatalogView(
                    view_name="vw_top_productos_exportados",
                    display_name="Top 10 Productos Exportados",
                    bq_view_path="comercio_exterior.vw_top_productos_exportados",
                    chart_type="bar",
                    sort_order=2,
                ),
            ],
        )
        assert catalog.code == "comercio_exterior"
        assert catalog.record_count == 2150000
        assert len(catalog.views) == 2
        assert catalog.views[0].view_name == "vw_balanza_comercial_mensual"

    def test_dwh_catalog_negative_record_count_fails(self):
        """Valida que record_count negativo sea rechazado."""
        with pytest.raises(ValidationError):
            DwhCatalog(
                code="comercio_exterior",
                name="Comercio Exterior",
                description="Desc",
                bq_dataset="comercio_exterior",
                data_source="INE",
                record_count=-10,  # type: ignore[arg-type]
            )

    @pytest.mark.parametrize("status", ["active", "inactive", "maintenance", "deprecated"])
    def test_dwh_catalog_valid_statuses(self, status: str):
        """Valida que los estados permitidos sean aceptados."""
        catalog = DwhCatalog(
            code="test_dwh",
            name="Test DWH",
            description="Desc",
            bq_dataset="test_ds",
            data_source="Fuente Test",
            status=status,
        )
        assert catalog.status == status

    def test_dwh_catalog_invalid_status_fails(self):
        """Valida que un estado no reconocido sea rechazado."""
        with pytest.raises(ValidationError):
            DwhCatalog(
                code="test_dwh",
                name="Test DWH",
                description="Desc",
                bq_dataset="test_ds",
                data_source="Fuente Test",
                status="non_existent_status",
            )

    def test_dwh_catalog_serialization_roundtrip(self):
        """Valida serialización y deserialización completa de DwhCatalog."""
        catalog = DwhCatalog(
            code="benchmark_regional",
            name="Benchmark Regional",
            description="Indicadores del Banco Mundial",
            bq_dataset="benchmark_regional",
            data_source="Banco Mundial",
            views=[
                CatalogView(
                    view_name="vw_comparativo",
                    display_name="Comparativo",
                    bq_view_path="benchmark_regional.vw_comparativo",
                )
            ],
        )
        data = catalog.to_firestore_dict()
        assert isinstance(data, dict)
        assert data["code"] == "benchmark_regional"
        assert len(data["views"]) == 1

        restored = DwhCatalog.from_firestore_dict(data)
        assert isinstance(restored, DwhCatalog)
        assert restored.views[0].view_name == "vw_comparativo"


# ==============================================================================
# 4. Pruebas de AuditLog
# ==============================================================================
class TestAuditLogSchema:
    """Pruebas del modelo AuditLog."""

    def test_valid_audit_log_creation(self):
        """Valida la creación de un registro de auditoría completo."""
        now = datetime.now(UTC)
        log = AuditLog(
            user_id="usr_abc123456",
            action="export_csv",
            resource_type="view",
            resource_id="vw_balanza_comercial_mensual",
            metadata={"rows_exported": 120, "filter_years": [2020, 2024]},
            ip_address="190.181.10.5",
            user_agent="Mozilla/5.0",
            created_at=now,
        )
        assert log.user_id == "usr_abc123456"
        assert log.action == "export_csv"
        assert log.metadata["rows_exported"] == 120
        assert log.created_at == now

    def test_audit_log_defaults(self):
        """Valida valores por defecto en AuditLog."""
        log = AuditLog(
            user_id="system",
            action="etl_load",
        )
        assert log.resource_type == "general"
        assert log.resource_id == ""
        assert log.metadata == {}
        assert log.ip_address == ""
        assert log.user_agent == ""
        assert isinstance(log.created_at, datetime)

    def test_audit_log_missing_required_fields_fails(self):
        """Valida que la omisión de user_id o action lance ValidationError."""
        with pytest.raises(ValidationError):
            AuditLog(user_id="user_123")  # type: ignore[call-arg]

        with pytest.raises(ValidationError):
            AuditLog(action="login")  # type: ignore[call-arg]

    def test_audit_log_serialization(self):
        """Valida serialización a diccionario para Firestore."""
        log = AuditLog(
            user_id="usr_999",
            action="login",
            resource_type="auth",
            resource_id="firebase_auth",
        )
        data = log.to_firestore_dict()
        assert data["user_id"] == "usr_999"
        assert data["action"] == "login"
        assert data["resource_type"] == "auth"


# ==============================================================================
# 5. Pruebas de UiAnalytics
# ==============================================================================
class TestUiAnalyticsSchema:
    """Pruebas del modelo UiAnalytics."""

    def test_valid_ui_analytics_creation(self):
        """Valida la creación de un evento de telemetría de UI."""
        now = datetime.now(UTC)
        event = UiAnalytics(
            session_id="a5d89f21-729a-4c22-9f33-10d93021f11a",
            user_id=None,
            page="01_balanza_comercial",
            event_type="filter_apply",
            event_data={"year_range": [2018, 2024], "flow": "EXPORTACION"},
            duration_ms=240,
            created_at=now,
        )
        assert event.session_id == "a5d89f21-729a-4c22-9f33-10d93021f11a"
        assert event.user_id is None
        assert event.duration_ms == 240
        assert event.event_data["flow"] == "EXPORTACION"

    def test_ui_analytics_defaults(self):
        """Valida valores por defecto de UiAnalytics."""
        event = UiAnalytics(
            session_id="sess_123",
            page="home",
            event_type="page_view",
        )
        assert event.user_id is None
        assert event.duration_ms is None
        assert event.event_data == {}
        assert isinstance(event.created_at, datetime)

    def test_ui_analytics_negative_duration_fails(self):
        """Valida que una duración negativa en milisegundos falle."""
        with pytest.raises(ValidationError):
            UiAnalytics(
                session_id="sess_123",
                page="home",
                event_type="page_view",
                duration_ms=-50,  # type: ignore[arg-type]
            )

    def test_ui_analytics_exclude_none_serialization(self):
        """Valida exclusión de campos None al serializar si se solicita."""
        event = UiAnalytics(
            session_id="sess_123",
            page="home",
            event_type="page_view",
            user_id=None,
            duration_ms=None,
        )
        data_all = event.to_firestore_dict(exclude_none=False)
        assert "user_id" in data_all
        assert data_all["user_id"] is None

        data_clean = event.to_firestore_dict(exclude_none=True)
        assert "user_id" not in data_clean
        assert "duration_ms" not in data_clean
        assert "session_id" in data_clean


# ==============================================================================
# 6. Pruebas de FirestoreBaseModel
# ==============================================================================
class TestFirestoreBaseModel:
    """Pruebas para los comportamientos base de FirestoreBaseModel."""

    def test_validate_assignment(self):
        """Valida que la modificación posterior de atributos sea re-validada."""
        profile = UserProfile(
            display_name="Paolo",
            email="paolo@test.com",
            role=UserRole.VIEWER,
        )
        with pytest.raises(ValidationError):
            profile.role = "invalid_role"  # type: ignore[assignment]

    def test_base_model_subclass_direct_instantiation(self):
        """Valida que subclases de FirestoreBaseModel hereden métodos de serialización."""

        class CustomDoc(FirestoreBaseModel):
            title: str
            views_count: int = 0

        data = {"title": "Reporte Anual", "views_count": 42}
        model = CustomDoc.from_firestore_dict(data)
        assert isinstance(model, CustomDoc)
        assert model.title == "Reporte Anual"
        assert model.to_firestore_dict() == data

    def test_firestore_schemas_module_reexport(self):
        """Valida que src.firestore_schemas re-exporte todos los modelos correctamente."""
        import src.firestore_schemas as schemas

        assert schemas.UserProfile is UserProfile
        assert schemas.DwhCatalog is DwhCatalog
        assert schemas.CatalogView is CatalogView
        assert schemas.AuditLog is AuditLog
        assert schemas.UiAnalytics is UiAnalytics
        assert schemas.UserRole is UserRole
        assert "UserProfile" in schemas.__all__
