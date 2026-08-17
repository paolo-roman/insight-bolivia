"""Módulo de lectura, validación de configuración y observabilidad del pipeline InsightBolivia.

Carga y valida la configuración centralizada desde ``config/config.yaml`` y
permite la sobreescritura dinámica mediante variables de entorno (.env).
Utiliza Pydantic v2 para garantizar tipos estrictos e inmutabilidad.
Provee formateadores de logs estructurados en JSON para observabilidad y auditoría.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field


class PipelineConfig(BaseModel):
    """Configuración general del pipeline ETL."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(default="comercio_exterior", description="Identificador del pipeline")
    description: str = Field(
        default="Pipeline ETL de Comercio Exterior del INE Bolivia",
        description="Descripción legible del pipeline",
    )
    schedule: str = Field(default="0 6 * * *", description="Expresión cron de ejecución")


class SourceConfig(BaseModel):
    """Configuración del origen de datos (INE Bolivia / Web Scraper)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    base_url: str = Field(default="https://www.ine.gob.bo", description="URL base portal INE")
    user_agent: str = Field(
        default=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        ),
        description="User-Agent para evitar bloqueos HTTP 403",
    )
    timeout_seconds: int = Field(default=30, ge=1, description="Timeout en segundos por petición")
    max_retries: int = Field(default=3, ge=0, description="Número máximo de reintentos")
    retry_backoff_factor: int = Field(default=2, ge=1, description="Factor exponencial reintentos")


class BigQueryConfig(BaseModel):
    """Configuración de Google BigQuery (OLAP Data Warehouse)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    project_id: str = Field(default="insight-bolivia", description="ID del proyecto GCP")
    location: str = Field(default="US", description="Región o multirregión BigQuery")
    dataset_staging: str = Field(default="staging", description="Dataset temporal ingesta cruda")
    dataset_comercio: str = Field(
        default="comercio_exterior", description="Datamart analítico principal (Star Schema)"
    )
    dataset_benchmark: str = Field(
        default="benchmark_regional", description="Dataset de indicadores internacionales"
    )
    dataset_operations: str = Field(
        default="operations", description="Dataset de logs y analítica operacional"
    )
    staging_retention_days: int = Field(
        default=180, ge=1, description="Días de retención para staging"
    )


class DataQualityConfig(BaseModel):
    """Umbrales y reglas de calidad de datos (Great Expectations)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    max_null_percentage: float = Field(
        default=5.0, ge=0.0, le=100.0, description="Porcentaje máximo tolerado de valores nulos"
    )
    volume_variation_threshold: float = Field(
        default=50.0, ge=0.0, description="Porcentaje umbral variación volumen vs promedio"
    )
    mandatory_columns: list[str] = Field(
        default_factory=lambda: [
            "fecha",
            "codigo_nandina",
            "pais_iso",
            "tipo_operacion",
            "valor_fob_usd",
        ],
        description="Columnas de presencia obligatoria sin nulos",
    )


class StreamlitConfig(BaseModel):
    """Configuración de la capa de visualización (Streamlit App)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    max_download_rows: int = Field(
        default=50000, ge=1, description="Límite estricto de filas por descarga CSV"
    )
    cache_ttl_seconds: int = Field(
        default=3600, ge=0, description="Tiempo de vida en caché para consultas analíticas"
    )


class LoggingConfig(BaseModel):
    """Configuración de observabilidad y logging estructurado."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    level: str = Field(
        default="INFO",
        description="Nivel de severidad de logs (DEBUG, INFO, WARNING, ERROR, CRITICAL)",
    )
    format: str = Field(
        default="json",
        description="Formato de emisión de registros ('json' o 'text')",
    )
    retention_days: int = Field(
        default=90, ge=1, description="Días de retención de registros de logs"
    )


class Settings(BaseModel):
    """Configuración global consolidada de la plataforma InsightBolivia."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    pipeline: PipelineConfig = Field(default_factory=PipelineConfig)
    source: SourceConfig = Field(default_factory=SourceConfig)
    bigquery: BigQueryConfig = Field(default_factory=BigQueryConfig)
    data_quality: DataQualityConfig = Field(default_factory=DataQualityConfig)
    streamlit: StreamlitConfig = Field(default_factory=StreamlitConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)


def load_dotenv_file(
    dotenv_path: str | Path | None = None,
    override: bool = False,
    set_environ: bool = True,
) -> dict[str, str]:
    """Carga variables de entorno desde un archivo .env si existe.

    Args:
        dotenv_path: Ruta opcional al archivo .env. Si es None, busca en rutas estándar.
        override: Si es True, sobreescribe variables existentes en os.environ.
        set_environ: Si es True, inyecta las variables parseadas en os.environ.

    Returns:
        Diccionario con las variables parseadas desde el archivo .env.
    """
    candidates: list[Path] = []
    if dotenv_path is not None:
        candidates.append(Path(dotenv_path).resolve())
    else:
        candidates.extend(
            [
                Path.cwd() / ".env",
                Path.cwd() / "insight-bolivia" / ".env",
                Path(__file__).resolve().parent.parent / ".env",
            ]
        )

    target_file: Path | None = None
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            target_file = candidate
            break

    if target_file is None:
        return {}

    parsed_vars: dict[str, str] = {}
    with target_file.open(encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue

            key, _, val = stripped.partition("=")
            key, val = key.strip(), val.strip()

            if (val.startswith('"') and val.endswith('"')) or (
                val.startswith("'") and val.endswith("'")
            ):
                val = val[1:-1]

            if key:
                parsed_vars[key] = val
                if set_environ and (override or key not in os.environ):
                    os.environ[key] = val

    return parsed_vars


def validate_mandatory_env_vars(required_vars: list[str] | None = None) -> None:
    """Valida la presencia de variables de entorno obligatorias para ejecución en GCP/CI.

    Args:
        required_vars: Lista de nombres de variables requeridas.
            Por defecto: ["BQ_PROJECT_ID", "GCP_SA_KEY"].

    Raises:
        ValueError: Si alguna variable requerida no está definida o está vacía.
    """
    if required_vars is None:
        required_vars = ["BQ_PROJECT_ID", "GCP_SA_KEY"]

    missing: list[str] = []
    for var in required_vars:
        val = os.getenv(var)
        if var == "GCP_SA_KEY" and not val and (
            os.getenv("GCP_SA_KEY_PATH") or os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        ):
            continue
        if var == "BQ_PROJECT_ID" and not val and os.getenv("GCP_PROJECT_ID"):
            continue

        if not val or not val.strip():
            missing.append(var)

    if missing:
        raise ValueError(
            f"Faltan las siguientes variables de entorno obligatorias: {', '.join(missing)}"
        )


class StructuredJSONFormatter(logging.Formatter):
    """Formateador de logs en formato JSON estructurado para observabilidad."""

    def format(self, record: logging.LogRecord) -> str:
        """Formatea un LogRecord en JSON unilínea compatible con Cloud Logging y SIEM."""
        record_time = datetime.fromtimestamp(record.created, tz=UTC)
        iso_timestamp = record_time.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

        details: dict[str, Any] = {}
        if hasattr(record, "details") and isinstance(record.details, dict):
            details.update(record.details)

        if record.exc_info:
            details["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            details["stack_info"] = self.formatStack(record.stack_info)

        log_payload: dict[str, Any] = {
            "timestamp": iso_timestamp,
            "level": record.levelname,
            "module": record.name,
            "message": record.getMessage(),
            "details": details,
        }
        return json.dumps(log_payload, default=str, ensure_ascii=False)


def setup_logging(
    level: str | int | None = None,
    format_type: str | None = None,
    log_file: str | Path | None = None,
    logger_name: str | None = None,
) -> logging.Logger:
    """Configura el sistema de logging estándar o estructurado en JSON."""
    target_logger = logging.getLogger(logger_name)

    if level is None:
        level_str = os.getenv("LOG_LEVEL", "INFO").upper()
        log_level = getattr(logging, level_str, logging.INFO)
    elif isinstance(level, str):
        log_level = getattr(logging, level.upper(), logging.INFO)
    else:
        log_level = level

    target_logger.setLevel(log_level)

    if format_type is None:
        format_type = os.getenv("LOG_FORMAT", "json").lower()

    if format_type == "json":
        formatter: logging.Formatter = StructuredJSONFormatter()
    else:
        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    target_logger.handlers.clear()

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setLevel(log_level)
    stream_handler.setFormatter(formatter)
    target_logger.addHandler(stream_handler)

    if log_file is not None:
        file_path = Path(log_file).resolve()
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(file_path, encoding="utf-8")
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        target_logger.addHandler(file_handler)

    return target_logger


def get_config_path(custom_path: str | Path | None = None) -> Path:
    """Resuelve la ruta absoluta al archivo ``config/config.yaml``."""
    if custom_path is not None:
        p = Path(custom_path).resolve()
        if not p.exists():
            raise FileNotFoundError(f"Archivo de configuración no encontrado en: {p}")
        return p

    candidates = [
        Path.cwd() / "config" / "config.yaml",
        Path.cwd() / "insight-bolivia" / "config" / "config.yaml",
        Path(__file__).resolve().parent.parent / "config" / "config.yaml",
    ]

    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()

    raise FileNotFoundError(
        "No se pudo localizar el archivo 'config/config.yaml' en las rutas estándar."
    )


def load_yaml_config(path: str | Path | None = None) -> dict[str, Any]:
    """Carga y parsea el archivo YAML de configuración."""
    resolved_path = get_config_path(path)
    with resolved_path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if data is None:
        raise ValueError(f"El archivo de configuración '{resolved_path}' está vacío.")

    if not isinstance(data, dict):
        raise ValueError(
            f"El archivo de configuración '{resolved_path}' debe ser un mapeo/diccionario."
        )

    return data


def _apply_env_overrides(raw_config: dict[str, Any]) -> dict[str, Any]:
    """Aplica sobreescrituras desde variables de entorno sobre el diccionario de configuración."""
    config = {k: (v.copy() if isinstance(v, dict) else v) for k, v in raw_config.items()}

    bq_section = config.setdefault("bigquery", {})
    if not isinstance(bq_section, dict):
        bq_section = {}
        config["bigquery"] = bq_section

    if env_val := os.getenv("BQ_PROJECT_ID") or os.getenv("GCP_PROJECT_ID"):
        bq_section["project_id"] = env_val
    if env_val := os.getenv("BQ_LOCATION"):
        bq_section["location"] = env_val
    if env_val := os.getenv("BQ_STAGING_DATASET"):
        bq_section["dataset_staging"] = env_val
    if env_val := os.getenv("BQ_DATASET") or os.getenv("BQ_COMERCIO_DATASET"):
        bq_section["dataset_comercio"] = env_val
    if env_val := os.getenv("BQ_BENCHMARK_DATASET"):
        bq_section["dataset_benchmark"] = env_val
    if env_val := os.getenv("BQ_OPERATIONS_DATASET"):
        bq_section["dataset_operations"] = env_val

    log_section = config.setdefault("logging", {})
    if not isinstance(log_section, dict):
        log_section = {}
        config["logging"] = log_section

    if env_val := os.getenv("LOG_LEVEL"):
        log_section["level"] = env_val.upper()
    if env_val := os.getenv("LOG_FORMAT"):
        log_section["format"] = env_val.lower()

    return config


_SETTINGS_CACHE: Settings | None = None


def get_settings(
    config_path: str | Path | None = None,
    reload: bool = False,
    strict_env: bool = False,
    load_env: bool = False,
) -> Settings:
    """Obtiene la instancia de configuración validada de la plataforma con soporte de caché."""
    global _SETTINGS_CACHE
    if reload or _SETTINGS_CACHE is None or config_path is not None or strict_env:
        if load_env:
            load_dotenv_file()

        if strict_env:
            validate_mandatory_env_vars()

        raw_yaml = load_yaml_config(config_path)
        merged_config = _apply_env_overrides(raw_yaml)
        settings = Settings.model_validate(merged_config)

        if config_path is None and not strict_env and not load_env:
            _SETTINGS_CACHE = settings
        return settings

    return _SETTINGS_CACHE


def _clear_settings_cache() -> None:
    """Limpia la caché de configuración en memoria."""
    global _SETTINGS_CACHE
    _SETTINGS_CACHE = None


get_settings.cache_clear = _clear_settings_cache  # type: ignore[attr-defined]
