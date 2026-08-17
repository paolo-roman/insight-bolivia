-- ==============================================================================
-- InsightBolivia — Vista: Balanza Comercial Mensual
-- ==============================================================================
-- Proyecto GCP: insight-bolivia
-- Dataset: comercio_exterior
-- Vista: vw_balanza_comercial_mensual
-- Épica: EPIC 03 - Data Warehouse Analítico en BigQuery (OLAP)
-- Ticket: TICK-EP3-003
--
-- Descripción:
-- Agregado analítico mensual del comercio exterior boliviano.
-- Calcula el total de Exportaciones (FOB), Importaciones (CIF) y el Saldo de
-- Balanza Comercial mensual, optimizada para consumo directo desde Streamlit.
-- Aprovecha el particionamiento mensual de fact_comercio_exterior y dim_tiempo.
-- ==============================================================================

CREATE OR REPLACE VIEW `insight-bolivia.comercio_exterior.vw_balanza_comercial_mensual`
OPTIONS (
  description = "Vista analítica pre-agregada de balanza comercial mensual (Exportaciones FOB vs Importaciones CIF y Saldo comercial)"
) AS
SELECT
    t.anio,
    t.mes,
    t.nombre_mes,
    t.trimestre,
    t.semestre,
    f.fecha,
    SUM(CASE WHEN f.tipo_operacion = 'EXPORTACION' THEN f.valor_fob_usd ELSE 0 END) AS total_exportaciones_usd,
    SUM(CASE WHEN f.tipo_operacion = 'IMPORTACION' THEN f.valor_cif_usd ELSE 0 END) AS total_importaciones_usd,
    SUM(CASE WHEN f.tipo_operacion = 'EXPORTACION' THEN f.valor_fob_usd ELSE 0 END)
    - SUM(CASE WHEN f.tipo_operacion = 'IMPORTACION' THEN f.valor_cif_usd ELSE 0 END) AS saldo_balanza_usd,
    SUM(CASE WHEN f.tipo_operacion = 'EXPORTACION' THEN f.peso_neto_kg ELSE 0 END) AS total_peso_neto_exportaciones_kg,
    SUM(CASE WHEN f.tipo_operacion = 'IMPORTACION' THEN f.peso_bruto_kg ELSE 0 END) AS total_peso_bruto_importaciones_kg,
    COUNT(CASE WHEN f.tipo_operacion = 'EXPORTACION' THEN 1 END) AS num_transacciones_exportacion,
    COUNT(CASE WHEN f.tipo_operacion = 'IMPORTACION' THEN 1 END) AS num_transacciones_importacion
FROM `insight-bolivia.comercio_exterior.fact_comercio_exterior` f
JOIN `insight-bolivia.comercio_exterior.dim_tiempo` t ON f.fecha = t.fecha
GROUP BY
    t.anio,
    t.mes,
    t.nombre_mes,
    t.trimestre,
    t.semestre,
    f.fecha;
