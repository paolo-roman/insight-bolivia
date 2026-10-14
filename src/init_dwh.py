"""Módulo de Aprovisionamiento Automatizado del Data Warehouse en Google BigQuery.

Orquesta la creación secuencial e idempotente de:
1. Datasets principales: `staging`, `comercio_exterior`, `benchmark_regional`, `operations`.
2. Tablas particionadas y clusterizadas según DDLs en `sql/ddl/`.
3. Vistas analíticas pre-agregadas según `sql/views/`.
4. Siembra de dimensiones estáticas (`dim_tiempo`, `dim_departamento_origen_destino`,
   `dim_via_transporte`, `dim_moneda`, `dim_pais`).

Uso:
    uv run python -m src.init_dwh [--dry-run] [--project-id P] [--skip-dimensions]
"""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from google.cloud import bigquery

from src.config import get_settings
from src.country_iso_mapping import INE_CODE_TO_ISO3, NAME_TO_ISO3
from src.load import get_bigquery_client

if TYPE_CHECKING:
    from collections.abc import Sequence

logger = logging.getLogger("insight_bolivia.init_dwh")

# Rutas estándar de DDLs
DDL_DIR = Path(__file__).resolve().parent.parent / "sql" / "ddl"
VIEWS_DIR = Path(__file__).resolve().parent.parent / "sql" / "views"

TABLE_DDL_FILES: tuple[str, ...] = (
    "create_stg_comercio_exterior.sql",
    "create_dim_tiempo.sql",
    "create_dim_producto.sql",
    "create_dim_pais.sql",
    "create_dim_departamento.sql",
    "create_dim_via_transporte.sql",
    "create_dim_aduana.sql",
    "create_dim_moneda.sql",
    "create_fact_comercio_exterior.sql",
    "create_fact_indicadores_bm.sql",
    "create_etl_control_log.sql",
    "create_ui_analytics_aggregated.sql",
)

VIEW_FILES: tuple[str, ...] = (
    "vw_balanza_comercial_mensual.sql",
    "vw_socios_comerciales.sql",
    "vw_top_productos_exportados.sql",
)


@dataclass(frozen=True)
class DatasetMetadata:
    """Metadatos formales de un dataset de BigQuery."""

    id: str
    desc: str
    table_exp_days: int | None
    labels: dict[str, str]


@dataclass
class ProvisioningReport:
    """Reporte estructurado del aprovisionamiento del DWH."""

    project_id: str
    datasets_created: list[str] = field(default_factory=list)
    tables_created: list[str] = field(default_factory=list)
    views_created: list[str] = field(default_factory=list)
    dimensions_seeded: dict[str, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    dry_run: bool = False

    @property
    def is_success(self) -> bool:
        """Indica si el aprovisionamiento concluyó sin errores."""
        return len(self.errors) == 0


def create_datasets(
    client: bigquery.Client | None,
    project_id: str,
    location: str = "US",
    dry_run: bool = False,
) -> list[str]:
    """Crea los 4 datasets estándar en BigQuery con sus políticas de expiración."""
    datasets_meta: list[DatasetMetadata] = [
        DatasetMetadata(
            id="staging",
            desc="Zona de aterrizaje temporal para ingesta cruda de datos (retención 180 días)",
            table_exp_days=180,
            labels={"environment": "production", "layer": "staging", "project": project_id},
        ),
        DatasetMetadata(
            id="comercio_exterior",
            desc="Datamart principal de Comercio Exterior de Bolivia (modelo estrella)",
            table_exp_days=None,
            labels={"environment": "production", "layer": "analytics", "domain": "comercio_exterior"},
        ),
        DatasetMetadata(
            id="benchmark_regional",
            desc="Indicadores macroeconómicos y comerciales internacionales (Banco Mundial)",
            table_exp_days=None,
            labels={"environment": "production", "layer": "analytics", "domain": "benchmark_regional"},
        ),
        DatasetMetadata(
            id="operations",
            desc="Logs de auditoría y control de ejecución ETL, telemetría y métricas operacionales",
            table_exp_days=None,
            labels={"environment": "production", "layer": "operations", "project": project_id},
        ),
    ]

    created: list[str] = []
    for meta in datasets_meta:
        if dry_run:
            logger.info("[DRY RUN] Se crearía dataset: %s.%s", project_id, meta.id)
            created.append(meta.id)
            continue

        if client is None:
            raise RuntimeError("Cliente de BigQuery no provisto para ejecución real.")

        dataset_ref = bigquery.DatasetReference(project_id, meta.id)
        ds = bigquery.Dataset(dataset_ref)
        ds.location = location
        ds.description = meta.desc
        ds.labels = meta.labels
        if meta.table_exp_days is not None:
            ms_val = meta.table_exp_days * 86400 * 1000
            ds.default_table_expiration_ms = ms_val
            ds.default_partition_expiration_ms = ms_val

        try:
            client.create_dataset(ds, exists_ok=True)
            logger.info("Dataset asegurado: %s.%s", project_id, meta.id)
            created.append(meta.id)
        except Exception as exc:
            logger.error("Error al crear dataset %s: %s", meta.id, exc)
            raise
    return created


def execute_sql_file(
    client: bigquery.Client | None,
    file_path: Path,
    project_id: str,
    dry_run: bool = False,
) -> None:
    """Ejecuta un script SQL sustituyendo el project_id por el configurado."""
    if not file_path.is_file():
        raise FileNotFoundError(f"Archivo SQL no encontrado: {file_path}")

    sql_text = file_path.read_text(encoding="utf-8")
    sql_text = sql_text.replace("`insight-bolivia.", f"`{project_id}.")
    sql_text = sql_text.replace("insight-bolivia:", f"{project_id}:")

    if dry_run:
        logger.info("[DRY RUN] Se ejecutaría: %s", file_path.name)
        return

    if client is None:
        raise RuntimeError("Cliente de BigQuery no provisto para ejecución real.")

    job = client.query(sql_text)
    job.result()
    logger.info("Ejecutado con éxito: %s", file_path.name)


def seed_dim_tiempo(client: bigquery.Client | None, project_id: str, dry_run: bool = False) -> int:
    """Siembra fechas mensuales 2000-2030 en `dim_tiempo`."""
    table_ref = f"`{project_id}.comercio_exterior.dim_tiempo`"
    sql = f"""
    MERGE {table_ref} T
    USING (
        SELECT
            d AS fecha,
            EXTRACT(YEAR FROM d) AS anio,
            EXTRACT(MONTH FROM d) AS mes,
            EXTRACT(QUARTER FROM d) AS trimestre,
            IF(EXTRACT(MONTH FROM d) <= 6, 1, 2) AS semestre,
            CASE EXTRACT(MONTH FROM d)
                WHEN 1 THEN 'Enero' WHEN 2 THEN 'Febrero' WHEN 3 THEN 'Marzo'
                WHEN 4 THEN 'Abril' WHEN 5 THEN 'Mayo' WHEN 6 THEN 'Junio'
                WHEN 7 THEN 'Julio' WHEN 8 THEN 'Agosto' WHEN 9 THEN 'Septiembre'
                WHEN 10 THEN 'Octubre' WHEN 11 THEN 'Noviembre' WHEN 12 THEN 'Diciembre'
            END AS nombre_mes,
            (EXTRACT(MONTH FROM d) = 12) AS es_fin_de_anio
        FROM UNNEST(GENERATE_DATE_ARRAY('2000-01-01', '2030-12-01', INTERVAL 1 MONTH)) AS d
    ) S
    ON T.fecha = S.fecha
    WHEN NOT MATCHED THEN
        INSERT (fecha, anio, mes, trimestre, semestre, nombre_mes, es_fin_de_anio)
        VALUES (S.fecha, S.anio, S.mes, S.trimestre, S.semestre, S.nombre_mes, S.es_fin_de_anio);
    """  # noqa: S608
    if dry_run:
        return 372

    if client is None:
        raise RuntimeError("Cliente de BigQuery no provisto.")

    job = client.query(sql)
    job.result()
    return 372


def seed_dim_departamentos(client: bigquery.Client | None, project_id: str, dry_run: bool = False) -> int:
    """Siembra los 9 departamentos de Bolivia en `dim_departamento_origen_destino`."""
    table_ref = f"`{project_id}.comercio_exterior.dim_departamento_origen_destino`"
    sql = f"""
    MERGE {table_ref} T
    USING (
        SELECT 1 AS id, 'CHQ' AS cod, 'Chuquisaca' AS nom, 'Valles' AS reg UNION ALL
        SELECT 2, 'LPZ', 'La Paz', 'Altiplano' UNION ALL
        SELECT 3, 'CBBA', 'Cochabamba', 'Valles' UNION ALL
        SELECT 4, 'ORU', 'Oruro', 'Altiplano' UNION ALL
        SELECT 5, 'POT', 'Potosí', 'Altiplano' UNION ALL
        SELECT 6, 'TJA', 'Tarija', 'Valles' UNION ALL
        SELECT 7, 'SCZ', 'Santa Cruz', 'Llanos' UNION ALL
        SELECT 8, 'BEN', 'Beni', 'Amazonía' UNION ALL
        SELECT 9, 'PND', 'Pando', 'Amazonía'
    ) S
    ON T.id_departamento = S.id
    WHEN NOT MATCHED THEN
        INSERT (id_departamento, codigo_departamento, nombre_departamento, region_geografica)
        VALUES (S.id, S.cod, S.nom, S.reg);
    """  # noqa: S608
    if dry_run:
        return 9

    if client is None:
        raise RuntimeError("Cliente de BigQuery no provisto.")

    job = client.query(sql)
    job.result()
    return 9


def seed_dim_via_transporte(client: bigquery.Client | None, project_id: str, dry_run: bool = False) -> int:
    """Siembra vías de transporte estándar en `dim_via_transporte`."""
    table_ref = f"`{project_id}.comercio_exterior.dim_via_transporte`"
    sql = f"""
    MERGE {table_ref} T
    USING (
        SELECT 1 AS id, 1 AS cod, 'Aérea' AS descr, 'Avión' AS med UNION ALL
        SELECT 2, 2, 'Marítima', 'Barco' UNION ALL
        SELECT 3, 3, 'Terrestre', 'Camión' UNION ALL
        SELECT 4, 4, 'Ferroviaria', 'Tren' UNION ALL
        SELECT 5, 5, 'Fluvial', 'Barcaza' UNION ALL
        SELECT 6, 6, 'Ductos', 'Ducto'
    ) S
    ON T.id_via_transporte = S.id
    WHEN NOT MATCHED THEN
        INSERT (id_via_transporte, codigo_via, descripcion, medio_transporte)
        VALUES (S.id, S.cod, S.descr, S.med);
    """  # noqa: S608
    if dry_run:
        return 6

    if client is None:
        raise RuntimeError("Cliente de BigQuery no provisto.")

    job = client.query(sql)
    job.result()
    return 6


def seed_dim_moneda(client: bigquery.Client | None, project_id: str, dry_run: bool = False) -> int:
    """Siembra monedas oficiales en `dim_moneda`."""
    table_ref = f"`{project_id}.comercio_exterior.dim_moneda`"
    sql = f"""
    MERGE {table_ref} T
    USING (
        SELECT 'BOB' AS cod, 'Boliviano' AS nom, 6.96 AS tc, DATE('2011-11-01') AS f,
               DATE('2011-11-01') AS vd, CAST(NULL AS DATE) AS vh, TRUE AS vig UNION ALL
        SELECT 'USD', 'Dólar Americano', 1.00, DATE('2000-01-01'),
               DATE('2000-01-01'), CAST(NULL AS DATE), TRUE UNION ALL
        SELECT 'EUR', 'Euro', 1.08, DATE('2024-01-01'),
               DATE('2024-01-01'), CAST(NULL AS DATE), TRUE
    ) S
    ON T.codigo_moneda = S.cod AND T.es_vigente = TRUE
    WHEN NOT MATCHED THEN
        INSERT (
            codigo_moneda, nombre_moneda, tipo_cambio_a_usd, fecha_tipo_cambio,
            vigente_desde, vigente_hasta, es_vigente
        )
        VALUES (S.cod, S.nom, S.tc, S.f, S.vd, S.vh, S.vig);
    """  # noqa: S608
    if dry_run:
        return 3

    if client is None:
        raise RuntimeError("Cliente de BigQuery no provisto.")

    job = client.query(sql)
    job.result()
    return 3


def seed_dim_pais(client: bigquery.Client | None, project_id: str, dry_run: bool = False) -> int:
    """Siembra los países estándar con mapeo ISO en `dim_pais`."""
    # Invertir INE_CODE_TO_ISO3 para obtener código INE por ISO
    iso_to_ine: dict[str, int] = {}
    for code, iso in INE_CODE_TO_ISO3.items():
        if iso not in iso_to_ine:
            iso_to_ine[iso] = code

    # Construir nombres estándar desde NAME_TO_ISO3
    iso_to_name: dict[str, str] = {}
    for name, iso in NAME_TO_ISO3.items():
        if iso not in iso_to_name:
            iso_to_name[iso] = name.capitalize()

    # Bloques y continentes de socios principales
    continents: dict[str, tuple[str, str, str]] = {
        "BRA": ("América", "América del Sur", "MERCOSUR"),
        "ARG": ("América", "América del Sur", "MERCOSUR"),
        "PER": ("América", "América del Sur", "CAN"),
        "COL": ("América", "América del Sur", "CAN"),
        "CHL": ("América", "América del Sur", "ALADI"),
        "USA": ("América", "América del Norte", "USMCA"),
        "CHN": ("Asia", "Asia Oriental", "APEC"),
        "JPN": ("Asia", "Asia Oriental", "APEC"),
        "DEU": ("Europa", "Europa Occidental", "UE"),
        "ESP": ("Europa", "Europa Occidental", "UE"),
        "BOL": ("América", "América del Sur", "CAN"),
    }

    rows: list[dict[str, Any]] = []
    seen_isos: set[str] = set()

    for iso in sorted(set(INE_CODE_TO_ISO3.values())):
        if iso in seen_isos:
            continue
        seen_isos.add(iso)
        cont, subreg, bloque = continents.get(iso, ("Otro", "Otro", "General"))
        nombre_es = iso_to_name.get(iso, iso)
        rows.append({
            "pais_iso": iso,
            "codigo_pais_ine": iso_to_ine.get(iso),
            "nombre_pais_es": nombre_es,
            "nombre_pais_en": nombre_es,
            "continente": cont,
            "subregion": subreg,
            "bloque_comercial": bloque,
        })

    if dry_run:
        return len(rows)

    if client is None:
        raise RuntimeError("Cliente de BigQuery no provisto.")

    table = client.get_table(f"{project_id}.comercio_exterior.dim_pais")
    batch_size = 100
    for i in range(0, len(rows), batch_size):
        chunk = rows[i : i + batch_size]
        errors = client.insert_rows_json(table, chunk)
        if errors:
            logger.warning("Errores insertando lote de dim_pais: %s", errors)
    return len(rows)


def provision_dwh(
    project_id: str | None = None,
    location: str = "US",
    client: bigquery.Client | None = None,
    dry_run: bool = False,
    skip_dimensions: bool = False,
) -> ProvisioningReport:
    """Ejecuta el ciclo de aprovisionamiento integral del Data Warehouse."""
    settings = get_settings()
    proj = project_id or settings.bigquery.project_id
    loc = location or settings.bigquery.location
    bq = client or (None if dry_run else get_bigquery_client(project=proj, location=loc))

    report = ProvisioningReport(project_id=proj, dry_run=dry_run)

    # 1. Crear Datasets
    logger.info("=== Paso 1/4: Creando Datasets en BigQuery ===")
    try:
        report.datasets_created = create_datasets(bq, proj, location=loc, dry_run=dry_run)
    except Exception as exc:
        report.errors.append(f"Fallo en creación de datasets: {exc}")
        return report

    # 2. Crear Tablas DDL
    logger.info("=== Paso 2/4: Creando Tablas del Modelo en Estrella ===")
    for ddl_name in TABLE_DDL_FILES:
        ddl_path = DDL_DIR / ddl_name
        try:
            execute_sql_file(bq, ddl_path, proj, dry_run=dry_run)
            report.tables_created.append(ddl_name)
        except Exception as exc:
            msg = f"Fallo al ejecutar {ddl_name}: {exc}"
            logger.error(msg)
            report.errors.append(msg)

    # 3. Crear Vistas Analíticas
    logger.info("=== Paso 3/4: Creando Vistas Analíticas Pre-agregadas ===")
    for view_name in VIEW_FILES:
        view_path = VIEWS_DIR / view_name
        try:
            execute_sql_file(bq, view_path, proj, dry_run=dry_run)
            report.views_created.append(view_name)
        except Exception as exc:
            msg = f"Fallo al crear vista {view_name}: {exc}"
            logger.error(msg)
            report.errors.append(msg)

    # 4. Sembrar Dimensiones Estáticas
    if not skip_dimensions and report.is_success:
        logger.info("=== Paso 4/4: Sembrando Dimensiones Estáticas ===")
        try:
            cnt_tiempo = seed_dim_tiempo(bq, proj, dry_run=dry_run)
            report.dimensions_seeded["dim_tiempo"] = cnt_tiempo

            cnt_depto = seed_dim_departamentos(bq, proj, dry_run=dry_run)
            report.dimensions_seeded["dim_departamento"] = cnt_depto

            cnt_via = seed_dim_via_transporte(bq, proj, dry_run=dry_run)
            report.dimensions_seeded["dim_via_transporte"] = cnt_via

            cnt_moneda = seed_dim_moneda(bq, proj, dry_run=dry_run)
            report.dimensions_seeded["dim_moneda"] = cnt_moneda

            cnt_pais = seed_dim_pais(bq, proj, dry_run=dry_run)
            report.dimensions_seeded["dim_pais"] = cnt_pais
        except Exception as exc:
            msg = f"Fallo sembrando dimensiones: {exc}"
            logger.error(msg)
            report.errors.append(msg)

    return report


def main(argv: Sequence[str] | None = None) -> int:
    """Punto de entrada de línea de comandos para aprovisionamiento."""
    parser = argparse.ArgumentParser(
        description="Aprovisionamiento e inicialización del DWH en Google BigQuery para InsightBolivia."
    )
    parser.add_argument("--dry-run", action="store_true", help="Simula las acciones sin modificar BigQuery.")
    parser.add_argument("--project-id", type=str, default=None, help="ID del proyecto GCP (override).")
    parser.add_argument("--skip-dimensions", action="store_true", help="Omite la siembra de dimensiones estáticas.")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    logger.info("Iniciando aprovisionamiento de BigQuery para InsightBolivia...")
    report = provision_dwh(
        project_id=args.project_id,
        dry_run=args.dry_run,
        skip_dimensions=args.skip_dimensions,
    )

    print("\n" + "=" * 60)
    print("REPORTE DE APROVISIONAMIENTO BIGQUERY")
    print("=" * 60)
    print(f"Proyecto:           {report.project_id}")
    print(f"Modo Dry-Run:       {report.dry_run}")
    print(f"Datasets Creados:   {len(report.datasets_created)} ({', '.join(report.datasets_created)})")
    print(f"Tablas Creadas:     {len(report.tables_created)}")
    print(f"Vistas Creadas:     {len(report.views_created)}")
    print(f"Dimensiones Sembradas: {report.dimensions_seeded}")
    if report.errors:
        print(f"ERRORES ({len(report.errors)}):")
        for err in report.errors:
            print(f"  [ERROR] {err}")
        return 1

    print("Estado:             [OK] COMPLETADO CON EXITO")
    print("=" * 60 + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
