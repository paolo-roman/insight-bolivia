# Informe de Auditoría de Seguridad Frontend (V1)
**Proyecto:** InsightBolivia  
**Componente:** Capa de Visualización Web (Streamlit UI/UX), Páginas y Componentes Analíticos  
**Fecha de Evaluación:** Octubre 2026  
**Auditor:** Antigravity Senior Frontend Security Specialist  
**Estado General:** ACEPTABLE CON OBSERVACIONES DE ALTO IMPACTO (Riesgo de XSS en interpolación HTML)

---

## 1. Resumen Ejecutivo y Postura de Seguridad Frontend

El frontend de **InsightBolivia** está implementado sobre **Streamlit 1.37+**, estructurado en módulos analíticos multipágina (`streamlit_app/pages/`) y componentes reutilizables (`streamlit_app/components/`), respaldado por un catálogo de metadatos en Cloud Firestore y vistas analíticas optimizadas en BigQuery.

### Indicadores Clave Frontend
| Vector de Seguridad | Evaluación | Nivel de Riesgo |
| :--- | :---: | :---: |
| **Dependencias Frontend (Streamlit / Plotly)** | 0 CVEs detectados | 🟢 Bajo |
| **Sanitización de Salidas (Prevención XSS)** | Interpolación directa en `st.markdown(..., unsafe_allow_html=True)` | 🔴 Alto |
| **Manejo de Sesiones y Estado del Cliente** | Identificador UUID v4 en `st.session_state` (No tokens expuestos) | 🟢 Seguro |
| **Protección contra DoS de Memoria (OOM)** | Límite estricto de 50,000 registros para descargas | 🟢 Seguro |
| **Protección XSRF / CSRF** | Activado en `.streamlit/config.toml` (`enableXsrfProtection = true`) | 🟢 Seguro |
| **Configuración CORS y Encabezados HTTP** | `enableCORS = true` sin directivas CSP explícitas | 🟡 Medio |

---

## 2. Reconocimiento y SCA de la Capa de Cliente

La capa cliente se ejecuta mediante el motor de Streamlit, consumiendo las librerías `streamlit>=1.37`, `plotly>=5.22` y componentes CSS/HTML personalizados.
- **Auditoría de Dependencias:** El escaneo con `pip-audit` confirmó que Streamlit y Plotly se encuentran libres de vulnerabilidades conocidas en las versiones instaladas.
- **Filtrado de Secretos en Bundler/Configuración:** Se verificó que `streamlit_app/.streamlit/config.toml` no contiene credenciales. El archivo `secrets.toml.example` sirve como plantilla segura sin claves reales y `secrets.toml` está explícitamente excluido por `.gitignore`.

---

## 3. Análisis de Vulnerabilidades del Cliente (Code Review)

### 🔴 HALLAZGO FE-01: Cross-Site Scripting (XSS) Reflejado/Almacenado mediante Interpolación de Cadenas en HTML
- **Severidad:** ALTA (CVSS 7.4)
- **CWE:** CWE-79 (Improper Neutralization of Input During Web Page Generation)
- **OWASP Top 10:** A03:2021 - Injection
- **Ubicaciones Identificadas:**
  1. `streamlit_app/app.py` (Líneas 181-218)
  2. `streamlit_app/pages/02_socios_comerciales.py` (Líneas 275-304)
  3. `streamlit_app/pages/03_productos_top.py` (Líneas 251-282)
  4. `streamlit_app/pages/05_benchmark_regional.py` (Líneas 275-330)

#### Evidencia de Código Vulnerable:

**Caso A: Datos de Firestore en Landing Page (`app.py`)**
```python
# app.py: líneas 212-218
st.markdown(
    f"""
    <div class="metric-card">
        <div class="metric-title">Fuente Oficial</div>
        <div class="metric-value" style="font-size: 1.1rem; margin-top: 0.7rem;">{data_source}</div>
    </div>
    """,
    unsafe_allow_html=True,
)
```
*Vulnerabilidad:* El valor de `data_source` proviene directamente de la base de datos Firestore (`catalog.data_source`). Si un usuario malintencionado modifica el catálogo en Firestore (véase hallazgo BK-01) inyectando una carga como `<img src=x onerror=alert(document.cookie)>`, la carga se ejecutará en el navegador de cualquier visitante del portal.

**Caso B: Datos de BigQuery en Socios Comerciales (`02_socios_comerciales.py`)**
```python
# 02_socios_comerciales.py: líneas 275-288
st.markdown(
    f"""
    <div class="metric-box">
        <div class="metric-title">Socio Comercial Principal</div>
        <div class="metric-val" style="font-size: 1.25rem;">
            {kpis["top_pais_nombre"]}
        </div>
        <div style="margin-top: 4px;">
            <span class="badge-country">{kpis["top_pais_pct"]:.1f}% del total ({kpis["top_pais_iso"]})</span>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)
```
*Vulnerabilidad:* `kpis["top_pais_nombre"]` y `kpis["top_bloque_nombre"]` provienen de agregaciones de BigQuery y tablas de dimensiones (`dim_pais`). La ausencia de sanitización o escape HTML expone al cliente a Stored XSS ante manipulaciones en las fuentes de datos.

**Caso C: Datos de Indicadores y Filtros en Benchmark Regional (`05_benchmark_regional.py`)**
```python
# 05_benchmark_regional.py: líneas 321-331
st.markdown(
    f"""
    <div class="metric-box">
        <div class="metric-title">Posición Regional</div>
        <div class="metric-val" style="font-size: 1.2rem; margin-top: 0.5rem;">
            🏆 {rank_str}
            <div style="font-size: 0.75rem; color: #94A3B8; margin-top: 2px;">{best_str}</div>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)
```
*Vulnerabilidad:* `best_str` contiene `kpis['best_country_name']` obtenido desde la API del Banco Mundial o metadatos de indicadores sin escapar.

#### Impacto:
Ejecución de scripts arbitrarios en el contexto del usuario en Streamlit Cloud. Un atacante podría secuestrar sesiones, alterar dinámicamente las visualizaciones para desinformar sobre datos macroeconómicos o redirigir a sitios maliciosos.

#### Remediación Recomendada:
Utilizar la función nativa `html.escape()` del módulo estándar de Python antes de interpolar cualquier valor dinámico dentro de cadenas HTML en `st.markdown`:
```python
import html

safe_source = html.escape(str(data_source))
safe_country = html.escape(str(kpis["top_pais_nombre"]))

st.markdown(
    f"""
    <div class="metric-box">
        <div class="metric-val">{safe_country}</div>
    </div>
    """,
    unsafe_allow_html=True,
)
```
O preferir los componentes nativos de Streamlit (`st.metric`, `st.badge`) cuando la personalización CSS extrema no sea estrictamente indispensable.

---

### 🟡 HALLAZGO FE-02: Parámetro de Límite sin Parametrizar en Consulta BigQuery
- **Severidad:** MEDIA (CVSS 5.3)
- **CWE:** CWE-89 (Improper Neutralization of Special Elements used in an SQL Command)
- **Ubicación:** `streamlit_app/utils/bq_client.py` (Líneas 221-224)
- **Descripción:**
  En la función `get_socios_comerciales`:
  ```python
  if limit is not None:
      query += f" LIMIT {limit}"
  ```
  Aunque `limit` está anotado como `int | None`, si en algún punto una entrada del usuario o un query param no tipado se envía directamente, rompe el principio de defensa en profundidad.
- **Remediación:**
  Validar explícitamente que sea un entero positivo y/o incluirlo como parámetro formal:
  ```python
  if limit is not None:
      clean_limit = int(limit)
      query += " LIMIT @limit_val"
      params.append(bigquery.ScalarQueryParameter("limit_val", "INT64", clean_limit))
  ```

---

### 🟡 HALLAZGO FE-03: Falta de Política de Seguridad de Contenido (CSP) y Configuración CORS
- **Severidad:** BAJA / INFORMATIVA (CVSS 3.7)
- **CWE:** CWE-1021 (Improper Restriction of Rendered UI Layers or Frames)
- **OWASP Top 10:** A05:2021 - Security Misconfiguration
- **Ubicación:** `streamlit_app/.streamlit/config.toml` (Línea 18)
- **Descripción:**
  La configuración actual establece:
  ```toml
  [server]
  headless = true
  enableCORS = true
  enableXsrfProtection = true
  ```
  Habilitar CORS de manera permisiva sin restricciones de origen (`origin`) ni cabeceras HTTP de seguridad como `Content-Security-Policy` (CSP), `X-Frame-Options` o `Strict-Transport-Security` facilita escenarios de Clickjacking o incrustación no autorizada en iframes maliciosos.
- **Remediación:**
  1. Si la aplicación se despliega tras un reverse proxy (Cloud Run, NGINX o Cloudflare), configurar cabeceras defensivas:
     - `Content-Security-Policy: default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline';`
     - `X-Frame-Options: SAMEORIGIN`
     - `X-Content-Type-Options: nosniff`
  2. En Streamlit Cloud, restringir `enableCORS = false` si la aplicación solo se consume desde su dominio principal.

---

## 4. Aspectos Positivos y Mecanismos de Protección Existentes

1. **Prevención de DoS por Agotamiento de Memoria (OOM):**
   - El módulo `streamlit_app/pages/04_descargas.py` implementa una verificación rígida de volumen (`MAX_DOWNLOAD_RECORDS = 50000`). Si la consulta excede este umbral, el sistema bloquea la generación del CSV/Excel en memoria RAM y muestra una advertencia interactiva, protegiendo el límite de 1 GB de Streamlit Cloud.
2. **Telemetría Segura y No Invasiva:**
   - La telemetría en `log_ui_event()` no almacena datos de identificación personal (PII), direcciones IP ni secretos; utiliza identificadores pseudo-anónimos UUID v4 generados en sesión.
   - La función es defensiva: captura cualquier excepción interna y nunca rompe el flujo visual del usuario.
3. **Caché Inteligente de Datos (`@st.cache_data(ttl=3600)`):**
   - Minimiza drásticamente los escaneos a BigQuery y lecturas a Firestore, garantizando la viabilidad económica bajo el Always Free Tier.

---

## 5. Plan de Remediación Técnica Frontend

| Prioridad | Tarea | Archivo(s) Afectado(s) | Complejidad |
| :---: | :--- | :--- | :---: |
| **P0** | Escapar variables dinámicas en bloques HTML usando `html.escape` | `streamlit_app/app.py`<br>`streamlit_app/pages/*.py` | Baja (1-2 horas) |
| **P1** | Parametrizar cláusula `LIMIT` en consultas dinámicas | `streamlit_app/utils/bq_client.py` | Muy Baja (30 mins) |
| **P2** | Ajustar configuración de servidor (`enableCORS` y headers) | `streamlit_app/.streamlit/config.toml` | Baja (1 hora) |
