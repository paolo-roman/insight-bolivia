# Changelog

Todos los cambios notables en este proyecto serán documentados en este archivo.

El formato está basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/),
y este proyecto adhiere a [Semantic Versioning](https://semver.org/lang/es/).

## [Unreleased]

### Added

- `Docs/REGLAS_NEGOCIO_COMERCIO_EXTERIOR.md` — Documento comprensivo de reglas de negocio para comercio exterior del INE Bolivia: esquemas estrella para exportaciones e importaciones, dimensiones compartidas y únicas, reglas de formateo NANDINA (10 dígitos), valores monetarios, tipo de cambio oficial (6.96 BOB/USD) y pesos (TICK-EP1-004).
- `notebooks/00_orquestador_eda.ipynb` — Notebook Jupyter orquestador parametrizado con Papermill para ejecutar EDAs sobre todos los archivos de comercio exterior (TICK-EP1-004).
- `notebooks/01_eda_exportaciones.ipynb` — Notebook Jupyter parametrizado para Análisis Exploratorio de Datos (EDA) de archivos individuales de exportaciones del INE (TICK-EP1-004).
- `notebooks/02_eda_importaciones.ipynb` — Notebook Jupyter parametrizado para Análisis Exploratorio de Datos (EDA) de archivos individuales de importaciones del INE (TICK-EP1-004).
- `notebooks/generate_eda_notebooks.py` — Script generador programático de los notebooks de análisis exploratorio (TICK-EP1-004).
- `src/extract.py` — Funciones de extracción para lectura resiliente de archivos Excel del INE (`read_ine_excel`, `get_excel_metadata`, `list_raw_files`) con preservación de dtypes string y detección automática de encoding (TICK-EP1-004).
- `src/transform.py` — Pipeline de transformación y normalización de esquemas del INE (`clean_export_dataframe`, `clean_import_dataframe`, `format_nandina`, `normalize_column_names`, `parse_flujo`, `compute_null_report`) con soporte para variaciones de nombres de columnas entre años (TICK-EP1-004).
- `src/validate.py` — Módulo de validación de calidad de datos (`run_export_validations`, `run_import_validations`, `validate_nandina_format`, `validate_non_negative`, `validate_weight_consistency`, `validate_null_threshold`, `validate_exchange_rate`) (TICK-EP1-004).
- `tests/test_extract.py`, `tests/test_transform.py`, `tests/test_validate.py` — 77 pruebas unitarias nuevas con 100% de cobertura sobre los módulos `src` (TICK-EP1-004).
- `.github/workflows/tests.yml` — Workflow de CI automatizado en GitHub Actions para Ruff Linter, auditoría Security pip-audit y Pytest con cobertura $\ge 90\%$ (TICK-EP1-003).
- `tests/conftest.py` — Fixtures compartidos de pytest con rutas a archivos sintéticos de prueba (TICK-EP1-002).
- `tests/test_fixtures_and_setup.py` — Suite de pruebas (24 tests) para validar fixtures, esquema, encoding e importabilidad de módulos `src` (TICK-EP1-002).
- `tests/generate_fixtures.py` — Script generador de datos sintéticos anonimizados para `tests/fixtures/` (TICK-EP1-002).
- `tests/fixtures/sample_exportaciones.xlsx` — Fixture Excel con 5 registros de exportaciones con esquema completo (TICK-EP1-002).
- `tests/fixtures/sample_importaciones.csv` — Fixture CSV UTF-8 con 5 registros de importaciones (TICK-EP1-002).
- `tests/fixtures/sample_empty.xlsx` — Fixture Excel vacío (solo encabezados, sin filas de datos) (TICK-EP1-002).
- `tests/fixtures/sample_bad_encoding.csv` — Fixture CSV con encoding ISO-8859-1 y caracteres acentuados (TICK-EP1-002).

### Changed

- Verificación de `uv run ruff check .` sin advertencias ni errores (0 lints) (TICK-EP1-002).
- Verificación de `uv run pip-audit` sin vulnerabilidades conocidas (0 CVEs) (TICK-EP1-002).
- Verificación de `uv run pytest --cov=src --cov-fail-under=90` operativa con cobertura 100% (TICK-EP1-002).

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
