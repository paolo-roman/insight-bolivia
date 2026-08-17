-- ==============================================================================
-- InsightBolivia — Vista: Principales Socios Comerciales
-- ==============================================================================
-- Proyecto GCP: insight-bolivia
-- Dataset: comercio_exterior
-- Vista: vw_socios_comerciales
-- Épica: EPIC 03 - Data Warehouse Analítico en BigQuery (OLAP)
-- Ticket: TICK-EP3-003
--
-- Descripción:
-- Agregado analítico de intercambio comercial por país, continente y bloque
-- comercial para exportaciones e importaciones de Bolivia.
-- Diseñada para alimentar mapas coropléticos (Choropleth con Plotly) y tablas de comercio exterior.
-- ==============================================================================

CREATE OR REPLACE VIEW `insight-bolivia.comercio_exterior.vw_socios_comerciales`
OPTIONS (
  description = "Vista analítica de volumen de comercio exterior por socio comercial, continente y bloque de integración"
) AS
SELECT
    t.anio,
    f.tipo_operacion,
    pa.pais_iso,
    pa.codigo_pais_ine,
    pa.nombre_pais_es,
    pa.nombre_pais_en,
    pa.continente,
    pa.subregion,
    pa.bloque_comercial,
    SUM(CASE WHEN f.tipo_operacion = 'EXPORTACION' THEN f.valor_fob_usd ELSE f.valor_cif_usd END) AS total_valor_usd,
    SUM(f.valor_fob_usd) AS total_fob_usd,
    SUM(f.valor_cif_usd) AS total_cif_usd,
    SUM(f.peso_bruto_kg) AS total_peso_bruto_kg,
    COUNT(*) AS num_transacciones
FROM `insight-bolivia.comercio_exterior.fact_comercio_exterior` f
JOIN `insight-bolivia.comercio_exterior.dim_tiempo` t ON f.fecha = t.fecha
JOIN `insight-bolivia.comercio_exterior.dim_pais` pa ON f.pais_iso = pa.pais_iso
GROUP BY
    t.anio,
    f.tipo_operacion,
    pa.pais_iso,
    pa.codigo_pais_ine,
    pa.nombre_pais_es,
    pa.nombre_pais_en,
    pa.continente,
    pa.subregion,
    pa.bloque_comercial;
