-- ==============================================================================
-- InsightBolivia — DDL: Dimensión Vía de Transporte
-- ==============================================================================
-- Proyecto GCP: insight-bolivia
-- Dataset: comercio_exterior
-- Tabla: dim_via_transporte
-- Épica: EPIC 03 - Data Warehouse Analítico en BigQuery (OLAP)
-- Ticket: TICK-EP3-002
--
-- Descripción:
-- Dimensión de vías de salida y medios de transporte utilizados para el
-- traslado internacional de mercancías (Aérea, Marítima, Terrestre, Ferroviaria, Fluvial, Ductos).
-- ==============================================================================

CREATE TABLE IF NOT EXISTS `insight-bolivia.comercio_exterior.dim_via_transporte`
(
  id_via_transporte INT64 NOT NULL OPTIONS(description="Identificador único de la vía de transporte"),
  codigo_via INT64 OPTIONS(description="Código numérico de la vía de salida o ingreso asignado por el INE"),
  descripcion STRING NOT NULL OPTIONS(description="Descripción de la vía de transporte (Aérea, Marítima, Terrestre, Ferroviaria, Fluvial, Ductos)"),
  medio_transporte STRING OPTIONS(description="Medio de transporte asociado (Camión, Avión, Barco, Tren, Ducto, etc.)")
)
CLUSTER BY id_via_transporte
OPTIONS (
  description = "Dimensión de vías y medios de transporte internacional de mercancías",
  labels = [
    ("layer", "analytics"),
    ("domain", "comercio_exterior"),
    ("type", "dimension"),
    ("scd", "type_1"),
    ("project", "insight-bolivia")
  ]
);
