"""InsightBolivia — Cliente y utilidades de acceso a Google BigQuery para Streamlit.

Proporciona funciones seguras y cacheadas mediante `@st.cache_data(ttl=3600)` para
consumir las vistas analíticas pre-agregadas del Data Warehouse y la tabla de benchmark:
- `vw_balanza_comercial_mensual`: Exportaciones FOB, Importaciones CIF y Saldo comercial.
- `vw_top_productos_exportados`: Ranking de productos arancelarios por valor FOB.
- `vw_socios_comerciales`: Volumen comercial por país de destino/origen y bloque.
- `fact_indicadores_bm`: Indicadores macroeconómicos y de comercio regional del Banco Mundial.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Sequence
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st
from google.cloud import bigquery
from google.oauth2 import service_account

logger = logging.getLogger("insight_bolivia.streamlit.bq_client")

# Nombres por defecto de proyecto y dataset
DEFAULT_PROJECT_ID = "insight-bolivia"
DEFAULT_DATASET = "comercio_exterior"
DEFAULT_LOCATION = "US"

QueryParams = Sequence[bigquery.ScalarQueryParameter | bigquery.ArrayQueryParameter]


def _get_secret_dict(key: str) -> dict[str, Any]:
    """Obtiene de forma segura una sección de diccionario desde st.secrets."""
    try:
        if hasattr(st, "secrets") and key in st.secrets:
            val = st.secrets[key]
            if isinstance(val, dict):
                return val
            if hasattr(val, "items"):
                return dict(val)
    except Exception:
        return {}
    return {}


def _get_credentials_from_secrets() -> service_account.Credentials | None:
    """Extrae credenciales de Google Service Account desde st.secrets si están disponibles."""
    try:
        sa_info = _get_secret_dict("gcp_service_account")
        if "client_email" in sa_info and "private_key" in sa_info and sa_info.get("private_key"):
            return service_account.Credentials.from_service_account_info(sa_info)
    except Exception as exc:
        logger.warning("No se pudieron cargar las credenciales desde st.secrets: %s", exc)
    return None


def get_bigquery_client(
    project: str | None = None,
    location: str | None = None,
) -> bigquery.Client:
    """Inicializa y retorna un cliente autenticado de Google BigQuery."""
    bq_secrets = _get_secret_dict("bigquery")
    sa_secrets = _get_secret_dict("gcp_service_account")

    resolved_project = (
        project
        or bq_secrets.get("project_id")
        or sa_secrets.get("project_id")
        or os.getenv("BQ_PROJECT_ID")
        or os.getenv("GCP_PROJECT_ID")
        or os.getenv("GOOGLE_CLOUD_PROJECT")
        or DEFAULT_PROJECT_ID
    )
    resolved_location = (
        location
        or bq_secrets.get("location")
        or os.getenv("BQ_LOCATION")
        or DEFAULT_LOCATION
    )

    client_kwargs: dict[str, Any] = {"location": resolved_location}
    if resolved_project:
        client_kwargs["project"] = resolved_project

    credentials = _get_credentials_from_secrets()
    if credentials is None:
        raw_key_path = os.getenv("GCP_SA_KEY_PATH") or os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        if raw_key_path and Path(raw_key_path).is_file():
            credentials = service_account.Credentials.from_service_account_file(raw_key_path)

    if credentials is not None:
        client_kwargs["credentials"] = credentials
        if not resolved_project and hasattr(credentials, "project_id") and credentials.project_id:
            client_kwargs["project"] = credentials.project_id

    return bigquery.Client(**client_kwargs)


@st.cache_data(ttl=3600, show_spinner=False)
def run_query(
    query: str,
    _params: QueryParams | None = None,
) -> pd.DataFrame:
    """Ejecuta una consulta SQL en BigQuery con `@st.cache_data(ttl=3600)`."""
    try:
        client = get_bigquery_client()
        job_config = bigquery.QueryJobConfig()
        if _params:
            job_config.query_parameters = list(_params)

        query_job = client.query(query, job_config=job_config)
        return query_job.to_dataframe()
    except Exception as exc:
        logger.error("Error al ejecutar consulta SQL en BigQuery: %s", exc)
        return pd.DataFrame()


@st.cache_data(ttl=3600, show_spinner=False)
def get_balanza_comercial(
    start_date: str | date | None = None,
    end_date: str | date | None = None,
    project_id: str | None = None,
    dataset: str | None = None,
) -> pd.DataFrame:
    """Consulta los datos de balanza comercial mensual en `vw_balanza_comercial_mensual`."""
    proj = project_id or DEFAULT_PROJECT_ID
    ds = dataset or DEFAULT_DATASET
    view_path = f"`{proj}.{ds}.vw_balanza_comercial_mensual`"

    query = f"""
    SELECT
        anio, mes, nombre_mes, trimestre, semestre, fecha,
        total_exportaciones_usd, total_importaciones_usd, saldo_balanza_usd,
        total_peso_neto_exportaciones_kg, total_peso_bruto_importaciones_kg,
        num_transacciones_exportacion, num_transacciones_importacion
    FROM {view_path}
    WHERE 1=1
    """  # noqa: S608
    params: list[bigquery.ScalarQueryParameter | bigquery.ArrayQueryParameter] = []

    if start_date is not None:
        s_date = start_date.isoformat() if isinstance(start_date, (date, datetime)) else start_date
        query += " AND fecha >= @start_date"
        params.append(bigquery.ScalarQueryParameter("start_date", "DATE", s_date))

    if end_date is not None:
        e_date = end_date.isoformat() if isinstance(end_date, (date, datetime)) else end_date
        query += " AND fecha <= @end_date"
        params.append(bigquery.ScalarQueryParameter("end_date", "DATE", e_date))

    query += " ORDER BY fecha ASC"
    return run_query(query, _params=params if params else None)


@st.cache_data(ttl=3600, show_spinner=False)
def get_top_productos(
    year: int | None = None,
    limit: int = 10,
    project_id: str | None = None,
    dataset: str | None = None,
) -> pd.DataFrame:
    """Consulta el ranking anual de productos en `vw_top_productos_exportados`."""
    proj = project_id or DEFAULT_PROJECT_ID
    ds = dataset or DEFAULT_DATASET
    view_path = f"`{proj}.{ds}.vw_top_productos_exportados`"

    query = f"""
    SELECT
        anio, ranking, codigo_nandina, descripcion_producto,
        partida_nandina, capitulo_nandina, seccion_nandina, sector_economico,
        total_fob_usd, total_peso_neto_kg, num_transacciones
    FROM {view_path}
    WHERE ranking <= @limit
    """  # noqa: S608
    params: list[bigquery.ScalarQueryParameter | bigquery.ArrayQueryParameter] = [
        bigquery.ScalarQueryParameter("limit", "INT64", limit),
    ]

    if year is not None:
        query += " AND anio = @year"
        params.append(bigquery.ScalarQueryParameter("year", "INT64", year))

    query += " ORDER BY anio DESC, ranking ASC"
    return run_query(query, _params=params)


@st.cache_data(ttl=3600, show_spinner=False)
def get_socios_comerciales(
    flow: str = "EXPORTACION",
    year: int | None = None,
    limit: int | None = None,
    project_id: str | None = None,
    dataset: str | None = None,
) -> pd.DataFrame:
    """Consulta el volumen de comercio exterior por país en `vw_socios_comerciales`."""
    proj = project_id or DEFAULT_PROJECT_ID
    ds = dataset or DEFAULT_DATASET
    view_path = f"`{proj}.{ds}.vw_socios_comerciales`"

    query = f"""
    SELECT
        anio, tipo_operacion, pais_iso, codigo_pais_ine, nombre_pais_es,
        nombre_pais_en, continente, subregion, bloque_comercial,
        total_valor_usd, total_fob_usd, total_cif_usd,
        total_peso_bruto_kg, num_transacciones
    FROM {view_path}
    WHERE tipo_operacion = @flow
    """  # noqa: S608
    params: list[bigquery.ScalarQueryParameter | bigquery.ArrayQueryParameter] = [
        bigquery.ScalarQueryParameter("flow", "STRING", flow.upper()),
    ]

    if year is not None:
        query += " AND anio = @year"
        params.append(bigquery.ScalarQueryParameter("year", "INT64", year))

    query += " ORDER BY total_valor_usd DESC"
    if limit is not None:
        query += f" LIMIT {limit}"

    return run_query(query, _params=params)


@st.cache_data(ttl=3600, show_spinner=False)
def get_available_date_range(
    project_id: str | None = None,
    dataset: str | None = None,
) -> tuple[date, date]:
    """Obtiene la fecha mínima y máxima con registros disponibles en el DWH."""
    default_min = date(2020, 1, 1)
    default_max = date.today()

    proj = project_id or DEFAULT_PROJECT_ID
    ds = dataset or DEFAULT_DATASET
    query = f"""
    SELECT MIN(fecha) AS min_date, MAX(fecha) AS max_date
    FROM `{proj}.{ds}.vw_balanza_comercial_mensual`
    """  # noqa: S608
    df = run_query(query)
    if not df.empty and pd.notna(df.iloc[0]["min_date"]) and pd.notna(df.iloc[0]["max_date"]):
        min_val = df.iloc[0]["min_date"]
        max_val = df.iloc[0]["max_date"]
        d_min = min_val if isinstance(min_val, date) else pd.to_datetime(min_val).date()
        d_max = max_val if isinstance(max_val, date) else pd.to_datetime(max_val).date()
        return d_min, d_max

    return default_min, default_max


@st.cache_data(ttl=3600, show_spinner=False)
def get_export_microdatos(
    start_date: str | date | None = None,
    end_date: str | date | None = None,
    flow: str | None = None,
    departamentos: Sequence[str] | None = None,
    sectores: Sequence[str] | None = None,
    search_term: str | None = None,
    limit: int = 50001,
    project_id: str | None = None,
    dataset: str | None = None,
) -> pd.DataFrame:
    """Consulta microdatos de comercio exterior para exportación con límite de seguridad."""
    proj = project_id or DEFAULT_PROJECT_ID
    ds = dataset or DEFAULT_DATASET
    fact_table = f"`{proj}.{ds}.fact_comercio_exterior`"
    dim_prod = f"`{proj}.{ds}.dim_producto`"
    dim_pais = f"`{proj}.{ds}.dim_pais`"
    dim_dept = f"`{proj}.{ds}.dim_departamento_origen_destino`"

    query = f"""
    SELECT
        f.fecha, f.anio, f.mes, f.tipo_operacion, f.codigo_nandina,
        COALESCE(p.descripcion_producto, 'Sin descripción') AS descripcion_producto,
        COALESCE(p.sector_economico, 'Otros Productos') AS sector_economico,
        f.pais_iso,
        COALESCE(pa.nombre_pais_es, f.pais_iso) AS pais_nombre,
        COALESCE(pa.bloque_comercial, 'Otros') AS bloque_comercial,
        COALESCE(d.nombre_departamento, 'Nacional') AS departamento,
        f.valor_fob_usd, f.valor_cif_usd, f.peso_neto_kg, f.peso_bruto_kg
    FROM {fact_table} f
    LEFT JOIN {dim_prod} p
        ON f.codigo_nandina = p.codigo_nandina AND p.es_vigente = TRUE
    LEFT JOIN {dim_pais} pa
        ON f.pais_iso = pa.pais_iso
    LEFT JOIN {dim_dept} d
        ON f.id_departamento = d.id_departamento
    WHERE 1=1
    """  # noqa: S608

    params: list[bigquery.ScalarQueryParameter | bigquery.ArrayQueryParameter] = []

    if start_date is not None:
        s_date = start_date.isoformat() if isinstance(start_date, (date, datetime)) else start_date
        query += " AND f.fecha >= @start_date"
        params.append(bigquery.ScalarQueryParameter("start_date", "DATE", s_date))

    if end_date is not None:
        e_date = end_date.isoformat() if isinstance(end_date, (date, datetime)) else end_date
        query += " AND f.fecha <= @end_date"
        params.append(bigquery.ScalarQueryParameter("end_date", "DATE", e_date))

    if flow and flow.upper() in ("EXPORTACION", "IMPORTACION"):
        query += " AND f.tipo_operacion = @flow"
        params.append(bigquery.ScalarQueryParameter("flow", "STRING", flow.upper()))

    if departamentos and len(departamentos) > 0 and len(departamentos) < 9:
        query += " AND d.nombre_departamento IN UNNEST(@departamentos)"
        params.append(bigquery.ArrayQueryParameter("departamentos", "STRING", list(departamentos)))

    if sectores and len(sectores) > 0:
        query += " AND p.sector_economico IN UNNEST(@sectores)"
        params.append(bigquery.ArrayQueryParameter("sectores", "STRING", list(sectores)))

    if search_term and search_term.strip():
        term = f"%{search_term.strip().lower()}%"
        query += " AND (LOWER(f.codigo_nandina) LIKE @search OR LOWER(p.descripcion_producto) LIKE @search)"
        params.append(bigquery.ScalarQueryParameter("search", "STRING", term))

    query += f" ORDER BY f.fecha DESC, f.valor_fob_usd DESC LIMIT {limit}"
    return run_query(query, _params=params if params else None)


@st.cache_data(ttl=3600, show_spinner=False)
def get_benchmark_indicadores(
    indicator_code: str | None = None,
    countries: Sequence[str] | None = None,
    start_year: int | None = None,
    end_year: int | None = None,
    project_id: str | None = None,
    dataset: str | None = None,
) -> pd.DataFrame:
    """Consulta indicadores macroeconómicos del Banco Mundial en `fact_indicadores_bm`."""
    proj = project_id or DEFAULT_PROJECT_ID
    ds = dataset or "benchmark_regional"
    table_path = f"`{proj}.{ds}.fact_indicadores_bm`"

    query = f"""
    SELECT
        id_indicador_bm, fecha, anio, pais_iso, pais_nombre,
        codigo_indicador, nombre_indicador, valor, unidad_medida,
        fuente, fecha_extraccion
    FROM {table_path}
    WHERE 1=1
    """  # noqa: S608
    params: list[bigquery.ScalarQueryParameter | bigquery.ArrayQueryParameter] = []

    if indicator_code:
        query += " AND codigo_indicador = @indicator_code"
        params.append(bigquery.ScalarQueryParameter("indicator_code", "STRING", indicator_code))

    if countries and len(countries) > 0:
        query += " AND pais_iso IN UNNEST(@countries)"
        params.append(bigquery.ArrayQueryParameter("countries", "STRING", [c.upper() for c in countries]))

    if start_year is not None:
        query += " AND anio >= @start_year"
        params.append(bigquery.ScalarQueryParameter("start_year", "INT64", start_year))

    if end_year is not None:
        query += " AND anio <= @end_year"
        params.append(bigquery.ScalarQueryParameter("end_year", "INT64", end_year))

    query += " ORDER BY anio ASC, pais_iso ASC"
    return run_query(query, _params=params if params else None)


