-- ==============================================================================
-- InsightBolivia — DDL: Dimensión País (Catálogo Geográfico y Comercial)
-- ==============================================================================
-- Proyecto GCP: insight-bolivia
-- Dataset: comercio_exterior
-- Tabla: dim_pais
-- Épica: EPIC 03 - Data Warehouse Analítico en BigQuery (OLAP)
-- Ticket: TICK-EP3-002
--
-- Descripción:
-- Dimensión de países de destino (exportaciones) y origen (importaciones).
-- Mapea los códigos numéricos propios del INE (RC-001/RC-002) al estándar
-- internacional ISO 3166-1 alpha-3, e incorpora jerarquías geográficas
-- (continente, subregión) y pertenencia a bloques comerciales (CAN, MERCOSUR, ALADI, UE).
-- ==============================================================================

CREATE TABLE IF NOT EXISTS `insight-bolivia.comercio_exterior.dim_pais`
(
  pais_iso STRING NOT NULL OPTIONS(description="Código internacional de país ISO 3166-1 alpha-3 (3 letras mayúsculas)"),
  codigo_pais_ine INT64 OPTIONS(description="Código numérico de país asignado por el INE de Bolivia (ej: 249: EE.UU., 23: Alemania, 63: Argentina)"),
  nombre_pais_es STRING OPTIONS(description="Nombre oficial o común del país en idioma español"),
  nombre_pais_en STRING OPTIONS(description="Nombre oficial o común del país en idioma inglés"),
  continente STRING OPTIONS(description="Continente de ubicación geográfica del país (América, Europa, Asia, África, Oceanía)"),
  subregion STRING OPTIONS(description="Subregión geográfica (ej: América del Sur, Europa Occidental, Sudeste Asiático)"),
  bloque_comercial STRING OPTIONS(description="Bloque de integración económica principal (CAN, MERCOSUR, ALADI, UE, USMCA, etc.)")
)
CLUSTER BY pais_iso
OPTIONS (
  description = "Dimensión de países con mapeo de códigos INE a ISO alpha-3 y jerarquías geoeconómicas",
  labels = [
    ("layer", "analytics"),
    ("domain", "comercio_exterior"),
    ("type", "dimension"),
    ("scd", "type_1"),
    ("project", "insight-bolivia")
  ]
);
