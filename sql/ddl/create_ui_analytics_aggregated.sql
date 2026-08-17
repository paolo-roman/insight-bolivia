-- ==============================================================================
-- InsightBolivia — DDL: Tabla de Analítica de UI Agregada (Retención Histórica)
-- ==============================================================================
-- Proyecto GCP: insight-bolivia
-- Dataset: operations
-- Tabla: ui_analytics_aggregated
-- Épica: EPIC 03 - Data Warehouse Analítico en BigQuery (OLAP)
-- Ticket: TICK-EP3-003
--
-- Descripción:
-- Tabla para almacenar métricas mensuales agregadas de telemetría y uso de la
-- plataforma Streamlit, exportadas periódicamente desde Cloud Firestore para
-- permitir análisis de retención histórica indefinida a costo cero.
--
-- Estrategias de Optimización (Costo Cero / Always Free Tier):
--   - Particionamiento: Mensual por la columna `fecha_mes` (DATE_TRUNC(fecha_mes, MONTH))
--   - Clustering: Por `page` y `event_type`
-- ==============================================================================

CREATE TABLE IF NOT EXISTS `insight-bolivia.operations.ui_analytics_aggregated`
(
  fecha_mes DATE NOT NULL OPTIONS(description="Primer día del mes representativo de la agregación (YYYY-MM-01)"),
  anio INT64 NOT NULL OPTIONS(description="Año correspondiente a la telemetría agregada"),
  mes INT64 NOT NULL OPTIONS(description="Mes del año 1-12 correspondiente a la telemetría agregada"),
  page STRING NOT NULL OPTIONS(description="Ruta o identificador de la página visitada en Streamlit (ej: 01_balanza_comercial)"),
  event_type STRING NOT NULL OPTIONS(description="Tipo de evento de interacción registrado (ej: page_view, filter_apply, export_csv)"),
  total_eventos INT64 NOT NULL OPTIONS(description="Cantidad total de eventos registrados durante el período mensual"),
  total_sesiones_unicas INT64 OPTIONS(description="Número de sesiones únicas registradas durante el mes"),
  total_usuarios_unicos INT64 OPTIONS(description="Número de usuarios únicos identificados durante el mes"),
  duracion_promedio_ms NUMERIC OPTIONS(description="Tiempo promedio de interacción o renderizado en milisegundos"),
  duracion_maxima_ms INT64 OPTIONS(description="Tiempo máximo de interacción registrado en milisegundos"),
  duracion_minima_ms INT64 OPTIONS(description="Tiempo mínimo de interacción registrado en milisegundos"),
  fecha_exportacion TIMESTAMP NOT NULL OPTIONS(description="Marca temporal en UTC de la exportación y agregación desde Cloud Firestore")
)
PARTITION BY DATE_TRUNC(fecha_mes, MONTH)
CLUSTER BY page, event_type
OPTIONS (
  description = "Tabla de retención histórica mensual para métricas de telemetría y uso exportadas desde Cloud Firestore",
  labels = [
    ("layer", "operations"),
    ("domain", "telemetry"),
    ("type", "aggregated_analytics"),
    ("project", "insight-bolivia")
  ]
);
