-- ==============================================================================
-- InsightBolivia — Vista: Top 10 Productos Exportados por Año
-- ==============================================================================
-- Proyecto GCP: insight-bolivia
-- Dataset: comercio_exterior
-- Vista: vw_top_productos_exportados
-- Épica: EPIC 03 - Data Warehouse Analítico en BigQuery (OLAP)
-- Ticket: TICK-EP3-003
--
-- Descripción:
-- Ranking anual de los principales 10 productos de exportación por valor FOB (USD).
-- Incluye descripción arancelaria NANDINA, sector económico y peso neto acumulado.
-- Filtra por la versión vigente de la dimensión de productos (p.es_vigente = TRUE)
-- y calcula el ranking con QUALIFY ROW_NUMBER() OVER (PARTITION BY t.anio ORDER BY SUM(f.valor_fob_usd) DESC) <= 10.
-- ==============================================================================

CREATE OR REPLACE VIEW `insight-bolivia.comercio_exterior.vw_top_productos_exportados`
OPTIONS (
  description = "Vista analítica de los 10 principales productos de exportación por año clasificados por valor FOB (USD)"
) AS
SELECT
    t.anio,
    ROW_NUMBER() OVER (PARTITION BY t.anio ORDER BY SUM(f.valor_fob_usd) DESC) AS ranking,
    p.codigo_nandina,
    p.descripcion_producto,
    p.partida_nandina,
    p.capitulo_nandina,
    p.seccion_nandina,
    p.sector_economico,
    SUM(f.valor_fob_usd) AS total_fob_usd,
    SUM(f.peso_neto_kg) AS total_peso_neto_kg,
    COUNT(*) AS num_transacciones
FROM `insight-bolivia.comercio_exterior.fact_comercio_exterior` f
JOIN `insight-bolivia.comercio_exterior.dim_tiempo` t ON f.fecha = t.fecha
JOIN `insight-bolivia.comercio_exterior.dim_producto` p ON f.codigo_nandina = p.codigo_nandina
WHERE f.tipo_operacion = 'EXPORTACION'
  AND p.es_vigente = TRUE
GROUP BY
    t.anio,
    p.codigo_nandina,
    p.descripcion_producto,
    p.partida_nandina,
    p.capitulo_nandina,
    p.seccion_nandina,
    p.sector_economico
QUALIFY ROW_NUMBER() OVER (PARTITION BY t.anio ORDER BY SUM(f.valor_fob_usd) DESC) <= 10;
