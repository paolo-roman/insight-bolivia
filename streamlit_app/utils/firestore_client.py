"""InsightBolivia — Cliente y utilidades de Google Cloud Firestore para Streamlit.

Proporciona funciones seguras y cacheadas para interactuar con las colecciones operacionales:
- `dwh_catalog`: Consulta de metadatos del Data Warehouse (`comercio_exterior`) con `@st.cache_data(ttl=3600)`.
- `ui_analytics`: Telemetría y registro no bloqueante de eventos de interacción (`page_view`, `filter_apply`, etc.).

Las credenciales se inyectan de forma segura desde `st.secrets` en runtime con
fallback automático a variables de entorno o Application Default Credentials (ADC).
"""

from __future__ import annotations

import logging
import os
import uuid
from pathlib import Path
from typing import Any

import streamlit as st
from google.cloud import firestore
from google.oauth2 import service_account

from src.firestore_models import DwhCatalog, UiAnalytics

logger = logging.getLogger("insight_bolivia.streamlit.firestore_client")

# Nombres canónicos de colecciones
COLLECTION_DWH_CATALOG = "dwh_catalog"
COLLECTION_UI_ANALYTICS = "ui_analytics"
DEFAULT_DWH_CODE = "comercio_exterior"
DEFAULT_FIRESTORE_DB = "(default)"


def _get_secret_dict(key: str) -> dict[str, Any]:
    """Obtiene de forma segura una sección de diccionario desde st.secrets."""
    try:
        if hasattr(st, "secrets") and key in st.secrets:
            val = st.secrets[key]
            if isinstance(val, dict):
                return val
            if hasattr(val, "items"):
                return dict(val)
    except Exception:
        return {}
    return {}


def _get_credentials_from_secrets() -> service_account.Credentials | None:
    """Extrae credenciales de Google Service Account desde st.secrets si están disponibles."""
    try:
        sa_info = _get_secret_dict("gcp_service_account")
        if "client_email" in sa_info and "private_key" in sa_info and sa_info.get("private_key"):
            return service_account.Credentials.from_service_account_info(sa_info)
    except Exception as exc:
        logger.warning("No se pudieron cargar las credenciales de Firestore desde st.secrets: %s", exc)
    return None


def get_firestore_client(
    database: str | None = None,
    project: str | None = None,
) -> firestore.Client:
    """Inicializa y retorna un cliente autenticado de Google Cloud Firestore.

    Prioridad de autenticación:
    1. `st.secrets["gcp_service_account"]` y `st.secrets["firestore"]`
    2. Archivo de clave referenciado en `GCP_SA_KEY_PATH` o `GOOGLE_APPLICATION_CREDENTIALS`
    3. Application Default Credentials (ADC).

    Parameters
    ----------
    database:
        Nombre de la base de datos de Firestore (por defecto ``(default)``).
    project:
        ID del proyecto GCP. Si es None, se infiere de secrets o entorno.

    Returns
    -------
    firestore.Client
        Cliente autenticado de Firestore.
    """
    fs_secrets = _get_secret_dict("firestore")
    sa_secrets = _get_secret_dict("gcp_service_account")

    resolved_db = (
        database
        or fs_secrets.get("database")
        or os.getenv("FIRESTORE_DATABASE")
        or DEFAULT_FIRESTORE_DB
    )
    resolved_project = (
        project
        or fs_secrets.get("project_id")
        or sa_secrets.get("project_id")
        or os.getenv("GOOGLE_CLOUD_PROJECT")
        or os.getenv("GCP_PROJECT_ID")
    )

    client_kwargs: dict[str, Any] = {"database": resolved_db}
    if resolved_project:
        client_kwargs["project"] = resolved_project

    credentials = _get_credentials_from_secrets()

    if credentials is None:
        raw_key_path = os.getenv("GCP_SA_KEY_PATH") or os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        if raw_key_path and Path(raw_key_path).is_file():
            credentials = service_account.Credentials.from_service_account_file(raw_key_path)

    if credentials is not None:
        client_kwargs["credentials"] = credentials
        if not resolved_project and hasattr(credentials, "project_id") and credentials.project_id:
            client_kwargs["project"] = credentials.project_id

    return firestore.Client(**client_kwargs)


@st.cache_data(ttl=3600, show_spinner=False)
def get_cached_dwh_catalog(code: str = DEFAULT_DWH_CODE) -> DwhCatalog | None:
    """Consulta y cachea los metadatos de un Data Warehouse en `dwh_catalog`.

    Protegido con `@st.cache_data(ttl=3600)` para cumplir con las cuotas del
    Always Free Tier de Firestore (50k lecturas/día).

    Parameters
    ----------
    code:
        Código único del Data Warehouse (ej: ``comercio_exterior``).

    Returns
    -------
    DwhCatalog | None
        Instancia con los metadatos del catálogo, o None si no se encuentra o falla la conexión.
    """
    try:
        client = get_firestore_client()
        doc_ref = client.collection(COLLECTION_DWH_CATALOG).document(code.strip())
        doc_snap = doc_ref.get()

        if not doc_snap.exists:
            logger.warning("No se encontró el Data Warehouse '%s' en Firestore.", code)
            return None

        data = doc_snap.to_dict() or {}
        return DwhCatalog.from_firestore_dict(data)
    except Exception as exc:
        logger.warning("No se pudo consultar dwh_catalog desde Firestore: %s", exc)
        return None


def get_session_id() -> str:
    """Obtiene o inicializa un identificador único de sesión (UUID v4) en st.session_state.

    Returns
    -------
    str
        UUID v4 de la sesión activa del usuario.
    """
    if "session_id" not in st.session_state:
        st.session_state["session_id"] = str(uuid.uuid4())
    return str(st.session_state["session_id"])


def log_ui_event(
    session_id: str,
    page: str,
    event_type: str,
    event_data: dict[str, Any] | None = None,
    duration_ms: int | None = None,
    user_id: str | None = None,
) -> str | None:
    """Registra un evento de telemetría de forma defensiva y no bloqueante en `ui_analytics`.

    Si la conexión a Firestore no está disponible o falla, la función registra un
    aviso en el log pero NO propaga la excepción, permitiendo que la interfaz de
    usuario continúe funcionando con normalidad.

    Parameters
    ----------
    session_id:
        UUID de la sesión de usuario.
    page:
        Nombre de la página o módulo interactuado (ej: ``home``, ``01_balanza``).
    event_type:
        Tipo de evento (ej: ``page_view``, ``filter_apply``, ``export_csv``).
    event_data:
        Diccionario con filtros o parámetros aplicados.
    duration_ms:
        Tiempo de procesamiento o interacción en milisegundos.
    user_id:
        ID del usuario autenticado si aplica.

    Returns
    -------
    str | None
        ID del documento creado en Firestore, o None si no se pudo registrar.
    """
    try:
        event = UiAnalytics(
            session_id=session_id,
            page=page,
            event_type=event_type,
            event_data=event_data or {},
            duration_ms=duration_ms,
            user_id=user_id,
        )

        client = get_firestore_client()
        col_ref = client.collection(COLLECTION_UI_ANALYTICS)
        doc_ref = col_ref.document()
        payload = event.to_firestore_dict(exclude_none=False)
        doc_ref.set(payload)

        logger.debug("Evento de UI registrado [%s:%s] en Firestore: %s", page, event_type, doc_ref.id)
        return doc_ref.id
    except Exception as exc:
        logger.debug("No se pudo registrar evento de UI en Firestore: %s", exc)
        return None
