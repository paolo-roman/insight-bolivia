"""Pruebas unitarias para el módulo de configuración src.config.

Verifica:
- Carga correcta de config/config.yaml por defecto.
- Validación estricta con Pydantic v2.
- Resolución de rutas y manejo de errores (archivo inexistente, vacío, inválido).
- Sobreescritura mediante variables de entorno (BQ_PROJECT_ID, BQ_LOCATION, etc.).
- Comportamiento de caché e invalidación de get_settings().
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from src.config import (
    BigQueryConfig,
    DataQualityConfig,
    PipelineConfig,
    Settings,
    SourceConfig,
    StreamlitConfig,
    _apply_env_overrides,
    get_config_path,
    get_settings,
    load_yaml_config,
)

if TYPE_CHECKING:
    from pathlib import Path

    from pytest import MonkeyPatch


class TestConfigModels:
    """Verifica los valores por defecto y validaciones de los modelos Pydantic."""

    def test_pipeline_config_defaults(self) -> None:
        cfg = PipelineConfig()
        assert cfg.name == "comercio_exterior"
        assert "Comercio Exterior" in cfg.description
        assert cfg.schedule == "0 6 * * *"

    def test_source_config_defaults(self) -> None:
        cfg = SourceConfig()
        assert "ine.gob.bo" in cfg.base_url
        assert cfg.timeout_seconds == 30
        assert cfg.max_retries == 3
        assert cfg.retry_backoff_factor == 2

    def test_bigquery_config_defaults(self) -> None:
        cfg = BigQueryConfig()
        assert cfg.project_id == "insight-bolivia"
        assert cfg.location == "US"
        assert cfg.dataset_staging == "staging"
        assert cfg.dataset_comercio == "comercio_exterior"
        assert cfg.dataset_benchmark == "benchmark_regional"
        assert cfg.dataset_operations == "operations"
        assert cfg.staging_retention_days == 180

    def test_data_quality_config_defaults(self) -> None:
        cfg = DataQualityConfig()
        assert cfg.max_null_percentage == 5.0
        assert cfg.volume_variation_threshold == 50.0
        assert len(cfg.mandatory_columns) == 5
        assert "codigo_nandina" in cfg.mandatory_columns

    def test_streamlit_config_defaults(self) -> None:
        cfg = StreamlitConfig()
        assert cfg.max_download_rows == 50000
        assert cfg.cache_ttl_seconds == 3600

    def test_settings_frozen(self) -> None:
        settings = Settings()
        with pytest.raises(ValidationError):
            # Model is frozen, direct assignment should fail
            settings.pipeline = PipelineConfig()  # type: ignore[misc]


class TestGetConfigPath:
    """Pruebas para la resolución de rutas del archivo de configuración."""

    def test_get_config_path_default(self) -> None:
        path = get_config_path()
        assert path.exists()
        assert path.name == "config.yaml"

    def test_get_config_path_custom_existing(self, tmp_path: Path) -> None:
        custom_file = tmp_path / "custom_config.yaml"
        custom_file.write_text("pipeline:\n  name: test\n", encoding="utf-8")
        result = get_config_path(custom_file)
        assert result == custom_file.resolve()

    def test_get_config_path_custom_not_found(self, tmp_path: Path) -> None:
        non_existent = tmp_path / "does_not_exist.yaml"
        with pytest.raises(FileNotFoundError, match="no encontrado"):
            get_config_path(non_existent)

    def test_get_config_path_standard_locations_not_found(self) -> None:
        with (
            patch("pathlib.Path.exists", return_value=False),
            pytest.raises(FileNotFoundError, match="No se pudo localizar"),
        ):
            get_config_path()


class TestLoadYamlConfig:
    """Pruebas de carga y parseo del archivo YAML."""

    def test_load_default_yaml(self) -> None:
        data = load_yaml_config()
        assert isinstance(data, dict)
        assert "pipeline" in data
        assert "bigquery" in data
        assert data["bigquery"]["dataset_staging"] == "staging"
        assert data["bigquery"]["dataset_comercio"] == "comercio_exterior"
        assert data["bigquery"]["dataset_benchmark"] == "benchmark_regional"
        assert data["bigquery"]["dataset_operations"] == "operations"
        assert data["bigquery"]["staging_retention_days"] == 180

    def test_load_empty_yaml_raises_value_error(self, tmp_path: Path) -> None:
        empty_file = tmp_path / "empty.yaml"
        empty_file.write_text("", encoding="utf-8")
        with pytest.raises(ValueError, match="está vacío"):
            load_yaml_config(empty_file)

    def test_load_non_dict_yaml_raises_value_error(self, tmp_path: Path) -> None:
        list_file = tmp_path / "list.yaml"
        list_file.write_text("- item1\n- item2\n", encoding="utf-8")
        with pytest.raises(ValueError, match="debe ser un mapeo/diccionario"):
            load_yaml_config(list_file)


class TestApplyEnvOverrides:
    """Pruebas de sobreescritura con variables de entorno."""

    def test_override_project_and_location(self, monkeypatch: MonkeyPatch) -> None:
        monkeypatch.setenv("BQ_PROJECT_ID", "custom-gcp-project")
        monkeypatch.setenv("BQ_LOCATION", "EU")
        monkeypatch.setenv("BQ_STAGING_DATASET", "custom_staging")
        monkeypatch.setenv("BQ_DATASET", "custom_comercio")
        monkeypatch.setenv("BQ_BENCHMARK_DATASET", "custom_benchmark")
        monkeypatch.setenv("BQ_OPERATIONS_DATASET", "custom_operations")

        raw = {"bigquery": {"project_id": "insight-bolivia", "location": "US"}}
        merged = _apply_env_overrides(raw)

        assert merged["bigquery"]["project_id"] == "custom-gcp-project"
        assert merged["bigquery"]["location"] == "EU"
        assert merged["bigquery"]["dataset_staging"] == "custom_staging"
        assert merged["bigquery"]["dataset_comercio"] == "custom_comercio"
        assert merged["bigquery"]["dataset_benchmark"] == "custom_benchmark"
        assert merged["bigquery"]["dataset_operations"] == "custom_operations"

    def test_override_with_gcp_project_id_fallback(self, monkeypatch: MonkeyPatch) -> None:
        monkeypatch.delenv("BQ_PROJECT_ID", raising=False)
        monkeypatch.setenv("GCP_PROJECT_ID", "fallback-gcp-project")

        raw = {"bigquery": {}}
        merged = _apply_env_overrides(raw)
        assert merged["bigquery"]["project_id"] == "fallback-gcp-project"

    def test_override_handles_non_dict_bigquery_section(self) -> None:
        raw = {"bigquery": "invalid_type"}
        merged = _apply_env_overrides(raw)
        assert isinstance(merged["bigquery"], dict)


class TestGetSettings:
    """Pruebas de la función unificada get_settings."""

    def test_get_settings_default(self) -> None:
        settings = get_settings(reload=True)
        assert isinstance(settings, Settings)
        assert settings.bigquery.project_id == "insight-bolivia"
        assert settings.bigquery.dataset_staging == "staging"
        assert settings.bigquery.dataset_comercio == "comercio_exterior"
        assert settings.bigquery.dataset_benchmark == "benchmark_regional"
        assert settings.bigquery.dataset_operations == "operations"
        assert settings.bigquery.staging_retention_days == 180

    def test_get_settings_cached(self) -> None:
        s1 = get_settings()
        s2 = get_settings()
        assert s1 is s2

    def test_get_settings_reload_invalidates_cache(self) -> None:
        s1 = get_settings()
        s2 = get_settings(reload=True)
        assert s1 == s2
        assert s1 is not s2
