-- ==============================================================================
-- InsightBolivia — DDL: Dimensión Departamento (Origen y Destino)
-- ==============================================================================
-- Proyecto GCP: insight-bolivia
-- Dataset: comercio_exterior
-- Tabla: dim_departamento_origen_destino
-- Épica: EPIC 03 - Data Warehouse Analítico en BigQuery (OLAP)
-- Ticket: TICK-EP3-002
--
-- Descripción:
-- Dimensión de los 9 departamentos de Bolivia y zonas geográficas nacionales,
-- utilizada para asociar el origen territorial de exportaciones y destino de importaciones.
-- ==============================================================================

CREATE TABLE IF NOT EXISTS `insight-bolivia.comercio_exterior.dim_departamento_origen_destino`
(
  id_departamento INT64 NOT NULL OPTIONS(description="Identificador único y código numérico del departamento asignado por el INE (1 a 9)"),
  codigo_departamento STRING OPTIONS(description="Código alfanumérico o abreviatura estándar (LPZ, SCZ, CBBA, ORU, POT, CHQ, TJA, BEN, PND)"),
  nombre_departamento STRING NOT NULL OPTIONS(description="Nombre oficial del departamento de Bolivia"),
  region_geografica STRING OPTIONS(description="Región geográfica tradicional (Altiplano, Valles, Llanos/Amazonía)")
)
CLUSTER BY id_departamento
OPTIONS (
  description = "Dimensión de departamentos de Bolivia para origen y destino comercial",
  labels = [
    ("layer", "analytics"),
    ("domain", "comercio_exterior"),
    ("type", "dimension"),
    ("scd", "type_1"),
    ("project", "insight-bolivia")
  ]
);
