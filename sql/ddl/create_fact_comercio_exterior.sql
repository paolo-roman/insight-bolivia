-- ==============================================================================
-- InsightBolivia — DDL: Tabla de Hechos de Comercio Exterior
-- ==============================================================================
-- Proyecto GCP: insight-bolivia
-- Dataset: comercio_exterior
-- Tabla: fact_comercio_exterior
-- Épica: EPIC 03 - Data Warehouse Analítico en BigQuery (OLAP)
-- Ticket: TICK-EP3-002
--
-- Descripción:
-- Tabla de hechos central del Data Warehouse analítico (Star Schema).
-- Consolida transacciones mensuales de Exportaciones e Importaciones de Bolivia.
--
-- Estrategias de Optimización (Costo Cero / Always Free Tier):
--   - Particionamiento: Mensual por la columna `fecha` (DATE_TRUNC(fecha, MONTH))
--   - Clustering: Por `codigo_nandina` y `pais_iso` para acelerar filtros combinados
-- ==============================================================================

CREATE TABLE IF NOT EXISTS `insight-bolivia.comercio_exterior.fact_comercio_exterior`
(
  id_transaccion INT64 NOT NULL OPTIONS(description="Identificador único y clave subrogada (surrogate key) de la transacción"),
  fecha DATE NOT NULL OPTIONS(description="Fecha representativa de la operación (primer día del mes YYYY-MM-01, clave foránea a dim_tiempo)"),
  codigo_nandina STRING NOT NULL OPTIONS(description="Código de partida arancelaria NANDINA de 10 dígitos (clave foránea a dim_producto)"),
  pais_iso STRING NOT NULL OPTIONS(description="Código de país ISO 3166-1 alpha-3 (clave foránea a dim_pais)"),
  id_departamento INT64 OPTIONS(description="Identificador del departamento de origen/destino (clave foránea a dim_departamento_origen_destino)"),
  id_via_transporte INT64 OPTIONS(description="Identificador de la vía de transporte utilizada (clave foránea a dim_via_transporte)"),
  id_aduana INT64 OPTIONS(description="Identificador de la administración aduanera de registro (clave foránea a dim_aduana)"),
  tipo_operacion STRING NOT NULL OPTIONS(description="Tipo de operación comercial: EXPORTACION o IMPORTACION"),
  valor_fob_usd NUMERIC OPTIONS(description="Valor FOB de la mercancía en dólares americanos (USD)"),
  valor_cif_usd NUMERIC OPTIONS(description="Valor CIF frontera de la mercancía en dólares americanos (USD, solo importaciones)"),
  valor_fob_bob NUMERIC OPTIONS(description="Valor FOB calculado en bolivianos (BOB) según tipo de cambio oficial"),
  peso_neto_kg NUMERIC OPTIONS(description="Peso neto de la mercancía en kilogramos (solo exportaciones)"),
  peso_bruto_kg NUMERIC OPTIONS(description="Peso bruto de la mercancía en kilogramos"),
  contenido_fino NUMERIC OPTIONS(description="Contenido fino en kilogramos para minerales y metales preciosos (nullable)"),
  anio INT64 NOT NULL OPTIONS(description="Año de la operación (derivado de fecha)"),
  mes INT64 NOT NULL OPTIONS(description="Mes de la operación 1-12 (derivado de fecha)"),
  trimestre INT64 NOT NULL OPTIONS(description="Trimestre de la operación 1-4 (derivado de fecha)")
)
PARTITION BY DATE_TRUNC(fecha, MONTH)
CLUSTER BY codigo_nandina, pais_iso
OPTIONS (
  description = "Tabla de hechos de comercio exterior de Bolivia particionada mensualmente y con clustering arancelario y geográfico",
  labels = [
    ("layer", "analytics"),
    ("domain", "comercio_exterior"),
    ("type", "fact"),
    ("project", "insight-bolivia")
  ]
);
