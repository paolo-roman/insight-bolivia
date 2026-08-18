-- ==============================================================================
-- InsightBolivia — DDL: Tabla de Hechos de Indicadores Banco Mundial
-- ==============================================================================
-- Proyecto GCP: insight-bolivia
-- Dataset: benchmark_regional
-- Tabla: fact_indicadores_bm
-- Épica: EPIC 07 - Enriquecimiento Internacional y Benchmark Regional
-- Ticket: TICK-EP7-001
--
-- Descripción:
-- Tabla de hechos de series macroeconómicas y de comercio exterior regional
-- extraídas de la API del Banco Mundial (WDI - World Development Indicators)
-- para Bolivia y países de referencia regional (Perú, Chile, Colombia, Paraguay, etc.).
--
-- Estrategias de Optimización (Costo Cero / Always Free Tier):
--   - Particionamiento: Anual por la columna `fecha` (DATE_TRUNC(fecha, YEAR))
--   - Clustering: Por `pais_iso` y `codigo_indicador` para acelerar filtros combinados
-- ==============================================================================

CREATE TABLE IF NOT EXISTS `insight-bolivia.benchmark_regional.fact_indicadores_bm`
(
  id_indicador_bm STRING NOT NULL OPTIONS(description="Identificador único determinista del registro (hash o clave compuesta)"),
  fecha DATE NOT NULL OPTIONS(description="Fecha representativa del año del indicador (YYYY-01-01)"),
  anio INT64 NOT NULL OPTIONS(description="Año del indicador macroeconómico"),
  pais_iso STRING NOT NULL OPTIONS(description="Código de país ISO 3166-1 alpha-3 (BOL, PER, CHL, COL, PRY, etc.)"),
  pais_nombre STRING NOT NULL OPTIONS(description="Nombre en español del país"),
  codigo_indicador STRING NOT NULL OPTIONS(description="Código oficial del indicador en el Banco Mundial (ej: NY.GDP.MKTP.CD)"),
  nombre_indicador STRING NOT NULL OPTIONS(description="Nombre descriptivo del indicador macroeconómico"),
  valor NUMERIC OPTIONS(description="Valor numérico del indicador en el período correspondiente"),
  unidad_medida STRING NOT NULL OPTIONS(description="Unidad de medida del indicador (USD, %, % del PIB, etc.)"),
  fuente STRING NOT NULL OPTIONS(description="Fuente de los datos (Banco Mundial - WDI)"),
  fecha_extraccion TIMESTAMP NOT NULL OPTIONS(description="Timestamp UTC en que fue extraído y cargado el registro")
)
PARTITION BY DATE_TRUNC(fecha, YEAR)
CLUSTER BY pais_iso, codigo_indicador
OPTIONS (
  description = "Tabla de hechos de indicadores macroeconómicos del Banco Mundial particionada anualmente con clustering por país e indicador",
  labels = [
    ("layer", "analytics"),
    ("domain", "benchmark_regional"),
    ("type", "fact"),
    ("project", "insight-bolivia")
  ]
);
