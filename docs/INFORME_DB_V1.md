# INFORME DE AUDITORÍA DE BASE DE DATOS Y CONSISTENCIA DE DATOS (DWH & FIRESTORE) — V1
**InsightBolivia — Plataforma de Inteligencia de Comercio Exterior**  
**Fecha:** 26 de Octubre de 2026  
**Auditor Responsable:** `db-auditor` (Senior Database & Data Consistency Auditor)  
**Alcance:** Modelos DDL BigQuery, Vistas Analíticas, Optimización Free-Tier ($0 USD / <= 1TB scan), Cloud Firestore (Modelos, Índices, Reglas, Seeds) e Idempotencia ETL.

---

## 1. RESUMEN EJECUTIVO

Se ha ejecutado una auditoría integral y rigurosa sobre la arquitectura de base de datos, capas de almacenamiento OLAP (Google BigQuery) y NoSQL operacional (Google Cloud Firestore), pipelines de ingesta ETL y consumo analítico desde Streamlit para **InsightBolivia**.

### Diagnóstico General
- **BigQuery DDL & Modelado Dimensional:** El modelo dimensional en estrella (Star Schema) implementa adecuadamente tipos de datos estándar (`NUMERIC`, `DATE`, `STRING`, `INT64`), soporte SCD Tipo 2 en dimensiones maestras (`dim_producto`, `dim_aduana`, `dim_moneda`) y particionamiento mensual en `fact_comercio_exterior`. No obstante, **ninguna tabla particionada activa la directiva `require_partition_filter = true`**, dejando el Data Warehouse vulnerable a escaneos completos no intencionados que violan el presupuesto gratuito ($0 USD / <= 1 TB/mes).
- **Vistas Analíticas:** Las vistas `vw_balanza_comercial_mensual` y `vw_socios_comerciales` están construidas con agregaciones eficientes. Sin embargo, la vista **`vw_benchmark_regional` no existe** en el repositorio ni en el aprovisionamiento DWH (los dashboards consultan directamente la tabla de hechos `fact_indicadores_bm`), y la vista `vw_top_productos_exportados` contiene un límite estático `QUALIFY <= 10` que mutila consultas con filtros dinámicos mayores y realiza un `INNER JOIN` restrictivo con `dim_producto` que descarta transacciones históricas no vigentes.
- **Riesgo de Costos en Streamlit (`bq_client.py`):** Múltiples funciones de consulta carecen de particionamiento obligatorio por defecto:
  1. `get_export_microdatos` permite escaneos completos sin fechas.
  2. `get_available_date_range` ejecuta un `MIN/MAX` sobre toda la tabla de hechos sin filtro de partición.
  3. `get_benchmark_indicadores` filtra por `anio` (columna `INT64`) en lugar de `fecha` (`DATE`), impidiendo la eliminación de particiones en BigQuery.
  4. Los dashboards de Streamlit (`02_socios_comerciales.py` y `03_productos_top.py`) establecen por defecto la opción "Todas las Gestiones (Consolidado)", desencadenando escaneos de todo el historial en el primer renderizado.
- **Firestore Operacional:** Los modelos Pydantic (`src/firestore_models.py`), esquemas y validadores están excelentemente estructurados. La cobertura de índices compuestos (`firestore/indexes/firestore.indexes.json`) cubre todas las consultas complejas activas. Las reglas de seguridad (`firestore.rules`) protegen contra escalamiento de privilegios, con la observación de que la telemetría UI pública opera exclusivamente a través del SDK de administración (Service Account).
- **Idempotencia ETL:** La deduplicación criptográfica SHA-256 en `operations.etl_control_log` y el `MERGE` atómico con clave compuesta y `FARM_FINGERPRINT` en `fact_comercio_exterior` son correctos y robustos. No obstante, se detectó una condición de carrera e idempotencia rota en `seed_dim_pais`, la omisión de la columna de partición en el MERGE de `fact_indicadores_bm`, y una tasa de cambio fijada en código duro (`6.96`) en lugar de consultar `dim_moneda`.

---

## 2. AUDITORÍA DE MODELO Y DDL (BIGQUERY)

### 2.1 Datasets y Políticas de Retención (`sql/ddl/00_create_datasets.sql`, `src/init_dwh.py`)
- **`staging`**: Configurado con retención de 180 días (`default_table_expiration_days = 180`, `default_partition_expiration_days = 180`).  
  *Observación:* En `src/init_dwh.py`, solo se configura `default_table_expiration_ms`, omitiendo la expiración por partición en el aprovisionamiento automatizado por API.
- **`comercio_exterior`**, **`benchmark_regional`**, **`operations`**: Correctamente configurados sin fecha de expiración para persistencia histórica indefinida. Ubicación estándar multi-región `US`.

### 2.2 Tabla de Hechos Central (`fact_comercio_exterior`)
- **Particionamiento:** `PARTITION BY DATE_TRUNC(fecha, MONTH)` (Conforme a grano mensual).
- **Clustering:** `CLUSTER BY codigo_nandina, pais_iso` (Excelente para filtros cruzados de producto y destino).
- **Clave Subrogada (Surrogate Key):** `id_transaccion INT64` generado mediante hash `FARM_FINGERPRINT` sobre 7 atributos naturales (`fecha`, `codigo_nandina`, `pais_iso`, `tipo_operacion`, `id_departamento`, `id_via_transporte`, `id_aduana`).
- **Restricciones:** Carece de constraints informativos `PRIMARY KEY (id_transaccion) NOT ENFORCED` y `FOREIGN KEY ... NOT ENFORCED` soportados modernamente por BigQuery para optimización de planes por el optimizador de costos.
- **Defensa de Costo:** **Falta la opción `require_partition_filter = true`**.

### 2.3 Tabla de Hechos Regional (`fact_indicadores_bm`)
- **Particionamiento:** `PARTITION BY DATE_TRUNC(fecha, YEAR)`.
- **Clustering:** `CLUSTER BY pais_iso, codigo_indicador`.
- **Defensa de Costo:** **Falta la opción `require_partition_filter = true`**.

### 2.4 Dimensiones y Staging
- **`stg_comercio_exterior`**: Particionada mensualmente por `fecha`. Tipado defensivo de códigos como cadenas (evitando colisiones numéricas/flotantes en NANDINA, capítulos y secciones).
- **Dimensiones SCD Tipo 2**: `dim_producto`, `dim_aduana`, `dim_moneda` implementan `vigente_desde DATE`, `vigente_hasta DATE`, `es_vigente BOOL`.
- **Dimensiones SCD Tipo 1**: `dim_pais`, `dim_departamento_origen_destino`, `dim_via_transporte`.
- **`etl_control_log`**: Particionada diariamente por `DATE(timestamp_ejecucion)` y clusterizada por `estado, nombre_archivo`.
- **`ui_analytics_aggregated`**: Particionada mensualmente por `DATE_TRUNC(fecha_mes, MONTH)` y clusterizada por `page, event_type`.

---

## 3. AUDITORÍA DE VISTAS ANALÍTICAS

### 3.1 `vw_balanza_comercial_mensual`
- **Agregación:** Correcta a nivel de `(anio, mes, nombre_mes, trimestre, semestre, fecha)`.
- **Cálculo de Métricas:** Separa limpiamente Exportaciones FOB e Importaciones CIF calculando `saldo_balanza_usd = total_exportaciones_usd - total_importaciones_usd`.
- **Optimización:** Une con `dim_tiempo` sobre `fecha = fecha`. BigQuery propaga el filtro de partición cuando las consultas externas filtran por `fecha`.

### 3.2 `vw_socios_comerciales`
- **Agregación:** Correcta por `(anio, tipo_operacion, pa.pais_iso, ... bloque_comercial)`.
- **Optimización:** Requiere filtrado temporal desde la consulta exterior. Si la consulta exterior filtra por `anio` (`t.anio`), el join con `dim_tiempo` puede retrasar el podado dinámico de particiones (DPP) frente a un filtrado directo sobre `f.fecha`.

### 3.3 `vw_top_productos_exportados`
- **Problema de Truncamiento:** Contiene `QUALIFY ROW_NUMBER() OVER (...) <= 10`. Esto impide que consumidores o dashboards soliciten un Top 15, Top 20 o Top 30.
- **Problema de Integridad Referencial:** Utiliza `JOIN dim_producto p ON f.codigo_nandina = p.codigo_nandina WHERE p.es_vigente = TRUE`. Si un producto fue exportado en años pasados pero su código ya no tiene una versión activa con `es_vigente = TRUE`, o si aún no ha sido sincronizado en `dim_producto`, el registro de hecho es **ignorado silenciosamente del ranking**.

### 3.4 `vw_benchmark_regional` (Ausente)
- La vista analítica especificada en los requerimientos arquitectónicos no existe en `sql/views/` ni fue registrada en `src/init_dwh.py`. Streamlit consulta directamente `fact_indicadores_bm`.

---

## 4. AUDITORÍA DE COSTOS Y CONSUMO EN STREAMLIT (`bq_client.py`)

BigQuery Always Free Tier otorga **1 TB/mes de procesamiento de consultas**. Al superarse, se incurre en cobros a razón de $6.25 USD por TB adicional (o fallas si el proyecto carece de facturación activa).

| Función Streamlit | Tabla/Vista Destino | Riesgo de Escaneo No Particionado | Causa Técnica |
|---|---|---|---|
| `get_available_date_range()` | `vw_balanza_comercial_mensual` | **ALTO (Escaneo Completo)** | Consulta `SELECT MIN(fecha), MAX(fecha)` sin cláusula `WHERE fecha`. Lee toda la tabla `fact_comercio_exterior`. |
| `get_export_microdatos()` | `fact_comercio_exterior` | **CRÍTICO (Escaneo Completo)** | Si `start_date` y `end_date` son `None`, ejecuta consulta con `LIMIT 50001` y `ORDER BY f.fecha DESC` escaneando todos los datos históricos. |
| `get_benchmark_indicadores()` | `fact_indicadores_bm` | **ALTO (Falla de Podado)** | Filtra con `anio >= @start_year`. La tabla está particionada por `fecha`, no por `anio`. BigQuery no puede podar particiones. |
| `get_socios_comerciales()` | `vw_socios_comerciales` | **MEDIO/ALTO** | Cuando `year=None` (opción predeterminada en UI), escanea todo el histórico sin filtro temporal. |
| `get_top_productos()` | `vw_top_productos_exportados` | **MEDIO/ALTO** | Cuando `year=None` (opción predeterminada en UI), consulta todos los años sin podado de particiones. |

---

## 5. AUDITORÍA DE CLOUD FIRESTORE

### 5.1 Modelos y Esquemas (`src/firestore_models.py`, `src/firestore_schemas.py`)
- Pydantic v2 con `ConfigDict(extra="forbid", validate_assignment=True, use_enum_values=True)`.
- Tipado y validadores estrictos:
  - `UserProfile`: Validación de regex de correo y nombres no vacíos. Roles enum `UserRole` (`admin`, `analyst`, `viewer`).
  - `DwhCatalog`: Validación de estados (`active`, `inactive`, `maintenance`, `deprecated`), catálogo de vistas anidadas `CatalogView`.
  - `AuditLog`: Registro de auditoría estructurado.
  - `UiAnalytics`: Telemetría defensiva con duraciones no negativas y metadatos JSON.

### 5.2 Índices Compuestos (`firestore/indexes/firestore.indexes.json`)
- `audit_log`: `(user_id ASC, created_at DESC)` y `(action ASC, created_at DESC)`. Cobertura óptima para consultas de actividad de usuario y auditoría por tipo de evento.
- `ui_analytics`: `(session_id ASC, created_at ASC)` y `(page ASC, created_at DESC)`. Cobertura óptima para reconstrucción de sesiones de usuario y embudos de navegación.
- **Resultado:** No se detectan índices faltantes para los patrones de consulta implementados.

### 5.3 Reglas de Seguridad (`firestore/rules/firestore.rules`)
- `rules_version = '2'`.
- RBAC implementado mediante documento `user_profiles/{uid}`: funciones `isAuthenticated()`, `getUserRole()`, `isAdmin()`.
- Colecciones append-only (`audit_log`, `ui_analytics`) tienen `update, delete: if false;` garantizando inmutabilidad.
- Control contra escalamiento de privilegios en `user_profiles` validando que los usuarios no puedan auto-asignarse roles superiores a `viewer`.
- *Observación:* La regla de `ui_analytics` exige `isAuthenticated()`. Debido a que Streamlit se conecta vía cuenta de servicio (Google Admin SDK), las reglas son superadas por privilegios IAM del backend. Sin embargo, si en el futuro se pretendiera enviar telemetría anónima directamente desde el frontend web, la regla rechazaría a los visitantes sin sesión Firebase.

### 5.4 Inicialización de Semillas (`src/seed_firestore.py`, `seed_catalog.json`)
- Ingesta estrictamente idempotente mediante `set(..., merge=True)` sobre el ID canónico (`comercio_exterior`, `benchmark_regional`).
- El archivo `seed_catalog.json` registra correctamente las 3 vistas de comercio exterior, pero `benchmark_regional` tiene `"views": []`.

---

## 6. AUDITORÍA DE PIPELINE ETL E IDEMPOTENCIA

### 6.1 Control de Idempotencia por Hash SHA-256 (`src/load.py`)
- Función `is_already_processed(hash_sha256)`: Consulta `operations.etl_control_log` verificando `hash_sha256 = @hash_val AND estado = 'SUCCESS'`.
- Evita reprocesamiento redundante de boletines mensuales ya cargados.
- Si un archivo se reenvía sin alteraciones, el pipeline retorna `LoadResult(status='SKIPPED')` sin modificar BigQuery ni Firestore.

### 6.2 MERGE Upsert en `fact_comercio_exterior` (`src/load_comercio_exterior.py`)
- **Clave Compuesta de Grano Completo:**
  `(fecha, codigo_nandina, pais_iso, tipo_operacion, id_departamento, id_via_transporte, id_aduana)`.
- **Condición ON del MERGE:**
  Incluye `T.fecha = S.fecha`, lo que garantiza que BigQuery active el podado de particiones en la tabla de destino durante la ejecución de la sentencia MERGE.
- **Manejo de Nulos:** Aplica `COALESCE` en dimensiones opcionales (`id_departamento`, `id_via_transporte`, `id_aduana` con valor predeterminado `-1`).
- **Surrogate Key:** Calcula `FARM_FINGERPRINT` sobre la concatenación determinista de los 7 campos de la clave compuesta.

### 6.3 Mantenimiento SCD Tipo 2 en `dim_producto` (`src/load_comercio_exterior.py`)
- Proceso en dos pasos por lote:
  1. Sentencia `MERGE` que detecta cambios en `descripcion_producto` o `sector_economico`, actualizando la versión activa: `SET es_vigente = FALSE, vigente_hasta = CURRENT_DATE()`.
  2. Sentencia `INSERT` que crea la nueva versión vigente con `es_vigente = TRUE, vigente_desde = CURRENT_DATE(), vigente_hasta = NULL`.
- Lógica idempotente y resistente a reprocesos.

---

## 7. HALLAZGOS DETALLADOS (FINDING FORMAT)

### [CRITICAL] DB-001 Riesgo de Agotamiento de Capa Gratuita por Escaneo No Particionado en `get_export_microdatos`
- **Severity:** CRITICAL
- **Area:** `streamlit_app/utils/bq_client.py:292-365`
- **Evidence:**
  ```python
  # streamlit_app/utils/bq_client.py:328-341
  WHERE 1=1
  if start_date is not None:
      query += " AND f.fecha >= @start_date"
  if end_date is not None:
      query += " AND f.fecha <= @end_date"
  ...
  query += " ORDER BY f.fecha DESC, f.valor_fob_usd DESC LIMIT @limit_val"
  ```
  Al llamar `get_export_microdatos()` sin parámetros de fecha (comportamiento validado en `test_get_export_microdatos_unfiltered_defaults`), la consulta se ejecuta con `WHERE 1=1 ORDER BY ... LIMIT 50001`. En BigQuery, el ordenamiento global antes de un `LIMIT` obliga al motor a leer todas las particiones de la tabla `fact_comercio_exterior` y realizar 3 `LEFT JOIN` completos sobre las dimensiones.
- **Reproduction:**
  1. Invocar en Python o test: `df = get_export_microdatos(start_date=None, end_date=None)`.
  2. Inspeccionar el plan de ejecución en BigQuery: `totalBytesBilled` equivale al tamaño total de `fact_comercio_exterior` más las 3 dimensiones unidas.
- **Impact:** Posible agotamiento del límite gratuito mensual de 1 TB de escaneo en GCP tras pocas descargas interactivas de usuarios.
- **Recommendation:**
  1. Exigir obligatoriamente `start_date` y `end_date` en la firma de `get_export_microdatos`, lanzando un `ValueError` si son `None`.
  2. En la página `04_descargas.py`, predeterminar un rango temporal acotado (ej: últimos 3 meses) en lugar de la totalidad del histórico disponible.
  3. Activar en el DDL de `fact_comercio_exterior` la opción `require_partition_filter = true`.
- **Suggested owner:** `backend-developer`

---

### [HIGH] DB-002 Falla de Eliminación de Particiones en `fact_indicadores_bm` por Filtrado en `anio`
- **Severity:** HIGH
- **Area:** `streamlit_app/utils/bq_client.py:369-410` y `src/extract_benchmark.py:284-296`
- **Evidence:**
  `fact_indicadores_bm` está particionada por `DATE_TRUNC(fecha, YEAR)`.
  Sin embargo, en `bq_client.py`:
  ```python
  if start_year is not None:
      query += " AND anio >= @start_year"
  if end_year is not None:
      query += " AND anio <= @end_year"
  ```
  Y en `extract_benchmark.py`:
  ```sql
  MERGE {target_table} T
  USING (...) S
  ON T.pais_iso = S.pais_iso
      AND T.codigo_indicador = S.codigo_indicador
      AND T.anio = S.anio
  ```
  La columna `anio` es un entero `INT64` y no la columna de partición `fecha`. BigQuery únicamente poda particiones cuando la cláusula `WHERE` o la condición `ON` del `MERGE` evalúan la columna de partición `fecha`.
- **Reproduction:**
  1. Ejecutar consulta sobre `fact_indicadores_bm` con `WHERE anio = 2023`.
  2. Revisar `bytes_scanned`: BigQuery escanea todos los años registrados (2000-2024).
- **Impact:** Sobrecosto y degradación de rendimiento innecesaria tanto en las consultas de Streamlit como en cada corrida del pipeline de ingesta del Banco Mundial.
- **Recommendation:**
  1. En `bq_client.py`, modificar los predicados a:
     ```sql
     AND fecha >= DATE(@start_year, 1, 1) AND fecha <= DATE(@end_year, 12, 31)
     ```
  2. En `extract_benchmark.py`, incluir `AND T.fecha = S.fecha` en la cláusula `ON` del `MERGE`.
- **Suggested owner:** `backend-developer`

---

### [HIGH] DB-003 Condición de Carrera e Inserción Parcial Irreversible en `seed_dim_pais`
- **Severity:** HIGH
- **Area:** `src/init_dwh.py:362-376`
- **Evidence:**
  ```python
  check_job = client.query(f"SELECT COUNT(1) AS cnt FROM `{project_id}.comercio_exterior.dim_pais`")
  results = list(check_job.result())
  if results and results[0].cnt > 0:
      return int(results[0].cnt)

  table = client.get_table(...)
  for i in range(0, len(rows), batch_size):
      chunk = rows[i : i + batch_size]
      client.insert_rows_json(table, chunk)
  ```
  A diferencia de `seed_dim_tiempo` y `seed_dim_departamentos` que ejecutan un `MERGE` atómico SQL, `seed_dim_pais` utiliza `SELECT COUNT(1)` seguido de lotes de `insert_rows_json`.
- **Reproduction:**
  1. Interrumpir la ejecución de `provision_dwh` tras el primer lote (100 filas insertadas de ~240).
  2. Ejecutar nuevamente `provision_dwh`.
  3. `SELECT COUNT(1)` retorna `100 > 0`, por lo que el script concluye exitosamente sin sembrar las 140 filas restantes.
- **Impact:** Catálogo de países incompleto de manera permanente ante fallos transitorios de red, corrompiendo los cruces analíticos posteriores.
- **Recommendation:**
  Reemplazar el bloque con una sentencia `MERGE` sobre `dim_pais` evaluando `ON T.pais_iso = S.pais_iso WHEN NOT MATCHED THEN INSERT ...`, unificando el estándar con las demás dimensiones.
- **Suggested owner:** `backend-developer`

---

### [HIGH] DB-004 Pérdida de Mapeo de País y Riesgo de Caída en `'ZZZ'` en `merge_into_fact_comercio_exterior`
- **Severity:** HIGH
- **Area:** `src/load_comercio_exterior.py:169` y `src/init_dwh.py:310-313`
- **Evidence:**
  En `init_dwh.py`:
  ```python
  for code, iso in INE_CODE_TO_ISO3.items():
      if iso not in iso_to_ine:
          iso_to_ine[iso] = code
  ```
  `dim_pais` sólo conserva un único `codigo_pais_ine` por país ISO3.
  En `load_comercio_exterior.py`:
  ```sql
  LEFT JOIN {pais_ref} P ON S.codigo_pais_ine = P.codigo_pais_ine
  ```
  Si el boletín del INE utiliza un código alternativo o si el campo `codigo_pais_ine` viene vacío o no coincide, el cruce devuelve `NULL` y asigna `COALESCE(P.pais_iso, 'ZZZ')`, descartando el nombre de país (`nombre_pais`) presente en staging.
- **Reproduction:**
  1. Procesar un registro en staging con `codigo_pais_ine = NULL` y `nombre_pais = 'ESTADOS UNIDOS'`.
  2. El MERGE inserta en `fact_comercio_exterior` con `pais_iso = 'ZZZ'`.
- **Impact:** Registros comerciales legítimos se agrupan en el código ficticio `'ZZZ'` (País Desconocido), distorsionando los mapas de comercio exterior y balances bilaterales.
- **Recommendation:**
  Asegurar que `stg_comercio_exterior` contenga la columna normalizada `pais_iso` resuelta previamente durante la etapa de transformación mediante `map_country_to_iso3()`, o utilizar una condición de unión defensiva en SQL:
  ```sql
  LEFT JOIN {pais_ref} P 
    ON S.codigo_pais_ine = P.codigo_pais_ine 
    OR LOWER(S.nombre_pais) = LOWER(P.nombre_pais_es)
  ```
- **Suggested owner:** `backend-developer`

---

### [MEDIUM] DB-005 Ausencia de la Vista Analítica `vw_benchmark_regional` en BigQuery
- **Severity:** MEDIUM
- **Area:** `sql/views/`, `src/init_dwh.py`, `firestore/seeds/seed_catalog.json`
- **Evidence:**
  1. En `sql/views/` solo existen 3 vistas (`vw_balanza_comercial_mensual.sql`, `vw_socios_comerciales.sql`, `vw_top_productos_exportados.sql`).
  2. `src/init_dwh.py:53` no incluye `vw_benchmark_regional.sql` en `VIEW_FILES`.
  3. `firestore/seeds/seed_catalog.json` define `"id": "benchmark_regional"` con `"views": []`.
  4. Streamlit consulta directamente la tabla de hechos `fact_indicadores_bm`.
- **Reproduction:**
  1. Ejecutar `Get-ChildItem sql/views`: se constata la inexistencia de `vw_benchmark_regional.sql`.
- **Impact:** Falta de uniformidad en la arquitectura de consumo OLAP. Exposición directa de la tabla de hechos a consultas de la interfaz de usuario.
- **Recommendation:**
  Crear el archivo `sql/ddl/views/vw_benchmark_regional.sql`, agregarlo a la orquestación en `init_dwh.py` y actualizar el catálogo de Firestore y `bq_client.py` para consultar a través de la vista.
- **Suggested owner:** `backend-developer`

---

### [MEDIUM] DB-006 Vista `vw_top_productos_exportados` Mutilada por `QUALIFY <= 10` e `INNER JOIN` con SCD2
- **Severity:** MEDIUM
- **Area:** `sql/views/vw_top_productos_exportados.sql:35-46`
- **Evidence:**
  ```sql
  JOIN `insight-bolivia.comercio_exterior.dim_producto` p ON f.codigo_nandina = p.codigo_nandina
  WHERE f.tipo_operacion = 'EXPORTACION'
    AND p.es_vigente = TRUE
  ...
  QUALIFY ROW_NUMBER() OVER (PARTITION BY t.anio ORDER BY SUM(f.valor_fob_usd) DESC) <= 10;
  ```
  1. El filtro estricto `<= 10` impide que consumidores obtengan rankings mayores (Top 15 o Top 20).
  2. Si un código NANDINA histórico sufrió un cierre de vigencia (`es_vigente = FALSE`) y no existe una versión actual activa, el `INNER JOIN` elimina completamente la transacción del cálculo anual.
- **Reproduction:**
  1. Insertar una transacción en `fact_comercio_exterior` con un código arancelario cuya versión en `dim_producto` tenga `es_vigente = FALSE`.
  2. Consultar `vw_top_productos_exportados`: la transacción no aparece en la suma de valores exportados.
- **Impact:** Subestimación del volumen y valor total de las exportaciones en el ranking histórico; incapacidad de satisfacer parámetros dinámicos de interfaz.
- **Recommendation:**
  1. Aumentar el límite del QUALIFY en la vista a `<= 100` o delegar el filtrado de ranking a la consulta consumidora.
  2. Cambiar a `LEFT JOIN` considerando el intervalo histórico de vigencia:
     ```sql
     LEFT JOIN `dim_producto` p 
       ON f.codigo_nandina = p.codigo_nandina 
       AND (f.fecha BETWEEN p.vigente_desde AND COALESCE(p.vigente_hasta, DATE '9999-12-31') OR p.es_vigente = TRUE)
     ```
- **Suggested owner:** `backend-developer`

---

### [MEDIUM] DB-007 Consulta de Rango de Fechas `get_available_date_range` Escanea Toda la Tabla de Hechos
- **Severity:** MEDIUM
- **Area:** `streamlit_app/utils/bq_client.py:266-289`
- **Evidence:**
  ```sql
  SELECT MIN(fecha) AS min_date, MAX(fecha) AS max_date
  FROM `{proj}.{ds}.vw_balanza_comercial_mensual`
  ```
  Esta consulta se ejecuta al inicializar las páginas `01_balanza_comercial.py`, `02_socios_comerciales.py`, `03_productos_top.py` y `04_descargas.py`. Al no tener filtro de partición, obliga a BigQuery a escanear todas las particiones mensuales de `fact_comercio_exterior`.
- **Reproduction:**
  1. Cargar la página `01_balanza_comercial.py` con caché limpio.
  2. Verificar los bytes procesados por la consulta interna de `get_available_date_range`.
- **Impact:** Consumo repetitivo del presupuesto gratuito de escaneo de 1 TB/mes sólo para poblar selectores de UI.
- **Recommendation:**
  Consultar el rango de fechas desde la metadata cacheada en Firestore (`dwh_catalog.last_data_refresh`) o desde la tabla de control ligera `operations.etl_control_log`, evitando tocar la tabla de hechos.
- **Suggested owner:** `backend-developer`

---

### [LOW] DB-008 Tipo de Cambio Fijo 6.96 en Código Duro en el MERGE de Comercio Exterior
- **Severity:** LOW
- **Area:** `src/load_comercio_exterior.py:161`
- **Evidence:**
  ```sql
  SUM(COALESCE(S.valor_fob_usd * 6.96, 0.0)) AS valor_fob_bob,
  ```
  El Data Warehouse cuenta con una dimensión dedicada `dim_moneda` con soporte SCD Tipo 2 expresamente diseñada para registrar tipos de cambio oficiales históricos.
- **Reproduction:**
  1. Inspeccionar `src/load_comercio_exterior.py` línea 161.
- **Impact:** Vulnerabilidad ante modificaciones cambiarias futuras o reprocesamiento de series previas a 2011.
- **Recommendation:**
  Vincular `dim_moneda` en el CTE de preparación del MERGE o parametrizar el factor de conversión cambiario desde la configuración centralizada `src/config.py`.
- **Suggested owner:** `backend-developer`

---

### [LOW] DB-009 Omisión de Expiración por Partición en `src/init_dwh.py`
- **Severity:** LOW
- **Area:** `src/init_dwh.py:137-140`
- **Evidence:**
  En `create_datasets()`, se configura:
  ```python
  if meta.table_exp_days is not None:
      ms_val = meta.table_exp_days * 86400 * 1000
      ds.default_table_expiration_ms = ms_val
  ```
  No se define `ds.default_partition_expiration_ms`.
- **Reproduction:**
  1. Ejecutar `init_dwh.py` contra BigQuery.
  2. Inspeccionar la configuración del dataset `staging`: las particiones no tienen expiración automática individual a los 180 días, solo la tabla entera.
- **Impact:** Acumulación progresiva de almacenamiento en la capa de staging más allá de la ventana de 6 meses.
- **Recommendation:**
  Agregar `ds.default_partition_expiration_ms = ms_val` cuando `table_exp_days` esté definido.
- **Suggested owner:** `backend-developer`

---

### [INFO] DB-010 Falta de Claves Primarias y Foráneas Declarativas (NOT ENFORCED) en BigQuery DDL
- **Severity:** INFO
- **Area:** `sql/ddl/create_fact_comercio_exterior.sql`, `sql/ddl/create_dim_*.sql`
- **Evidence:**
  Las sentencias DDL definen tipos de datos y opciones, pero no declaran constraints informativas:
  `PRIMARY KEY (id_transaccion) NOT ENFORCED`
  `FOREIGN KEY (codigo_nandina) REFERENCES dim_producto(codigo_nandina) NOT ENFORCED`
- **Reproduction:**
  1. Revisar los archivos DDL en `sql/ddl/`.
- **Impact:** El motor de optimización de consultas de BigQuery (BI Engine y optimizador de costos) aprovecha las restricciones no forzadas para realizar eliminación de joins redundantes (join elimination) y mejorar los tiempos de respuesta.
- **Recommendation:**
  Incorporar las cláusulas `PRIMARY KEY (...) NOT ENFORCED` y `FOREIGN KEY (...) NOT ENFORCED` en los DDLs correspondientes.
- **Suggested owner:** `backend-developer`

---

## 8. MATRIZ DE RIESGOS Y PLAN DE REMEDIACIÓN

| ID | Hallazgo | Severidad | Esfuerzo Estimado | Agente Asignado |
|---|---|---|---|---|
| **DB-001** | Escaneo completo en `get_export_microdatos` | **CRITICAL** | 2 horas | `backend-developer` |
| **DB-002** | Falla de podado en `fact_indicadores_bm` (`anio` vs `fecha`) | **HIGH** | 1 hora | `backend-developer` |
| **DB-003** | Condición de carrera en `seed_dim_pais` | **HIGH** | 1.5 horas | `backend-developer` |
| **DB-004** | Caída en `'ZZZ'` por cruce débil de países en MERGE | **HIGH** | 2 horas | `backend-developer` |
| **DB-005** | Vista analítica ausente `vw_benchmark_regional` | **MEDIUM** | 2 horas | `backend-developer` |
| **DB-006** | `QUALIFY <= 10` e `INNER JOIN` en `vw_top_productos_exportados` | **MEDIUM** | 1.5 horas | `backend-developer` |
| **DB-007** | Escaneo completo en `get_available_date_range` | **MEDIUM** | 1 hora | `backend-developer` |
| **DB-008** | Tipo de cambio 6.96 en código duro | **LOW** | 1 hora | `backend-developer` |
| **DB-009** | Falta `default_partition_expiration_ms` en `init_dwh.py` | **LOW** | 0.5 horas | `backend-developer` |
| **DB-010** | Constraints `NOT ENFORCED` faltantes en BigQuery DDL | **INFO** | 1 hora | `backend-developer` |

---
**Conclusión de Auditoría:**  
La base de datos analítica y el almacén NoSQL de **InsightBolivia** cuentan con una arquitectura moderna y bien concebida. La resolución de los hallazgos críticos de particionamiento y consistencia de cruces garantizará de forma definitiva la operación a costo cero ($0 USD) dentro del Always Free Tier y la total exactitud en las cifras macroeconómicas presentadas.
