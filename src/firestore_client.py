"""Cliente helper y utilidades de acceso a Google Cloud Firestore (Modo Nativo).

Proporciona funciones tipadas y seguras para interactuar con las colecciones
operacionales de InsightBolivia:
- `dwh_catalog`: Consulta y actualización de metadatos de Data Warehouses y vistas.
- `audit_log`: Registro inmutable de eventos de auditoría del sistema y usuarios.
- `ui_analytics`: Telemetría y eventos de interacción del dashboard Streamlit.
- `user_profiles`: Consulta y gestión de perfiles de usuario y roles RBAC.
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from google.cloud import firestore
from google.oauth2 import service_account

from src.firestore_models import AuditLog, DwhCatalog, UiAnalytics, UserProfile

# Configuración de logging estructurado
logger = logging.getLogger("insight_bolivia.firestore_client")

# Nombres canónicos de las colecciones de Firestore
COLLECTION_DWH_CATALOG = "dwh_catalog"
COLLECTION_AUDIT_LOG = "audit_log"
COLLECTION_UI_ANALYTICS = "ui_analytics"
COLLECTION_USER_PROFILES = "user_profiles"


def get_firestore_client(
    database: str | None = None,
    project: str | None = None,
    credentials_path: str | Path | None = None,
) -> firestore.Client:
    """Inicializa y retorna una instancia autenticada del cliente de Cloud Firestore.

    Soporta autenticación mediante:
    1. Archivo de clave de Service Account (`credentials_path`, `GCP_SA_KEY_PATH`
       o `GOOGLE_APPLICATION_CREDENTIALS`).
    2. Application Default Credentials (ADC) o credenciales implícitas de GCP.

    Parameters
    ----------
    database:
        Nombre de la base de datos de Firestore. Si es None, busca en la variable
        ``FIRESTORE_DATABASE`` o usa ``"(default)"``.
    project:
        ID del proyecto de GCP. Si es None, busca en ``GOOGLE_CLOUD_PROJECT``,
        ``GCP_PROJECT_ID`` o en las credenciales cargadas.
    credentials_path:
        Ruta opcional al archivo JSON de credenciales de la cuenta de servicio de GCP.

    Returns
    -------
    firestore.Client
        Cliente autenticado de Google Cloud Firestore.

    Raises
    ------
    FileNotFoundError
        Si se especifica una ruta de credenciales que no existe en el sistema de archivos.
    """
    resolved_db = database or os.getenv("FIRESTORE_DATABASE") or "(default)"
    resolved_project = project or os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GCP_PROJECT_ID")

    # Resolución de ruta de credenciales
    raw_key_path = credentials_path or os.getenv("GCP_SA_KEY_PATH") or os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

    client_kwargs: dict[str, Any] = {"database": resolved_db}
    if resolved_project:
        client_kwargs["project"] = resolved_project

    if raw_key_path:
        key_file = Path(raw_key_path)
        if not key_file.is_file():
            raise FileNotFoundError(f"No se encontró el archivo de credenciales de GCP en: '{key_file}'")
        credentials = service_account.Credentials.from_service_account_file(str(key_file))
        client_kwargs["credentials"] = credentials
        if not resolved_project and hasattr(credentials, "project_id") and credentials.project_id:
            client_kwargs["project"] = credentials.project_id

    return firestore.Client(**client_kwargs)


def get_dwh_catalog(
    code: str,
    client: firestore.Client | None = None,
) -> DwhCatalog | None:
    """Consulta los metadatos y vistas de un Data Warehouse en `dwh_catalog`.

    Parameters
    ----------
    code:
        Código único identificador del Data Warehouse (ej: ``comercio_exterior``).
    client:
        Instancia opcional del cliente de Firestore. Si es None, se inicializa automáticamente.

    Returns
    -------
    DwhCatalog | None
        Instancia de ``DwhCatalog`` con los datos y vistas, o None si el documento no existe.

    Raises
    ------
    ValueError
        Si el parámetro ``code`` está vacío o no es una cadena válida.
    """
    if not isinstance(code, str) or not code.strip():
        raise ValueError("El código del Data Warehouse ('code') debe ser una cadena no vacía.")

    cleaned_code = code.strip()
    db = client if client is not None else get_firestore_client()
    doc_ref = db.collection(COLLECTION_DWH_CATALOG).document(cleaned_code)
    doc_snap = doc_ref.get()

    if not doc_snap.exists:
        logger.warning("No se encontró el Data Warehouse con código '%s' en Firestore.", cleaned_code)
        return None

    data = doc_snap.to_dict() or {}
    return DwhCatalog.from_firestore_dict(data)


def list_dwh_catalogs(
    status: str | None = None,
    client: firestore.Client | None = None,
) -> list[DwhCatalog]:
    """Lista los Data Warehouses registrados en la colección `dwh_catalog`.

    Parameters
    ----------
    status:
        Filtro opcional por estado operativo (ej: ``active``, ``maintenance``, ``inactive``).
    client:
        Instancia opcional del cliente de Firestore.

    Returns
    -------
    list[DwhCatalog]
        Lista de Data Warehouses validados.
    """
    db = client if client is not None else get_firestore_client()
    col_ref = db.collection(COLLECTION_DWH_CATALOG)

    if status:
        query = col_ref.where(filter=firestore.FieldFilter("status", "==", status.strip().lower()))
        snapshots = query.stream()
    else:
        snapshots = col_ref.stream()

    catalogs: list[DwhCatalog] = []
    for snap in snapshots:
        data = snap.to_dict() or {}
        catalogs.append(DwhCatalog.from_firestore_dict(data))

    return catalogs


def update_last_refresh(
    code: str,
    timestamp: datetime | None = None,
    record_count: int | None = None,
    client: firestore.Client | None = None,
) -> bool:
    """Actualiza la fecha de última sincronización y conteo de registros tras el ETL.

    Parameters
    ----------
    code:
        Código único identificador del Data Warehouse.
    timestamp:
        Fecha y hora de la actualización. Si es None, se asigna ``datetime.now(UTC)``.
    record_count:
        Total de registros consolidados tras la ingesta (opcional, debe ser >= 0).
    client:
        Instancia opcional del cliente de Firestore.

    Returns
    -------
    bool
        True si la actualización fue exitosa.

    Raises
    ------
    ValueError
        Si ``code`` es inválido o ``record_count`` es negativo.
    KeyError
        Si el Data Warehouse especificado no existe en la colección ``dwh_catalog``.
    """
    if not isinstance(code, str) or not code.strip():
        raise ValueError("El código del Data Warehouse ('code') debe ser una cadena no vacía.")

    if record_count is not None and record_count < 0:
        raise ValueError(f"El conteo de registros ('record_count') no puede ser negativo: {record_count}")

    cleaned_code = code.strip()
    db = client if client is not None else get_firestore_client()
    doc_ref = db.collection(COLLECTION_DWH_CATALOG).document(cleaned_code)

    doc_snap = doc_ref.get()
    if not doc_snap.exists:
        raise KeyError(f"No se encontró el Data Warehouse con código '{cleaned_code}' en '{COLLECTION_DWH_CATALOG}'.")

    now = datetime.now(UTC)
    refresh_time = timestamp if timestamp is not None else now

    updates: dict[str, Any] = {
        "last_data_refresh": refresh_time,
        "updated_at": now,
    }
    if record_count is not None:
        updates["record_count"] = record_count

    doc_ref.update(updates)
    logger.info(
        "Actualizado last_data_refresh para DWH '%s' a %s (registros: %s).",
        cleaned_code,
        refresh_time.isoformat(),
        record_count if record_count is not None else "sin cambios",
    )
    return True


def log_audit_event(
    action: str,
    resource_type: str = "general",
    resource_id: str = "",
    metadata: dict[str, Any] | None = None,
    user_id: str = "system",
    ip_address: str = "",
    user_agent: str = "",
    client: firestore.Client | None = None,
) -> str:
    """Registra un evento inmutable de auditoría en la colección `audit_log`.

    Parameters
    ----------
    action:
        Acción ejecutada (ej: ``query``, ``export``, ``etl_load``, ``login``).
    resource_type:
        Tipo de recurso accedido (ej: ``view``, ``dataset``, ``etl``, ``auth``).
    resource_id:
        Identificador del recurso afectado.
    metadata:
        Diccionario con metadatos contextuales de la operación.
    user_id:
        Identificador del usuario o sistema (por defecto ``system``).
    ip_address:
        Dirección IP de origen del cliente.
    user_agent:
        Cadena User-Agent del navegador o cliente.
    client:
        Instancia opcional del cliente de Firestore.

    Returns
    -------
    str
        ID del documento de auditoría creado en Firestore.
    """
    event = AuditLog(
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        metadata=metadata or {},
        ip_address=ip_address,
        user_agent=user_agent,
    )

    db = client if client is not None else get_firestore_client()
    col_ref = db.collection(COLLECTION_AUDIT_LOG)
    doc_ref = col_ref.document()

    payload = event.to_firestore_dict(exclude_none=False)
    doc_ref.set(payload)

    logger.info("Registrado evento de auditoría [%s] para usuario '%s' con ID '%s'.", action, user_id, doc_ref.id)
    return doc_ref.id


def record_ui_event(
    session_id: str,
    page: str,
    event_type: str,
    event_data: dict[str, Any] | None = None,
    duration_ms: int | None = None,
    user_id: str | None = None,
    client: firestore.Client | None = None,
) -> str:
    """Registra un evento de telemetría e interacción en `ui_analytics`.

    Parameters
    ----------
    session_id:
        Identificador único de la sesión del usuario (UUID).
    page:
        Página o sección del dashboard interactuada.
    event_type:
        Tipo de evento registrado (ej: ``page_view``, ``filter_apply``, ``export_csv``).
    event_data:
        Parámetros y filtros aplicados en el evento.
    duration_ms:
        Duración en milisegundos de la interacción o tiempo de carga.
    user_id:
        Identificador del usuario autenticado si aplica.
    client:
        Instancia opcional del cliente de Firestore.

    Returns
    -------
    str
        ID del documento de analítica creado en Firestore.
    """
    event = UiAnalytics(
        session_id=session_id,
        page=page,
        event_type=event_type,
        event_data=event_data or {},
        duration_ms=duration_ms,
        user_id=user_id,
    )

    db = client if client is not None else get_firestore_client()
    col_ref = db.collection(COLLECTION_UI_ANALYTICS)
    doc_ref = col_ref.document()

    payload = event.to_firestore_dict(exclude_none=False)
    doc_ref.set(payload)

    logger.debug("Registrado evento UI [%s] en página '%s' (sesión: %s).", event_type, page, session_id)
    return doc_ref.id


def get_user_profile(
    user_id: str,
    client: firestore.Client | None = None,
) -> UserProfile | None:
    """Consulta el perfil de un usuario en la colección `user_profiles`.

    Parameters
    ----------
    user_id:
        Firebase Authentication UID del usuario.
    client:
        Instancia opcional del cliente de Firestore.

    Returns
    -------
    UserProfile | None
        Instancia de ``UserProfile`` o None si no existe.

    Raises
    ------
    ValueError
        Si ``user_id`` está vacío o no es una cadena válida.
    """
    if not isinstance(user_id, str) or not user_id.strip():
        raise ValueError("El 'user_id' debe ser una cadena no vacía.")

    cleaned_uid = user_id.strip()
    db = client if client is not None else get_firestore_client()
    doc_ref = db.collection(COLLECTION_USER_PROFILES).document(cleaned_uid)
    doc_snap = doc_ref.get()

    if not doc_snap.exists:
        logger.warning("No se encontró el perfil de usuario para UID '%s'.", cleaned_uid)
        return None

    data = doc_snap.to_dict() or {}
    return UserProfile.from_firestore_dict(data)


def upsert_user_profile(
    user_id: str,
    profile: UserProfile | dict[str, Any],
    client: firestore.Client | None = None,
) -> str:
    """Crea o actualiza de forma idempotente un perfil de usuario en `user_profiles`.

    Parameters
    ----------
    user_id:
        Firebase Authentication UID del usuario.
    profile:
        Instancia de ``UserProfile`` o diccionario con los datos del perfil.
    client:
        Instancia opcional del cliente de Firestore.

    Returns
    -------
    str
        ID del documento de perfil de usuario actualizado.

    Raises
    ------
    ValueError
        Si ``user_id`` es inválido o los datos del perfil no cumplen con el esquema.
    """
    if not isinstance(user_id, str) or not user_id.strip():
        raise ValueError("El 'user_id' debe ser una cadena no vacía.")

    cleaned_uid = user_id.strip()
    if isinstance(profile, dict):
        validated_profile = UserProfile.model_validate(profile)
    elif isinstance(profile, UserProfile):
        validated_profile = profile
    else:
        raise ValueError(
            f"El parámetro 'profile' debe ser una instancia de UserProfile o dict, "
            f"se recibió '{type(profile).__name__}'."
        )

    db = client if client is not None else get_firestore_client()
    doc_ref = db.collection(COLLECTION_USER_PROFILES).document(cleaned_uid)

    payload = validated_profile.to_firestore_dict(exclude_none=False)
    doc_ref.set(payload, merge=True)

    logger.info("Perfil de usuario '%s' actualizado con éxito.", cleaned_uid)
    return cleaned_uid
