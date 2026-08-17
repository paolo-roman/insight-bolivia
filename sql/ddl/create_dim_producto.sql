-- ==============================================================================
-- InsightBolivia — DDL: Dimensión Producto (Nomenclatura NANDINA)
-- ==============================================================================
-- Proyecto GCP: insight-bolivia
-- Dataset: comercio_exterior
-- Tabla: dim_producto
-- Épica: EPIC 03 - Data Warehouse Analítico en BigQuery (OLAP)
-- Ticket: TICK-EP3-002
--
-- Descripción:
-- Dimensión conforme a la Nomenclatura Arancelaria Común de la Comunidad
-- Andina (NANDINA). Incorpora soporte para Slowly Changing Dimensions (SCD)
-- Tipo 2 para gestionar cambios históricos en las descripciones y clasificaciones
-- arancelarias a lo largo de las distintas gestiones.
-- ==============================================================================

CREATE TABLE IF NOT EXISTS `insight-bolivia.comercio_exterior.dim_producto`
(
  codigo_nandina STRING NOT NULL OPTIONS(description="Código arancelario NANDINA de 10 dígitos (preservando ceros a la izquierda)"),
  descripcion_producto STRING OPTIONS(description="Descripción oficial del producto o mercancía según la partida NANDINA"),
  partida_nandina STRING OPTIONS(description="Partida arancelaria NANDINA correspondiente a los primeros 4 dígitos"),
  capitulo_nandina STRING OPTIONS(description="Capítulo arancelario NANDINA correspondiente a los primeros 2 dígitos"),
  seccion_nandina STRING OPTIONS(description="Sección arancelaria del Sistema Armonizado / NANDINA"),
  sector_economico STRING OPTIONS(description="Sector económico o categoría de actividad asociada al producto"),
  vigente_desde DATE NOT NULL OPTIONS(description="Fecha de inicio de vigencia de la versión del registro (SCD Tipo 2)"),
  vigente_hasta DATE OPTIONS(description="Fecha de fin de vigencia de la versión del registro (NULL si es versión actual, SCD Tipo 2)"),
  es_vigente BOOL NOT NULL OPTIONS(description="Indicador de versión actual activa (TRUE: versión vigente, FALSE: versión histórica)")
)
CLUSTER BY codigo_nandina
OPTIONS (
  description = "Dimensión de productos y partidas arancelarias NANDINA con soporte SCD Tipo 2",
  labels = [
    ("layer", "analytics"),
    ("domain", "comercio_exterior"),
    ("type", "dimension"),
    ("scd", "type_2"),
    ("project", "insight-bolivia")
  ]
);
