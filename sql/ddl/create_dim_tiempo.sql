-- ==============================================================================
-- InsightBolivia — DDL: Dimensión Tiempo
-- ==============================================================================
-- Proyecto GCP: insight-bolivia
-- Dataset: comercio_exterior
-- Tabla: dim_tiempo
-- Épica: EPIC 03 - Data Warehouse Analítico en BigQuery (OLAP)
-- Ticket: TICK-EP3-002
--
-- Descripción:
-- Dimensión temporal estática precargada para navegación y agregación
-- analítica por año, mes, trimestre, semestre y banderas de período.
-- Representa la granularidad mensual del comercio exterior boliviano.
-- ==============================================================================

CREATE TABLE IF NOT EXISTS `insight-bolivia.comercio_exterior.dim_tiempo`
(
  fecha DATE NOT NULL OPTIONS(description="Fecha representativa del período (primer día del mes YYYY-MM-01)"),
  anio INT64 NOT NULL OPTIONS(description="Año de la operación comercial (ej: 2021, 2026)"),
  mes INT64 NOT NULL OPTIONS(description="Mes numérico de la operación (1-12)"),
  trimestre INT64 NOT NULL OPTIONS(description="Trimestre del año (1-4)"),
  semestre INT64 NOT NULL OPTIONS(description="Semestre del año (1-2)"),
  nombre_mes STRING NOT NULL OPTIONS(description="Nombre completo del mes en español (Enero, Febrero, ... Diciembre)"),
  es_fin_de_anio BOOL NOT NULL OPTIONS(description="Indicador de cierre anual (TRUE para el mes de Diciembre, FALSE en otros meses)")
)
CLUSTER BY fecha
OPTIONS (
  description = "Dimensión temporal estática precargada a nivel mensual",
  labels = [
    ("layer", "analytics"),
    ("domain", "comercio_exterior"),
    ("type", "dimension"),
    ("project", "insight-bolivia")
  ]
);
