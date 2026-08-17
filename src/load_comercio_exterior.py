"""Módulo de carga de datos para el dominio de Comercio Exterior en Google BigQuery.

Implementa las operaciones DML especializadas para Comercio Exterior:
- Mantenimiento SCD Tipo 2 en la dimensión `comercio_exterior.dim_producto`.
- Sentencia `MERGE` (upsert atómico) en `comercio_exterior.fact_comercio_exterior`
  sobre la clave natural de grano completo y surrogate key con `FARM_FINGERPRINT`.
- Orquestación del pipeline de carga de comercio exterior con control de
  idempotencia, trazabilidad en `etl_control_log` y sincronización con Firestore.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from google.cloud import bigquery

from src.config import get_settings
from src.firestore_client import get_firestore_client
from src.load import (
    LoadError,
    LoadResult,
    get_bigquery_client,
    is_already_processed,
    load_to_staging,
    log_etl_execution,
    sync_firestore_metadata,
)

if TYPE_CHECKING:
    import pandas as pd
    from google.cloud import firestore

logger = logging.getLogger("insight_bolivia.load.comercio_exterior")


def sync_dim_producto_scd2(
    client: bigquery.Client | None = None,
    project_id: str | None = None,
    dataset_staging: str | None = None,
    dataset_comercio: str | None = None,
    hash_sha256: str = "",
) -> dict[str, int]:
    """Actualiza `dim_producto` bajo SCD Tipo 2 para registros del lote actual."""
    settings = get_settings()
    bq = client or get_bigquery_client()
    proj = project_id or bq.project or settings.bigquery.project_id
    ds_stg = dataset_staging or settings.bigquery.dataset_staging
    ds_com = dataset_comercio or settings.bigquery.dataset_comercio

    dim_ref = f"`{proj}.{ds_com}.dim_producto`"
    stg_ref = f"`{proj}.{ds_stg}.stg_comercio_exterior`"

    close_merge_sql = f"""
        MERGE {dim_ref} T
        USING (
            SELECT DISTINCT
                codigo_nandina,
                descripcion_nandina AS descripcion_producto,
                SUBSTR(codigo_nandina, 1, 4) AS partida_nandina,
                capitulo_nandina,
                seccion_nandina,
                COALESCE(descripcion_actividad, 'General') AS sector_economico
            FROM {stg_ref}
            WHERE hash_sha256 = @hash_val AND codigo_nandina IS NOT NULL
        ) S
        ON T.codigo_nandina = S.codigo_nandina AND T.es_vigente = TRUE
        WHEN MATCHED AND (
            COALESCE(T.descripcion_producto, '') != COALESCE(S.descripcion_producto, '')
            OR COALESCE(T.sector_economico, '') != COALESCE(S.sector_economico, '')
        ) THEN
        UPDATE SET es_vigente = FALSE, vigente_hasta = CURRENT_DATE();
    """  # noqa: S608

    insert_sql = f"""
        INSERT INTO {dim_ref}
        (
            codigo_nandina, descripcion_producto, partida_nandina, capitulo_nandina,
            seccion_nandina, sector_economico, vigente_desde, vigente_hasta, es_vigente
        )
        SELECT DISTINCT
            S.codigo_nandina, S.descripcion_nandina, SUBSTR(S.codigo_nandina, 1, 4),
            S.capitulo_nandina, S.seccion_nandina,
            COALESCE(S.descripcion_actividad, 'General'),
            CURRENT_DATE(), CAST(NULL AS DATE), TRUE
        FROM {stg_ref} S
        LEFT JOIN {dim_ref} T
            ON S.codigo_nandina = T.codigo_nandina AND T.es_vigente = TRUE
        WHERE S.hash_sha256 = @hash_val
            AND S.codigo_nandina IS NOT NULL
            AND T.codigo_nandina IS NULL;
    """  # noqa: S608

    job_config = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("hash_val", "STRING", hash_sha256.strip())]
    )

    close_job = bq.query(close_merge_sql, job_config=job_config)
    close_job.result()
    insert_job = bq.query(insert_sql, job_config=job_config)
    insert_job.result()

    stats = {
        "closed_records": close_job.num_dml_affected_rows or 0,
        "inserted_records": insert_job.num_dml_affected_rows or 0,
    }
    logger.info("SCD2 dim_producto: cerrados=%d, insertados=%d.", stats["closed_records"], stats["inserted_records"])
    return stats


def merge_into_fact_comercio_exterior(
    client: bigquery.Client | None = None,
    project_id: str | None = None,
    dataset_staging: str | None = None,
    dataset_comercio: str | None = None,
    hash_sha256: str = "",
) -> int:
    """Ejecuta MERGE (upsert) en fact_comercio_exterior usando la clave de grano completo."""
    settings = get_settings()
    bq = client or get_bigquery_client()
    proj = project_id or bq.project or settings.bigquery.project_id
    ds_stg = dataset_staging or settings.bigquery.dataset_staging
    ds_com = dataset_comercio or settings.bigquery.dataset_comercio

    fact_ref = f"`{proj}.{ds_com}.fact_comercio_exterior`"
    stg_ref = f"`{proj}.{ds_stg}.stg_comercio_exterior`"
    pais_ref = f"`{proj}.{ds_com}.dim_pais`"

    merge_sql = f"""
        MERGE {fact_ref} T
        USING (
            SELECT
                FARM_FINGERPRINT(CONCAT(
                    CAST(S.fecha AS STRING),
                    COALESCE(S.codigo_nandina, ''),
                    COALESCE(P.pais_iso, 'ZZZ'),
                    COALESCE(S.tipo_operacion, ''),
                    CAST(COALESCE(S.codigo_departamento, -1) AS STRING),
                    CAST(COALESCE(S.codigo_via, -1) AS STRING),
                    CAST(COALESCE(S.codigo_aduana, -1) AS STRING)
                )) AS id_transaccion,
                S.fecha, S.codigo_nandina, COALESCE(P.pais_iso, 'ZZZ') AS pais_iso,
                S.codigo_departamento AS id_departamento,
                S.codigo_via AS id_via_transporte,
                S.codigo_aduana AS id_aduana,
                S.tipo_operacion,
                COALESCE(S.valor_fob_usd, 0.0) AS valor_fob_usd,
                S.valor_cif_frontera_usd AS valor_cif_usd,
                COALESCE(S.valor_fob_usd * 6.96, 0.0) AS valor_fob_bob,
                S.peso_neto_kg, S.peso_bruto_kg, S.contenido_fino,
                EXTRACT(YEAR FROM S.fecha) AS anio,
                EXTRACT(MONTH FROM S.fecha) AS mes,
                EXTRACT(QUARTER FROM S.fecha) AS trimestre
            FROM {stg_ref} S
            LEFT JOIN {pais_ref} P ON S.codigo_pais_ine = P.codigo_pais_ine
            WHERE S.hash_sha256 = @hash_val
        ) S
        ON T.fecha = S.fecha
            AND T.codigo_nandina = S.codigo_nandina
            AND T.pais_iso = S.pais_iso
            AND T.tipo_operacion = S.tipo_operacion
            AND COALESCE(T.id_departamento, -1) = COALESCE(S.id_departamento, -1)
            AND COALESCE(T.id_via_transporte, -1) = COALESCE(S.id_via_transporte, -1)
            AND COALESCE(T.id_aduana, -1) = COALESCE(S.id_aduana, -1)
        WHEN MATCHED THEN
            UPDATE SET
                valor_fob_usd = S.valor_fob_usd,
                valor_cif_usd = S.valor_cif_usd,
                valor_fob_bob = S.valor_fob_bob,
                peso_neto_kg = S.peso_neto_kg,
                peso_bruto_kg = S.peso_bruto_kg,
                contenido_fino = S.contenido_fino,
                anio = S.anio,
                mes = S.mes,
                trimestre = S.trimestre
        WHEN NOT MATCHED THEN
            INSERT (
                id_transaccion, fecha, codigo_nandina, pais_iso, id_departamento,
                id_via_transporte, id_aduana, tipo_operacion, valor_fob_usd,
                valor_cif_usd, valor_fob_bob, peso_neto_kg, peso_bruto_kg,
                contenido_fino, anio, mes, trimestre
            )
            VALUES (
                S.id_transaccion, S.fecha, S.codigo_nandina, S.pais_iso, S.id_departamento,
                S.id_via_transporte, S.id_aduana, S.tipo_operacion, S.valor_fob_usd,
                S.valor_cif_usd, S.valor_fob_bob, S.peso_neto_kg, S.peso_bruto_kg,
                S.contenido_fino, S.anio, S.mes, S.trimestre
            );
    """  # noqa: S608

    job_config = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("hash_val", "STRING", hash_sha256.strip())]
    )
    job = bq.query(merge_sql, job_config=job_config)
    job.result()
    affected = job.num_dml_affected_rows or 0
    logger.info("MERGE fact_comercio_exterior completado: %d filas afectadas.", affected)
    return affected


def load_comercio_exterior(
    df_staging: pd.DataFrame,
    filename: str,
    file_hash: str,
    fecha_publicacion: Any | None = None,
    force: bool = False,
    bq_client: bigquery.Client | None = None,
    fs_client: firestore.Client | None = None,
) -> LoadResult:
    """Orquesta el proceso completo de carga incremental e idempotente para Comercio Exterior."""
    start_time = datetime.now(UTC)
    bq = bq_client or get_bigquery_client()
    fs = fs_client or get_firestore_client()

    if not force and is_already_processed(file_hash, client=bq):
        logger.info("Archivo con hash '%s' ya procesado con anterioridad. Omitiendo carga.", file_hash)
        exec_id = log_etl_execution(
            nombre_archivo=filename,
            hash_sha256=file_hash,
            estado="SKIPPED",
            registros_procesados=len(df_staging),
            fecha_publicacion=fecha_publicacion,
            client=bq,
        )
        duration = (datetime.now(UTC) - start_time).total_seconds()
        return LoadResult(
            status="SKIPPED",
            records_staging=0,
            records_fact=0,
            sha256=file_hash,
            execution_id=exec_id,
            duration_seconds=duration,
        )

    try:
        rows_stg = load_to_staging(df_staging, client=bq)
        sync_dim_producto_scd2(client=bq, hash_sha256=file_hash)
        rows_fact = merge_into_fact_comercio_exterior(client=bq, hash_sha256=file_hash)

        exec_id = log_etl_execution(
            nombre_archivo=filename,
            hash_sha256=file_hash,
            estado="SUCCESS",
            registros_procesados=rows_stg,
            fecha_publicacion=fecha_publicacion,
            client=bq,
        )

        try:
            sync_firestore_metadata(code="comercio_exterior", record_count=rows_fact, client=fs)
        except Exception as fs_err:
            logger.warning("No se pudo actualizar metadata en Firestore: %s", fs_err)

        duration = (datetime.now(UTC) - start_time).total_seconds()
        return LoadResult(
            status="SUCCESS",
            records_staging=rows_stg,
            records_fact=rows_fact,
            sha256=file_hash,
            execution_id=exec_id,
            duration_seconds=duration,
        )

    except Exception as exc:
        duration = (datetime.now(UTC) - start_time).total_seconds()
        logger.exception("Fallo crítico en pipeline de carga para archivo '%s': %s", filename, exc)
        try:
            log_etl_execution(
                nombre_archivo=filename,
                hash_sha256=file_hash,
                estado="FAILED",
                registros_procesados=0,
                fecha_publicacion=fecha_publicacion,
                detalles_error=str(exc),
                client=bq,
            )
        except Exception as log_err:
            logger.error("No se pudo registrar estado FAILED en etl_control_log: %s", log_err)

        raise LoadError(f"Error cargando comercio exterior para '{filename}': {exc}") from exc


__all__ = [
    "load_comercio_exterior",
    "merge_into_fact_comercio_exterior",
    "sync_dim_producto_scd2",
]
