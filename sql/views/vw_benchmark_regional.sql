-- ==============================================================================
-- InsightBolivia — Vista: Benchmark Regional de Indicadores
-- ==============================================================================
-- Proyecto GCP: insight-bolivia
-- Dataset: benchmark_regional
-- Vista: vw_benchmark_regional
-- Épica: EPIC 03 - Data Warehouse Analítico en BigQuery (OLAP)
--
-- Descripción:
-- Vista analítica pre-agregada de indicadores del Banco Mundial por país, año e
-- indicador macroeconómico para comparativas regionales en Streamlit.
-- ==============================================================================

CREATE OR REPLACE VIEW `insight-bolivia.benchmark_regional.vw_benchmark_regional`
OPTIONS (
  description = "Vista analítica pre-agregada de indicadores macroeconómicos del Banco Mundial por país, año e indicador"
) AS
SELECT
    id_indicador_bm,
    fecha,
    anio,
    pais_iso,
    pais_nombre,
    codigo_indicador,
    nombre_indicador,
    valor,
    unidad_medida,
    fuente,
    fecha_extraccion
FROM `insight-bolivia.benchmark_regional.fact_indicadores_bm`;
