# Informe de Auditoría QA: Lógica de Negocio y Transformación de Datos (V1)

> **Documento:** `docs/INFORME_QA_V1.md`  
> **Proyecto:** InsightBolivia — Plataforma Analítica de Comercio Exterior  
> **Épica / Work Package:** WP-02 Business Logic & Data Transformation QA Audit  
> **Auditor Asignado:** `api-business-logic-tester` (Senior QA & Business Logic Tester)  
> **Fecha de Emisión:** 2026-10-26  
> **Versión:** 1.0.0  
> **Estado del Dictamen:** **OBSERVADO** (Aprobación sujeta a remediación de hallazgos Altos y Medios)  
> **Destinatario para Subsanación:** `subsanar-bugs-qa` / `backend-developer`  

---

## 1. Resumen Ejecutivo

Se ejecutó una auditoría exhaustiva de aseguramiento de calidad (QA) funcional, lógica de negocio e integridad de transformaciones de datos sobre el núcleo de la plataforma **InsightBolivia**, contrastando la implementación técnica contra las especificaciones oficiales del Instituto Nacional de Estadística (INE) documentadas en `Docs/REGLAS_NEGOCIO_COMERCIO_EXTERIOR.md`.

Se auditaron las capas de extracción, transformación, enriquecimiento, validación con **Great Expectations (GX 1.x)**, consultas SQL pre-agregadas en BigQuery y módulos de cálculo analítico para Streamlit.

### 1.1 Resumen Estadístico de Hallazgos

| Severidad | Cantidad | Descripción del Impacto |
| :--- | :---: | :--- |
| **CRITICAL** | **0** | Ningún fallo bloqueante de ejecución total del sistema. |
| **HIGH** | **2** | Errores en agregación de balanza comercial ante nulos y omisiones en la suite de Great Expectations. |
| **MEDIUM** | **4** | Riesgos de unicidad en BigQuery MERGE, corrupción en formateo de NANDINA y orfandad dimensional. |
| **LOW** | **4** | Ambigüedades en subcadenas de países, valores por defecto no alertados e inconsistencias visuales en KPIs. |
| **INFO** | **0** | Observaciones informativas resueltas en la auditoría. |
| **TOTAL** | **10** | **Requiere plan de subsanación priorizado.** |

---

## 2. Alcance y Cobertura de Pruebas

### 2.1 Módulos y Artefactos Auditados

1. **Transformación y Normalización (`src/transform.py`):**
   - Lectura heterogénea (Excel `.xlsx`, `.csv` con Latin-1/UTF-8, `.dbf`).
   - Normalización de columnas canónicas y alias interanuales (`VIASAL2`, `CUCIR3`, `GCE`, `CIIU3`).
   - Formateo arancelario NANDINA (10 dígitos, preservación de ceros a la izquierda).
   - Conversión cambiaria fija (6.96 BOB/USD) y derivación de dimensiones temporales (año, mes, trimestre, fecha `YYYY-MM-01`).
   - Esquemas de Staging (`stg_comercio_exterior`) y Hechos (`fact_comercio_exterior`).

2. **Validación de Calidad de Datos (`src/validate.py`):**
   - Validaciones ligeras en Pandas (`validate_nandina_format`, `validate_non_negative`, `validate_weight_consistency`, `validate_exchange_rate`, `validate_null_threshold`).
   - Suite formal de Great Expectations 1.x (`build_comercio_exterior_suite`, `validate_transformed_data`).

3. **Mapeo Geográfico e ISO (`src/country_iso_mapping.py`):**
   - Mapeo de códigos numéricos INE (1-999) y nombres en español a ISO 3166-1 alpha-3.
   - Manejo de códigos no identificados y asignación de código reservado `ZZZ`.

4. **Benchmark Internacional (`src/extract_benchmark.py`):**
   - Consumo de API del Banco Mundial (`wbgapi`), normalización a `fact_indicadores_bm` y cálculo de hash determinista SHA-256.

5. **Lógica Analítica y Agregaciones SQL (`sql/views/vw_balanza_comercial_mensual.sql` y `streamlit_app/components/`):**
   - Cálculo de balanza comercial: $\text{Balanza} = \sum \text{FOB}_{\text{export}} - \sum \text{CIF}_{\text{import}}$.
   - Convención de signos (Superávit $\ge 0$, Déficit $< 0$).
   - Tasa de cobertura comercial: $(\text{FOB} / \text{CIF}) \times 100$.

### 2.2 Automatización y Evidencia de Ejecución

Se implementó una suite especializada de pruebas de control de calidad en `tests/test_qa_business_logic_audit.py` conteniendo **19 pruebas automatizadas** que validan casos felices, límites numéricos, coherencia física y casos de borde.

- **Comando ejecutado:** `uv run pytest tests/test_qa_business_logic_audit.py -v`
- **Resultado:** **19 passed** en 8.39s (100% éxito).
- **Linter de Seguridad y Estilo:** `uv run ruff check .` $\rightarrow$ **0 errores, 0 advertencias**.

---

## 3. Matriz de Validación de Reglas de Negocio INE

| Código | Regla Oficial INE | Estado QA | Observaciones / Desviaciones |
| :--- | :--- | :---: | :--- |
| **RN-001** | NANDINA debe ser siempre cadena de 10 dígitos | **CUMPLE** | Implementado con `str.zfill(10)` y validado por regex `^\d{10}$`. |
| **RN-002** | NANDINA no debe convertirse a tipo numérico | **CUMPLE** | Se preserva como string en Staging y Fact. |
| **RN-003** | Preservar ceros a la izquierda (~6% del universo) | **CUMPLE** | Validado con códigos como `0901110000` (Café). |
| **RN-004** | Eliminar sufijo `.0` si llega como float antes de zfill | **CUMPLE** | Regex `\.0$` implementado en `src/transform.py`. |
| **RN-005/006** | Capítulo (2 dígitos) y Partida (4 dígitos) | **CUMPLE** | Substrings `[:2]` y `[:4]` derivados correctamente. |
| **RV-001/002** | Exportaciones FOB USD y CIF Frontera USD | **CUMPLE** | Mapeados desde `VALOR` y `FRO` respectivamente. |
| **RV-003/004** | Tipo de cambio oficial 6.96 BOB/USD (fijo) | **OBSERVADO** | Verificado en 6.96 con tolerancia $\pm 0.10$. Sin embargo, la suite GX omite verificar `ADU / FRO` en la tabla de hechos. |
| **RV-006** | Todos los valores monetarios deben ser $\ge 0$ | **OBSERVADO** | `valor_cif_usd` no tiene validación de no-negatividad en la suite de Great Expectations (BUG-QA-002). |
| **RP-001/002** | Exportaciones tienen bruto y neto; Importaciones solo bruto | **CUMPLE** | Consistente con esquemas INE y tablas de hechos. |
| **RP-003** | Coherencia física: `peso_bruto_kg >= peso_neto_kg` | **CUMPLE** | Validado tanto en Pandas como en GX (`ExpectColumnPairValuesAToBeGreaterThanB`). |
| **RP-004** | Pesos deben ser $\ge 0$ | **OBSERVADO** | Ni `peso_bruto_kg` ni `peso_neto_kg` cuentan con cota inferior en la suite de GX (BUG-QA-002). |
| **RC-001/003** | Mapeo de códigos numéricos INE a ISO 3166-1 alpha-3 | **OBSERVADO** | Mapeo funcional, pero falta la inserción de `'ZZZ'` en la tabla sembrada `dim_pais` (BUG-QA-004). |
| **RF-001/002** | Parsing del campo `FLUJO` y no alteración de crudos | **CUMPLE** | Separa código numérico y descripción respetando typo original del INE (`PRESONALES`). |
| **RN-BAL** | $\text{Balanza Comercial} = \text{FOB}_{\text{exp}} - \text{CIF}_{\text{imp}}$ | **OBSERVADO** | Vulnerable a nulos en SQL si una fila de importación carece de CIF (BUG-QA-001). |

---

## 4. Catálogo Detallado de Hallazgos (Finding Format)

### [HIGH] BUG-QA-001 Omisión de COALESCE en valor_cif_usd en vw_balanza_comercial_mensual provoca Saldo NULL
- **Severity:** HIGH
- **Area:** `sql/views/vw_balanza_comercial_mensual.sql:29-31`
- **Evidence:**
  ```sql
  SUM(CASE WHEN f.tipo_operacion = 'EXPORTACION' THEN f.valor_fob_usd ELSE 0 END) AS total_exportaciones_usd,
  SUM(CASE WHEN f.tipo_operacion = 'IMPORTACION' THEN f.valor_cif_usd ELSE 0 END) AS total_importaciones_usd,
  SUM(CASE WHEN f.tipo_operacion = 'EXPORTACION' THEN f.valor_fob_usd ELSE 0 END)
  - SUM(CASE WHEN f.tipo_operacion = 'IMPORTACION' THEN f.valor_cif_usd ELSE 0 END) AS saldo_balanza_usd
  ```
- **Reproduction:**
  1. Insertar una transacción en `fact_comercio_exterior` con `tipo_operacion = 'IMPORTACION'` y `valor_cif_usd IS NULL`.
  2. Ejecutar la consulta de la vista `vw_balanza_comercial_mensual` para ese mes.
  3. En SQL estándar, `CASE WHEN ... THEN f.valor_cif_usd` evalúa a `NULL` cuando el valor es nulo. Si un mes solo cuenta con registros de importación sin CIF liquidado, `SUM()` retorna `NULL`.
  4. La resta `SUM(exportaciones) - NULL` evalúa a `NULL`, dejando el `saldo_balanza_usd` en nulo en lugar de preservar el saldo exportador.
- **Impact:** En boletines preliminares del INE con liquidaciones aduaneras pendientes, la vista mensual genera saldos comerciales nulos, provocando que la UI de Streamlit muestre `$0.00` o rompa gráficos de evolución.
- **Recommendation:** Aplicar `COALESCE(f.valor_cif_usd, 0.0)` dentro de la expresión condicional:
  ```sql
  SUM(CASE WHEN f.tipo_operacion = 'IMPORTACION' THEN COALESCE(f.valor_cif_usd, 0.0) ELSE 0.0 END) AS total_importaciones_usd,
  SUM(CASE WHEN f.tipo_operacion = 'EXPORTACION' THEN COALESCE(f.valor_fob_usd, 0.0) ELSE 0.0 END)
  - SUM(CASE WHEN f.tipo_operacion = 'IMPORTACION' THEN COALESCE(f.valor_cif_usd, 0.0) ELSE 0.0 END) AS saldo_balanza_usd
  ```
- **Suggested owner:** `backend-developer`

---

### [HIGH] BUG-QA-002 Ausencia de validación de no-negatividad para valor_cif_usd y pesos físicos en Great Expectations
- **Severity:** HIGH
- **Area:** `src/validate.py:284-290` (`build_comercio_exterior_suite`)
- **Evidence:**
  ```python
  # Solo se valida valor_fob_usd y valor_fob_bob
  expectations.append(gxe.ExpectColumnValuesToBeBetween(column="valor_fob_usd", min_value=0.0))
  expectations.append(gxe.ExpectColumnValuesToBeBetween(column="valor_fob_bob", min_value=0.0))
  expectations.append(gxe.ExpectColumnValuesToBeBetween(column="mes", min_value=1, max_value=12))
  expectations.append(gxe.ExpectColumnValuesToBeBetween(column="trimestre", min_value=1, max_value=4))
  ```
- **Reproduction:**
  1. Construir un DataFrame de hechos con `valor_cif_usd = -2500.0`, `peso_bruto_kg = -100.0` y `peso_neto_kg = -150.0`.
  2. Ejecutar `validate_transformed_data(df)`.
  3. La validación GX concluye con `success = True`, pasando por alto violaciones a las reglas RV-006 y RP-004 de `Docs/REGLAS_NEGOCIO_COMERCIO_EXTERIOR.md`.
- **Impact:** Registros anómalos con montos CIF negativos o pesos negativos son autorizados para ingesta en BigQuery, distorsionando la balanza comercial y reportes de volumen físico.
- **Recommendation:** Incorporar en `build_comercio_exterior_suite`:
  ```python
  expectations.append(gxe.ExpectColumnValuesToBeBetween(column="valor_cif_usd", min_value=0.0))
  expectations.append(gxe.ExpectColumnValuesToBeBetween(column="peso_bruto_kg", min_value=0.0))
  expectations.append(gxe.ExpectColumnValuesToBeBetween(column="peso_neto_kg", min_value=0.0))
  expectations.append(gxe.ExpectColumnValuesToBeBetween(column="contenido_fino", min_value=0.0))
  ```
- **Suggested owner:** `backend-developer`

---

### [MEDIUM] BUG-QA-003 format_nandina rellena cadenas vacías produciendo códigos ficticios de 10 ceros
- **Severity:** MEDIUM
- **Area:** `src/transform.py:218-225` (`format_nandina`)
- **Evidence:**
  ```python
  def format_nandina(series: pd.Series) -> pd.Series:
      return (
          series.astype(str)
          .str.strip()
          .str.replace(r"\.0$", "", regex=True)
          .str.zfill(10)
      )
  ```
  Al ejecutar `format_nandina(pd.Series([""]))`, el resultado es `'0000000000'`.
- **Reproduction:**
  1. Proveer una serie con valores vacíos `""` o espacios `"   "`.
  2. `format_nandina` retorna `'0000000000'`.
  3. Al validar con `validate_nandina_format` o con la regex de GX `^\d{10}$`, `'0000000000'` aprueba como válido a pesar de que el Capítulo 00 no existe en la nomenclatura NANDINA (los capítulos válidos van del 01 al 97).
- **Impact:** Transacciones con partidas arancelarias omitidas se convierten en registros espurios `'0000000000'`, eludiendo controles de integridad de nulos y corrompiendo el cálculo de productos líderes.
- **Recommendation:** Reemplazar cadenas vacías o valores `'nan'` / `'None'` por `None` o `NaN` antes del `zfill`, o condicionar:
  ```python
  cleaned = series.astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
  return cleaned.where(cleaned.str.len() > 0, None).apply(lambda x: x.zfill(10) if x else None)
  ```
- **Suggested owner:** `backend-developer`

---

### [MEDIUM] BUG-QA-004 Ausencia de registro por defecto ('ZZZ') en dim_pais provoca pérdida de registros en INNER JOINs
- **Severity:** MEDIUM
- **Area:** `src/init_dwh.py:307-377` (`seed_dim_pais`) y `sql/ddl/create_dim_pais.sql`
- **Evidence:**
  `seed_dim_pais` itera exclusivamente sobre `sorted(set(INE_CODE_TO_ISO3.values()))`. El código especial `ZZZ` (país no identificado o no clasificado asignado por `map_country_to_iso3`) no está presente en `INE_CODE_TO_ISO3`.
- **Reproduction:**
  1. Ejecutar el aprovisionamiento de `dim_pais` con `seed_dim_pais`.
  2. Consultar `SELECT COUNT(1) FROM dim_pais WHERE pais_iso = 'ZZZ'`. Retorna 0.
  3. Ejecutar una consulta analítica que una `fact_comercio_exterior` con `dim_pais` mediante `INNER JOIN`:
     ```sql
     SELECT f.*, p.nombre_pais_es FROM fact_comercio_exterior f JOIN dim_pais p ON f.pais_iso = p.pais_iso
     ```
  4. Toda transacción con país no mapeado (`pais_iso = 'ZZZ'`) queda completamente excluida de los resultados analíticos.
- **Impact:** Pérdida silenciosa de registros de comercio exterior en reportes agregados y vistas analíticas que utilicen joins internos con `dim_pais`.
- **Recommendation:** Sembrar explícitamente el registro comodín en `seed_dim_pais`:
  ```python
  rows.append({
      "pais_iso": "ZZZ",
      "codigo_pais_ine": -1,
      "nombre_pais_es": "País no especificado / Desconocido",
      "nombre_pais_en": "Unspecified / Unknown Country",
      "continente": "Otro",
      "subregion": "Otro",
      "bloque_comercial": "General",
  })
  ```
- **Suggested owner:** `backend-developer`

---

### [MEDIUM] BUG-QA-005 Dimensión dim_aduana no se encuentra sembrada ni sincronizada por el pipeline ETL
- **Severity:** MEDIUM
- **Area:** `src/init_dwh.py` y `src/load_comercio_exterior.py:157`
- **Evidence:**
  `sql/ddl/create_dim_aduana.sql` define la dimensión de aduanas con soporte SCD Tipo 2, pero `init_dwh.py` no cuenta con ninguna rutina `seed_dim_aduana`. En `load_comercio_exterior.py:157`, la tabla de hechos asigna `S.codigo_aduana AS id_aduana` directamente, almacenando el código INE numérico en lugar de una surrogate key referenciada a `dim_aduana`.
- **Reproduction:**
  1. Revisar `src/init_dwh.py`. Existen semillas para tiempo, departamentos, vía transporte, moneda y países, pero no para aduanas.
  2. En BigQuery, la tabla `dim_aduana` permanece vacía (0 filas).
- **Impact:** Imposibilidad de enriquecer consultas de aduanas con su nombre oficial, tipo de recinto (frontera, interior, aeropuerto) y ubicación geográfica desde el Star Schema.
- **Recommendation:** Crear la función `seed_dim_aduana` en `src/init_dwh.py` con el catálogo oficial de administraciones aduaneras de la Aduana Nacional de Bolivia (ANB), o sincronizarla dinámicamente desde `stg_comercio_exterior` con SCD Tipo 2.
- **Suggested owner:** `backend-developer`

---

### [MEDIUM] BUG-QA-008 transform_benchmark_data carece de deduplicación previa a BigQuery MERGE
- **Severity:** MEDIUM
- **Area:** `src/extract_benchmark.py:193-239` (`transform_benchmark_data`)
- **Evidence:**
  `transform_benchmark_data` itera sobre `raw_records` y añade directamente a la lista `rows`. Si la API del Banco Mundial o el generador retornan registros redundantes para una misma combinación de `(pais_iso, codigo_indicador, anio)`, el DataFrame resultante contiene duplicados exactos.
- **Reproduction:**
  1. Invocar `transform_benchmark_data` pasando una lista con dos diccionarios idénticos `[item, item]`.
  2. El DataFrame resultante contiene 2 filas con idéntico `id_indicador_bm`.
  3. Al intentar cargar estos datos mediante `load_benchmark_to_bigquery`, la sentencia `MERGE` de BigQuery falla con el error:
     `UPDATE/MERGE must match at most one source row for each target row`.
- **Impact:** Fallos no controlados en la ejecución de tareas programadas (`cron` de GitHub Actions) de benchmark macroeconómico.
- **Recommendation:** Agregar deduplicación explícita antes de retornar el DataFrame:
  ```python
  df = df.drop_duplicates(subset=["pais_iso", "codigo_indicador", "anio"]).reset_index(drop=True)
  ```
- **Suggested owner:** `backend-developer`

---

### [LOW] BUG-QA-006 Colisión por subcadena en map_country_to_iso3 ante nombres genéricos
- **Severity:** LOW
- **Area:** `src/country_iso_mapping.py:273-275`
- **Evidence:**
  ```python
  # Búsqueda parcial o por subcadena
  for name_key, iso3 in NAME_TO_ISO3.items():
      if name_key in clean_str or clean_str in name_key:
          return iso3
  ```
  La condición `clean_str in name_key` permite que cualquier palabra corta contenida en el nombre de un país retorne el ISO de dicho país.
- **Reproduction:**
  1. Invocar `map_country_to_iso3("REPUBLICA")`.
  2. Debido a que `'CAMERUN REPUBLICA UNIDA DEL'` está en `NAME_TO_ISO3`, la función retorna `'CMR'` (Camerún).
  3. Palabras genéricas como `'ESTADOS'` retornan `'USA'`, `'PAISES'` retorna `'NLD'`.
- **Impact:** Falsos positivos en asignación de países si los datos crudos del INE contienen denominaciones abreviadas o truncadas no contempladas.
- **Recommendation:** Restringir la búsqueda por subcadena a coincidencias de palabras completas (`\b{term}\b`) o exigir que `clean_str` tenga al menos 4 caracteres y solo aplicar si representa una proporción significativa de `name_key`.
- **Suggested owner:** `backend-developer`

---

### [LOW] BUG-QA-007 Asignación silenciosa de año 2000 y mes 1 ante valores nulos en derive_temporal_columns
- **Severity:** LOW
- **Area:** `src/transform.py:322-323` (`derive_temporal_columns`)
- **Evidence:**
  ```python
  df["anio"] = pd.Series(year_s, index=df.index).fillna(2000).astype("int64")
  df["mes"] = pd.Series(month_s, index=df.index).fillna(1).astype("int64")
  ```
- **Reproduction:**
  1. Transformar un DataFrame con `gestion = None` y `mes = None`.
  2. La función asigna `anio = 2000`, `mes = 1` y fecha `2000-01-01` sin emitir ninguna alerta en los logs.
- **Impact:** Enmascaramiento de registros con metadatos de tiempo corruptos, asignándolos artificialmente al 1 de enero de 2000.
- **Recommendation:** Emitir un `logger.warning` cuando se detecten valores nulos en columnas temporales obligatorias y permitir que el registro sea capturado por las reglas de validación en lugar de asignarle un valor falso por omisión.
- **Suggested owner:** `backend-developer`

---

### [LOW] BUG-QA-009 Tasa de cobertura de balanza comercial retorna 0.0% cuando importaciones son cero y exportaciones > 0
- **Severity:** LOW
- **Area:** `streamlit_app/components/balanza_charts.py:65`
- **Evidence:**
  ```python
  tasa_cobertura = (total_exp / total_imp * 100.0) if total_imp > 0 else 0.0
  ```
- **Reproduction:**
  1. Simular un periodo donde un departamento registró USD 5,000,000 en exportaciones y USD 0 en importaciones.
  2. `compute_balanza_kpis` calcula `tasa_cobertura_pct = 0.0`.
- **Impact:** Interpretación económica distorsionada en la interfaz: una tasa de cobertura de 0.0% sugiere ausencia total de exportaciones, cuando en realidad la cobertura es infinita/completa (superávit absoluto).
- **Recommendation:** Si `total_imp == 0` y `total_exp > 0`, retornar `None` o `100.0` y en la UI desplegar `N/A (Sin importaciones)` o `>100%`.
- **Suggested owner:** `backend-developer` / `frontend-developer`

---

### [LOW] BUG-QA-010 Generación no determinista de id_transaccion en transform_to_fact
- **Severity:** LOW
- **Area:** `src/transform.py:465` (`transform_to_fact`)
- **Evidence:**
  ```python
  fact["id_transaccion"] = range(1, len(stg) + 1)
  ```
- **Reproduction:**
  1. Procesar dos archivos independientes con `transform_to_fact`.
  2. Ambos generarán claves subrogadas `id_transaccion = [1, 2, 3, ...]`.
  3. Si estos DataFrames se unieran directamente sin pasar por el `MERGE` de BigQuery (que sí usa `FARM_FINGERPRINT`), habría colisiones de claves primarias.
- **Impact:** Inconsistencia entre la lógica de transformación en memoria de Python y la lógica de ingesta en `src/load_comercio_exterior.py`.
- **Recommendation:** Generar `id_transaccion` mediante hash determinista MD5 o SHA-256 de la clave natural compuesta (`fecha`, `codigo_nandina`, `pais_iso`, `tipo_operacion`, `id_departamento`, `id_via_transporte`, `id_aduana`).
- **Suggested owner:** `backend-developer`

---

## 5. Recomendaciones de Mejora y Buenas Prácticas

1. **Endurecimiento de la Suite de Great Expectations:**
   - Elevar la exigencia de no-nulos en `anio`, `mes` y `trimestre` al 100% (`mostly=1.0`), dado que en BigQuery dichas columnas están restringidas con `NOT NULL`. Mantener `mostly=0.95` permitiría que lotes con hasta 5% de nulos provoquen fallos catastróficos en el driver de carga de BigQuery.
   - Restringir `id_departamento` al conjunto numérico válido `[1, 2, 3, 4, 5, 6, 7, 8, 9]`.
   - Restringir `id_via_transporte` al conjunto válido `[1, 2, 3, 4, 5, 6]`.

2. **UI/UX en Dashboard de Balanza Comercial:**
   - En `streamlit_app/components/balanza_charts.py`, diferenciar visualmente el estado de **Equilibrio Comercial** ($0). Actualmente `saldo >= 0` se etiqueta automáticamente como `🟢 Superávit`, lo cual oculta el equilibrio neutro ($0).

3. **Manejo de Escalas en Gráficos Radar de Benchmark:**
   - En `build_multidimensional_radar_chart`, normalizar las métricas mediante escalado Min-Max (0 a 100) antes de graficar en coordenadas polares. Mezclar Inflación (que puede llegar a 200%) con Crecimiento del PIB (-5% a 5%) distorsiona la escala radial del radar.

---

## 6. Verificación de Criterios de Aceptación (Task Brief)

- [x] **Cálculo de balanza comercial y convención de signos verificado:** Confirmada la fórmula oficial $\text{FOB} - \text{CIF}$. Se identificó el riesgo de saldo nulo por ausencia de `COALESCE` (BUG-QA-001) y manejo de cobertura con importaciones cero (BUG-QA-009).
- [x] **Regex NANDINA y alineación de diccionarios territoriales y aduaneros:** Verificado cumplimiento de 10 dígitos y ceros a la izquierda. Se documentó el hallazgo de relleno sobre strings vacíos (BUG-QA-003) y falta de semilla en `dim_aduana` (BUG-QA-005) y comodín en `dim_pais` (BUG-QA-004).
- [x] **Cobertura y confiabilidad de la suite de Great Expectations:** Se probó la suite GX 1.x. Se documentó la falta de validación de no-negatividad en CIF y pesos (BUG-QA-002) y la discrepancia de tolerancia en columnas obligatorias.
- [x] **Indicadores de Benchmark regional y tratamiento de datos faltantes:** Se verificó la extracción de los 8 indicadores WDI con `wbgapi`. Se identificó el riesgo de duplicados previo a la sentencia `MERGE` (BUG-QA-008).
- [x] **Auditoría de casos de borde (bisiestos, negativos, nulos, ceros):** Aprobadas las pruebas de años bisiestos (2020, 2024), divisiones por cero controladas y rechazo de negativos en validaciones nativas.
- [x] **Informe de QA detallado y compatible con `subsanar-bugs-qa`:** Redactado en `docs/INFORME_QA_V1.md` siguiendo estrictamente el estándar de reporte.
