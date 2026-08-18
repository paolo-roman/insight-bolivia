"""Módulo de extracción y carga de indicadores macroeconómicos internacionales.

Utiliza la librería `wbgapi` para consultar los indicadores del Banco Mundial (WDI)
para Bolivia y países de referencia regional (Perú, Chile, Colombia, Paraguay, etc.),
los transforma al modelo tabular analítico y los ingesta de forma idempotente
mediante sentencia MERGE en Google BigQuery (`benchmark_regional.fact_indicadores_bm`).
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import sys
import time
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, Any

import pandas as pd
import wbgapi as wb
from google.cloud import bigquery

from src.config import get_settings
from src.load import (
    LoadError,
    get_bigquery_client,
    is_already_processed,
    log_etl_execution,
    sync_firestore_metadata,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from google.cloud import firestore

logger = logging.getLogger("insight_bolivia.extract_benchmark")

DEFAULT_COUNTRIES: list[str] = ["BOL", "PER", "CHL", "COL", "PRY"]

COUNTRY_NAMES_ES: dict[str, str] = {
    "BOL": "Bolivia",
    "PER": "Perú",
    "CHL": "Chile",
    "COL": "Colombia",
    "PRY": "Paraguay",
    "BRA": "Brasil",
    "ARG": "Argentina",
    "ECU": "Ecuador",
    "URY": "Uruguay",
    "VEN": "Venezuela",
    "MEX": "México",
}

DEFAULT_INDICATORS: dict[str, dict[str, str]] = {
    "NY.GDP.MKTP.CD": {"nombre": "PIB a precios actuales", "unidad": "USD", "descripcion": "PIB en dólares actuales"},
    "NY.GDP.MKTP.KD.ZG": {
        "nombre": "Crecimiento anual del PIB",
        "unidad": "%",
        "descripcion": "Tasa anual de crecimiento porcentual del PIB",
    },
    "NE.EXP.GNFS.KD.ZG": {
        "nombre": "Crecimiento anual de exportaciones",
        "unidad": "%",
        "descripcion": "Crecimiento anual de exportaciones de bienes y servicios",
    },
    "FP.CPI.TOTL.ZG": {
        "nombre": "Inflación precios al consumidor",
        "unidad": "%",
        "descripcion": "Tasa de inflación anual según IPC",
    },
    "NE.EXP.GNFS.CD": {
        "nombre": "Exportaciones de bienes y servicios",
        "unidad": "USD",
        "descripcion": "Exportaciones en dólares actuales",
    },
    "NE.IMP.GNFS.CD": {
        "nombre": "Importaciones de bienes y servicios",
        "unidad": "USD",
        "descripcion": "Importaciones en dólares actuales",
    },
    "NE.IMP.GNFS.KD.ZG": {
        "nombre": "Crecimiento anual de importaciones",
        "unidad": "%",
        "descripcion": "Crecimiento anual de importaciones de bienes y servicios",
    },
    "NE.TRD.GNFS.ZS": {
        "nombre": "Apertura comercial",
        "unidad": "% del PIB",
        "descripcion": "Comercio exterior total como % del PIB",
    },
}


class ExtractBenchmarkError(Exception):
    """Excepción específica para fallos en la extracción o transformación de benchmark."""


@dataclass(frozen=True)
class BenchmarkETLResult:
    """Resultado estructurado de la ejecución del pipeline ETL de Benchmark."""

    status: str
    records_extracted: int
    records_loaded: int
    sha256: str
    execution_id: str
    duration_seconds: float
    error_details: str | None = None

    @property
    def is_success(self) -> bool:
        """Indica si el pipeline concluyó con éxito o fue omitido por idempotencia."""
        return self.status in {"SUCCESS", "SKIPPED"}


def fetch_world_bank_data(
    indicators: Sequence[str] | None = None,
    countries: Sequence[str] | None = None,
    start_year: int = 2000,
    end_year: int | None = None,
) -> list[dict[str, Any]]:
    """Consulta la API del Banco Mundial usando `wbgapi` para países e indicadores dados."""
    target_indicators = list(indicators) if indicators is not None else list(DEFAULT_INDICATORS.keys())
    target_countries = [c.upper() for c in (countries if countries is not None else DEFAULT_COUNTRIES)]
    current_year = datetime.now(UTC).year
    resolved_end_year = end_year if end_year is not None else current_year

    if start_year > resolved_end_year:
        raise ValueError(f"start_year ({start_year}) no puede ser mayor que end_year ({resolved_end_year}).")
    if not target_indicators:
        raise ValueError("La lista de indicadores no puede estar vacía.")
    if not target_countries:
        raise ValueError("La lista de países no puede estar vacía.")

    years_range = range(start_year, resolved_end_year + 1)
    logger.info(
        "Extrayendo datos de Banco Mundial: países=%s, indicadores=%d, rango=%d-%d",
        target_countries,
        len(target_indicators),
        start_year,
        resolved_end_year,
    )

    try:
        raw_generator = wb.data.fetch(series=target_indicators, economy=target_countries, time=years_range)
        records = list(raw_generator)
        logger.info("Extracción de Banco Mundial finalizada con %d registros brutos.", len(records))
        return records
    except Exception as exc:
        msg = f"Error consultando la API del Banco Mundial con wbgapi: {exc}"
        logger.error(msg, exc_info=True)
        raise ExtractBenchmarkError(msg) from exc


def calculate_benchmark_hash(df: pd.DataFrame) -> str:
    """Calcula un hash SHA-256 determinista a partir del contenido del DataFrame de benchmark."""
    if df.empty:
        return hashlib.sha256(b"empty_benchmark_dataframe").hexdigest()

    sorted_df = df.sort_values(by=["pais_iso", "codigo_indicador", "anio"]).copy()
    content = sorted_df.to_csv(index=False, columns=["pais_iso", "codigo_indicador", "anio", "valor"])
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def transform_benchmark_data(
    raw_records: Sequence[dict[str, Any]],
    indicators_meta: dict[str, dict[str, str]] | None = None,
    extraction_timestamp: datetime | None = None,
) -> pd.DataFrame:
    """Transforma y normaliza los registros del Banco Mundial a la estructura de fact_indicadores_bm."""
    meta = indicators_meta if indicators_meta is not None else DEFAULT_INDICATORS
    now_ts = extraction_timestamp or datetime.now(UTC)
    expected_cols = [
        "id_indicador_bm",
        "fecha",
        "anio",
        "pais_iso",
        "pais_nombre",
        "codigo_indicador",
        "nombre_indicador",
        "valor",
        "unidad_medida",
        "fuente",
        "fecha_extraccion",
    ]

    if not raw_records:
        return pd.DataFrame(columns=expected_cols)

    rows: list[dict[str, Any]] = []
    for item in raw_records:
        val = item.get("value")
        if val is None or pd.isna(val):
            continue

        raw_economy = item.get("economy") or ""
        pais_iso = str(raw_economy).strip().upper()
        raw_time = item.get("time") or ""
        time_clean = str(raw_time).upper().replace("YR", "").strip()
        try:
            anio = int(time_clean)
        except ValueError:
            continue

        codigo_ind = str(item.get("series") or "").strip()
        pais_nombre = COUNTRY_NAMES_ES.get(pais_iso, pais_iso)
        ind_info = meta.get(codigo_ind, {})
        nombre_ind = ind_info.get("nombre", codigo_ind)
        unidad = ind_info.get("unidad", "Unidad")

        unique_key = f"{pais_iso}_{codigo_ind}_{anio}"
        id_bm = hashlib.sha256(unique_key.encode("utf-8")).hexdigest()[:16]

        rows.append(
            {
                "id_indicador_bm": id_bm,
                "fecha": date(anio, 1, 1),
                "anio": anio,
                "pais_iso": pais_iso,
                "pais_nombre": pais_nombre,
                "codigo_indicador": codigo_ind,
                "nombre_indicador": nombre_ind,
                "valor": float(val),
                "unidad_medida": unidad,
                "fuente": "Banco Mundial - WDI",
                "fecha_extraccion": now_ts,
            }
        )

    if not rows:
        return pd.DataFrame(columns=expected_cols)

    df = pd.DataFrame(rows)
    df["anio"] = df["anio"].astype("int64")
    df["valor"] = df["valor"].astype("float64")
    df["fecha_extraccion"] = pd.to_datetime(df["fecha_extraccion"], utc=True)
    return pd.DataFrame(df[expected_cols])


def load_benchmark_to_bigquery(
    df: pd.DataFrame,
    client: bigquery.Client | None = None,
    project_id: str | None = None,
    dataset_staging: str | None = None,
    dataset_benchmark: str | None = None,
    table_name: str = "fact_indicadores_bm",
) -> int:
    """Carga de forma atómica e idempotente el DataFrame en BigQuery usando Staging y MERGE."""
    if df.empty:
        logger.warning("DataFrame de benchmark vacío. Carga omitida.")
        return 0

    settings = get_settings()
    bq = client or get_bigquery_client()
    proj = project_id or bq.project or settings.bigquery.project_id
    ds_stg = dataset_staging or settings.bigquery.dataset_staging
    ds_bm = dataset_benchmark or settings.bigquery.dataset_benchmark

    stg_table = f"{proj}.{ds_stg}.stg_indicadores_bm"
    target_table = f"`{proj}.{ds_bm}.{table_name}`"

    df_stg = df.copy()
    if "fecha" in df_stg.columns:
        df_stg["fecha"] = pd.to_datetime(df_stg["fecha"]).dt.date
    if "fecha_extraccion" in df_stg.columns:
        df_stg["fecha_extraccion"] = pd.to_datetime(df_stg["fecha_extraccion"], utc=True)

    job_config = bigquery.LoadJobConfig(
        write_disposition="WRITE_TRUNCATE",
        schema_update_options=[bigquery.SchemaUpdateOption.ALLOW_FIELD_ADDITION],
    )

    try:
        load_job = bq.load_table_from_dataframe(df_stg, stg_table, job_config=job_config)
        load_job.result()
        logger.info("Cargados %d registros en Staging '%s'.", len(df_stg), stg_table)
    except Exception as exc:
        msg = f"Error cargando datos en Staging '{stg_table}': {exc}"
        logger.error(msg, exc_info=True)
        raise LoadError(msg) from exc

    merge_sql = f"""
        MERGE {target_table} T
        USING `{stg_table}` S
        ON T.pais_iso = S.pais_iso
            AND T.codigo_indicador = S.codigo_indicador
            AND T.anio = S.anio
        WHEN MATCHED THEN
            UPDATE SET
                id_indicador_bm = S.id_indicador_bm,
                fecha = S.fecha,
                pais_nombre = S.pais_nombre,
                nombre_indicador = S.nombre_indicador,
                valor = S.valor,
                unidad_medida = S.unidad_medida,
                fuente = S.fuente,
                fecha_extraccion = S.fecha_extraccion
        WHEN NOT MATCHED THEN
            INSERT (
                id_indicador_bm, fecha, anio, pais_iso, pais_nombre,
                codigo_indicador, nombre_indicador, valor, unidad_medida,
                fuente, fecha_extraccion
            )
            VALUES (
                S.id_indicador_bm, S.fecha, S.anio, S.pais_iso, S.pais_nombre,
                S.codigo_indicador, S.nombre_indicador, S.valor, S.unidad_medida,
                S.fuente, S.fecha_extraccion
            );
    """  # noqa: S608

    try:
        merge_job = bq.query(merge_sql)
        merge_job.result()
        affected = merge_job.num_dml_affected_rows or 0
        logger.info("MERGE en '%s' completado: %d filas afectadas.", target_table, affected)
        return affected
    except Exception as exc:
        msg = f"Error ejecutando MERGE en tabla destino '{target_table}': {exc}"
        logger.error(msg, exc_info=True)
        raise LoadError(msg) from exc


def run_benchmark_etl(
    start_year: int = 2000,
    end_year: int | None = None,
    countries: Sequence[str] | None = None,
    indicators: Sequence[str] | None = None,
    client_bq: bigquery.Client | None = None,
    client_fs: firestore.Client | None = None,
    force: bool = False,
) -> BenchmarkETLResult:
    """Orquesta la extracción, normalización, control de idempotencia y carga del benchmark regional."""
    t_start = time.perf_counter()
    logger.info("=== Iniciando Pipeline de Benchmark Internacional (Banco Mundial) ===")

    try:
        raw_data = fetch_world_bank_data(
            indicators=indicators,
            countries=countries,
            start_year=start_year,
            end_year=end_year,
        )

        df_bench = transform_benchmark_data(raw_data)
        records_extracted = len(df_bench)

        if df_bench.empty:
            duration = round(time.perf_counter() - t_start, 2)
            logger.warning("No se obtuvieron registros válidos para ingesta.")
            return BenchmarkETLResult(
                status="SUCCESS",
                records_extracted=0,
                records_loaded=0,
                sha256="empty",
                execution_id="none",
                duration_seconds=duration,
            )

        sha256_hash = calculate_benchmark_hash(df_bench)

        if not force and is_already_processed(hash_sha256=sha256_hash, client=client_bq):
            duration = round(time.perf_counter() - t_start, 2)
            logger.info("Lote de benchmark con hash '%s' ya procesado. Omitiendo carga.", sha256_hash)
            return BenchmarkETLResult(
                status="SKIPPED",
                records_extracted=records_extracted,
                records_loaded=0,
                sha256=sha256_hash,
                execution_id="idempotency_skip",
                duration_seconds=duration,
            )

        records_loaded = load_benchmark_to_bigquery(df_bench, client=client_bq)

        exec_id = log_etl_execution(
            nombre_archivo="world_bank_wdi_benchmark",
            hash_sha256=sha256_hash,
            estado="SUCCESS",
            registros_procesados=records_loaded,
            fecha_publicacion=datetime.now(UTC).date(),
            client=client_bq,
        )

        try:
            sync_firestore_metadata(
                code="benchmark_regional",
                record_count=records_loaded,
                client=client_fs,
            )
        except Exception as fs_err:
            logger.warning("Fallo no crítico al sincronizar metadata en Firestore: %s", fs_err)

        duration = round(time.perf_counter() - t_start, 2)
        logger.info("Pipeline Benchmark completado: %d extraídos, %d cargados.", records_extracted, records_loaded)
        return BenchmarkETLResult(
            status="SUCCESS",
            records_extracted=records_extracted,
            records_loaded=records_loaded,
            sha256=sha256_hash,
            execution_id=exec_id,
            duration_seconds=duration,
        )

    except Exception as exc:
        duration = round(time.perf_counter() - t_start, 2)
        err_msg = str(exc)
        logger.error("Fallo crítico en el Pipeline de Benchmark: %s", err_msg, exc_info=True)
        try:
            log_etl_execution(
                nombre_archivo="world_bank_wdi_benchmark",
                hash_sha256="error_execution_hash",
                estado="FAILED",
                registros_procesados=0,
                detalles_error=err_msg,
                client=client_bq,
            )
        except Exception as log_err:
            logger.error("No se pudo registrar el fallo en control_log: %s", log_err)

        return BenchmarkETLResult(
            status="FAILED",
            records_extracted=0,
            records_loaded=0,
            sha256="none",
            execution_id="none",
            duration_seconds=duration,
            error_details=err_msg,
        )


def main(argv: Sequence[str] | None = None) -> int:
    """Punto de entrada CLI para la ejecución del pipeline de benchmark regional."""
    parser = argparse.ArgumentParser(
        description="Extracción y carga de indicadores macroeconómicos del Banco Mundial a BigQuery."
    )
    parser.add_argument("--start-year", type=int, default=2000, help="Año inicial de la serie de tiempo.")
    parser.add_argument("--end-year", type=int, default=None, help="Año final de la serie de tiempo.")
    parser.add_argument("--countries", nargs="+", default=None, help="Códigos ISO alpha-3 de los países.")
    parser.add_argument("--indicators", nargs="+", default=None, help="Códigos de indicadores del Banco Mundial.")
    parser.add_argument("--force", action="store_true", help="Fuerza la ejecución ignorando idempotencia.")
    parser.add_argument("-v", "--verbose", action="store_true", help="Habilita logging en nivel DEBUG.")

    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    result = run_benchmark_etl(
        start_year=args.start_year,
        end_year=args.end_year,
        countries=args.countries,
        indicators=args.indicators,
        force=args.force,
    )
    return 0 if result.is_success else 1


if __name__ == "__main__":
    sys.exit(main())
