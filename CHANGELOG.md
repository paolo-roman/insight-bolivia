# Changelog

Todos los cambios notables en este proyecto serán documentados en este archivo.

El formato está basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/),
y este proyecto adhiere a [Semantic Versioning](https://semver.org/lang/es/).

## [Unreleased]

## [0.1.0] - 2026-08-12

### Added

- Inicialización del proyecto Python con gestor de paquetes `uv`.
- Configuración de `pyproject.toml` con todas las dependencias base del proyecto.
- Estructura de directorios estándar siguiendo el Apéndice A de la arquitectura:
  - `src/` — Paquete principal con módulos placeholder (`extract`, `transform`, `load`, `validate`, `config`).
  - `sql/ddl/` y `sql/views/` — Scripts DDL y vistas SQL para BigQuery.
  - `supabase/migrations/` — Migraciones versionadas para Supabase.
  - `tests/` — Suite de pruebas con directorio de fixtures.
  - `streamlit_app/` — Aplicación Streamlit con estructura de páginas y componentes.
  - `notebooks/` — Jupyter notebooks para análisis exploratorio.
  - `config/` — Archivos de configuración del pipeline (`config.yaml`).
  - `gx/` — Contexto y suites de Great Expectations.
  - `data/raw/` — Directorio para archivos fuente descargados.
  - `.github/workflows/` — Workflows de GitHub Actions.
- Archivo `.gitignore` estricto con reglas para secretos, datos, Python, GX e IDEs.
- Plantilla `.env.example` con todas las variables de entorno requeridas.
- Plantilla `streamlit_app/.streamlit/secrets.toml.example` para credenciales de Streamlit.
- Licencia BSD 3-Clause con nota de protección de marca "InsightBolivia".
- Archivo `README.md` con instrucciones de setup local mediante `uv`.
- Archivo `last_run.txt` para mantener activo el cron de GitHub Actions.
- Configuración de Ruff (linter/formatter) en `pyproject.toml`.
- Configuración de Pytest y coverage en `pyproject.toml`.
- Archivo `config/config.yaml` con parámetros del pipeline ETL.
- Configuración mínima de Great Expectations (`gx/great_expectations.yml`).

[Unreleased]: https://github.com/insightbolivia/insight-bolivia/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/insightbolivia/insight-bolivia/releases/tag/v0.1.0
