# Informe de Auditoría de Seguridad y Calidad Backend (V2)
**Proyecto:** InsightBolivia  
**Componente:** Backend, Pipelines ETL, Data Warehouse (BigQuery), Cloud Firestore y CI/CD  
**Fecha de Evaluación:** Octubre 2026  
**Auditor:** Full-Stack Security & Pentest Auditor  
**Estado General:** ACEPTABLE CON OBSERVACIONES DE ALTO IMPACTO (Vulnerabilidades SCA en Dependencias y Hardening Operacional)

---

## 1. Resumen Ejecutivo y Postura de Seguridad (V2)

Se ha completado la segunda ronda de auditoría de seguridad integral (**V2**) sobre el backend de **InsightBolivia**, verificando el estado de remediación de las observaciones críticas reportadas en la versión V1 (BK-01 a BK-04), analizando la integridad del código fuente tras las actualizaciones, y evaluando el ecosistema de dependencias y servicios en la nube (`Cloud Firestore`, `Google BigQuery`, `GitHub Actions`).

### Comparativa de Indicadores Clave de Seguridad (KPIs: V1 vs V2)
| Indicador | Evaluación V1 | Evaluación V2 | Variación / Estado |
| :--- | :---: | :---: | :---: |
| **Vulnerabilidades en Dependencias (SCA)** | 0 CVEs | **44 CVEs conocidos** en 3 paquetes | 🔴 Requiere actualización urgente |
| **Análisis Estático (Ruff Linter & Security)** | 0 Violaciones | **0 Violaciones** (`ruff check .`) | 🟢 Óptimo y conforme |
| **Análisis Estático con Bandit** | No ejecutado | 13 Alertas B608 (Falsos Positivos DDL/Param) | 🟡 Analizado y mitigado |
| **Cobertura de Pruebas Unitarias** | 98.58% (748 tests) | **98.23% (766/766 tests pasados)** | 🟢 Óptimo (Umbral >= 90% cumplido) |
| **Gestión de Secretos y Credenciales** | 0 secretos | **0 secretos hardcodeados**, historial limpio | 🟢 Seguro (Verificado en Git) |
| **Reglas de Seguridad Cloud Firestore** | 1 Crítica, 1 Alta | **BK-01 y BK-02 Subsanados**; 2 mejoras de hardening | 🟢 Subsanado con recomendaciones |
| **Seguridad en Ingestión HTTP (Archivos)** | 1 Media (Traversal) | **BK-03 Subsanado** (Doble validación de ruta) | 🟢 Subsanado y blindado |
| **Seguridad en CI/CD (GitHub Actions)** | 1 Media (Inyección) | **BK-04 Subsanado** (Aislamiento en `env:`) | 🟢 Subsanado y blindado |
| **Pipeline de Integración Continua (CI)** | Pasando | ⚠️ **Bloqueado por `pip-audit` en paso CI** | 🔴 Bloqueante operacional |

---

## 2. Análisis Detallado de Software Composition Analysis (SCA)

### 2.1 Diagnóstico de `pip-audit`
La ejecución de `uv run pip-audit` sobre el árbol de dependencias resuelto en `uv.lock` identificó **44 vulnerabilidades conocidas** concentradas en 3 paquetes del entorno:

```
Found 44 known vulnerabilities in 3 packages
Name     Version   ID                  Fix Versions
-------- --------- ------------------- ------------
certifi  2026.7.22 PYSEC-2026-4320     2026.10.19
filelock 4.1.2     CVE-2026-112906     4.2.1
filelock 4.1.2     CVE-2026-112940     4.2.1
filelock 4.1.2     CVE-2026-112914     4.2.1
filelock 4.1.2     CVE-2026-112913     4.2.1
filelock 4.1.2     CVE-2026-112937     4.2.1
filelock 4.1.2     CVE-2026-112907     4.2.1
pillow   12.3.0    CVE-2026-112895...  13.0.0 (37 CVEs)
```

#### A. `certifi` (Versión actual: 2026.7.22 | Corrección: >=2026.10.19)
- **ID:** `PYSEC-2026-4320`
- **Árbol de Invocación:** Requerido transitivamente por `requests` (usado por `google-api-core`, `google-cloud-bigquery`, `google-cloud-firestore`, `firebase-admin`, `wbgapi`, `great-expectations`, `streamlit`) y `httpx`/`httpcore` (usado por `firebase-admin[http2]`, `jupyterlab`).
- **Naturaleza del Riesgo:** El paquete `certifi` provee la lista de entidades certificadoras raíz (Root CAs) de confianza de Mozilla. Certificados obsoletos o desconfiados por las autoridades en la versión 2026.7.22 podrían permitir ataques de Man-in-the-Middle (MitM) en peticiones TLS salientes hacia endpoints externos (Banco Mundial, INE, GCP).

#### B. `filelock` (Versión actual: 4.1.2 | Corrección: >=4.2.1)
- **IDs:** `CVE-2026-112906`, `CVE-2026-112940`, `CVE-2026-112914`, `CVE-2026-112913`, `CVE-2026-112937`, `CVE-2026-112907`
- **Árbol de Invocación:** Requerido transitivamente por `cachecontrol[filecache]` -> `firebase-admin` y `pip-audit`.
- **Naturaleza del Riesgo:** Vulnerabilidades de manipulación de enlaces simbólicos (symlink following) y condiciones de carrera (TOCTOU) al gestionar archivos temporales de bloqueo en sistemas multiusuario o entornos de contenedores, lo que podría derivar en denegación de servicio local o corrupción de caché.

#### C. `pillow` (Versión actual: 12.3.0 | Corrección: >=13.0.0)
- **IDs:** 37 CVEs reconocidos, incluyendo desbordamientos de búfer en decodificación de formatos de imagen, fugas de memoria y desreferenciación de punteros nulos (`CVE-2026-112895`, `CVE-2026-112400`, `GHSA-78g4-xqwv-q3g8`, entre otros).
- **Árbol de Invocación:** Requerido directamente por `streamlit 1.66.0`.
- **Causa Raíz de Bloqueo de Actualización:** La versión instalada de `streamlit==1.66.0` fijaba en sus metadatos de distribución la restricción `pillow<13,>=9.2.0`, impidiendo que el gestor de paquetes actualizara Pillow a la serie 13.0.0.

### 2.2 Ruta de Actualización y Remediación Verificada
Se verificó empíricamente en el repositorio mediante simulación en seco (`--dry-run`) la compatibilidad y resolución de dependencias:
- La versión `streamlit 1.66.1` relaja la restricción de Pillow a `pillow<14,>=9.2.0`.
- Comando de resolución comprobado:
  ```bash
  uv lock --upgrade-package streamlit --upgrade-package pillow --upgrade-package certifi --upgrade-package filelock
  ```
- **Resultado de la resolución:**
  - `certifi`: `v2026.7.22` -> `v2026.10.23` (Resuelve `PYSEC-2026-4320`)
  - `filelock`: `v4.1.2` -> `v4.2.4` (Resuelve los 6 CVEs)
  - `pillow`: `v12.3.0` -> `v13.0.0` (Resuelve los 37 CVEs)
  - `streamlit`: `v1.66.0` -> `v1.66.1` (Permite `pillow 13.0.0`)
- **Impacto en CI:** La actualización de estas dependencias es crítica e inmediata, ya que el paso 38 de `.github/workflows/tests.yml` (`uv run pip-audit`) actualmente aborta cualquier Pull Request con código de retorno 1.

---

## 3. Estado de Subsanación de Hallazgos V1

### ✅ BK-01: Escalamiento de Privilegios en Reglas de Firestore (Subsanado)
- **Evaluación V2:** Se verificó el archivo `firestore/rules/firestore.rules` (líneas 35-40).
  ```javascript
  match /user_profiles/{userId} {
    allow read: if isAuthenticated() && (request.auth.uid == userId || isAdmin());
    allow create: if isAuthenticated() && request.auth.uid == userId && (request.resource.data.role == 'viewer' || isAdmin());
    allow update: if isAuthenticated() && (isAdmin() || (request.auth.uid == userId && request.resource.data.role == resource.data.role));
    allow delete: if isAdmin();
  }
  ```
  La regla de actualización `allow update` exige ahora estrictamente que `request.resource.data.role == resource.data.role` cuando la petición proviene del propietario del documento. Un usuario con rol `viewer` no puede autoasignarse el valor `admin`.
- **Validación:** 49 pruebas unitarias en `tests/test_firestore_rules.py` validan todos los vectores de elevación de privilegios no autorizados, confirmando que la vulnerabilidad se encuentra neutralizada.

### ✅ BK-02: Creación No Autenticada en Logs y Analítica (Subsanado)
- **Evaluación V2:** En `firestore/rules/firestore.rules` (líneas 54-68), las colecciones `audit_log` y `ui_analytics` cambiaron de `allow create: if true;` a `allow create: if isAuthenticated();`, y mantienen `allow update, delete: if false;`.
  Se erradicó el vector de inserción anónima y saturación de cuotas por bots no autenticados en la red pública.

### ✅ BK-03: Posible Path Traversal en Extracción de Archivos (Subsanado)
- **Evaluación V2:** En `src/extract_comercio_exterior.py`, la función `_extract_filename_from_response` aplica `Path(decoded).name.replace("\x00", "").strip()`, descartando cualquier componente de directorio relativo (`../`) o inyección de bytes nulos. Adicionalmente, en `download_resource` (líneas 367-370), se incorporó una defensa en profundidad canónica:
  ```python
  resolved_dest = dest_dir.resolve()
  final_path = (dest_dir / filename).resolve()
  if not str(final_path).startswith(str(resolved_dest)):
      raise ValueError(f"Ruta de destino no autorizada detectada: {final_path}")
  ```
  La contención del archivo en el directorio de destino es absoluta.

### ✅ BK-04: Riesgo de Inyección de Comandos en Workflow de GitHub Actions (Subsanado)
- **Evaluación V2:** En `.github/workflows/etl_comercio_exterior.yml`, los inputs del workflow se desacoplaron de la interpolación directa en texto bash `${{ inputs.* }}`. Ahora se mapean a variables de entorno formales del step (`env: INPUT_DATE_RANGE: ${{ inputs.date_range }}`, etc.), y el bloque `run: |` los consume exclusivamente como variables de entorno de shell protegidas (`"$INPUT_DATE_RANGE"`).

---

## 4. Nuevos Hallazgos de Seguridad Backend (V2)

### 🟡 HALLAZGO BK-05: Dependencia de `get()` en Reglas Firestore para RBAC vs Custom Claims
- **Severidad:** MEDIA (CVSS 5.3)
- **CWE:** CWE-400 (Uncontrolled Resource Consumption) / CWE-284 (Improper Access Control)
- **Ubicación:** `firestore/rules/firestore.rules` (líneas 15-22)
- **Descripción:**
  La función auxiliar `getUserRole()` evalúa el rol del usuario mediante una llamada documental `get()`:
  ```javascript
  function getUserRole() {
    return get(/databases/$(database)/documents/user_profiles/$(request.auth.uid)).data.role;
  }
  ```
  En Cloud Firestore, cada invocación de la función `get()` en las reglas de seguridad computa como una lectura documental facturable y consume parte del límite de 10 `get()` por solicitud. Si un usuario realiza múltiples operaciones, esto introduce latencia adicional y riesgo de agotamiento de cuotas. Además, si el documento `/user_profiles/<uid>` no existe aún o se encuentra temporalmente corrupto, la evaluación falla de forma inesperada.
- **Impacto:** Sobrecosto en lecturas de Firestore y acoplamiento entre reglas de seguridad y la estructura de documentos NoSQL.
- **Remediación Recomendada:**
  Migrar la asignación de roles a **Firebase Custom Claims** administrados desde el backend administrativo con el SDK de Firebase Admin (`firebase_admin.auth.set_custom_user_claims(uid, {"role": "admin"})`).
  En `firestore.rules`, sustituir por:
  ```javascript
  function isAdmin() {
    return isAuthenticated() && request.auth.token.role == 'admin';
  }
  ```

---

### 🟡 HALLAZGO BK-06: Falta de Límite de Gasto / Facturación en Consultas BigQuery (`maximum_bytes_billed`)
- **Severidad:** MEDIA (CVSS 5.1)
- **CWE:** CWE-770 (Allocation of Resources Without Limits) / CWE-400 (Uncontrolled Resource Consumption)
- **OWASP API Security:** API4:2023 - Unrestricted Resource Consumption
- **Ubicación:** `src/load.py`, `src/extract_benchmark.py`, `streamlit_app/utils/bq_client.py` (función `run_query`)
- **Descripción:**
  Las consultas ejecutadas a BigQuery a través de `bigquery.QueryJobConfig()` no configuran el parámetro `maximum_bytes_billed`:
  ```python
  job_config = bigquery.QueryJobConfig()
  if _params:
      job_config.query_parameters = list(_params)
  query_job = client.query(query, job_config=job_config)
  ```
  Aunque las tablas principales (`fact_comercio_exterior` y `fact_indicadores_bm`) están particionadas y clusterizadas, la omisión de `maximum_bytes_billed` implica que cualquier consulta imprevista, error en filtros o escaneo no planificado podría escanear cientos de gigabytes o terabytes de datos, exponiendo la cuenta a cobros inesperados más allá de la cuota mensual gratuita (1 TB/mes).
- **Impacto:** Riesgo de "Denial of Wallet" / sobrecostos no controlados en Google Cloud Platform.
- **Remediación Recomendada:**
  Configurar un límite prudencial de bytes facturados por consulta (por ejemplo, 250 MB por consulta analítica):
  ```python
  MAX_QUERY_BYTES = 250 * 1024 * 1024  # 250 MB
  job_config = bigquery.QueryJobConfig(
      maximum_bytes_billed=MAX_QUERY_BYTES
  )
  ```

---

### 🟢 HALLAZGO BK-07: Ausencia de Validación de Esquema y Tamaño en Inserciones de `audit_log` y `ui_analytics`
- **Severidad:** BAJA (CVSS 3.5)
- **CWE:** CWE-20 (Improper Input Validation)
- **Ubicación:** `firestore/rules/firestore.rules` (líneas 54-68)
- **Descripción:**
  Las colecciones `audit_log` y `ui_analytics` permiten `allow create: if isAuthenticated();` sin validar la estructura ni el tamaño del documento entrante. Un usuario legítimamente autenticado con rol `viewer` podría insertar documentos de hasta 1 MB con campos no autorizados o cargas basura.
  Adicionalmente, dado que los eventos del backend y de Streamlit se insertan mediante la Service Account de Google Cloud (la cual elude las reglas de Firestore por diseño), la regla pública `allow create: if isAuthenticated();` puede no ser necesaria a menos que existan clientes web/móviles directos.
- **Remediación Recomendada:**
  Si únicamente el backend escribe logs y telemetría, cerrar la creación externa (`allow create: if false;`). En caso de requerir inserción desde clientes frontend autenticados, validar los campos obligatorios y limitar el tamaño del payload:
  ```javascript
  match /ui_analytics/{eventId} {
    allow read: if isAdmin();
    allow create: if isAuthenticated() &&
                     request.resource.data.keys().hasAll(['event_type', 'timestamp', 'session_id']) &&
                     request.resource.data.size() < 10;
    allow update, delete: if false;
  }
  ```

---

### 🟢 HALLAZGO BK-08: Exclusión Preventiva Explícita del Directorio `credentials/` en `.gitignore`
- **Severidad:** BAJA / INFORMATIVA (CVSS 2.1)
- **CWE:** CWE-522 (Insufficiently Protected Credentials)
- **Ubicación:** `.gitignore` (líneas 18-25)
- **Descripción:**
  El archivo `.gitignore` excluye patrones específicos de archivos de credenciales (`*service_account*.json`, `*gcp_key*.json`, `*credentials*.json`). Existe un directorio en el workspace llamado `credentials/` que actualmente alberga `credentials/gcp_key.json` (el cual está correctamente ignorado por la regla de archivo). No obstante, el directorio `credentials/` no está listado en su totalidad. Si un desarrollador almacena una clave con un nombre no contemplado (por ejemplo, `credentials/private.pem` o `credentials/auth.token`), podría haber riesgo de exposición accidental.
- **Remediación:**
  Añadir explícitamente `credentials/` y `credentials/*` en la sección de credenciales de `.gitignore`.

---

## 5. Auditoría de Inyección SQL y Parámetros en BigQuery

Se revisaron minuciosamente los 13 reportes generados por el analizador Bandit (regla B608 `hardcoded_sql_expressions`):
1. **Pipelines ETL (`src/load_comercio_exterior.py`, `src/extract_benchmark.py`, `src/init_dwh.py`, `src/load.py`):**
   - Las sentencias `MERGE`, `INSERT` y `CREATE TABLE` emplean interpolación f-string estrictamente para nombres de tablas y esquemas (`{stg_ref}`, `{pais_ref}`, `{target_table}`) derivados de configuraciones de sistema fuertemente tipadas en `pydantic`.
   - Los datos y valores provienen de DataFrames de pandas cargados mediante la API binaria `load_table_from_dataframe` o están protegidos mediante parámetros `@hash_val`.
   - **Veredicto:** Falsos positivos de inyección SQL. La interpolación de identificadores es el patrón estándar en Google Cloud BigQuery ya que la sintaxis SQL no admite parametrización de identificadores de catálogo.
2. **Cliente Analítico (`streamlit_app/utils/bq_client.py`):**
   - Todas las funciones de consulta dinámicas (`get_balanza_comercial`, `get_top_productos`, `get_socios_comerciales`, `get_export_microdatos`, `get_benchmark_indicadores`) utilizan `bigquery.ScalarQueryParameter` y `bigquery.ArrayQueryParameter`.
   - La cláusula `LIMIT` fue parametrizada con `@limit_val` y validación de enteros `clean_limit < 0` (subsanación de FE-02).
   - **Veredicto:** 100% de cumplimiento con parametrización de consultas BigQuery.

---

## 6. Auditoría de Secretos y Configuración de Repositorio

- **Búsqueda Automatizada de Patrones de Secretos:** Se ejecutó un escaneo sobre la totalidad de los archivos versionados buscando patrones de claves privadas RSA/EC, API keys de Google (`AIza...`), tokens de GitHub y webhooks de Discord.
  - Resultados: Cero credenciales reales comprometidas. Las coincidencias corresponden a ejemplos de documentación (`secrets.toml.example`, `README.md`) y cadenas sintéticas de pruebas en `tests/test_notifications.py` y `tests/test_config.py`.
- **Historial de Git:** Se verificó el log histórico de cambios sobre archivos de secretos y variables de entorno. Ningún commit previo contiene credenciales de Service Account ni tokens de producción.

---

## 7. Plan de Remediación Backend V2

| Prioridad | ID | Acción Recomendada | Archivo(s) | Esfuerzo |
| :---: | :---: | :--- | :--- | :---: |
| **P0** | **SEC-SCA-01** | Actualizar `streamlit>=1.66.1`, `pillow>=13.0.0`, `certifi>=2026.10.19`, `filelock>=4.2.1` con `uv lock` | `pyproject.toml`, `uv.lock` | 30 mins |
| **P1** | **BK-06** | Incorporar `maximum_bytes_billed` en `QueryJobConfig` para todas las consultas BigQuery | `src/load.py`, `streamlit_app/utils/bq_client.py` | 1 hora |
| **P1** | **BK-05** | Evaluar transición de `getUserRole()` a Firebase Custom Claims en `firestore.rules` | `firestore/rules/firestore.rules` | 2 horas |
| **P2** | **BK-07** | Añadir validación de campos obligatorios o restringir a backend en `audit_log` y `ui_analytics` | `firestore/rules/firestore.rules` | 1 hora |
| **P2** | **BK-08** | Incorporar `credentials/` explícitamente en `.gitignore` | `.gitignore` | 5 mins |
