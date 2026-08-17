-- ==============================================================================
-- InsightBolivia — DDL: Dimensión Aduana
-- ==============================================================================
-- Proyecto GCP: insight-bolivia
-- Dataset: comercio_exterior
-- Tabla: dim_aduana
-- Épica: EPIC 03 - Data Warehouse Analítico en BigQuery (OLAP)
-- Ticket: TICK-EP3-002
--
-- Descripción:
-- Dimensión de recintos y administraciones aduaneras de registro del comercio
-- exterior de Bolivia (Fronteriza, Interior, Aeroportuaria, Zona Franca).
-- Incorpora soporte SCD Tipo 2 para registrar traslados, aperturas o reclasificaciones.
-- ==============================================================================

CREATE TABLE IF NOT EXISTS `insight-bolivia.comercio_exterior.dim_aduana`
(
  id_aduana INT64 NOT NULL OPTIONS(description="Identificador único (surrogate key) de la administración aduanera"),
  codigo_aduana INT64 OPTIONS(description="Código numérico de aduana asignado por el INE o Aduana Nacional (ANB)"),
  nombre_aduana STRING NOT NULL OPTIONS(description="Nombre y denominación oficial de la aduana (ej: Aeropuerto Viru-Viru, Tambo Quemado, Arica)"),
  ciudad STRING OPTIONS(description="Ciudad o localidad donde opera la administración aduanera"),
  departamento STRING OPTIONS(description="Departamento o país de ubicación del recinto aduanero (ej: Santa Cruz, Oruro, Chile)"),
  tipo STRING OPTIONS(description="Tipo de administración aduanera: Fronteriza, Interior, Aeroportuaria, Zona Franca o Agencia Exterior"),
  vigente_desde DATE NOT NULL OPTIONS(description="Fecha de inicio de vigencia de la versión del registro (SCD Tipo 2)"),
  vigente_hasta DATE OPTIONS(description="Fecha de fin de vigencia de la versión del registro (NULL si es versión actual, SCD Tipo 2)"),
  es_vigente BOOL NOT NULL OPTIONS(description="Indicador de versión actual activa (TRUE: versión vigente, FALSE: versión histórica)")
)
CLUSTER BY id_aduana
OPTIONS (
  description = "Dimensión de administraciones aduaneras con soporte SCD Tipo 2",
  labels = [
    ("layer", "analytics"),
    ("domain", "comercio_exterior"),
    ("type", "dimension"),
    ("scd", "type_2"),
    ("project", "insight-bolivia")
  ]
);
