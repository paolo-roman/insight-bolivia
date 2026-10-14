"""Pruebas unitarias y de simulación lógica para reglas de seguridad de Cloud Firestore.

Valida:
1. Conformidad sintáctica y estructural de `firestore/rules/firestore.rules` (Firestore Rules v2).
2. Definición y signaturas de funciones auxiliares (`isAuthenticated`, `getUserRole`, `isAdmin`).
3. Cobertura de reglas granulares por colección (`user_profiles`, `dwh_catalog`, `audit_log`, `ui_analytics`).
4. Evaluación lógica exhaustiva RBAC (anon, viewer, analyst, admin) para todas las operaciones CRUD.
5. Inmutabilidad estricta de colecciones append-only (`audit_log`, `ui_analytics`).
6. Aislamiento de perfiles de usuario y protección contra anti-patrones de seguridad.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

import pytest

from src.firestore_models import UserRole


# --- 1. Definición de Tipos y Modelo de Simulación de Reglas ---
class FirestoreOperation(StrEnum):
    """Operaciones estándar de lectura/escritura en Cloud Firestore."""

    GET = "get"
    LIST = "list"
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"

    @property
    def is_read(self) -> bool:
        """Determina si la operación pertenece al grupo 'read'."""
        return self in (FirestoreOperation.GET, FirestoreOperation.LIST)

    @property
    def is_write(self) -> bool:
        """Determina si la operación pertenece al grupo 'write'."""
        return self in (FirestoreOperation.CREATE, FirestoreOperation.UPDATE, FirestoreOperation.DELETE)


@dataclass(frozen=True)
class AuthContext:
    """Contexto de autenticación en la solicitud (request.auth)."""

    uid: str | None = None
    email: str | None = None

    @property
    def is_authenticated(self) -> bool:
        """Verifica si la solicitud contiene credenciales de usuario."""
        return self.uid is not None


class FirestoreRulesEvaluator:
    """Motor de evaluación y simulación lógica de las reglas declaradas en `firestore.rules`.

    Implementa el modelo semántico exacto de las reglas de seguridad v2 para InsightBolivia:
    - `isAuthenticated()`: request.auth != null
    - `getUserRole()`: get(/databases/$(database)/documents/user_profiles/$(request.auth.uid)).data.role
    - `isAdmin()`: isAuthenticated() && getUserRole() == 'admin'
    """

    def __init__(self, database_name: str = "(default)") -> None:
        self.database = database_name
        self._user_profiles_db: dict[str, dict[str, Any]] = {}

    def set_user_profile(self, uid: str, role: UserRole | str) -> None:
        """Registra un perfil de usuario simulado en la base de datos."""
        role_value = role.value if isinstance(role, UserRole) else role
        self._user_profiles_db[uid] = {"role": role_value}

    def clear_database(self) -> None:
        """Limpia el estado de perfiles simulados."""
        self._user_profiles_db.clear()

    # --- Helpers de Reglas ---
    def is_authenticated(self, auth: AuthContext | None) -> bool:
        """Helper: isAuthenticated()."""
        return auth is not None and auth.is_authenticated

    def get_user_role(self, auth: AuthContext | None) -> str | None:
        """Helper: getUserRole()."""
        if not self.is_authenticated(auth) or auth is None or auth.uid is None:
            return None
        profile = self._user_profiles_db.get(auth.uid)
        if profile is None:
            return None
        return str(profile.get("role"))

    def is_admin(self, auth: AuthContext | None) -> bool:
        """Helper: isAdmin()."""
        return self.is_authenticated(auth) and self.get_user_role(auth) == UserRole.ADMIN.value

    # --- Evaluador Principal ---
    def evaluate(
        self,
        collection: str,
        document_id: str,
        operation: FirestoreOperation,
        auth: AuthContext | None = None,
        incoming_data: dict[str, Any] | None = None,
    ) -> bool:
        """Evalúa si una operación está permitida según las reglas de seguridad actualizadas."""
        is_auth = self.is_authenticated(auth)
        is_adm = self.is_admin(auth)

        # 1. Colección: user_profiles/{userId} (BK-01: Protección RBAC)
        if collection == "user_profiles":
            user_id = document_id
            if not is_auth or auth is None:
                return False
            is_owner = auth.uid == user_id
            if operation.is_read:
                return is_owner or is_adm
            if operation == FirestoreOperation.CREATE:
                target_role = (incoming_data or {}).get("role", "viewer")
                return (is_owner and target_role == "viewer") or is_adm
            if operation == FirestoreOperation.UPDATE:
                if is_adm:
                    return True
                if not is_owner:
                    return False
                existing_role = self.get_user_role(auth) or "viewer"
                target_role = (incoming_data or {}).get("role", existing_role)
                return target_role == existing_role
            if operation == FirestoreOperation.DELETE:
                return is_adm
            return False

        # 2. Colección: dwh_catalog/{catalogId}
        if collection == "dwh_catalog":
            if operation.is_read:
                return True
            if operation.is_write:
                return is_adm
            return False

        # 3. Colección: audit_log/{logId} (BK-02: Requiere autenticación)
        if collection == "audit_log":
            if operation.is_read:
                return is_adm
            if operation == FirestoreOperation.CREATE:
                return is_auth
            return False

        # 4. Colección: ui_analytics/{eventId} (BK-02: Requiere autenticación)
        if collection == "ui_analytics":
            if operation.is_read:
                return is_adm
            if operation == FirestoreOperation.CREATE:
                return is_auth
            return False

        return False


# --- 2. Fixtures de Pruebas ---
@pytest.fixture
def rules_file_path() -> Path:
    """Ruta al archivo firestore.rules del proyecto."""
    project_root = Path(__file__).resolve().parent.parent
    return project_root / "firestore" / "rules" / "firestore.rules"


@pytest.fixture
def rules_content(rules_file_path: Path) -> str:
    """Contenido en texto plano del archivo firestore.rules."""
    assert rules_file_path.is_file(), f"No se encontró el archivo {rules_file_path}"
    return rules_file_path.read_text(encoding="utf-8")


@pytest.fixture
def evaluator() -> FirestoreRulesEvaluator:
    """Instancia del evaluador con base de datos simulada y usuarios precargados."""
    sim = FirestoreRulesEvaluator()
    sim.set_user_profile("usr_admin_01", UserRole.ADMIN)
    sim.set_user_profile("usr_analyst_01", UserRole.ANALYST)
    sim.set_user_profile("usr_viewer_01", UserRole.VIEWER)
    sim.set_user_profile("usr_no_role", "")
    return sim


# --- 3. Pruebas de Estructura y Sintaxis del Archivo firestore.rules ---
class TestFirestoreRulesFileSyntax:
    """Verifica que el archivo de reglas exista y cumpla la especificación formal v2."""

    def test_rules_file_exists(self, rules_file_path: Path):
        """Verifica que el archivo exista en la ruta firestore/rules/firestore.rules."""
        assert rules_file_path.is_file()

    def test_declares_rules_version_2(self, rules_content: str):
        """Verifica que se declare explícitamente rules_version = '2';."""
        lines = [line.strip() for line in rules_content.splitlines() if line.strip()]
        assert any(
            line.startswith("rules_version") and "'2'" in line or '"2"' in line for line in lines
        ), "Debe declarar rules_version = '2';"

    def test_declares_firestore_service(self, rules_content: str):
        """Verifica que el servicio esté declarado como cloud.firestore."""
        assert "service cloud.firestore" in rules_content

    def test_declares_database_documents_root_match(self, rules_content: str):
        """Verifica el bloque match raíz /databases/{database}/documents."""
        assert "match /databases/{database}/documents" in rules_content

    def test_balanced_braces_and_parentheses(self, rules_content: str):
        """Verifica que todas las llaves y paréntesis estén perfectamente balanceados."""
        # Limpieza básica de comentarios de línea para evitar falsos positivos
        clean_lines = []
        for line in rules_content.splitlines():
            line_no_comment = line.split("//")[0]
            clean_lines.append(line_no_comment)
        clean_text = "\n".join(clean_lines)

        assert clean_text.count("{") == clean_text.count("}"), "Llaves desbalanceadas en firestore.rules"
        assert clean_text.count("(") == clean_text.count(")"), "Paréntesis desbalanceados en firestore.rules"

    def test_all_helper_functions_declared(self, rules_content: str):
        """Verifica que las 3 funciones auxiliares requeridas estén declaradas."""
        assert "function isAuthenticated()" in rules_content
        assert "function getUserRole()" in rules_content
        assert "function isAdmin()" in rules_content

    def test_all_target_collections_declared(self, rules_content: str):
        """Verifica que las 4 colecciones requeridas posean su respectivo bloque match."""
        assert "match /user_profiles/{userId}" in rules_content
        assert "match /dwh_catalog/{catalogId}" in rules_content
        assert "match /audit_log/{logId}" in rules_content
        assert "match /ui_analytics/{eventId}" in rules_content

    def test_no_dangerous_global_wildcards(self, rules_content: str):
        """Verifica que no existan reglas comodín abiertas (allow read, write: if true;) en la raíz."""
        assert "match /{document=**}" not in rules_content
        assert "allow read, write: if true;" not in rules_content


# --- 4. Pruebas de Funciones Auxiliares (Helper Functions) ---
class TestHelperFunctions:
    """Pruebas unitarias sobre los métodos lógicos equivalentes a los helpers de Firestore."""

    def test_is_authenticated_true_when_auth_uid_present(self, evaluator: FirestoreRulesEvaluator):
        auth = AuthContext(uid="usr_viewer_01")
        assert evaluator.is_authenticated(auth) is True

    def test_is_authenticated_false_when_auth_none(self, evaluator: FirestoreRulesEvaluator):
        assert evaluator.is_authenticated(None) is False
        assert evaluator.is_authenticated(AuthContext(uid=None)) is False

    def test_get_user_role_returns_correct_role(self, evaluator: FirestoreRulesEvaluator):
        assert evaluator.get_user_role(AuthContext(uid="usr_admin_01")) == "admin"
        assert evaluator.get_user_role(AuthContext(uid="usr_analyst_01")) == "analyst"
        assert evaluator.get_user_role(AuthContext(uid="usr_viewer_01")) == "viewer"

    def test_get_user_role_returns_none_for_unknown_user(self, evaluator: FirestoreRulesEvaluator):
        assert evaluator.get_user_role(AuthContext(uid="usr_inexistente")) is None
        assert evaluator.get_user_role(None) is None

    def test_is_admin_true_only_for_admin_role(self, evaluator: FirestoreRulesEvaluator):
        assert evaluator.is_admin(AuthContext(uid="usr_admin_01")) is True
        assert evaluator.is_admin(AuthContext(uid="usr_analyst_01")) is False
        assert evaluator.is_admin(AuthContext(uid="usr_viewer_01")) is False
        assert evaluator.is_admin(AuthContext(uid="usr_no_role")) is False
        assert evaluator.is_admin(None) is False


# --- 5. Pruebas RBAC por Colección: user_profiles ---
class TestUserProfilesCollectionRules:
    """Reglas de user_profiles: Solo el propio usuario o admin puede leer/escribir."""

    def test_anonymous_cannot_read_or_write_profiles(self, evaluator: FirestoreRulesEvaluator):
        """Un usuario no autenticado no puede leer ni escribir ningún perfil."""
        for op in FirestoreOperation:
            assert evaluator.evaluate("user_profiles", "usr_viewer_01", op, auth=None) is False

    def test_user_can_read_and_update_own_profile(self, evaluator: FirestoreRulesEvaluator):
        """Un usuario regular puede leer y actualizar su propio perfil."""
        auth = AuthContext(uid="usr_viewer_01")
        assert evaluator.evaluate("user_profiles", "usr_viewer_01", FirestoreOperation.GET, auth=auth) is True
        assert evaluator.evaluate("user_profiles", "usr_viewer_01", FirestoreOperation.UPDATE, auth=auth) is True

    def test_privilege_escalation_blocked(self, evaluator: FirestoreRulesEvaluator):
        """BK-01: Un usuario regular no puede auto-asignarse rol admin en create ni update."""
        auth = AuthContext(uid="usr_viewer_01")
        assert (
            evaluator.evaluate(
                "user_profiles",
                "usr_viewer_01",
                FirestoreOperation.CREATE,
                auth=auth,
                incoming_data={"role": "admin"},
            )
            is False
        )
        assert (
            evaluator.evaluate(
                "user_profiles",
                "usr_viewer_01",
                FirestoreOperation.CREATE,
                auth=auth,
                incoming_data={"role": "viewer"},
            )
            is True
        )
        assert (
            evaluator.evaluate(
                "user_profiles",
                "usr_viewer_01",
                FirestoreOperation.UPDATE,
                auth=auth,
                incoming_data={"role": "admin"},
            )
            is False
        )
        assert (
            evaluator.evaluate(
                "user_profiles",
                "usr_viewer_01",
                FirestoreOperation.UPDATE,
                auth=auth,
                incoming_data={"role": "viewer"},
            )
            is True
        )
        assert evaluator.evaluate("user_profiles", "usr_viewer_01", FirestoreOperation.DELETE, auth=auth) is False

    def test_user_cannot_read_or_write_other_profile(self, evaluator: FirestoreRulesEvaluator):
        """Un usuario regular (viewer/analyst) no puede acceder a perfiles de otros usuarios."""
        viewer_auth = AuthContext(uid="usr_viewer_01")
        analyst_auth = AuthContext(uid="usr_analyst_01")

        for op in FirestoreOperation:
            assert evaluator.evaluate("user_profiles", "usr_analyst_01", op, auth=viewer_auth) is False
            assert evaluator.evaluate("user_profiles", "usr_viewer_01", op, auth=analyst_auth) is False

    def test_admin_can_read_and_write_any_profile(self, evaluator: FirestoreRulesEvaluator):
        """Un administrador puede leer y escribir el perfil de cualquier usuario."""
        admin_auth = AuthContext(uid="usr_admin_01")
        target_users = ["usr_admin_01", "usr_viewer_01", "usr_analyst_01", "usr_cualquiera"]

        for uid in target_users:
            for op in FirestoreOperation:
                assert evaluator.evaluate("user_profiles", uid, op, auth=admin_auth) is True


# --- 6. Pruebas RBAC por Colección: dwh_catalog ---
class TestDwhCatalogCollectionRules:
    """Reglas de dwh_catalog: Lectura pública general; escritura exclusiva para admin."""

    @pytest.mark.parametrize(
        "auth",
        [
            None,
            AuthContext(uid="usr_viewer_01"),
            AuthContext(uid="usr_analyst_01"),
            AuthContext(uid="usr_admin_01"),
        ],
    )
    def test_public_read_access_allowed_for_all(
        self, evaluator: FirestoreRulesEvaluator, auth: AuthContext | None
    ):
        """Cualquier cliente (anónimo, viewer, analyst, admin) puede leer el catálogo."""
        assert evaluator.evaluate("dwh_catalog", "comercio_exterior", FirestoreOperation.GET, auth=auth) is True
        assert evaluator.evaluate("dwh_catalog", "comercio_exterior", FirestoreOperation.LIST, auth=auth) is True

    @pytest.mark.parametrize(
        "auth",
        [
            None,
            AuthContext(uid="usr_viewer_01"),
            AuthContext(uid="usr_analyst_01"),
            AuthContext(uid="usr_desconocido"),
        ],
    )
    def test_write_access_denied_for_non_admins(
        self, evaluator: FirestoreRulesEvaluator, auth: AuthContext | None
    ):
        """Usuarios no administradores tienen estrictamente denegada la escritura en dwh_catalog."""
        for write_op in (FirestoreOperation.CREATE, FirestoreOperation.UPDATE, FirestoreOperation.DELETE):
            assert (
                evaluator.evaluate("dwh_catalog", "comercio_exterior", write_op, auth=auth) is False
            ), f"Operación {write_op} debió ser denegada para {auth}"

    def test_write_access_allowed_only_for_admin(self, evaluator: FirestoreRulesEvaluator):
        """Solo un usuario con rol admin puede crear, actualizar o eliminar registros del catálogo."""
        admin_auth = AuthContext(uid="usr_admin_01")
        for write_op in (FirestoreOperation.CREATE, FirestoreOperation.UPDATE, FirestoreOperation.DELETE):
            assert evaluator.evaluate("dwh_catalog", "comercio_exterior", write_op, auth=admin_auth) is True


# --- 7. Pruebas RBAC por Colección: audit_log (Inmutabilidad y Lectura Admin) ---
class TestAuditLogCollectionRules:
    """Reglas de audit_log: Lectura exclusiva admin; inserción autenticada; inmutable."""

    @pytest.mark.parametrize(
        "auth,expected",
        [
            (None, False),
            (AuthContext(uid="usr_viewer_01"), True),
            (AuthContext(uid="usr_analyst_01"), True),
            (AuthContext(uid="usr_admin_01"), True),
        ],
    )
    def test_create_requires_auth_mitigates_dos(
        self, evaluator: FirestoreRulesEvaluator, auth: AuthContext | None, expected: bool
    ):
        """BK-02: Se bloquea la creación anónima y se exige autenticación para mitigar DoS/Cost Bomb."""
        assert evaluator.evaluate("audit_log", "log_auto_123", FirestoreOperation.CREATE, auth=auth) is expected

    @pytest.mark.parametrize("auth", [None, AuthContext(uid="usr_viewer_01"), AuthContext(uid="usr_analyst_01")])
    def test_read_denied_for_non_admins(self, evaluator: FirestoreRulesEvaluator, auth: AuthContext | None):
        """Usuarios no administradores no pueden leer la bitácora de auditoría."""
        assert evaluator.evaluate("audit_log", "log_auto_123", FirestoreOperation.GET, auth=auth) is False
        assert evaluator.evaluate("audit_log", "log_auto_123", FirestoreOperation.LIST, auth=auth) is False

    def test_read_allowed_for_admin(self, evaluator: FirestoreRulesEvaluator):
        """Los administradores pueden leer la bitácora de auditoría."""
        admin_auth = AuthContext(uid="usr_admin_01")
        assert evaluator.evaluate("audit_log", "log_auto_123", FirestoreOperation.GET, auth=admin_auth) is True
        assert evaluator.evaluate("audit_log", "log_auto_123", FirestoreOperation.LIST, auth=admin_auth) is True

    @pytest.mark.parametrize(
        "auth",
        [None, AuthContext(uid="usr_viewer_01"), AuthContext(uid="usr_analyst_01"), AuthContext(uid="usr_admin_01")],
    )
    def test_update_and_delete_strictly_forbidden_immutable(
        self, evaluator: FirestoreRulesEvaluator, auth: AuthContext | None
    ):
        """Garantía de inmutabilidad: NADIE puede modificar o eliminar logs de auditoría."""
        assert evaluator.evaluate("audit_log", "log_auto_123", FirestoreOperation.UPDATE, auth=auth) is False
        assert evaluator.evaluate("audit_log", "log_auto_123", FirestoreOperation.DELETE, auth=auth) is False


# --- 8. Pruebas RBAC por Colección: ui_analytics (Inmutabilidad y Telemetría) ---
class TestUiAnalyticsCollectionRules:
    """Reglas de ui_analytics: Lectura admin; inserción autenticada; inmutable."""

    @pytest.mark.parametrize(
        "auth,expected",
        [
            (None, False),
            (AuthContext(uid="usr_viewer_01"), True),
            (AuthContext(uid="usr_analyst_01"), True),
            (AuthContext(uid="usr_admin_01"), True),
        ],
    )
    def test_create_requires_auth_telemetry_ingestion(
        self, evaluator: FirestoreRulesEvaluator, auth: AuthContext | None, expected: bool
    ):
        """BK-02: Se bloquea la creación anónima en telemetría para mitigar saturación y abuso de cuota."""
        assert evaluator.evaluate("ui_analytics", "evt_auto_123", FirestoreOperation.CREATE, auth=auth) is expected

    @pytest.mark.parametrize("auth", [None, AuthContext(uid="usr_viewer_01"), AuthContext(uid="usr_analyst_01")])
    def test_read_denied_for_non_admins(self, evaluator: FirestoreRulesEvaluator, auth: AuthContext | None):
        """La lectura de telemetría está protegida y es inaccesible para no administradores."""
        assert evaluator.evaluate("ui_analytics", "evt_auto_123", FirestoreOperation.GET, auth=auth) is False
        assert evaluator.evaluate("ui_analytics", "evt_auto_123", FirestoreOperation.LIST, auth=auth) is False

    def test_read_allowed_for_admin(self, evaluator: FirestoreRulesEvaluator):
        """Los administradores pueden consultar métricas de uso y telemetría."""
        admin_auth = AuthContext(uid="usr_admin_01")
        assert evaluator.evaluate("ui_analytics", "evt_auto_123", FirestoreOperation.GET, auth=admin_auth) is True
        assert evaluator.evaluate("ui_analytics", "evt_auto_123", FirestoreOperation.LIST, auth=admin_auth) is True

    @pytest.mark.parametrize(
        "auth",
        [None, AuthContext(uid="usr_viewer_01"), AuthContext(uid="usr_analyst_01"), AuthContext(uid="usr_admin_01")],
    )
    def test_update_and_delete_strictly_forbidden_immutable(
        self, evaluator: FirestoreRulesEvaluator, auth: AuthContext | None
    ):
        """Inmutabilidad estricta: No se permite modificar ni borrar eventos de telemetría."""
        assert evaluator.evaluate("ui_analytics", "evt_auto_123", FirestoreOperation.UPDATE, auth=auth) is False
        assert evaluator.evaluate("ui_analytics", "evt_auto_123", FirestoreOperation.DELETE, auth=auth) is False


# --- 9. Pruebas de Seguridad Negativas y Colecciones Desconocidas ---
class TestDefensiveSecurityAndUnknownCollections:
    """Verifica el principio de denegación por defecto (default-deny) para rutas no mapeadas."""

    def test_unregistered_collection_denied_for_all(self, evaluator: FirestoreRulesEvaluator):
        """Cualquier colección no explícitamente declarada debe ser denegada por defecto."""
        unregistered_collections = ["system_secrets", "internal_configs", "payments", "temp_files"]
        admin_auth = AuthContext(uid="usr_admin_01")

        for coll in unregistered_collections:
            for op in FirestoreOperation:
                assert (
                    evaluator.evaluate(coll, "doc_123", op, auth=admin_auth) is False
                ), f"Colección no registrada {coll} debió ser denegada"
                assert (
                    evaluator.evaluate(coll, "doc_123", op, auth=None) is False
                ), f"Colección no registrada {coll} debió ser denegada a anónimos"
