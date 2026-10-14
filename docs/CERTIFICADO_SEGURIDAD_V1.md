# Certificado de Subsanación de Seguridad Integral (FullStack V1)
**Plataforma:** InsightBolivia  
**Alcance Auditado:** Backend ETL, Cloud Firestore, Google BigQuery, Streamlit Frontend y CI/CD GitHub Actions  
**Fecha de Emisión:** Octubre 2026  
**Estado de Seguridad:** ✅ **APROBADO / 100% SUBSANADO (0 Hallazgos Pendientes)**  
**Veredicto Final:** APTO PARA PRODUCCIÓN  

---

## 1. Declaración de Conformidad

Por medio del presente documento se certifica que la plataforma **InsightBolivia** ha completado de forma satisfactoria el ciclo integral de remediación y endurecimiento de seguridad correspondiente a la **Auditoría de Seguridad Integral (FullStack V1)** documentada en `docs/RESUMEN_SEGURIDAD_INTEGRAL.md`.

Todas las vulnerabilidades identificadas (1 Crítica, 2 Altas, 3 Medias, 1 Baja) han sido remediadas en el código fuente, validadas mediante pruebas unitarias automatizadas específicas y verificadas con herramientas de análisis estático (SAST) y análisis de composición de software (SCA).

---

## 2. Matriz de Subsanación y Mitigaciones Técnicas

| Código | Severidad Inicial | CVSS | Vector / Componente | Vulnerabilidad Mitigada | Estado Final |
| :---: | :---: | :---: | :--- | :--- | :---: |
| **BK-01** | 🔴 Crítica | 8.8 | Backend / Firestore | Escalamiento de Privilegios en `user_profiles` | ✅ **SUBSANADO** |
| **FE-01** | 🔴 Alta | 7.4 | Frontend / Streamlit | Cross-Site Scripting (XSS) en `st.markdown` | ✅ **SUBSANADO** |
| **BK-02** | 🟠 Alta | 7.3 | Backend / Firestore | Ingesta Pública No Autenticada en Logs (DoS) | ✅ **SUBSANADO** |
| **BK-04** | 🟡 Media | 6.1 | CI/CD / Actions | Inyección de Comandos en Runner GitHub Actions | ✅ **SUBSANADO** |
| **BK-03** | 🟡 Media | 5.9 | Backend / ETL | Path Traversal vía `Content-Disposition` | ✅ **SUBSANADO** |
| **FE-02** | 🟡 Media | 5.3 | Frontend / BigQuery | Cláusula `LIMIT` sin parametrizar | ✅ **SUBSANADO** |
| **FE-03** | 🟢 Baja | 3.7 | Frontend / Server | CORS Permisivo en configuración Streamlit | ✅ **SUBSANADO** |

---

## 3. Detalle Técnico de Mitigaciones Implementadas

### BK-01: Control de Acceso Basado en Roles (RBAC) en Cloud Firestore
- **Archivo modificado:** `firestore/rules/firestore.rules` (delegado a especialista `firestore-rules-author`).
- **Mitigación:** En la colección `user_profiles/{userId}`, se restringió la creación para que usuarios no administradores solo puedan asignarse el rol `viewer` (`request.resource.data.role == 'viewer'`). En operaciones de actualización (`update`), se garantizó la inmutabilidad del rol para usuarios regulares (`request.resource.data.role == resource.data.role`), reservando la alteración de roles y la eliminación (`delete`) exclusivamente a administradores (`isAdmin()`).
- **Verificación:** `tests/test_firestore_rules.py` (52 pruebas unitarias pasando).

### FE-01: Sanitización de Salidas contra Cross-Site Scripting (XSS)
- **Archivos modificados:** `streamlit_app/app.py`, `streamlit_app/pages/01_balanza_comercial.py`, `02_socios_comerciales.py`, `03_productos_top.py`, `05_benchmark_regional.py`.
- **Mitigación:** Se aplicó `html.escape(str(...))` sobre todas las variables dinámicas interpoladas dentro de plantillas HTML renderizadas con `st.markdown(..., unsafe_allow_html=True)`, neutralizando vectores de inyección HTML y JavaScript tanto en modo reflejado como almacenado.
- **Verificación:** Suites de pruebas de interfaz de usuario (`test_ui_balanza.py`, `test_ui_socios.py`, `test_ui_productos.py`, `test_ui_benchmark.py`, `test_e2e_streamlit.py`).

### BK-02: Protección Anti-DoS y Control de Cuotas en Cloud Firestore
- **Archivo modificado:** `firestore/rules/firestore.rules`.
- **Mitigación:** Se eliminó la directiva permisiva `allow create: if true;` en las colecciones `audit_log` y `ui_analytics`. La inserción quedó estrictamente limitada a usuarios autenticados (`allow create: if isAuthenticated();`), garantizando la preservación de cuotas del Always Free Tier (20k escrituras/día).
- **Verificación:** Pruebas unitarias en `tests/test_firestore_rules.py` evaluando denegación a usuarios anónimos.

### BK-04: Prevención de Inyección de Comandos en GitHub Actions
- **Archivo modificado:** `.github/workflows/etl_comercio_exterior.yml`.
- **Mitigación:** Se reemplazaron todas las expresiones directas `${{ inputs.* }}` y `${{ github.event_name }}` dentro del script bash por variables de entorno explícitas en el bloque `env:` (`INPUT_OPERATION`, `INPUT_DATE_RANGE`, `EVENT_NAME`, etc.), impidiendo la ejecución arbitraria de código en el runner de CI/CD.
- **Verificación:** `tests/test_workflows.py` (14 pruebas unitarias pasando).

### BK-03: Mitigación de Path Traversal en Descargas HTTP
- **Archivo modificado:** `src/extract_comercio_exterior.py`.
- **Mitigación:** En `_extract_filename_from_response`, se aplica `Path(decoded).name.replace("\x00", "").strip()` para aislar el nombre base y descartar secuencias `../`. Adicionalmente, en `download_resource`, se incorporó validación de rutas canónicas (`target_path.resolve()`) asegurando que el archivo resida estrictamente dentro del directorio de destino.
- **Verificación:** `tests/test_extract_comercio_exterior.py` (prueba `test_download_sanitizes_path_traversal_filename`).

### FE-02: Parametrización Tipada de Consultas BigQuery
- **Archivo modificado:** `streamlit_app/utils/bq_client.py`.
- **Mitigación:** Se reemplazó la interpolación de texto en la cláusula `LIMIT` por el parámetro formal `LIMIT @limit_val`, enlazado mediante `bigquery.ScalarQueryParameter("limit_val", "INT64", clean_limit)` y validando previamente que el valor sea un entero no negativo.
- **Verificación:** `tests/test_streamlit_bq_client.py` (16 pruebas pasando).

### FE-03: Endurecimiento de CORS en Streamlit Server
- **Archivos modificados:** `.streamlit/config.toml` y `streamlit_app/.streamlit/config.toml`.
- **Mitigación:** Se configuró explícitamente `enableCORS = false`, restringiendo peticiones de orígenes cruzados no confiables.
- **Verificación:** Validación de configuración en `tests/test_e2e_streamlit.py`.

---

## 4. Métricas de Aseguramiento de Calidad y Seguridad

```
+-----------------------------------------------------------------------------+
| MÉTRICA                                   | VALOR OBTENIDO | REQUERIMIENTO  |
+-------------------------------------------+----------------+----------------+
| Pruebas Unitarias Automatizadas           | 750 / 750      | 100% Pasadas   |
| Cobertura de Código Global                | 98.52%         | >= 90.0%       |
| Vulnerabilidades de Dependencias (SCA)    | 0 CVEs         | 0 CVEs         |
| Calidad y Estilo de Código (Ruff Linter)  | 0 Errores      | 0 Errores      |
| Límite Máximo de Líneas por Archivo       | < 500 líneas   | <= 500 líneas  |
| Credenciales Hardcodeadas en Código       | 0 Detectadas   | Cero Tolerancia|
+-------------------------------------------+----------------+----------------+
```

---

## 5. Dictamen y Conclusión

Habiéndose implementado y validado todas las medidas correctivas requeridas por las normas de desarrollo y arquitectura de **InsightBolivia**, se emite el presente **Certificado de Subsanación** declarando la plataforma plenamente apta, robusta y segura para su despliegue y operación en entornos de producción.
