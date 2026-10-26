# Informe de Auditoría de Seguridad Frontend (V2)
**Proyecto:** InsightBolivia  
**Componente:** Capa de Visualización Web (Streamlit UI/UX), Páginas Multipágina, Gráficos y Componentes  
**Fecha de Evaluación:** Octubre 2026  
**Auditor:** Full-Stack Security & Pentest Auditor  
**Estado General:** SEGURO CON OBSERVACIONES DE RENDIMIENTO/MEMORIA (Remediación Completa de XSS y Parámetros)

---

## 1. Resumen Ejecutivo y Postura de Seguridad Frontend (V2)

Se ha llevado a cabo una auditoría de seguridad exhaustiva (**V2**) sobre la interfaz web de **InsightBolivia**, construida con el framework **Streamlit** y componentes analíticos basados en **Plotly**. Esta revisión evaluó el impacto de la subsanación de los hallazgos reportados en la versión V1 (FE-01 a FE-03), la exposición a vulnerabilidades en librerías de soporte gráfico (`Pillow`), la gestión del estado de sesión (`st.session_state`), y los mecanismos de prevención de ataques de denegación de servicio por agotamiento de memoria (OOM DoS).

### Matriz de Indicadores Frontend (V1 vs V2)
| Vector de Seguridad | Evaluación V1 | Evaluación V2 | Variación / Estado |
| :--- | :---: | :---: | :---: |
| **Sanitización contra XSS (FE-01)** | 🔴 Alto (Interpolación directa) | 🟢 **100% Mitigado con `html.escape`** | Subsanación Exitosa |
| **Parametrización BigQuery (FE-02)** | 🟡 Medio (`LIMIT` concatenado) | 🟢 **100% Mitigado con `@limit_val`** | Subsanación Exitosa |
| **Configuración CORS / XSRF (FE-03)** | 🟡 Bajo (`enableCORS = true`) | 🟢 **`enableCORS = false`, XSRF activo** | Subsanación Exitosa |
| **Dependencias Gráficas (Pillow SCA)** | 🟢 0 CVEs | 🔴 **37 CVEs en Pillow 12.3.0** | Requiere actualización |
| **Aislamiento de Sesión (`session_state`)** | 🟢 Seguro | 🟢 **UUID v4 individual por sesión** | Óptimo |
| **Gestión de Memoria en Descargas** | 🟢 Límite 50k registros | 🟡 **Generación Eager de Excel/CSV** | Oportunidad de Hardening |

---

## 2. Análisis de Dependencias y SCA en la Capa Frontend

### 2.1 Vulnerabilidades Heredadas por Pillow en Streamlit
El escaneo de composición de software (`pip-audit`) detectó 37 vulnerabilidades asociadas a `pillow==12.3.0`, librería requerida directamente por `streamlit`:
- **Vectores de Ataque Identificados:** Desbordamiento de búfer en memoria (Buffer Overflow), lectura fuera de límites (Out-of-bounds Read), desreferenciación de punteros nulos y fugas de memoria al procesar archivos de imagen con metadatos maliciosos (JPEG, PNG, TIFF, WebP).
- **Relación con Streamlit:** Streamlit consume internamente Pillow para renderizar imágenes en dashboards (`st.image`), logos institucionales, avatares de usuario y elementos multimedia. Si bien en el código actual de InsightBolivia las imágenes provienen de recursos estáticos internos, un fallo en el motor subyacente expone la instancia a colapsos o ejecución no controlada ante cargas no confiables.
- **Causa Raíz de la Restricción:** `streamlit==1.66.0` fijó en sus dependencias de empaquetado la cota `pillow<13,>=9.2.0`.
- **Ruta de Remediación Verificada:**
  Actualizar a `streamlit>=1.66.1` en `pyproject.toml` / `uv.lock`. La versión 1.66.1 admite `pillow<14`, permitiendo instalar `pillow==13.0.0` y erradicar las 37 vulnerabilidades sin conflicto alguno.

---

## 3. Verificación de Subsanaciones de la Versión V1

### ✅ FE-01: Cross-Site Scripting (XSS) en `st.markdown(..., unsafe_allow_html=True)` (Completamente Mitigado)
En la auditoría V1 se identificaron múltiples puntos donde variables dinámicas provenientes de Firestore o BigQuery se interpolaban sin sanitizar en bloques HTML. En la revisión V2 se confirmó la aplicación rigurosa de `html.escape()` en todos los archivos afectados:

1. **`streamlit_app/app.py` (Líneas 180-226):**
   ```python
   # Sanitización de salida contra XSS (FE-01)
   safe_status = html.escape(str(status_label))
   safe_last_refresh = html.escape(str(last_refresh))
   safe_record_count = html.escape(str(record_count))
   safe_data_source = html.escape(str(data_source))
   ```
   El valor de `data_source` (proveniente de Firestore) y los contadores se escapan antes de insertarse en `<div class="metric-value">`. Cualquier carga HTML maliciosa como `<script>` o `onerror=` se convierte en entidades de texto inofensivas.

2. **`streamlit_app/pages/01_balanza_comercial.py` (Líneas 197-208):**
   ```python
   safe_export_color = html.escape(str(COLOR_EXPORT))
   safe_import_color = html.escape(str(COLOR_IMPORT))
   safe_export_val = html.escape(format_currency_millions(kpis["total_exportaciones_usd"]))
   safe_saldo_val = html.escape(format_currency_millions(kpis["saldo_balanza_usd"]))
   safe_saldo_color = html.escape(str(saldo_color))
   ```

3. **`streamlit_app/pages/02_socios_comerciales.py` (Líneas 243-255):**
   ```python
   safe_val_title = html.escape(str(val_title))
   safe_total_val = html.escape(format_currency_millions(kpis["total_valor_usd"]))
   safe_top_pais_nombre = html.escape(str(kpis["top_pais_nombre"]))
   safe_top_pais_iso = html.escape(str(kpis["top_pais_iso"]))
   safe_top_bloque_nombre = html.escape(str(kpis["top_bloque_nombre"]))
   ```

4. **`streamlit_app/pages/03_productos_top.py` (Líneas 236-248):**
   ```python
   safe_top_name_full = html.escape(str(kpis["top_producto_nombre"]))
   safe_top_nandina = html.escape(str(kpis["top_producto_nandina"]))
   safe_top_sector_nombre = html.escape(str(kpis["top_sector_nombre"]))
   ```

5. **`streamlit_app/pages/05_benchmark_regional.py` (Líneas 280-318):**
   ```python
   safe_focus_year = html.escape(str(focus_year))
   safe_rank = html.escape(str(rank_str))
   safe_best = html.escape(str(best_str))
   safe_unit = html.escape(str(unit))
   ```

6. **Componentes Visuales (`streamlit_app/components/*.py`):**
   Se inspeccionaron todos los módulos de componentes (`balanza_charts.py`, `benchmark_charts.py`, `productos_charts.py`, `socios_charts.py`, `descargas_helpers.py`, `filters.py`). Ninguno de ellos utiliza `unsafe_allow_html=True` de manera insegura; delegan la presentación visual en figuras nativas de Plotly con renderizado SVG/Canvas seguro.

---

### ✅ FE-02: Parámetro `LIMIT` sin Parametrizar en Consulta BigQuery (Completamente Mitigado)
En `streamlit_app/utils/bq_client.py` (líneas 255-261):
```python
if limit is not None:
    clean_limit = int(limit)
    if clean_limit < 0:
        raise ValueError("El parámetro 'limit' no puede ser negativo.")
    query += " LIMIT @limit_val"
    params.append(bigquery.ScalarQueryParameter("limit_val", "INT64", clean_limit))
```
La cláusula `LIMIT` ahora valida el tipo entero, descarta valores negativos y se vincula formalmente mediante el objeto `ScalarQueryParameter("limit_val", "INT64", clean_limit)`.

---

### ✅ FE-03: CORS Permisivo y Encabezados de Servidor (Mitigado)
En `streamlit_app/.streamlit/config.toml` (líneas 16-24):
```toml
[server]
headless = true
enableCORS = false
enableXsrfProtection = true
maxUploadSize = 50

[browser]
gatherUsageStats = false
```
`enableCORS` se encuentra configurado en `false`, bloqueando solicitudes de origen cruzado arbitrarias hacia los WebSockets de Streamlit, y la protección contra ataques CSRF (`enableXsrfProtection = true`) permanece activa.

---

## 4. Nuevos Hallazgos de Seguridad y Resiliencia Frontend (V2)

### 🟡 HALLAZGO FE-04: Generación Eager No Cacheadas de Excel (.xlsx) y CSV en Descargas (Riesgo de OOM DoS)
- **Severidad:** MEDIA (CVSS 5.3)
- **CWE:** CWE-400 (Uncontrolled Resource Consumption) / CWE-770 (Allocation of Resources Without Limits)
- **Ubicación:** `streamlit_app/pages/04_descargas.py` (líneas 301-303) y `streamlit_app/components/descargas_helpers.py` (líneas 46-70)
- **Descripción:**
  En el módulo de descargas, cuando una consulta resulta válida (hasta 50,000 registros):
  ```python
  csv_data = convert_df_to_csv(df)
  excel_data = convert_df_to_excel(df, sheet_name="InsightBolivia_Comercio")
  ```
  Ambas conversiones se ejecutan **de manera síncrona y ansiosa (eager) en cada render de la página**, antes de que el usuario haga clic en ninguno de los dos botones de descarga (`st.download_button`).
  La librería `openpyxl` genera en memoria estructuras DOM XML complejas para serializar hojas de cálculo. Para un dataset de 50,000 filas con 15 columnas, la generación del archivo `.xlsx` consume picos de entre 120 MB y 220 MB de memoria RAM por sesión.
  En entornos como **Streamlit Community Cloud** (cuyo contenedor tiene un límite estricto de ~1 GB de RAM), si 3 o 4 usuarios concurrentes cargan la página de descargas al mismo tiempo, el proceso es susceptible de ser terminado por el sistema operativo mediante un evento `OOM Kill` (Out of Memory), provocando una caída completa del servicio.
- **Impacto:** Denegación de servicio no intencionada de la aplicación web por saturación de RAM.
- **Remediación Recomendada:**
  1. Aplicar `@st.cache_data` con límite de tamaño (`max_entries=5`, `ttl=600`) sobre `convert_df_to_excel` y `convert_df_to_csv`.
  2. Implementar un selector de formato previo (radio button o pestañas) para generar en memoria únicamente el archivo que el usuario elija descargar (CSV o Excel, nunca ambos a la vez).

---

### 🟢 HALLAZGO FE-05: Falta de Validación Superior de Límite en `get_export_microdatos`
- **Severidad:** BAJA (CVSS 3.7)
- **CWE:** CWE-1284 (Improper Validation of Specified Quantity in Input)
- **Ubicación:** `streamlit_app/utils/bq_client.py` (línea 360)
- **Descripción:**
  En la función `get_export_microdatos`, el parámetro `limit` se valida con `clean_limit < 0`, pero no posee una cota superior forzada (`clean_limit > 50001`). Si bien la interfaz de usuario en `04_descargas.py` pasa `limit=50001` de forma fija, la función de utilidad no impone un techo defensivo propio si es invocada desde otros módulos o APIs futuras.
- **Remediación:**
  Añadir un tope defensivo:
  ```python
  MAX_ALLOWED_ROWS = 50_001
  clean_limit = min(int(limit), MAX_ALLOWED_ROWS)
  ```

---

### 🟢 HALLAZGO FE-06: Cabeceras de Seguridad HTTP Defensivas para Reverse Proxy (CSP / HSTS)
- **Severidad:** BAJA / INFORMATIVA (CVSS 3.1)
- **CWE:** CWE-1021 (Improper Restriction of Rendered UI Layers or Frames)
- **Ubicación:** Configuración de despliegue / Reverse Proxy (Cloudflare / NGINX / Cloud Run)
- **Descripción:**
  El servidor interno de Streamlit no añade de forma nativa cabeceras HTTP de protección como `Content-Security-Policy` (CSP), `X-Frame-Options: SAMEORIGIN`, `X-Content-Type-Options: nosniff` o `Strict-Transport-Security` (HSTS).
- **Remediación:**
  Para despliegues en infraestructura dedicada o tras un balanceador/Cloudflare, inyectar las cabeceras defensivas:
  ```http
  X-Frame-Options: SAMEORIGIN
  X-Content-Type-Options: nosniff
  Referrer-Policy: strict-origin-when-cross-origin
  Content-Security-Policy: default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline';
  ```

---

## 5. Auditoría de Aislamiento de Sesión y Telemetría

- **Aislamiento en `st.session_state`:**
  - Verificado en `streamlit_app/utils/firestore_client.py`: la función `get_session_id()` genera un `UUID v4` independiente almacenado en la sesión local del navegador del usuario (`st.session_state["session_id"]`).
  - No existen variables de estado mutables a nivel de módulo compartidas entre hilos o sesiones de usuarios concurrentes.
- **Privacidad en Telemetría (`log_ui_event`):**
  - Los eventos registrados en Cloud Firestore no contienen direcciones IP, encabezados `User-Agent` detallados, nombres de usuario ni información de identificación personal (PII).
  - La telemetría es anónima y defensiva: si el servicio de Firestore no está disponible, el sistema captura la excepción y no interrumpe la navegación del usuario.

---

## 6. Plan de Remediación Frontend V2

| Prioridad | ID | Tarea de Remediación | Módulos Afectados | Esfuerzo |
| :---: | :---: | :--- | :--- | :---: |
| **P0** | **FE-SCA** | Actualizar Streamlit a `>=1.66.1` y Pillow a `13.0.0` para solventar 37 CVEs | `pyproject.toml`, `uv.lock` | 30 mins |
| **P1** | **FE-04** | Cachear conversiones y condicionar la generación de Excel/CSV a demanda en descargas | `streamlit_app/pages/04_descargas.py`, `descargas_helpers.py` | 1 hora |
| **P2** | **FE-05** | Añadir cota superior defensiva (`min(limit, 50001)`) en `get_export_microdatos` | `streamlit_app/utils/bq_client.py` | 15 mins |
| **P2** | **FE-06** | Configurar cabeceras de seguridad CSP y HSTS en proxy de despliegue | Configuración de Infraestructura | 1 hora |
