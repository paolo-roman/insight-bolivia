"""Módulo de lectura y validación de configuración del pipeline InsightBolivia.

Carga y valida la configuración centralizada desde ``config/config.yaml`` y
permite la sobreescritura dinámica mediante variables de entorno (.env).
Utiliza Pydantic v2 para garantizar tipos estrictos e inmutabilidad.
"""

from __future__ import annotations

import os
from functools import lru_cache
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

    base_url: str = Field(
        default="https://www.ine.gob.bo",
        description="URL base del portal del INE Bolivia",
    )
    user_agent: str = Field(
        default=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        ),
        description="User-Agent para evitar bloqueos HTTP 403",
    )
    timeout_seconds: int = Field(default=30, ge=1, description="Timeout en segundos por petición")
    max_retries: int = Field(default=3, ge=0, description="Número máximo de reintentos")
    retry_backoff_factor: int = Field(
        default=2, ge=1, description="Factor exponencial de reintentos"
    )


class BigQueryConfig(BaseModel):
    """Configuración de Google BigQuery (OLAP Data Warehouse)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    project_id: str = Field(
        default="insight-bolivia",
        description="ID del proyecto GCP",
    )
    location: str = Field(
        default="US",
        description="Región o multirregión de BigQuery",
    )
    dataset_staging: str = Field(
        default="staging",
        description="Dataset temporal de ingesta cruda",
    )
    dataset_comercio: str = Field(
        default="comercio_exterior",
        description="Datamart analítico principal (Star Schema)",
    )
    dataset_benchmark: str = Field(
        default="benchmark_regional",
        description="Dataset de indicadores internacionales",
    )
    dataset_operations: str = Field(
        default="operations",
        description="Dataset de logs y analítica operacional",
    )
    staging_retention_days: int = Field(
        default=180,
        ge=1,
        description="Días de retención/expiración para tablas y particiones de staging",
    )


class DataQualityConfig(BaseModel):
    """Umbrales y reglas de calidad de datos (Great Expectations)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    max_null_percentage: float = Field(
        default=5.0,
        ge=0.0,
        le=100.0,
        description="Porcentaje máximo tolerado de valores nulos",
    )
    volume_variation_threshold: float = Field(
        default=50.0,
        ge=0.0,
        description="Porcentaje umbral de variación de volumen vs promedio histórico",
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
        default=50000,
        ge=1,
        description="Límite estricto de filas por descarga CSV",
    )
    cache_ttl_seconds: int = Field(
        default=3600,
        ge=0,
        description="Tiempo de vida en caché para consultas analíticas",
    )


class Settings(BaseModel):
    """Configuración global consolidada de la plataforma InsightBolivia."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    pipeline: PipelineConfig = Field(default_factory=PipelineConfig)
    source: SourceConfig = Field(default_factory=SourceConfig)
    bigquery: BigQueryConfig = Field(default_factory=BigQueryConfig)
    data_quality: DataQualityConfig = Field(default_factory=DataQualityConfig)
    streamlit: StreamlitConfig = Field(default_factory=StreamlitConfig)


def get_config_path(custom_path: str | Path | None = None) -> Path:
    """Resuelve la ruta absoluta al archivo ``config/config.yaml``.

    Args:
        custom_path: Ruta personalizada opcional. Si se provee, se verifica su existencia.

    Returns:
        Path absoluto al archivo de configuración.

    Raises:
        FileNotFoundError: Si no se encuentra el archivo de configuración.
    """
    if custom_path is not None:
        p = Path(custom_path).resolve()
        if not p.exists():
            raise FileNotFoundError(f"Archivo de configuración no encontrado en: {p}")
        return p

    # Búsqueda en ubicaciones estándar
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
    """Carga y parsea el archivo YAML de configuración.

    Args:
        path: Ruta al archivo YAML. Si es None, utiliza ``get_config_path()``.

    Returns:
        Diccionario con la configuración parseada.

    Raises:
        FileNotFoundError: Si el archivo no existe.
        ValueError: Si el YAML está vacío o su formato es inválido.
    """
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

    # Sobreescrituras de BigQuery
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

    return config


@lru_cache(maxsize=1)
def get_settings(
    config_path: str | Path | None = None,
    reload: bool = False,
) -> Settings:
    """Obtiene la instancia de configuración validada de la plataforma (con caché LRU).

    Args:
        config_path: Ruta opcional a un archivo de configuración alternativo.
        reload: Si es True, invalida la caché y vuelve a cargar los parámetros.

    Returns:
        Instancia inmutable de ``Settings`` con los valores consolidados.
    """
    if reload:
        get_settings.cache_clear()

    raw_yaml = load_yaml_config(config_path)
    merged_config = _apply_env_overrides(raw_yaml)
    return Settings.model_validate(merged_config)
