-- ==============================================================================
-- InsightBolivia — DDL: Dimensión Moneda y Tipos de Cambio
-- ==============================================================================
-- Proyecto GCP: insight-bolivia
-- Dataset: comercio_exterior
-- Tabla: dim_moneda
-- Épica: EPIC 03 - Data Warehouse Analítico en BigQuery (OLAP)
-- Ticket: TICK-EP3-002
--
-- Descripción:
-- Dimensión de monedas y tipos de cambio oficiales frente al Dólar Americano (USD).
-- Registra el tipo de cambio oficial del BCB (6.96 BOB/USD fijo desde 2011, RV-004)
-- con soporte SCD Tipo 2 para auditoría y eventuales ajustes históricos.
-- ==============================================================================

CREATE TABLE IF NOT EXISTS `insight-bolivia.comercio_exterior.dim_moneda`
(
  codigo_moneda STRING NOT NULL OPTIONS(description="Código estándar internacional de moneda ISO 4217 (BOB, USD, EUR, etc.)"),
  nombre_moneda STRING NOT NULL OPTIONS(description="Nombre oficial de la unidad monetaria"),
  tipo_cambio_a_usd NUMERIC NOT NULL OPTIONS(description="Tipo de cambio oficial respecto al Dólar Americano (USD). Para BOB: 6.96 oficial BCB)"),
  fecha_tipo_cambio DATE NOT NULL OPTIONS(description="Fecha de referencia o fijación del tipo de cambio"),
  vigente_desde DATE NOT NULL OPTIONS(description="Fecha de inicio de vigencia de la cotización (SCD Tipo 2)"),
  vigente_hasta DATE OPTIONS(description="Fecha de fin de vigencia de la cotización (NULL si es versión actual, SCD Tipo 2)"),
  es_vigente BOOL NOT NULL OPTIONS(description="Indicador de cotización vigente activa (TRUE: versión vigente, FALSE: versión histórica)")
)
CLUSTER BY codigo_moneda
OPTIONS (
  description = "Dimensión de monedas y tipos de cambio oficiales con soporte SCD Tipo 2",
  labels = [
    ("layer", "analytics"),
    ("domain", "comercio_exterior"),
    ("type", "dimension"),
    ("scd", "type_2"),
    ("project", "insight-bolivia")
  ]
);
