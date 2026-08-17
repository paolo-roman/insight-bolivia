"""Pruebas unitarias para el módulo de configuración y observabilidad src.config.

Verifica:
- Carga correcta de config/config.yaml por defecto.
- Validación estricta con Pydantic v2 (Pipeline, Source, BigQuery, GX, Streamlit, Logging).
- Resolución de rutas y manejo de errores (archivo inexistente, vacío, inválido).
- Sobreescritura mediante variables de entorno (BQ, Logging).
- Carga segura de archivos .env (load_dotenv_file).
- Validación de variables obligatorias (validate_mandatory_env_vars).
- Formateo de logs estructurados en JSON (StructuredJSONFormatter).
- Inicialización y configuración del subsistema de logging (setup_logging).
- Comportamiento de caché e invalidación de get_settings().
"""

from __future__ import annotations

import json
import logging
import os
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from src.config import (
    BigQueryConfig,
    DataQualityConfig,
    LoggingConfig,
    PipelineConfig,
    Settings,
    SourceConfig,
    StreamlitConfig,
    StructuredJSONFormatter,
    _apply_env_overrides,
    get_config_path,
    get_settings,
    load_dotenv_file,
    load_yaml_config,
    setup_logging,
    validate_mandatory_env_vars,
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

    def test_logging_config_defaults(self) -> None:
        cfg = LoggingConfig()
        assert cfg.level == "INFO"
        assert cfg.format == "json"
        assert cfg.retention_days == 90

    def test_settings_frozen(self) -> None:
        settings = Settings()
        with pytest.raises(ValidationError):
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
        assert "logging" in data
        assert data["logging"]["level"] == "INFO"
        assert data["logging"]["format"] == "json"

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
        monkeypatch.setenv("LOG_LEVEL", "DEBUG")
        monkeypatch.setenv("LOG_FORMAT", "TEXT")

        raw = {"bigquery": {"project_id": "insight-bolivia", "location": "US"}}
        merged = _apply_env_overrides(raw)

        assert merged["bigquery"]["project_id"] == "custom-gcp-project"
        assert merged["bigquery"]["location"] == "EU"
        assert merged["bigquery"]["dataset_staging"] == "custom_staging"
        assert merged["bigquery"]["dataset_comercio"] == "custom_comercio"
        assert merged["bigquery"]["dataset_benchmark"] == "custom_benchmark"
        assert merged["bigquery"]["dataset_operations"] == "custom_operations"
        assert merged["logging"]["level"] == "DEBUG"
        assert merged["logging"]["format"] == "text"

    def test_override_with_gcp_project_id_fallback(self, monkeypatch: MonkeyPatch) -> None:
        monkeypatch.delenv("BQ_PROJECT_ID", raising=False)
        monkeypatch.setenv("GCP_PROJECT_ID", "fallback-gcp-project")

        raw = {"bigquery": {}}
        merged = _apply_env_overrides(raw)
        assert merged["bigquery"]["project_id"] == "fallback-gcp-project"

    def test_override_handles_non_dict_sections(self) -> None:
        raw = {"bigquery": "invalid_type", "logging": "invalid_type"}
        merged = _apply_env_overrides(raw)
        assert isinstance(merged["bigquery"], dict)
        assert isinstance(merged["logging"], dict)


class TestLoadDotenvFile:
    """Pruebas para el cargador de variables de entorno .env."""

    def test_load_dotenv_success(self, tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text(
            "# Comentario\n"
            "TEST_VAR_A=hello\n"
            "TEST_VAR_B=\"world\"\n"
            "TEST_VAR_C='single quoted'\n"
            "   \n"
            "INVALID_LINE_WITHOUT_EQUALS\n",
            encoding="utf-8",
        )
        monkeypatch.delenv("TEST_VAR_A", raising=False)
        monkeypatch.delenv("TEST_VAR_B", raising=False)
        monkeypatch.delenv("TEST_VAR_C", raising=False)

        loaded = load_dotenv_file(env_file)
        assert isinstance(loaded, dict)
        assert loaded["TEST_VAR_A"] == "hello"
        assert loaded["TEST_VAR_B"] == "world"
        assert loaded["TEST_VAR_C"] == "single quoted"
        assert os.getenv("TEST_VAR_A") == "hello"
        assert os.getenv("TEST_VAR_B") == "world"
        assert os.getenv("TEST_VAR_C") == "single quoted"

    def test_load_dotenv_respects_no_override(self, tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text("PRESET_VAR=from_file\n", encoding="utf-8")
        monkeypatch.setenv("PRESET_VAR", "from_env")

        load_dotenv_file(env_file, override=False)
        assert os.getenv("PRESET_VAR") == "from_env"

        load_dotenv_file(env_file, override=True)
        assert os.getenv("PRESET_VAR") == "from_file"

    def test_load_dotenv_without_setting_environ(self, tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text("NO_SET_VAR=value_123\n", encoding="utf-8")
        monkeypatch.delenv("NO_SET_VAR", raising=False)

        loaded = load_dotenv_file(env_file, set_environ=False)
        assert loaded.get("NO_SET_VAR") == "value_123"
        assert os.getenv("NO_SET_VAR") is None

    def test_load_dotenv_file_not_found(self, tmp_path: Path) -> None:
        non_existent = tmp_path / "absent.env"
        assert load_dotenv_file(non_existent) == {}

    def test_load_dotenv_default_candidates(self) -> None:
        result = load_dotenv_file(None, set_environ=False)
        assert isinstance(result, dict)


class TestValidateMandatoryEnvVars:
    """Pruebas de validación de variables de entorno obligatorias."""

    def test_validate_passes_when_all_present(self, monkeypatch: MonkeyPatch) -> None:
        monkeypatch.setenv("BQ_PROJECT_ID", "my-project")
        monkeypatch.setenv("GCP_SA_KEY", '{"type": "service_account"}')
        validate_mandatory_env_vars()

    def test_validate_passes_with_gcp_project_and_sa_key_path(self, monkeypatch: MonkeyPatch) -> None:
        monkeypatch.delenv("BQ_PROJECT_ID", raising=False)
        monkeypatch.delenv("GCP_SA_KEY", raising=False)
        monkeypatch.setenv("GCP_PROJECT_ID", "fallback-proj")
        monkeypatch.setenv("GCP_SA_KEY_PATH", "/path/to/key.json")
        validate_mandatory_env_vars()

    def test_validate_passes_with_google_application_credentials(self, monkeypatch: MonkeyPatch) -> None:
        monkeypatch.delenv("GCP_SA_KEY", raising=False)
        monkeypatch.setenv("BQ_PROJECT_ID", "my-project")
        monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "/path/to/adc.json")
        validate_mandatory_env_vars()

    def test_validate_fails_when_mandatory_missing(self, monkeypatch: MonkeyPatch) -> None:
        monkeypatch.delenv("BQ_PROJECT_ID", raising=False)
        monkeypatch.delenv("GCP_PROJECT_ID", raising=False)
        monkeypatch.delenv("GCP_SA_KEY", raising=False)
        monkeypatch.delenv("GCP_SA_KEY_PATH", raising=False)
        monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)

        with pytest.raises(ValueError, match="Faltan las siguientes variables"):
            validate_mandatory_env_vars()

    def test_validate_custom_required_vars(self, monkeypatch: MonkeyPatch) -> None:
        monkeypatch.delenv("CUSTOM_KEY", raising=False)
        with pytest.raises(ValueError, match="CUSTOM_KEY"):
            validate_mandatory_env_vars(["CUSTOM_KEY"])


class TestStructuredJSONFormatter:
    """Pruebas del formateador estructurado JSON."""

    def test_format_basic_log(self) -> None:
        formatter = StructuredJSONFormatter()
        record = logging.LogRecord(
            name="insight_bolivia.test",
            level=logging.INFO,
            pathname=__file__,
            lineno=10,
            msg="Mensaje de prueba: %s",
            args=("ok",),
            exc_info=None,
        )

        formatted = formatter.format(record)
        data = json.loads(formatted)

        assert "timestamp" in data
        assert data["timestamp"].endswith("Z")
        assert data["level"] == "INFO"
        assert data["module"] == "insight_bolivia.test"
        assert data["message"] == "Mensaje de prueba: ok"
        assert data["details"] == {}

    def test_format_with_details_and_exception(self) -> None:
        formatter = StructuredJSONFormatter()
        try:
            msg_err = "Error intencional"
            raise RuntimeError(msg_err)
        except RuntimeError:
            import sys

            exc_info = sys.exc_info()

        record = logging.LogRecord(
            name="insight_bolivia.error",
            level=logging.ERROR,
            pathname=__file__,
            lineno=20,
            msg="Fallo en ejecución",
            args=(),
            exc_info=exc_info,
        )
        record.details = {"rows_processed": 100, "status": "failed"}  # type: ignore[attr-defined]

        formatted = formatter.format(record)
        data = json.loads(formatted)

        assert data["level"] == "ERROR"
        assert data["details"]["rows_processed"] == 100
        assert data["details"]["status"] == "failed"
        assert "exception" in data["details"]
        assert "RuntimeError: Error intencional" in data["details"]["exception"]

    def test_format_with_stack_info(self) -> None:
        formatter = StructuredJSONFormatter()
        record = logging.LogRecord(
            name="insight_bolivia.stack",
            level=logging.WARNING,
            pathname=__file__,
            lineno=30,
            msg="Advertencia con stack",
            args=(),
            exc_info=None,
            sinfo="Stack traceback line 1\nStack traceback line 2",
        )
        formatted = formatter.format(record)
        data = json.loads(formatted)
        assert "stack_info" in data["details"]


class TestSetupLogging:
    """Pruebas de la inicialización de logging."""

    def test_setup_logging_json_output(self) -> None:
        logger = setup_logging(level="DEBUG", format_type="json", logger_name="test_json_logger")
        assert logger.level == logging.DEBUG
        assert len(logger.handlers) == 1
        assert isinstance(logger.handlers[0].formatter, StructuredJSONFormatter)

    def test_setup_logging_text_output(self) -> None:
        logger = setup_logging(level=logging.WARNING, format_type="text", logger_name="test_text_logger")
        assert logger.level == logging.WARNING
        assert len(logger.handlers) == 1
        assert not isinstance(logger.handlers[0].formatter, StructuredJSONFormatter)

    def test_setup_logging_with_file(self, tmp_path: Path) -> None:
        log_file = tmp_path / "logs" / "test.log"
        logger = setup_logging(level="INFO", format_type="json", log_file=log_file, logger_name="test_file_logger")
        assert len(logger.handlers) == 2  # StreamHandler + FileHandler

        logger.info("Registro persistido en archivo")
        for handler in logger.handlers:
            handler.flush()

        assert log_file.exists()
        content = log_file.read_text(encoding="utf-8")
        assert "Registro persistido en archivo" in content
        parsed = json.loads(content.strip())
        assert parsed["message"] == "Registro persistido en archivo"

    def test_setup_logging_defaults_from_env(self, monkeypatch: MonkeyPatch) -> None:
        monkeypatch.setenv("LOG_LEVEL", "ERROR")
        monkeypatch.setenv("LOG_FORMAT", "text")
        logger = setup_logging(logger_name="test_env_logger")
        assert logger.level == logging.ERROR


class TestGetSettings:
    """Pruebas de la función unificada get_settings."""

    def test_get_settings_default(self) -> None:
        settings = get_settings(reload=True)
        assert isinstance(settings, Settings)
        assert settings.bigquery.project_id == "insight-bolivia"
        assert settings.bigquery.dataset_staging == "staging"
        assert settings.bigquery.dataset_comercio == "comercio_exterior"
        assert settings.logging.level == "INFO"
        assert settings.logging.format == "json"
        assert settings.logging.retention_days == 90

    def test_get_settings_cached(self) -> None:
        s1 = get_settings()
        s2 = get_settings()
        assert s1 is s2

    def test_get_settings_reload_invalidates_cache(self) -> None:
        s1 = get_settings()
        s2 = get_settings(reload=True)
        assert s1 == s2
        assert s1 is not s2
        get_settings.cache_clear()  # type: ignore[attr-defined]
        s3 = get_settings()
        assert s3 == s1
        assert s3 is not s2

    def test_get_settings_strict_env_success(self, monkeypatch: MonkeyPatch) -> None:
        monkeypatch.setenv("BQ_PROJECT_ID", "test-project")
        monkeypatch.setenv("GCP_SA_KEY", "dummy-key")
        settings = get_settings(reload=True, strict_env=True)
        assert isinstance(settings, Settings)

    def test_get_settings_strict_env_failure(self, monkeypatch: MonkeyPatch) -> None:
        monkeypatch.delenv("BQ_PROJECT_ID", raising=False)
        monkeypatch.delenv("GCP_PROJECT_ID", raising=False)
        monkeypatch.delenv("GCP_SA_KEY", raising=False)
        monkeypatch.delenv("GCP_SA_KEY_PATH", raising=False)
        monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)

        with (
            patch("src.config.load_dotenv_file", return_value={}),
            pytest.raises(ValueError, match="Faltan las siguientes variables"),
        ):
            get_settings(reload=True, strict_env=True)

    def test_get_settings_load_env(self) -> None:
        with patch("src.config.load_dotenv_file", return_value={"LOADED": "1"}) as mock_load:
            settings = get_settings(reload=True, load_env=True)
            mock_load.assert_called_once()
            assert isinstance(settings, Settings)
