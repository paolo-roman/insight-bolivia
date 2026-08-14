# Changelog

Todos los cambios notables en este proyecto serán documentados en este archivo.

El formato está basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/),
y este proyecto adhiere a [Semantic Versioning](https://semver.org/lang/es/).

## [Unreleased]

### Added

- `sql/ddl/00_create_datasets.sql` — Script DDL y comandos CLI (`bq mk`) para el aprovisionamiento de los 4 datasets principales en Google BigQuery (`staging`, `comercio_exterior`, `benchmark_regional`, `operations`) con retención de 180 días en `staging`, histórico indefinido en datamarts y documentación de alertas de presupuesto $0 USD en Google Cloud Billing (TICK-EP3-001).
- `tests/test_config.py` — Suite de 19 pruebas unitarias con 100% de cobertura validando lectura de configuración YAML, validación estricta con Pydantic v2, resolución de rutas, manejo de errores y sobreescrituras por variables de entorno (TICK-EP3-001).
- `tests/test_sql_ddl.py` — Suite de 6 pruebas unitarias validando sentencias DDL, retención de particiones/tablas de 180 días en staging, ausencia de caducidad en comercio exterior, y comandos CLI / Billing en `00_create_datasets.sql` (TICK-EP3-001).
- `src/firestore_client.py` — Módulo helper cliente para Google Cloud Firestore (Modo Nativo) con autenticación flexible (ADC, `GCP_SA_KEY_PATH`, `GOOGLE_APPLICATION_CREDENTIALS` o Service Account JSON), consultas tipadas de catálogo (`get_dwh_catalog`, `list_dwh_catalogs`), actualización operacional tras ETL (`update_last_refresh`), registro inmutable de auditoría (`log_audit_event`), telemetría de interacción (`record_ui_event`), y gestión de perfiles de usuario (`get_user_profile`, `upsert_user_profile`) (TICK-EP2-004).
- `tests/test_firestore_client.py` — Suite de 49 pruebas unitarias con 100% de cobertura validando inicialización del cliente Firestore, resolución de proyectos y bases de datos, consultas de catálogo, actualización de timestamps, registro de auditoría y telemetría, y operaciones sobre perfiles de usuario con mocks aislados (TICK-EP2-004).
- `firestore/seeds/seed_catalog.json` — Catálogo semilla estructurado en JSON para el Data Warehouse **Comercio Exterior de Bolivia** (`comercio_exterior`) con configuración de BigQuery (`insight-bolivia`), metadatos operativos, URL de Streamlit y registro de sus 3 vistas analíticas (`vw_balanza_comercial_mensual`, `vw_top_productos_exportados`, `vw_socios_comerciales`) (TICK-EP2-003).
- `src/seed_firestore.py` — Script ejecutable y módulo utilitario para inicialización y carga de datos semilla a la colección `dwh_catalog` en Cloud Firestore de forma idempotente (`set(..., merge=True)`), con soporte de validación Pydantic, flags CLI (`--dry-run`, `--database`, `--project`, `--file`, `--verbose`) y logging estructurado (TICK-EP2-003).
- `tests/test_seed_firestore.py` — Suite de 24 pruebas unitarias con 100% de cobertura validando sintaxis de `seed_catalog.json`, lectura de archivos, validación Pydantic, idempotencia de ingesta, cliente Firestore, flags de CLI y manejo de excepciones (TICK-EP2-003).
- `firestore/rules/firestore.rules` — Reglas de seguridad declarativas v2 para Google Cloud Firestore (Modo Nativo) con control de acceso basado en roles (RBAC: `admin`, `analyst`, `viewer`), funciones auxiliares (`isAuthenticated`, `getUserRole`, `isAdmin`), aislamiento de perfiles de usuario en `user_profiles`, lectura pública de `dwh_catalog`, e inmutabilidad estricta (`update`/`delete` deshabilitados) en colecciones append-only (`audit_log` y `ui_analytics`) (TICK-EP2-002).
- `tests/test_firestore_rules.py` — Suite de 51 pruebas unitarias con simulación lógica exhaustiva de seguridad Firestore Rules v2, validación sintáctica de archivo, balanceo estructural, helpers RBAC, inmutabilidad y pruebas de seguridad negativas ante rutas no autorizadas (TICK-EP2-002).
- `firestore/indexes/firestore.indexes.json` — Definición declarativa de índices compuestos de Cloud Firestore para consultas ordenadas por tiempo en `audit_log` (`user_id + created_at`, `action + created_at`) y `ui_analytics` (`session_id + created_at`, `page + created_at`) (TICK-EP2-001).
- `src/firestore_models.py` & `src/firestore_schemas.py` — Modelos Pydantic v2 para validación estricta de documentos NoSQL en Cloud Firestore (`UserProfile`, `CatalogView`, `DwhCatalog`, `AuditLog`, `UiAnalytics`, `UserRole`) con soporte de serialización/deserialización Firestore (`to_firestore_dict`, `from_firestore_dict`) y validadores de email, nombres y rangos (TICK-EP2-001).
- `tests/test_firestore_schemas.py` — Suite de 36 pruebas unitarias con 100% de cobertura sobre esquemas Pydantic, restricciones RBAC, serialización y validación formal de `firestore.indexes.json` (TICK-EP2-001).
- `firestore/` — Estructura de carpetas declarativas para Google Cloud Firestore (`firestore/rules/`, `firestore/indexes/`, `firestore/seeds/`) (TICK-ADJ-001).
- `Docs/REGLAS_NEGOCIO_COMERCIO_EXTERIOR.md` — Documento comprensivo de reglas de negocio para comercio exterior del INE Bolivia: esquemas estrella para exportaciones e importaciones, dimensiones compartidas y únicas, reglas de formateo NANDINA (10 dígitos), valores monetarios, tipo de cambio oficial (6.96 BOB/USD) y pesos (TICK-EP1-004).
- `notebooks/00_orquestador_eda.ipynb` — Notebook Jupyter orquestador parametrizado con Papermill para ejecutar EDAs sobre todos los archivos de comercio exterior (TICK-EP1-004).
- `notebooks/01_eda_exportaciones.ipynb` — Notebook Jupyter parametrizado para Análisis Exploratorio de Datos (EDA) de archivos individuales de exportaciones del INE (TICK-EP1-004).
- `notebooks/02_eda_importaciones.ipynb` — Notebook Jupyter parametrizado para Análisis Exploratorio de Datos (EDA) de archivos individuales de importaciones del INE (TICK-EP1-004).
- `notebooks/generate_eda_notebooks.py` — Script generador programático de los notebooks de análisis exploratorio (TICK-EP1-004).
- `src/extract.py` — Funciones de extracción para lectura resiliente de archivos Excel del INE (`read_ine_excel`, `get_excel_metadata`, `list_raw_files`) con preservación de dtypes string y detección automática de encoding (TICK-EP1-004).
- `src/transform.py` — Pipeline de transformación y normalización de esquemas del INE (`clean_export_dataframe`, `clean_import_dataframe`, `format_nandina`, `normalize_column_names`, `parse_flujo`, `compute_null_report`) con soporte para variaciones de nombres de columnas entre años (TICK-EP1-004).
- `src/validate.py` — Módulo de validación de calidad de datos (`run_export_validations`, `run_import_validations`, `validate_nandina_format`, `validate_non_negative`, `validate_weight_consistency`, `validate_null_threshold`, `validate_exchange_rate`) (TICK-EP1-004).
- `tests/test_notebooks.py` — Suite de pruebas (8 tests) para validar estructura de notebooks, tags de parámetros Papermill y ejecución integrada con datos reales (TICK-EP1-004).
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

- `config/config.yaml` — Configuración centralizada ampliada para BigQuery incluyendo `project_id: "insight-bolivia"`, `location: "US"`, `dataset_benchmark: "benchmark_regional"` y `staging_retention_days: 180` (TICK-EP3-001).
- `src/config.py` — Implementación completa del módulo de configuración con modelos Pydantic v2 inmutables (`PipelineConfig`, `SourceConfig`, `BigQueryConfig`, `DataQualityConfig`, `StreamlitConfig`, `Settings`), funciones de resolución de rutas, parseo seguro YAML, inyección de variables de entorno y caching `@lru_cache` (TICK-EP3-001).
- `tests/test_fixtures_and_setup.py` — Actualización del test de importación de `src.config` para validar exportaciones públicas principales (`Settings`, `get_settings`, `load_yaml_config`, `BigQueryConfig`) (TICK-EP3-001).
- `src/firestore_models.py` — Actualización del método `from_firestore_dict` con anotación de tipo `Self` para garantizar inferencia estricta de tipos en subclases Pydantic (TICK-EP2-004).
- `tests/test_fixtures_and_setup.py` — Adición de prueba unitaria para verificar la importabilidad de `src.firestore_client` (TICK-EP2-004).
- `src/firestore_models.py` — Adaptación del modelo `DwhCatalog` con campo `id` opcional, `last_data_refresh` nullable (`datetime | None = None`) y `bq_project` por defecto `"insight-bolivia"` para alineación completa con el archivo de catálogo semilla (TICK-EP2-003).
- `tests/test_fixtures_and_setup.py` — Adición de prueba unitaria para verificar la importabilidad de `src.seed_firestore` (TICK-EP2-003).

- `pyproject.toml` & `uv.lock` — Sustitución de dependencia `supabase>=2.7` por `google-cloud-firestore>=2.16` y `firebase-admin>=6.5` con sincronización determinista del entorno (TICK-ADJ-001).
- `.env.example` — Eliminación de variables de Supabase y adición de variables de Cloud Firestore / GCP (`FIRESTORE_DATABASE=(default)`) (TICK-ADJ-001).
- `streamlit_app/.streamlit/secrets.toml.example` — Plantilla de credenciales actualizada para Google Cloud Platform unificado (BigQuery y Cloud Firestore) (TICK-ADJ-001).
- `README.md` — Actualización integral de arquitectura, prerrequisitos de Firebase/GCP y árbol de directorios del proyecto (TICK-ADJ-001).
- `Docs/Backlog_Tickets_Desarrollo_InsightBolivia.md` — Actualización integral de trazabilidad y gobernanza del backlog: inclusión del campo `Estado` (`✅ Completado` / `⏳ Pendiente`) en los 28 tickets de desarrollo, sincronización de la tabla de resumen de épicas (9 completados, 19 pendientes) y adición de la columna de estado en la Matriz de Trazabilidad técnica (TICK-EP1-001 a TICK-EP2-004).
- `src/config.py` — Actualización de documentación de módulo para Cloud Firestore (TICK-ADJ-001).
- Verificación de `uv run ruff check .` sin advertencias ni errores (0 lints) (TICK-EP1-002, TICK-ADJ-001, TICK-EP2-003).
- Verificación de `uv run pip-audit` sin vulnerabilidades conocidas (0 CVEs) (TICK-EP1-002, TICK-ADJ-001, TICK-EP2-003).
- Verificación de `uv run pytest --cov=src --cov-fail-under=90` operativa con cobertura 100% (TICK-EP1-002, TICK-ADJ-001, TICK-EP2-003).

### Removed

- `supabase/` — Eliminación de directorio de migraciones de Supabase en favor de la arquitectura documental de Firestore (TICK-ADJ-001).

### Fixed

- Configuración de build-system (`hatchling`) en `pyproject.toml` e instalación del paquete `insight-bolivia` en modo editable en el `.venv` para que `src` sea resoluble como paquete Python estándar directamente desde `site-packages` por el entorno virtual e intérprete del IDE.
- Configuración de resolución de módulos para Pyright/VS Code (`[tool.pyright]` en `pyproject.toml`, `pyrightconfig.json` en raíz del workspace y subdirectorio, y `.vscode/settings.json`) con `extraPaths = ["insight-bolivia"]` y definición del intérprete de Python virtual.
- Corrección de imports y sintaxis de f-strings en el generador `notebooks/generate_eda_notebooks.py` y notebooks asociados.


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
