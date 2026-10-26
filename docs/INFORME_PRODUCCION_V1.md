# Informe de Auditoría de Producción y Resiliencia Operativa V1.0

**Proyecto:** InsightBolivia  
**Fecha de Auditoría:** 26 de Octubre de 2026  
**Auditor:** DevOps, Architecture & Production Readiness Specialist (`devops-auditor`)  
**Rama / Commit Auditado:** `main` (`2fe163c`)  
**Veredicto Final:** **GO-WITH-RISKS** (Pase a producción condicionado a la subsanación de riesgos identificados)

---

## 1. Resumen Ejecutivo y Veredicto

Se ha completado la auditoría exhaustiva de arquitectura operacional, tuberías de ingesta (ETL), automatización CI/CD, observabilidad, runbooks y preparación para despliegue en producción de la plataforma **InsightBolivia**.

### Veredicto: **GO-WITH-RISKS**

La plataforma exhibe una **madurez técnica sobresaliente** en calidad de código (cobertura de pruebas unitarias del **98.35%** con 766 pruebas pasando exitosamente y 0 fallos de linter Ruff), desacoplamiento arquitectónico, diseño OLAP en estrella sobre BigQuery con costo **$0.00 USD**, validación de esquemas con Great Expectations 1.x e idempotencia estricta mediante SHA-256 en streaming. 

No obstante, se otorga veredicto **GO-WITH-RISKS** debido a **dos hallazgos de severidad ALTA y tres de severidad MEDIA** que requieren atención inmediata:
1. **Fallo en barrera de seguridad de dependencias (`pip-audit`)**: La auditoría de seguridad automatizada en CI falla (código de salida 1) por 44 vulnerabilidades conocidas en dependencias fijadas en `uv.lock` (`certifi`, `filelock`, `pillow`).
2. **Éxito silencioso ante extracciones vacías o fallidas ("Ghost Runs")**: Si el portal del INE falla o cambia su estructura y la descarga web falla, el orquestador principal finaliza con código de salida `0`, impidiendo que GitHub Actions detecte el fallo y despache alertas a Discord.
3. **Deriva de nomenclatura en variables de entorno**: Inconsistencias entre `.env.example`, `config.yaml`, `src/config.py` y el runbook de cargas manuales sobre nombres de datasets de BigQuery y Firestore.
4. **Desconexión de parámetros de red de `config.yaml`**: Los parámetros de timeout y retries configurados en `config.yaml` no son inyectados en la invocación de `extract_comercio_exterior` desde `src/main.py`.
5. **Riesgo de fallo en commit anti-cron por reglas de protección de rama**: El push automático de `last_run.txt` directo a `main` fallará si la rama tiene habilitada protección de pull requests.

---

## 2. Scorecard de Producción

| Dimensión Operativa | Estado | Métricas Clave | Observaciones Principales |
| :--- | :---: | :--- | :--- |
| **1. Arquitectura y Configuración 12-Factor** | `RISK` | 100% tipado estricto con Pydantic v2 | Desalineación menor en nombres de variables de entorno entre docs, `.env.example` y `src/config.py`. Parámetros de red de `config.yaml` no heredados por el extractor. |
| **2. Aislamiento de Secretos y Credenciales** | `OK` | 0 secretos hardcodeados, `.gitignore` completo | Claves JSON y `.env` excluidas. Inyección en CI mediante GitHub Secrets y en Streamlit Cloud vía `st.secrets`. |
| **3. Resiliencia de Ingesta ETL y Tolerancia de Red** | `RISK` | SHA-256 en streaming, 3 retries HTTP, User-Agent real | Idempotencia sólida. Riesgo de "Ghost Runs" ante fallos de scraping donde descargas fallidas se descartan y retornan código 0. |
| **4. Integridad de Esquema y Calidad de Datos (GX)** | `OK` | 100% validación previa a BigQuery con Great Expectations | Reglas estrictas de nulidad, rangos, regex NANDINA de 10 dígitos y coherencia física ponderada para importaciones. |
| **5. Automatización CI/CD y Barreras de Calidad** | `RISK` | 766 tests OK, cov 98.35%, Ruff clean | `pip-audit` bloquea CI por 44 CVEs en dependencias bloqueadas. Commit automático de `last_run.txt` choca con branch protection. |
| **6. Monitoreo, Alerting y Observabilidad** | `RISK` | Logs JSON estructurados, Discord Embeds formateados | Logs estructurados compatibles con SIEM/Cloud Logging. Alerta de Discord envía texto estático genérico y solo dispara ante `exit code != 0`. |
| **7. Preparación de Despliegue en la Nube (GCP & Streamlit)** | `OK` | Particionado BigQuery mensual, 1 GB RAM respetado | Arquitectura probada para mantenerse estrictamente en el *Always Free Tier* ($0 USD). Límites de descarga de 50k filas protegen la memoria. |
| **8. Runbooks Operacionales y Troubleshooting** | `OK` | 8 problemas reales documentados con causas y soluciones | Guías completas, diagramas Mermaid claros, comandos reproducibles con `uv`. |

---

## 3. Hallazgos Detallados de Auditoría

### [HIGH] PROD-01: Fallo de auditoría de seguridad `pip-audit` que bloquea el pipeline CI
- **Severidad:** HIGH
- **Área:** `.github/workflows/tests.yml:37` / `uv.lock`
- **Evidencia:** La ejecución local y en CI del comando `uv run pip-audit` finaliza con código de salida 1:
  ```
  Found 44 known vulnerabilities in 3 packages
  certifi   2026.7.22  PYSEC-2026-4320  Fix: 2026.10.19
  filelock  4.1.2      CVE-2026-112906 (y 5 más) Fix: 4.2.1
  pillow    12.3.0     CVE-2026-112895 (y 36 más) Fix: 13.0.0
  ```
- **Reproducción:**
  1. Ejecutar en la terminal raíz: `uv run pip-audit`.
  2. Comprobar que el comando reporta 44 vulnerabilidades y retorna código `1`.
- **Impacto:** En el workflow [`.github/workflows/tests.yml`](file:///c:/Proyectos/InsightBolivia/insight-bolivia/.github/workflows/tests.yml#L37), el paso *"Run Dependency Security Audit"* fallará ante cualquier push o pull request a `main`/`develop`, bloqueando las barreras de integración continua.
- **Recomendación:** Actualizar las dependencias transitivas fijadas en `uv.lock` ejecutando:
  ```bash
  uv lock --upgrade-package certifi --upgrade-package filelock --upgrade-package pillow
  ```
- **Sugerido para:** `devops-engineer`

---

### [HIGH] PROD-02: Éxito silencioso del pipeline ante fallos de scraping o archivos no procesados ("Ghost Runs")
- **Severidad:** HIGH
- **Área:** [`src/main.py`](file:///c:/Proyectos/InsightBolivia/insight-bolivia/src/main.py#L267-L274), [`src/main.py`](file:///c:/Proyectos/InsightBolivia/insight-bolivia/src/main.py#L319-L323), [`src/extract_comercio_exterior.py`](file:///c:/Proyectos/InsightBolivia/insight-bolivia/src/extract_comercio_exterior.py#L461-L469)
- **Evidencia:** 
  1. En `src/main.py:267-274`, el orquestador consume `extract_summary.downloaded`, pero ignora por completo `extract_summary.failed`. Si 5 archivos fallan en su descarga, no son registrados en `summary.results` ni incrementan `summary.failed_files`.
  2. Si no se encuentran archivos (ej. caída del portal del INE y no hay archivos locales nuevos), `run_etl_pipeline()` retorna un `summary` con `total_files = 0` y `failed_files = 0`.
  3. La propiedad `is_success` evalúa `self.failed_files == 0` (True), por lo que `main()` retorna código `0`.
- **Reproducción:**
  1. Simular indisponibilidad de red hacia `ine.gob.bo` o directorio raw vacío.
  2. Ejecutar `uv run python -m src.main`.
  3. Comprobar que el proceso sale con código 0 (`echo $?` -> 0).
- **Impacto:** En GitHub Actions, el job programado finalizará en estado verde (`Success`). El paso de alerta por Discord (`if: failure()`) **no se ejecutará**, y el paso de anti-cron comiteará un nuevo timestamp en `last_run.txt`. El equipo operativo asumirá que la ingesta diaria fue exitosa cuando en realidad no se procesó ningún dato.
- **Recomendación:**
  1. Si `extract_summary.failed` contiene elementos y no se activó `--skip-extract`, añadir dichos fallos a `summary.results` como `FileProcessingResult(status="ERROR")` para que `failed_files > 0`.
  2. En `src/main.py:461`, si `summary.total_files == 0` durante una ejecución programada (sin filtros de fecha restrictivos), registrar una advertencia crítica o permitir un flag `--fail-on-empty` para alertar en Discord.
- **Sugerido para:** `backend-developer`

---

### [MEDIUM] PROD-03: Deriva de nomenclatura y variables de entorno entre `.env.example`, `config.py` y Runbook
- **Severidad:** MEDIUM
- **Área:** [`.env.example`](file:///c:/Proyectos/InsightBolivia/insight-bolivia/.env.example#L18-L19), [`src/config.py`](file:///c:/Proyectos/InsightBolivia/insight-bolivia/src/config.py#L376-L382), [`docs/GUIA_CARGAS_MANUALES_Y_TROUBLESHOOTING.md`](file:///c:/Proyectos/InsightBolivia/insight-bolivia/docs/GUIA_CARGAS_MANUALES_Y_TROUBLESHOOTING.md#L46-L53)
- **Evidencia:**
  - En `.env.example`: se declaran `BQ_DATASET_STAGING` y `BQ_DATASET_OPERATIONS`.
  - En `src/config.py`: se leen `os.getenv("BQ_STAGING_DATASET")` y `os.getenv("BQ_OPERATIONS_DATASET")`. Las variables con el prefijo invertido de `.env.example` son ignoradas y toman el valor por defecto de `config.yaml`.
  - En `GUIA_CARGAS_MANUALES_Y_TROUBLESHOOTING.md`: se documentan `BIGQUERY_DATASET_STAGING` y `FIRESTORE_DATABASE_ID`, las cuales no existen en el código ni en `.env.example`.
  - Faltan en `.env.example`: `BQ_BENCHMARK_DATASET` y `LOG_FORMAT`.
- **Reproducción:**
  1. Configurar en `.env`: `BQ_DATASET_STAGING=mi_staging_personalizado`.
  2. Ejecutar `python -c "from src.config import get_settings; print(get_settings().bigquery.dataset_staging)"`.
  3. Imprime `"staging"` en lugar de `"mi_staging_personalizado"`.
- **Impacto:** Si un operador configura nombres de datasets personalizados siguiendo `.env.example` o el runbook, sus variables serán silenciosamente ignoradas, enviando escrituras a los datasets por defecto.
- **Recomendación:** Unificar y soportar alias en `src/config.py`:
  ```python
  bq_section["dataset_staging"] = os.getenv("BQ_STAGING_DATASET") or os.getenv("BQ_DATASET_STAGING") or bq_section.get("dataset_staging")
  bq_section["dataset_operations"] = os.getenv("BQ_OPERATIONS_DATASET") or os.getenv("BQ_DATASET_OPERATIONS") or bq_section.get("dataset_operations")
  ```
  Y actualizar `.env.example` y la guía de troubleshooting con la nomenclatura canónica.
- **Sugerido para:** `backend-developer`

---

### [MEDIUM] PROD-04: Desconexión de parámetros de red de `config.yaml` en la invocación del extractor
- **Severidad:** MEDIUM
- **Área:** [`src/main.py:267-270`](file:///c:/Proyectos/InsightBolivia/insight-bolivia/src/main.py#L267-L270), [`src/extract_comercio_exterior.py:413-430`](file:///c:/Proyectos/InsightBolivia/insight-bolivia/src/extract_comercio_exterior.py#L413-L430)
- **Evidencia:** `config/config.yaml` define:
  ```yaml
  source:
    timeout_seconds: 30
    max_retries: 3
    retry_backoff_factor: 2
  ```
  Sin embargo, en `_discover_files_to_process()` de `src/main.py`:
  ```python
  extract_summary = extract_comercio_exterior(
      sources=sources_map, output_base_dir=base_dir, exclude_dictionaries=True
  )
  ```
  No se le pasa la sesión configurada ni los parámetros `timeout=settings.source.timeout_seconds`. `extract_comercio_exterior` recurre a sus valores por defecto (`backoff_factor=1.0`, `timeout=30`).
- **Reproducción:** Cambiar `retry_backoff_factor: 5` o `timeout_seconds: 60` en `config.yaml`. Comprobar mediante depurador que `extract_comercio_exterior` sigue operando con `backoff_factor=1.0` y `timeout=30`.
- **Impacto:** Cualquier ajuste operativo en `config.yaml` orientado a mitigar problemas de red o latencias del portal del INE no tiene efecto práctico en la extracción.
- **Recomendación:** Instanciar la sesión resiliente usando `settings.source` y propagarla a `extract_comercio_exterior(..., session=resilient_session, timeout=settings.source.timeout_seconds)`.
- **Sugerido para:** `backend-developer`

---

### [MEDIUM] PROD-05: Commit automático de `last_run.txt` vulnerable a reglas de protección de rama en `main`
- **Severidad:** MEDIUM
- **Área:** [`.github/workflows/etl_comercio_exterior.yml:127-135`](file:///c:/Proyectos/InsightBolivia/insight-bolivia/.github/workflows/etl_comercio_exterior.yml#L127-L135)
- **Evidencia:** El paso para prevenir la desactivación del cron de GitHub Actions (inactividad de 60 días) ejecuta:
  ```bash
  date -u +"%Y-%m-%dT%H:%M:%SZ" > last_run.txt
  git config user.name "github-actions[bot]"
  git config user.email "github-actions[bot]@users.noreply.github.com"
  git add last_run.txt
  git diff --quiet && git diff --staged --quiet || (git commit -m "chore(cron): update last_run.txt timestamp [skip ci]" && git push)
  ```
- **Reproducción:** Si el repositorio activa reglas de protección de rama en `main` (*"Require pull request before merging"* sin excepción explícita para `github-actions[bot]`), el comando `git push` es rechazado con error HTTP 403 / *Protected branch*.
- **Impacto:** El pipeline ETL falla en el último paso tras haber cargado los datos exitosamente, provocando falsos positivos en las alertas de fallo y ensuciando el historial de commits de `main` con 365 commits anuales de tipo chore.
- **Recomendación:**
  1. Utilizar una rama huérfana de telemetría (ej. `cron-keepalive`) en lugar de `main`.
  2. O bien, utilizar una Action comunitaria estándar como `gautamkrishnar/keepalive-workflow` que no contamina el historial de `main`.
  3. Registrar la fecha de última ejecución en Firestore (`dwh_catalog.last_data_refresh`), la cual ya se actualiza en cada corrida sin necesidad de commits en Git.
- **Sugerido para:** `devops-engineer`

---

### [LOW] PROD-06: Configuración de `.devcontainer/devcontainer.json` desactualizada y no funcional
- **Severidad:** LOW
- **Área:** [`.devcontainer/devcontainer.json:4-23`](file:///c:/Proyectos/InsightBolivia/insight-bolivia/.devcontainer/devcontainer.json#L4-L23)
- **Evidencia:**
  - Línea 4: Configura la imagen `mcr.microsoft.com/devcontainers/python:1-3.11-bookworm` (Python 3.11), cuando el estándar del proyecto es Python 3.12 (`.python-version = 3.12`).
  - Línea 20: Intenta instalar `pip3 install --user -r requirements.txt`, pero `requirements.txt` no existe en el repositorio (el proyecto usa `uv` y `pyproject.toml`).
  - Línea 22: Ejecuta `streamlit run src/__init__.py --server.enableCORS false --server.enableXsrfProtection false`. El archivo `src/__init__.py` no es la aplicación Streamlit (la aplicación está en `streamlit_app/app.py`). Además, desactiva la protección XSRF.
- **Reproducción:** Iniciar el proyecto en GitHub Codespaces o VS Code Dev Container. La inicialización omite dependencias y Streamlit falla al apuntar a un archivo incorrecto.
- **Impacto:** Entorno de desarrollo en la nube inoperativo para nuevos colaboradores.
- **Recomendación:** Actualizar `devcontainer.json` para usar Python 3.12, instalar `uv`, ejecutar `uv sync` y configurar `postAttachCommand` con `uv run streamlit run streamlit_app/app.py`.
- **Sugerido para:** `devops-engineer`

---

### [LOW] PROD-07: Mensaje estático y falta de contexto granular en alertas de fallo de Discord
- **Severidad:** LOW
- **Área:** [`.github/workflows/etl_comercio_exterior.yml:120-126`](file:///c:/Proyectos/InsightBolivia/insight-bolivia/.github/workflows/etl_comercio_exterior.yml#L120-L126), [`src/notifications.py`](file:///c:/Proyectos/InsightBolivia/insight-bolivia/src/notifications.py)
- **Evidencia:** En el paso de fallo de GitHub Actions, el argumento `--error` envía un texto hardcodeado:
  `"El pipeline ETL de Comercio Exterior ha fallado durante la ejecución en GitHub Actions."`
  No se captura el archivo fallido, el error de validación de Great Expectations ni la traza del error de BigQuery.
- **Reproducción:** Forzar un fallo en una regla de GX y revisar el payload enviado al webhook de Discord.
- **Impacto:** El equipo de guardia recibe la notificación de que hubo un fallo, pero está obligado a abrir el navegador y navegar por los logs de GitHub Actions para diagnosticar la naturaleza del problema.
- **Recomendación:** En `src/main.py`, capturar las excepciones no controladas o fallos de validación GX y disparar `send_discord_alert()` directamente con el resumen de archivos fallidos antes de salir con código 1.
- **Sugerido para:** `backend-developer`

---

### [INFO] PROD-08: Ausencia de `requirements.txt` congelado como salvaguarda en Streamlit Community Cloud
- **Severidad:** INFO
- **Área:** Raíz del repositorio / Streamlit Cloud
- **Evidencia:** El repositorio cuenta con `pyproject.toml` y `uv.lock`. Streamlit Community Cloud soporta `pyproject.toml`, pero su resolvedor basado en `pip` puede sufrir variaciones de resolución en compilaciones en frío frente a entornos que utilizan `requirements.txt`.
- **Impacto:** Posible degradación en tiempos de arranque en frío o riesgo de discrepancia de dependencias en caso de reinstalación de contenedores de Streamlit Cloud.
- **Recomendación:** Generar un `requirements.txt` automáticamente en CI o pre-commit mediante `uv pip compile pyproject.toml -o requirements.txt` como red de seguridad.
- **Sugerido para:** `devops-engineer`

---

## 4. Auditoría Técnica por Pilar Operativo

### Pilar 1: Arquitectura y Metodología 12-Factor
- **Codebase (Factor 1):** Un único repositorio versionado en Git con ramas `main` y `develop`. Compatible.
- **Dependencies (Factor 2):** Gestión moderna y determinista mediante `uv` (`pyproject.toml` y `uv.lock`). No se detectaron llamadas impuras a `pip` o `python` en scripts operativos.
- **Config (Factor 3):** Configuración desacoplada en `config/config.yaml` y `.env`. Validación estricta con Pydantic v2 en `src/config.py`. *(Observación: Requiere subsanar desalineación de nombres detectada en PROD-03).*
- **Backing Services (Factor 4):** BigQuery y Cloud Firestore son tratados como recursos adjuntos mediante credenciales inyectadas sin URLs o endpoints hardcodeados.
- **Build, Release, Run (Factor 5):** Estricta separación entre CI (`tests.yml`), orquestación ETL (`etl_comercio_exterior.yml`) y runtime de Streamlit Cloud.
- **Processes (Factor 6):** El pipeline ETL es un proceso *stateless* e idempotente; no depende de estado en memoria local entre corridas consecutivas.
- **Concurrency (Factor 8):** Grupo de concurrencia `group: etl-comercio-exterior-pipeline` con `cancel-in-progress: false` garantiza que no existan dos ejecuciones simultáneas escribiendo en BigQuery.

### Pilar 2: Resiliencia de Ingesta y Tolerancia a Fallos
- **Sesión HTTP y Retries:** `create_resilient_session()` utiliza `urllib3.util.retry.Retry` con retroceso exponencial y reintentos ante códigos `429, 500, 502, 503, 504`.
- **User-Agent Defensivo:** Cabecera completa simulando un navegador Google Chrome real sobre Windows 10, mitigando bloqueos WAF típicos de portales gubernamentales.
- **Timeouts:** Configurado en `timeout=30` en llamadas de scraping y descargas streaming en chunks de 64 KB.
- **Seguridad en Descargas (CWE-22):** `download_resource()` valida que la ruta de destino resuelta (`final_path.resolve()`) comience estrictamente con la ruta del directorio base, previniendo vulnerabilidades de *Path Traversal*.
- **Idempotencia Dual:** Control SHA-256 en disco local y verificación previa contra `operations.etl_control_log` en BigQuery antes de la transformación pesada.

### Pilar 3: Automatización CI/CD y Barreras de Calidad
- **Pruebas y Cobertura:** 766 pruebas unitarias e integradas ejecutadas en **48.05 segundos**. Cobertura global de **98.35%** (muy por encima del umbral mandatorio del 90.0%).
- **Linter y Formato:** `ruff check .` con reglas estrictas de pyflakes, pycodestyle, bandit (`S`), flake8-bugbear, isort y use-pathlib. 0 errores.
- **Artefactos de Diagnóstico:** `actions/upload-artifact@v4` almacena reportes de Great Expectations (`data_docs`) y logs con retención de 14 días bajo condición `if: always()`.
- **Anti-Cron Deactivation:** Mecanismo implementado para burlar la suspensión de 60 días de GitHub Actions. *(Observación: Requiere ajuste de rama según PROD-05).*

### Pilar 4: Observabilidad, Monitoreo y Auditoría
- **Logging Estructurado:** Formateador `StructuredJSONFormatter` emite registros JSON de una sola línea con `timestamp` UTC ISO 8601, `level`, `module`, `message` y `details`. Compatible con Google Cloud Logging y Datadog.
- **Auditoría Dual:** Cada lote procesado se registra en BigQuery (`operations.etl_control_log`) y en Firestore (`audit_log` y actualización de `dwh_catalog`).
- **Alertas en Discord:** Módulo `src/notifications.py` implementa generación de Discord Embeds con colores semánticos (rojo para fallos, verde para éxitos), enlaces directos a la corrida de GitHub Actions y truncado defensivo a 1000 caracteres.

### Pilar 5: Despliegue en Streamlit Cloud y BigQuery ($0 Costo)
- **Always Free Tier de GCP:** 
  - Almacenamiento en BigQuery particionado mensualmente por `fecha`, reduciendo el escaneo de consultas a unos pocos Megabytes por interacción.
  - Vistas analíticas pre-agregadas (`vw_balanza_comercial_mensual`, `vw_socios_comerciales`, `vw_top_productos_exportados`) evitan que la UI consulte la tabla de hechos a grano fino.
  - Caché `@st.cache_data(ttl=3600)` elimina consultas redundantes a BigQuery.
- **Límites de Memoria (1 GB RAM):**
  - Módulo de microdatos (`04_descargas.py`) bloquea exportaciones superiores a 50,000 filas.
  - Normalización de columnas numéricas de `decimal.Decimal` a `float64` reduce el consumo de memoria en un ~60%.
- **Proxies de Punto de Entrada:** Soporte automático para Streamlit Cloud mediante `app.py`, `src/main.py` (`_is_running_in_streamlit()`) y delegación en `pages/`.

### Pilar 6: Runbooks Operacionales y Procedimientos de Emergencia
- `docs/GUIA_CARGAS_MANUALES_Y_TROUBLESHOOTING.md`: Documento de alta calidad operativa. Describe 8 incidencias de producción reales con causas técnicas exactas y resoluciones paso a paso.
- `docs/ARQUITECTURA_Y_FUNCIONAMIENTO_INTERNO.md`: Describe detalladamente el flujo de datos E2E, modelos en estrella, SCD Tipo 2, llaves sustitutas `FARM_FINGERPRINT` y catálogo de vistas.

---

## 5. Plan de Subsanación y Hoja de Ruta Priorizada

### Fase 1: Inmediata (Previa al Lanzamiento Oficial en Producción)
1. **Actualizar dependencias vulnerables (PROD-01):**
   ```bash
   uv lock --upgrade-package certifi --upgrade-package filelock --upgrade-package pillow
   uv run pip-audit
   ```
2. **Eliminar el éxito silencioso ante fallos ("Ghost Runs") (PROD-02):**
   - Incorporar `extract_summary.failed` al cómputo de `summary.failed_files` en `src/main.py`.
   - Asegurar que `src/main.py` retorne código 1 si hubo fallos de descarga.
3. **Unificar variables de entorno y alias (PROD-03):**
   - Agregar soporte para `BQ_DATASET_STAGING` y `BQ_STAGING_DATASET` en `src/config.py`.
   - Alinear `.env.example` y `GUIA_CARGAS_MANUALES_Y_TROUBLESHOOTING.md`.
4. **Conectar parámetros de red de `config.yaml` al extractor (PROD-04):**
   - Propagar `settings.source.timeout_seconds` y sesión con `retry_backoff_factor` en `_discover_files_to_process()`.

### Fase 2: Mediano Plazo (Primer Sprint Post-Lanzamiento)
1. **Refactorizar Anti-Cron Keepalive (PROD-05):** Mover el commit de `last_run.txt` a una rama huérfana de telemetría o adoptar `gautamkrishnar/keepalive-workflow`.
2. **Corregir `.devcontainer/devcontainer.json` (PROD-06):** Migrar a Python 3.12 y configurar invocación con `uv` y `streamlit_app/app.py`.
3. **Enriquecer alertas de Discord (PROD-07):** Inyectar el nombre del archivo fallido y el error específico devuelto por Great Expectations o BigQuery en el payload del webhook.
4. **Generar `requirements.txt` automático (PROD-08):** Configurar compilación en CI para redundancia de despliegue en Streamlit Cloud.

---

## 6. Conclusión y Declaración de Idoneidad Operativa

La plataforma **InsightBolivia** cuenta con una base de código excepcionalmente robusta, modular, respaldada por una cobertura de pruebas superior al 98% y diseñada con un estricto respeto a los límites de costo gratuito de Google Cloud Platform y Streamlit Community Cloud.

Resolviendo los 4 puntos de la **Fase 1 Inmediata** (actualización de candados de dependencias, captura defensiva de fallos en el extractor y alineación de variables de entorno), el sistema pasa a estado **GO PLENO** con plena garantía de estabilidad, tolerancia a cortes de red e integridad analítica en producción.
