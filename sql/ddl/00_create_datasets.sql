-- ==============================================================================
-- InsightBolivia — Provisionamiento de Datasets en Google BigQuery (OLAP)
-- ==============================================================================
-- Proyecto GCP: insight-bolivia
-- Ubicación: US (Multi-region)
-- Épica: EPIC 03 - Data Warehouse Analítico en BigQuery
-- Ticket: TICK-EP3-001
--
-- Descripción:
-- Este script define los 4 datasets principales del Data Warehouse analítico:
--   1. staging: Zona de aterrizaje temporal (retención 180 días / 6 meses).
--   2. comercio_exterior: Datamart principal (histórico indefinido, sin expiración).
--   3. benchmark_regional: Indicadores internacionales (histórico indefinido).
--   4. operations: Logs de ejecución ETL y métricas de uso agregadas.
--
-- Además, documenta los comandos de aprovisionamiento vía CLI (`bq mk`) y
-- la configuración de Alerta de Presupuesto $0 USD en Google Cloud Billing.
-- ==============================================================================

-- ==============================================================================
-- 1. SENTENCIAS DDL ESTÁNDAR (BigQuery SQL)
-- ==============================================================================

-- 1.1 Dataset: staging
-- Zona de aterrizaje temporal para archivos crudos extraídos del INE.
-- Las tablas y particiones expiran automáticamente a los 180 días (6 meses).
CREATE SCHEMA IF NOT EXISTS `insight-bolivia.staging`
OPTIONS (
  location = 'US',
  description = 'Zona de aterrizaje temporal para ingesta cruda de datos (retención 180 días)',
  default_table_expiration_days = 180,
  default_partition_expiration_days = 180,
  labels = [
    ('environment', 'production'),
    ('layer', 'staging'),
    ('project', 'insight-bolivia')
  ]
);

-- 1.2 Dataset: comercio_exterior
-- Datamart principal con modelo estrella (Star Schema: facts, dims, views).
-- Persistencia histórica indefinida para análisis longitudinal de tendencias.
CREATE SCHEMA IF NOT EXISTS `insight-bolivia.comercio_exterior`
OPTIONS (
  location = 'US',
  description = 'Datamart principal de Comercio Exterior de Bolivia (modelo estrella, histórico indefinido)',
  labels = [
    ('environment', 'production'),
    ('layer', 'analytics'),
    ('domain', 'comercio_exterior'),
    ('project', 'insight-bolivia')
  ]
);

-- 1.3 Dataset: benchmark_regional
-- Almacén de indicadores económicos y comerciales internacionales (Banco Mundial, CEPAL).
-- Persistencia histórica indefinida sin expiración automática de tablas.
CREATE SCHEMA IF NOT EXISTS `insight-bolivia.benchmark_regional`
OPTIONS (
  location = 'US',
  description = 'Indicadores económicos y comerciales internacionales (Banco Mundial, CEPAL)',
  labels = [
    ('environment', 'production'),
    ('layer', 'analytics'),
    ('domain', 'benchmark_regional'),
    ('project', 'insight-bolivia')
  ]
);

-- 1.4 Dataset: operations
-- Logs de auditoría de ejecución ETL (etl_control_log) y telemetría agregada.
-- Persistencia indefinida para auditoría y observabilidad operativa.
CREATE SCHEMA IF NOT EXISTS `insight-bolivia.operations`
OPTIONS (
  location = 'US',
  description = 'Logs de auditoría y control de ejecución ETL, telemetría y métricas operacionales',
  labels = [
    ('environment', 'production'),
    ('layer', 'operations'),
    ('project', 'insight-bolivia')
  ]
);


-- ==============================================================================
-- 2. COMANDOS CLI ALTERNATIVOS (Google Cloud SDK / bq CLI)
-- ==============================================================================
-- Ejecutar desde terminal con permisos de BigQuery Admin o BigQuery Data Editor:
--
-- # 2.1 Crear dataset staging (180 días = 15,552,000 segundos)
-- bq --location=US mk --dataset \
--   --description="Zona de aterrizaje temporal para ingesta cruda de datos (retención 180 días)" \
--   --default_table_expiration=15552000 \
--   --default_partition_expiration=15552000 \
--   --label="environment:production" \
--   --label="layer:staging" \
--   --label="project:insight-bolivia" \
--   insight-bolivia:staging
--
-- # 2.2 Crear dataset comercio_exterior (sin expiración)
-- bq --location=US mk --dataset \
--   --description="Datamart principal de Comercio Exterior de Bolivia (modelo estrella, histórico indefinido)" \
--   --label="environment:production" \
--   --label="layer:analytics" \
--   --label="domain:comercio_exterior" \
--   --label="project:insight-bolivia" \
--   insight-bolivia:comercio_exterior
--
-- # 2.3 Crear dataset benchmark_regional (sin expiración)
-- bq --location=US mk --dataset \
--   --description="Indicadores económicos y comerciales internacionales (Banco Mundial, CEPAL)" \
--   --label="environment:production" \
--   --label="layer:analytics" \
--   --label="domain:benchmark_regional" \
--   --label="project:insight-bolivia" \
--   insight-bolivia:benchmark_regional
--
-- # 2.4 Crear dataset operations (sin expiración)
-- bq --location=US mk --dataset \
--   --description="Logs de auditoría y control de ejecución ETL, telemetría y métricas operacionales" \
--   --label="environment:production" \
--   --label="layer:operations" \
--   --label="project:insight-bolivia" \
--   insight-bolivia:operations


-- ==============================================================================
-- 3. ALERTA DE PRESUPUESTO $0 USD EN GOOGLE CLOUD BILLING
-- ==============================================================================
-- Para garantizar la operación a costo cero dentro del Always Free Tier
-- (10 GB almacenamiento BigQuery, 1 TB escaneo/mes, 1 GB Firestore, 50k reads/día),
-- se debe configurar una alerta de presupuesto en Google Cloud Billing:
--
-- Paso A: Identificar la Cuenta de Facturación (Billing Account)
--   gcloud billing accounts list
--
-- Paso B: Crear el canal de notificación por correo (si no existe)
--   gcloud monitoring channels create \
--     --display-name="Equipo InsightBolivia - Alertas de Costo" \
--     --type=email \
--     --channel-content='{"email_address": "alertas@insightbolivia.org"}' \
--     --project=insight-bolivia
--
-- Paso C: Crear la regla de presupuesto de $0 USD con alertas graduales
--   gcloud billing budgets create \
--     --billing-account=${BILLING_ACCOUNT_ID} \
--     --display-name="Alerta Presupuesto $0 USD - InsightBolivia" \
--     --budget-amount=0.01USD \
--     --filter-projects=projects/insight-bolivia \
--     --threshold-rule=percent=0.01,basis=current-spend \
--     --threshold-rule=percent=0.50,basis=current-spend \
--     --threshold-rule=percent=0.90,basis=current-spend \
--     --threshold-rule=percent=1.00,basis=current-spend \
--     --notifications-rule-monitoring-notification-channels="projects/insight-bolivia/notificationChannels/${CHANNEL_ID}"
--
-- Paso D: Verificación en GCP Console
--   1. Ir a GCP Console -> Facturación (Billing) -> Presupuestos y alertas (Budgets & alerts).
--   2. Verificar que el presupuesto "Alerta Presupuesto $0 USD - InsightBolivia" esté activo.
--   3. Confirmar que los umbrales de alerta envíen notificaciones inmediatas al detectar
--      cualquier gasto superior a $0.00 USD.
-- ==============================================================================
