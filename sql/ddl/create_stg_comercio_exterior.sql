-- ==============================================================================
-- InsightBolivia — DDL: Tabla de Staging de Comercio Exterior
-- ==============================================================================
-- Proyecto GCP: insight-bolivia
-- Dataset: staging
-- Tabla: stg_comercio_exterior
-- Épica: EPIC 03 - Data Warehouse Analítico en BigQuery (OLAP)
-- Ticket: TICK-EP3-002
--
-- Descripción:
-- Tabla de aterrizaje y staging temporal para la ingesta normalizada de los
-- boletines mensuales de Exportaciones (38 columnas) e Importaciones (29 columnas)
-- del Instituto Nacional de Estadística (INE) de Bolivia.
-- ==============================================================================

CREATE TABLE IF NOT EXISTS `insight-bolivia.staging.stg_comercio_exterior`
(
  gestion INT64 OPTIONS(description="Año de referencia de la operación extraído del boletín del INE"),
  mes INT64 OPTIONS(description="Mes de referencia de la operación (1-12)"),
  fecha DATE OPTIONS(description="Fecha representativa de la operación (primer día del mes YYYY-MM-01)"),
  flujo_codigo INT64 OPTIONS(description="Código de flujo de exportación (1: Exportaciones, 2: Reexportaciones, 3: Efectos personales)"),
  flujo_desc STRING OPTIONS(description="Descripción del flujo de exportación según el boletín del INE"),
  tipo_operacion STRING OPTIONS(description="Tipo de operación comercial: EXPORTACION o IMPORTACION"),
  codigo_nandina STRING OPTIONS(description="Código arancelario NANDINA de 10 dígitos (preservando ceros a la izquierda)"),
  descripcion_nandina STRING OPTIONS(description="Descripción de la mercancía según la partida NANDINA"),
  capitulo_nandina STRING OPTIONS(description="Capítulo arancelario NANDINA (primeros 2 dígitos)"),
  descripcion_capitulo STRING OPTIONS(description="Descripción del capítulo arancelario NANDINA"),
  seccion_nandina STRING OPTIONS(description="Sección arancelaria NANDINA"),
  descripcion_seccion STRING OPTIONS(description="Descripción de la sección arancelaria NANDINA"),
  codigo_pais_ine INT64 OPTIONS(description="Código numérico de país asignado por el INE"),
  nombre_pais STRING OPTIONS(description="Nombre del país de destino (exportación) u origen (importación)"),
  codigo_departamento INT64 OPTIONS(description="Código de departamento asignado por el INE"),
  nombre_departamento STRING OPTIONS(description="Nombre del departamento de origen o destino"),
  codigo_aduana INT64 OPTIONS(description="Código de aduana asignado por el INE"),
  nombre_aduana STRING OPTIONS(description="Nombre y descripción de la aduana de salida o ingreso"),
  codigo_via INT64 OPTIONS(description="Código de la vía de transporte asignado por el INE"),
  descripcion_via STRING OPTIONS(description="Descripción de la vía de transporte (Aérea, Marítima, Terrestre, etc.)"),
  codigo_medio INT64 OPTIONS(description="Código del medio de transporte asignado por el INE"),
  descripcion_medio STRING OPTIONS(description="Descripción del medio de transporte"),
  zona_geoeconomica STRING OPTIONS(description="Zona geoeconómica de destino u origen (UE, ALADI, etc.)"),
  otras_zonas STRING OPTIONS(description="Otras clasificaciones comerciales (CAN, MERCOSUR, NAFTA/TLC)"),
  codigo_cuci STRING OPTIONS(description="Código de Clasificación Uniforme para el Comercio Internacional (CUCI Rev. 3)"),
  descripcion_cuci STRING OPTIONS(description="Descripción según clasificación CUCI Rev. 3"),
  codigo_gce STRING OPTIONS(description="Código de Grandes Categorías Económicas (GCE Rev. 3)"),
  descripcion_gce STRING OPTIONS(description="Descripción según Grandes Categorías Económicas"),
  codigo_ciiu STRING OPTIONS(description="Código CIIU Rev. 3"),
  descripcion_ciiu STRING OPTIONS(description="Descripción según clasificación CIIU Rev. 3"),
  codigo_actividad STRING OPTIONS(description="Código de actividad económica (CODACT2)"),
  descripcion_actividad STRING OPTIONS(description="Descripción de la actividad económica (DESACT2)"),
  codigo_tnt INT64 OPTIONS(description="Código Tradicional / No Tradicional (TNT)"),
  descripcion_tnt STRING OPTIONS(description="Descripción de producto Tradicional o No Tradicional"),
  codigo_cuode STRING OPTIONS(description="Código CUODE (Clasificación por Uso o Destino Económico, solo importaciones)"),
  descripcion_cuode STRING OPTIONS(description="Descripción CUODE (solo importaciones)"),
  valor_fob_usd NUMERIC OPTIONS(description="Valor FOB en dólares americanos (USD)"),
  valor_cif_frontera_usd NUMERIC OPTIONS(description="Valor CIF frontera en dólares americanos (USD, solo importaciones)"),
  valor_cif_frontera_bob NUMERIC OPTIONS(description="Valor CIF frontera en bolivianos (BOB, solo importaciones)"),
  valor_gravamenes_bob NUMERIC OPTIONS(description="Gravámenes aduaneros pagados en bolivianos (BOB, solo importaciones)"),
  peso_bruto_kg NUMERIC OPTIONS(description="Peso bruto en kilogramos"),
  peso_neto_kg NUMERIC OPTIONS(description="Peso neto en kilogramos (solo exportaciones)"),
  contenido_fino NUMERIC OPTIONS(description="Contenido fino en kilogramos (minerales y metales preciosos)"),
  nombre_archivo_origen STRING OPTIONS(description="Nombre del archivo original procesado desde el portal del INE"),
  hash_sha256 STRING OPTIONS(description="Hash SHA-256 del archivo procesado para idempotencia y auditoría"),
  fecha_ingesta TIMESTAMP OPTIONS(description="Timestamp UTC de ingesta en la capa de staging")
)
PARTITION BY DATE_TRUNC(fecha, MONTH)
OPTIONS (
  description = "Tabla de staging para ingesta cruda normalizada de boletines de comercio exterior del INE (retención 180 días)",
  labels = [
    ("layer", "staging"),
    ("domain", "comercio_exterior"),
    ("project", "insight-bolivia")
  ]
);
