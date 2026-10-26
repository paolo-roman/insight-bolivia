# Resumen Consolidado de Auditoría Pre-Producción — InsightBolivia V1.0

**Fecha:** 2026-10-26  
**Veredicto Global:** **GO-WITH-RISKS** (Aprobado condicionado a la subsanación de los hallazgos P0/High antes del lanzamiento a producción)  
**Equipo Auditor:**
- `ui-ux-inspector` (Auditoría UI/UX y E2E: `docs/INFORME_UX_E2E_V1.md`)
- `api-business-logic-tester` (Auditoría de Lógica de Negocio y QA: `docs/INFORME_QA_V1.md`)
- `db-auditor` (Auditoría de Bases de Datos, DDL y Consistencia: `docs/INFORME_DB_V1.md`)
- `security-auditor` (Auditoría de Seguridad y Pentesting: `docs/RESUMEN_SEGURIDAD_INTEGRAL_V2.md`)
- `devops-auditor` (Auditoría de DevOps y Resiliencia Operativa: `docs/INFORME_PRODUCCION_V1.md`)

---

## 1. Matriz Consolidada de Hallazgos por Severidad y Capa

| Capa / Auditoría | CRITICAL | HIGH | MEDIUM | LOW | INFO | TOTAL |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| **UI/UX & E2E** (`WP-01`) | 0 | 1 | 3 | 4 | 2 | 10 |
| **Lógica de Negocio & QA** (`WP-02`) | 0 | 2 | 4 | 4 | 0 | 10 |
| **Base de Datos & BigQuery** (`WP-03`) | 1 | 3 | 3 | 2 | 1 | 10 |
| **Seguridad & Dependencias** (`WP-04`) | 0 | 1 | 3 | 3 | 1 | 8 |
| **DevOps & Ingesta ETL** (`WP-05`) | 0 | 2 | 3 | 2 | 1 | 8 |
| **TOTAL CONSOLIDADO** | **1** | **9** | **16** | **15** | **5** | **46** |

---

## 2. Hallazgos Críticos y de Alta Severidad (Bloqueantes de Go-Live P0)

### 2.1 [CRITICAL] DB-001 / SEC-BK-06: Escaneo Crudo sin Partición en `get_export_microdatos`
- **Impacto:** Riesgo de agotamiento de la cuota mensual gratuita de BigQuery (1 TB/mes) en Streamlit si un usuario consulta microdatos sin rango de fechas obligatorio.
- **Remediación:** En `streamlit_app/utils/bq_client.py`, forzar rango obligatorio de fechas sobre la columna `fecha`, rechazar consultas abiertas y configurar `maximum_bytes_billed = 250 * 1024 * 1024` (250 MB) en `QueryJobConfig`.

### 2.2 [HIGH] SEC-SCA-01 / PROD-01: 44 Vulnerabilidades Conocidas en `uv.lock`
- **Impacto:** Falla en la barrera de seguridad de CI (`pip-audit`) debido a dependencias con CVEs en `certifi`, `filelock` y `pillow`.
- **Remediación:** Actualizar dependencias mediante `uv lock --upgrade-package streamlit --upgrade-package pillow --upgrade-package certifi --upgrade-package filelock` y `uv sync`.

### 2.3 [HIGH] PROD-02: Éxito Silencioso en Extracciones Fallidas ("Ghost Runs")
- **Impacto:** Si la descarga del portal del INE falla, el proceso en `src/main.py` registraba éxito retornando código de salida 0.
- **Remediación:** Evaluar `extract_summary.failed`, propagar el conteo a `failed_files`, notificar a Discord y finalizar con `sys.exit(1)`.

### 2.4 [HIGH] BUG-QA-001: Saldo Comercial Nulo en `vw_balanza_comercial_mensual.sql`
- **Impacto:** Falta de `COALESCE` en importaciones CIF genera valores `NULL` en el saldo mensual cuando no hay importaciones registradas.
- **Remediación:** Aplicar `COALESCE(cif.total_cif_usd, 0)` en la fórmula de resta de la vista SQL y en `src/init_dwh.py`.

### 2.5 [HIGH] BUG-QA-002: Ausencia de Expectativa de No-Negatividad en GX
- **Impacto:** La suite de Great Expectations omitía la regla de no-negatividad para `valor_cif_usd`, pesos físicos y contenido fino.
- **Remediación:** Incorporar `expect_column_values_to_be_between(min_value=0)` en `src/validate.py`.

### 2.6 [HIGH] DB-002: Poda de Particiones Omitida en `fact_indicadores_bm`
- **Impacto:** Filtro por `anio` en vez de `fecha` omite el pruning mensual de partición en BigQuery.
- **Remediación:** Alinear el filtro temporal sobre la columna particionada `fecha`.

### 2.7 [HIGH] DB-003 / BUG-QA-004: Registro Comodín `'ZZZ'` y Concurrencia en `dim_pais`
- **Impacto:** Pérdida de registros transaccionales en `INNER JOIN` si el código de país no existe o es indeterminado.
- **Remediación:** Sembrar `'ZZZ'` (País no determinado) en `dim_pais` e implementar sembrado idempotente sin condición de carrera.

### 2.8 [HIGH] UX-01: Incompatibilidad de Texto en Modo Claro
- **Impacto:** Encabezados con color fijo blanco (`#F8FAFC`) resultan invisibles sobre fondo blanco en navegadores con tema claro.
- **Remediación:** Reemplazar estilos fijos por variables CSS adaptables al tema de Streamlit (`var(--text-color)`).

---

## 3. Plan de Remediación Inmediata (Ola de Corrección)

1. **Dependencias y Seguridad:** Actualizar paquetes vulnerables en `uv.lock` y verificar paso limpio de `pip-audit`.
2. **Backend & ETL:** Subsanar `src/main.py` (ghost runs), `src/validate.py` (GX no-negatividad), `src/country_iso_mapping.py` / `src/init_dwh.py` (sembrado 'ZZZ' y view balanza).
3. **BigQuery Client:** Agregar límites `maximum_bytes_billed` y validación defensiva de fechas en `streamlit_app/utils/bq_client.py`.
4. **Streamlit Frontend:** Corregir contraste de modo claro en `streamlit_app/app.py` y optimizar la generación de Excel en `04_descargas.py`.
5. **Verificación:** Ejecutar la suite completa de pruebas unitarias (`uv run pytest`) verificando cobertura $\ge 90\%$ y linter `uv run ruff check .`.
