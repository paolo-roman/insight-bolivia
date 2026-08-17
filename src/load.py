"""Módulo base de carga de datos a Google BigQuery y Firestore.

Proporciona utilidades genéricas de autenticación, carga a Staging,
registro de auditoría en `etl_control_log`, verificación de idempotencia
y sincronización con Google Cloud Firestore (`dwh_catalog`).

Para la carga específica de Comercio Exterior (SCD Tipo 2 en `dim_producto`,
`MERGE` en `fact_comercio_exterior`), véase ``src.load_comercio_exterior``.
"""

from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pandas as pd
from google.cloud import bigquery
from google.oauth2 import service_account

from src.config import get_settings
from src.firestore_client import get_firestore_client, log_audit_event, update_last_refresh

if TYPE_CHECKING:
    from google.cloud import firestore

    from src.load_comercio_exterior import (
        load_comercio_exterior,
        merge_into_fact_comercio_exterior,
        sync_dim_producto_scd2,
    )

logger = logging.getLogger("insight_bolivia.load")


class LoadError(Exception):
    """Excepción base para errores ocurridos durante el proceso de carga ETL."""


@dataclass(frozen=True)
class LoadResult:
    """Resultado estructurado de la ejecución del pipeline de carga."""

    status: str
    records_staging: int
    records_fact: int
    sha256: str
    execution_id: str
    duration_seconds: float
    error_details: str | None = None

    @property
    def is_success(self) -> bool:
        """Indica si la carga concluyó con éxito o fue omitida por idempotencia."""
        return self.status in {"SUCCESS", "SKIPPED"}


def get_bigquery_client(
    project: str | None = None,
    location: str | None = None,
    credentials_path: str | Path | None = None,
) -> bigquery.Client:
    """Inicializa y retorna un cliente autenticado de Google BigQuery."""
    settings = get_settings()
    resolved_project = (
        project
        or os.getenv("BQ_PROJECT_ID")
        or os.getenv("GCP_PROJECT_ID")
        or os.getenv("GOOGLE_CLOUD_PROJECT")
        or settings.bigquery.project_id
    )
    resolved_location = location or os.getenv("BQ_LOCATION") or settings.bigquery.location
    raw_key = (
        credentials_path
        or os.getenv("GCP_SA_KEY_PATH")
        or os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    )

    client_kwargs: dict[str, Any] = {"location": resolved_location}
    if resolved_project:
        client_kwargs["project"] = resolved_project

    if raw_key:
        key_file = Path(raw_key)
        if not key_file.is_file():
            raise FileNotFoundError(f"No se encontró el archivo de credenciales de GCP en: '{key_file}'")
        credentials = service_account.Credentials.from_service_account_file(str(key_file))
        client_kwargs["credentials"] = credentials
        if not resolved_project and hasattr(credentials, "project_id") and credentials.project_id:
            client_kwargs["project"] = credentials.project_id

    return bigquery.Client(**client_kwargs)


def is_already_processed(
    hash_sha256: str,
    client: bigquery.Client | None = None,
    project_id: str | None = None,
    dataset_operations: str | None = None,
) -> bool:
    """Verifica si un archivo ya fue procesado exitosamente en `etl_control_log`."""
    if not hash_sha256 or not hash_sha256.strip():
        raise ValueError("El hash SHA-256 no puede estar vacío.")

    settings = get_settings()
    bq = client or get_bigquery_client()
    proj = project_id or bq.project or settings.bigquery.project_id
    ds_ops = dataset_operations or settings.bigquery.dataset_operations

    table_ref = f"`{proj}.{ds_ops}.etl_control_log`"
    query = f"SELECT COUNT(1) AS total FROM {table_ref} WHERE hash_sha256 = @hash_val AND estado = 'SUCCESS'"  # noqa: S608
    job_config = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("hash_val", "STRING", hash_sha256.strip())]
    )

    query_job = bq.query(query, job_config=job_config)
    results = list(query_job.result())
    if results and len(results) > 0:
        return int(results[0]["total"]) > 0
    return False


def load_to_staging(
    df: pd.DataFrame,
    client: bigquery.Client | None = None,
    project_id: str | None = None,
    dataset_staging: str | None = None,
    table_name: str = "stg_comercio_exterior",
    write_disposition: str = "WRITE_APPEND",
) -> int:
    """Carga un DataFrame normalizado a la tabla de Staging en BigQuery."""
    if df.empty:
        logger.warning("El DataFrame a cargar en Staging está vacío.")
        return 0

    settings = get_settings()
    bq = client or get_bigquery_client()
    proj = project_id or bq.project or settings.bigquery.project_id
    ds_stg = dataset_staging or settings.bigquery.dataset_staging
    table_ref = f"{proj}.{ds_stg}.{table_name}"

    df_to_load = df.copy()
    if "fecha" in df_to_load.columns:
        df_to_load["fecha"] = pd.to_datetime(df_to_load["fecha"]).dt.date
    if "fecha_ingesta" in df_to_load.columns:
        df_to_load["fecha_ingesta"] = pd.to_datetime(df_to_load["fecha_ingesta"], utc=True)

    job_config = bigquery.LoadJobConfig(
        write_disposition=write_disposition,
        schema_update_options=[bigquery.SchemaUpdateOption.ALLOW_FIELD_ADDITION],
    )

    job = bq.load_table_from_dataframe(df_to_load, table_ref, job_config=job_config)
    job.result()
    loaded_rows = job.output_rows or len(df_to_load)
    logger.info("Cargados %d registros en tabla Staging '%s'.", loaded_rows, table_ref)
    return loaded_rows


def log_etl_execution(
    nombre_archivo: str,
    hash_sha256: str,
    estado: str,
    registros_procesados: int = 0,
    fecha_publicacion: Any | None = None,
    detalles_error: str | None = None,
    client: bigquery.Client | None = None,
    project_id: str | None = None,
    dataset_operations: str | None = None,
) -> str:
    """Inserta un registro de auditoría en la tabla `etl_control_log` de BigQuery."""
    settings = get_settings()
    bq = client or get_bigquery_client()
    proj = project_id or bq.project or settings.bigquery.project_id
    ds_ops = dataset_operations or settings.bigquery.dataset_operations
    table_ref = f"{proj}.{ds_ops}.etl_control_log"

    exec_id = str(uuid.uuid4())
    now = datetime.now(UTC)

    pub_date: date | None = None
    if isinstance(fecha_publicacion, datetime):
        pub_date = fecha_publicacion.date()
    elif isinstance(fecha_publicacion, date):
        pub_date = fecha_publicacion
    elif isinstance(fecha_publicacion, str) and fecha_publicacion.strip():
        pub_date = pd.to_datetime(fecha_publicacion).date()

    row = {
        "id": exec_id,
        "nombre_archivo": nombre_archivo,
        "hash_sha256": hash_sha256,
        "fecha_publicacion": pub_date.isoformat() if pub_date else None,
        "registros_procesados": registros_procesados,
        "timestamp_ejecucion": now.isoformat(),
        "estado": estado.upper(),
        "detalles_error": detalles_error,
    }

    errors = bq.insert_rows_json(table_ref, [row])
    if errors:
        msg = f"Error insertando log en '{table_ref}': {errors}"
        logger.error(msg)
        raise LoadError(msg)

    logger.info("Registrada ejecución ETL '%s' con estado '%s' en control log.", exec_id, estado)
    return exec_id


def sync_firestore_metadata(
    code: str = "comercio_exterior",
    record_count: int | None = None,
    timestamp: datetime | None = None,
    client: firestore.Client | None = None,
) -> bool:
    """Actualiza la metadata en el catálogo de Firestore y emite un evento de auditoría."""
    fs_client = client or get_firestore_client()
    now = timestamp or datetime.now(UTC)
    updated = update_last_refresh(code=code, timestamp=now, record_count=record_count, client=fs_client)
    log_audit_event(
        action="etl_load",
        resource_type="dwh_catalog",
        resource_id=code,
        metadata={"record_count": record_count, "synced_at": now.isoformat()},
        client=fs_client,
    )
    return updated


def __getattr__(name: str) -> Any:
    """Re-exportación dinámica de funciones de comercio exterior para compatibilidad hacia atrás."""
    if name in {"load_comercio_exterior", "merge_into_fact_comercio_exterior", "sync_dim_producto_scd2"}:
        import src.load_comercio_exterior as _lce

        return getattr(_lce, name)
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


__all__ = [
    "LoadError",
    "LoadResult",
    "get_bigquery_client",
    "is_already_processed",
    "load_comercio_exterior",
    "load_to_staging",
    "log_etl_execution",
    "merge_into_fact_comercio_exterior",
    "sync_dim_producto_scd2",
    "sync_firestore_metadata",
]
