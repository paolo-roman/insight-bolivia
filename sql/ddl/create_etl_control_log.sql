-- ==============================================================================
-- InsightBolivia — DDL: Tabla de Control de Auditoría e Idempotencia ETL
-- ==============================================================================
-- Proyecto GCP: insight-bolivia
-- Dataset: operations
-- Tabla: etl_control_log
-- Épica: EPIC 03 - Data Warehouse Analítico en BigQuery (OLAP)
-- Ticket: TICK-EP3-003
--
-- Descripción:
-- Tabla de control y trazabilidad de ejecuciones del pipeline ETL.
-- Almacena metadatos de archivos ingeridos del INE, hashes criptográficos SHA-256
-- para garantizar idempotencia en la ingestión y diagnóstico de ejecuciones.
--
-- Estrategias de Optimización (Costo Cero / Always Free Tier):
--   - Particionamiento: Diario por la columna `timestamp_ejecucion`
--   - Clustering: Por `estado` y `nombre_archivo`
-- ==============================================================================

CREATE TABLE IF NOT EXISTS `insight-bolivia.operations.etl_control_log`
(
  id STRING NOT NULL OPTIONS(description="Identificador único del registro de ejecución ETL (UUID o identificador correlativo)"),
  nombre_archivo STRING NOT NULL OPTIONS(description="Nombre del archivo procesado o descargado del INE"),
  hash_sha256 STRING NOT NULL OPTIONS(description="Hash SHA-256 del contenido del archivo para verificación de idempotencia"),
  fecha_publicacion DATE OPTIONS(description="Fecha de publicación oficial del boletín o archivo según el INE"),
  registros_procesados INT64 OPTIONS(description="Cantidad de registros válidos procesados e insertados/actualizados"),
  timestamp_ejecucion TIMESTAMP NOT NULL OPTIONS(description="Marca temporal en UTC del inicio o fin de la ejecución del pipeline"),
  estado STRING NOT NULL OPTIONS(description="Estado de la ejecución: SUCCESS, FAILED, RUNNING, SKIPPED"),
  detalles_error STRING OPTIONS(description="Mensaje descriptivo o traza de error en caso de fallo en la ejecución")
)
PARTITION BY DATE(timestamp_ejecucion)
CLUSTER BY estado, nombre_archivo
OPTIONS (
  description = "Tabla de control de auditoría e idempotencia para las ejecuciones del pipeline ETL",
  labels = [
    ("layer", "operations"),
    ("domain", "operations"),
    ("type", "control_log"),
    ("project", "insight-bolivia")
  ]
);
