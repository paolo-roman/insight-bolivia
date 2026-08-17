"""Script Orquestador Principal del Pipeline ETL InsightBolivia.

Coordina la ejecución secuencial End-to-End (E2E) del pipeline de ingesta de datos
de Comercio Exterior del INE Bolivia: extract -> transform -> validate -> load.
Provee la interfaz CLI para ejecución local y GitHub Actions:
    uv run python -m src.main [--dry-run] [--force-reprocess] [--date-range R]
"""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd

from src.config import get_settings, load_dotenv_file, setup_logging, validate_mandatory_env_vars
from src.extract import list_raw_files
from src.extract_comercio_exterior import (
    INE_EXPORTACIONES_URL,
    INE_IMPORTACIONES_URL,
    compute_sha256,
    extract_comercio_exterior,
)
from src.load import is_already_processed
from src.load_comercio_exterior import LoadResult, load_comercio_exterior
from src.transform import read_raw_file, transform_to_fact, transform_to_staging
from src.validate import GXValidationReport, validate_transformed_data

if TYPE_CHECKING:
    from google.cloud import bigquery, firestore

logger = logging.getLogger("insight_bolivia.main")


@dataclass
class FileProcessingResult:
    """Resultado del procesamiento individual de un archivo en el pipeline."""

    file_path: Path
    operation_type: str
    hash_sha256: str
    records_raw: int = 0
    records_staging: int = 0
    validation_passed: bool = False
    status: str = "PENDING"  # SUCCESS, SKIPPED, VALIDATION_FAILED, ERROR, DRY_RUN
    validation_report: GXValidationReport | None = None
    load_result: LoadResult | None = None
    error_message: str | None = None


@dataclass
class PipelineExecutionSummary:
    """Resumen consolidado de la ejecución del pipeline ETL."""

    total_files: int = 0
    successful_files: int = 0
    skipped_files: int = 0
    failed_files: int = 0
    dry_run: bool = False
    results: list[FileProcessingResult] = field(default_factory=list)
    start_time: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    end_time: str | None = None
    duration_seconds: float = 0.0

    @property
    def is_success(self) -> bool:
        """Indica si el pipeline concluyó exitosamente sin archivos fallidos."""
        return self.failed_files == 0


def parse_date_range(range_str: str | None) -> tuple[datetime | None, datetime | None]:
    """Parsea un string de rango de fechas o gestión en límites (inicio, fin)."""
    if not range_str or not range_str.strip():
        return None, None

    cleaned = range_str.strip()
    delimiter = ":" if ":" in cleaned else (".." if ".." in cleaned else None)

    if delimiter is None:
        if len(cleaned) == 4 and cleaned.isdigit():
            year = int(cleaned)
            return datetime(year, 1, 1, tzinfo=UTC), datetime(year, 12, 31, 23, 59, 59, tzinfo=UTC)
        if len(cleaned) == 7 and cleaned[4] == "-" and cleaned[:4].isdigit() and cleaned[5:].isdigit():
            year, month = int(cleaned[:4]), int(cleaned[5:])
            if not 1 <= month <= 12:
                raise ValueError(f"Mes inválido en rango de fecha: {month}")
            start = datetime(year, month, 1, tzinfo=UTC)
            next_m = 1 if month == 12 else month + 1
            next_y = year + 1 if month == 12 else year
            end = datetime(next_y, next_m, 1, tzinfo=UTC) - pd.Timedelta(seconds=1)
            return start, end
        start_dt = pd.to_datetime(cleaned, utc=True).to_pydatetime()
        return start_dt, start_dt

    parts = cleaned.split(delimiter, 1)
    raw_start, raw_end = parts[0].strip(), parts[1].strip()
    start_dt = pd.to_datetime(raw_start, utc=True).to_pydatetime() if raw_start else None
    end_dt = pd.to_datetime(raw_end, utc=True).to_pydatetime() if raw_end else None

    if start_dt and end_dt and start_dt > end_dt:
        raise ValueError(f"La fecha de inicio ({start_dt}) no puede ser posterior a la de fin ({end_dt}).")

    return start_dt, end_dt


def filter_dataframe_by_date(
    df: pd.DataFrame,
    start_date: datetime | None,
    end_date: datetime | None,
) -> pd.DataFrame:
    """Filtra un DataFrame por columna temporal 'fecha' o 'gestion'/'mes'."""
    if df.empty or (start_date is None and end_date is None):
        return df

    filtered = df.copy()
    if "fecha" in filtered.columns:
        ts_series = pd.to_datetime(filtered["fecha"], errors="coerce", utc=True)
        mask = pd.Series(True, index=filtered.index)
        if start_date is not None:
            mask &= ts_series >= pd.Timestamp(start_date)
        if end_date is not None:
            mask &= ts_series <= pd.Timestamp(end_date)
        res_df = filtered.loc[mask]
        return pd.DataFrame(res_df).reset_index(drop=True)

    if "gestion" in filtered.columns:
        gestiones = pd.to_numeric(filtered["gestion"], errors="coerce")
        mask = pd.Series(True, index=filtered.index)
        if start_date is not None:
            mask &= gestiones >= start_date.year
        if end_date is not None:
            mask &= gestiones <= end_date.year
        res_df = filtered.loc[mask]
        return pd.DataFrame(res_df).reset_index(drop=True)

    return filtered


def process_single_file(
    file_path: Path,
    operation_type: str,
    options: argparse.Namespace,
    *,
    bq_client: bigquery.Client | None = None,
    fs_client: firestore.Client | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> FileProcessingResult:
    """Ejecuta el ciclo de vida ETL para un único archivo."""
    logger.info("Iniciando procesamiento de archivo: %s (operación: %s)", file_path.name, operation_type)

    if not file_path.exists() or not file_path.is_file():
        logger.error("El archivo objetivo no existe: %s", file_path)
        return FileProcessingResult(
            file_path=file_path,
            operation_type=operation_type,
            hash_sha256="",
            status="ERROR",
            error_message=f"Archivo no encontrado: {file_path}",
        )

    file_hash = compute_sha256(file_path)
    res = FileProcessingResult(file_path=file_path, operation_type=operation_type, hash_sha256=file_hash)

    # 1. Idempotencia previa
    if not options.force_reprocess and not options.dry_run and bq_client is not None:
        try:
            if is_already_processed(file_hash, client=bq_client):
                logger.info("Archivo '%s' ya procesado anteriormente. Omitiendo.", file_path.name)
                res.status = "SKIPPED"
                return res
        except Exception as exc:
            logger.warning("No se pudo verificar idempotencia previa en BigQuery: %s", exc)

    # 2. Transformación Staging
    try:
        df_raw = read_raw_file(file_path)
        res.records_raw = len(df_raw)
        df_stg = transform_to_staging(
            df_raw, operation_type=operation_type, filename=file_path.name, file_hash=file_hash
        )

        if start_date is not None or end_date is not None:
            df_stg = filter_dataframe_by_date(df_stg, start_date, end_date)

        res.records_staging = len(df_stg)
        if df_stg.empty:
            logger.warning("DataFrame de staging vacío para '%s'.", file_path.name)
            res.status = "SKIPPED"
            return res

        # 3. Transformación Fact y Validación de Calidad GX
        df_fact = transform_to_fact(df_raw, operation_type=operation_type)
        if start_date is not None or end_date is not None:
            df_fact = filter_dataframe_by_date(df_fact, start_date, end_date)

        if not options.skip_validation:
            val_report = validate_transformed_data(df_fact, build_docs_on_failure=True, raise_on_error=False)
            res.validation_report = val_report
            res.validation_passed = val_report.success
            if not val_report.success:
                logger.error(
                    "Validación GX FALLIDA para '%s': %s",
                    file_path.name,
                    val_report.summary_message,
                    extra={"details": {"failed_expectations": val_report.failed_details}},
                )
                res.status = "VALIDATION_FAILED"
                res.error_message = val_report.summary_message
                return res
        else:
            res.validation_passed = True

        # 4. Carga a BigQuery
        if options.dry_run:
            logger.info("Modo --dry-run activo: Persistencia omitida para '%s'.", file_path.name)
            res.status = "DRY_RUN"
            return res

        load_res = load_comercio_exterior(
            df_staging=df_stg,
            filename=file_path.name,
            file_hash=file_hash,
            force=options.force_reprocess,
            bq_client=bq_client,
            fs_client=fs_client,
        )
        res.load_result = load_res
        res.status = load_res.status
        return res

    except Exception as exc:
        logger.exception("Error procesando archivo '%s': %s", file_path.name, exc)
        res.status = "ERROR"
        res.error_message = str(exc)
        return res


def _discover_files_to_process(options: argparse.Namespace, base_dir: Path) -> list[tuple[Path, str]]:
    """Descubre la lista de archivos a procesar según las opciones configuradas."""
    files_to_process: list[tuple[Path, str]] = []

    if options.file:
        custom_file = Path(options.file).resolve()
        op_type = options.operation if options.operation != "all" else "exportaciones"
        if "imp" in custom_file.name.lower() or "import" in str(custom_file).lower():
            op_type = "importaciones"
        elif "exp" in custom_file.name.lower() or "export" in str(custom_file).lower():
            op_type = "exportaciones"
        return [(custom_file, op_type)]

    operations = ["exportaciones", "importaciones"] if options.operation == "all" else [options.operation]

    if not options.skip_extract:
        sources_map = {}
        if "exportaciones" in operations:
            sources_map["exportaciones"] = INE_EXPORTACIONES_URL
        if "importaciones" in operations:
            sources_map["importaciones"] = INE_IMPORTACIONES_URL

        extract_summary = extract_comercio_exterior(
            sources=sources_map, output_base_dir=base_dir, exclude_dictionaries=True
        )
        for meta in extract_summary.downloaded:
            if meta.file_path and meta.file_path.exists():
                files_to_process.append((meta.file_path, meta.resource.operation_type))

    if not files_to_process:
        for op in operations:
            op_folder = base_dir / op
            if op_folder.is_dir():
                for f in list_raw_files(op_folder):
                    files_to_process.append((f, op))

    return files_to_process


def run_etl_pipeline(
    options: argparse.Namespace,
    *,
    bq_client: bigquery.Client | None = None,
    fs_client: firestore.Client | None = None,
) -> PipelineExecutionSummary:
    """Orquesta la ejecución secuencial completa del pipeline ETL."""
    start_ts = datetime.now(UTC)
    setup_logging(level=options.log_level, format_type=options.log_format)

    logger.info(
        "=== INICIANDO PIPELINE ETL INSIGHTBOLIVIA ===",
        extra={"details": {"dry_run": options.dry_run, "force": options.force_reprocess, "op": options.operation}},
    )

    if options.strict_env and not options.dry_run:
        load_dotenv_file()
        validate_mandatory_env_vars()

    start_date, end_date = parse_date_range(options.date_range)
    base_dir = Path(options.raw_dir).resolve() if options.raw_dir else Path("data/raw/comercio exterior").resolve()

    summary = PipelineExecutionSummary(dry_run=options.dry_run, start_time=start_ts.isoformat())
    files_to_process = _discover_files_to_process(options, base_dir)
    summary.total_files = len(files_to_process)

    if not files_to_process:
        logger.warning("No se encontraron archivos para procesar en el pipeline.")
        summary.end_time = datetime.now(UTC).isoformat()
        summary.duration_seconds = (datetime.now(UTC) - start_ts).total_seconds()
        return summary

    for file_path, op_type in files_to_process:
        result = process_single_file(
            file_path=file_path,
            operation_type=op_type,
            options=options,
            bq_client=bq_client,
            fs_client=fs_client,
            start_date=start_date,
            end_date=end_date,
        )
        summary.results.append(result)
        if result.status in {"SUCCESS", "DRY_RUN"}:
            summary.successful_files += 1
        elif result.status == "SKIPPED":
            summary.skipped_files += 1
        else:
            summary.failed_files += 1

    end_ts = datetime.now(UTC)
    summary.end_time = end_ts.isoformat()
    summary.duration_seconds = (end_ts - start_ts).total_seconds()

    logger.info(
        "=== PIPELINE ETL FINALIZADO ===",
        extra={
            "details": {
                "total": summary.total_files,
                "exitosos": summary.successful_files,
                "omitidos": summary.skipped_files,
                "fallidos": summary.failed_files,
                "duracion_seg": round(summary.duration_seconds, 2),
                "estado": "OK" if summary.is_success else "CON_ERRORES",
            }
        },
    )
    return summary


def build_arg_parser() -> argparse.ArgumentParser:
    """Construye el parser de argumentos de línea de comandos del pipeline."""
    parser = argparse.ArgumentParser(
        prog="uv run python -m src.main",
        description="Orquestador CLI del Pipeline ETL de Comercio Exterior de InsightBolivia.",
    )
    parser.add_argument(
        "--force-reprocess",
        "-f",
        action="store_true",
        default=False,
        help="Forzar reprocesamiento de archivos omitiendo el chequeo de idempotencia por hash SHA-256.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Ejecutar extracción, transformación y validación sin persistir en BigQuery ni en Firestore.",
    )
    parser.add_argument(
        "--date-range",
        type=str,
        default=None,
        help="Filtro de fecha o gestión (ej: '2024', '2024-01:2024-12', '2024-01-01:2024-12-31').",
    )
    parser.add_argument(
        "--operation",
        "-o",
        type=str,
        choices=["all", "exportaciones", "importaciones"],
        default="all",
        help="Dominio u operación a procesar (por defecto: 'all').",
    )
    parser.add_argument(
        "--skip-extract",
        action="store_true",
        default=False,
        help="Omitir web scraping del INE y procesar únicamente archivos locales existentes en --raw-dir.",
    )
    parser.add_argument(
        "--file",
        type=str,
        default=None,
        help="Ruta a un archivo local específico para procesar individualmente.",
    )
    parser.add_argument(
        "--raw-dir",
        type=str,
        default=None,
        help="Directorio base para archivos de datos crudos (default: 'data/raw/comercio exterior').",
    )
    parser.add_argument(
        "--skip-validation",
        action="store_true",
        default=False,
        help="Omitir la suite de validación de calidad de datos con Great Expectations.",
    )
    parser.add_argument(
        "--strict-env",
        action="store_true",
        default=False,
        help="Exigir validación estricta de variables de entorno obligatorias de GCP antes de ejecutar.",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default=None,
        help="Nivel de severidad de registros de log (por defecto configurado en config.yaml o INFO).",
    )
    parser.add_argument(
        "--log-format",
        type=str,
        choices=["json", "text"],
        default=None,
        help="Formato de salida de logs ('json' para producción/SIEM o 'text' para desarrollo local).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Punto de entrada principal para ejecución CLI."""
    parser = build_arg_parser()
    options = parser.parse_args(argv)

    try:
        settings = get_settings(load_env=True)
        if options.log_level is None:
            options.log_level = settings.logging.level
        if options.log_format is None:
            options.log_format = settings.logging.format
    except Exception:
        if options.log_level is None:
            options.log_level = "INFO"
        if options.log_format is None:
            options.log_format = "json"

    try:
        summary = run_etl_pipeline(options)
        return 0 if summary.is_success else 1
    except Exception as exc:
        logger.exception("Error no controlado en la ejecución del pipeline: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
