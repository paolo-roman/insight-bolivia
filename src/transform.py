"""Módulo de transformación y normalización de datos de comercio exterior.

Normaliza formatos heterogéneos de los archivos del INE Bolivia (Excel, CSV, DBF),
estandariza nombres de columnas a snake_case, formatea códigos NANDINA a 10 dígitos,
mapea códigos y nombres de país a ISO 3166-1 alpha-3, calcula columnas derivadas
(anio, mes, trimestre, fecha, valor_fob_bob), deduplica registros y prepara
DataFrames limpios para Staging y la Tabla de Hechos en BigQuery.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
from charset_normalizer import from_bytes

from src.country_iso_mapping import map_country_to_iso3

# ---------------------------------------------------------------------------
# Constantes de negocio
# ---------------------------------------------------------------------------
OFFICIAL_EXCHANGE_RATE_BOB_USD = 6.96

EXPORT_COLUMN_ALIASES: dict[str, str] = {
    "VIASAL2": "VIASAL",
    "DESVIA2": "DESVIA",
    "CUCIR3": "CUCI3",
    "GCE": "GCE3",
    "CIIU3": "CIIUR3",
}

IMPORT_COLUMN_ALIASES: dict[str, str] = {}

EXPORT_CANONICAL_COLUMNS: list[str] = [
    "ADUDES", "DESADU", "GESTION", "MES", "FLUJO",
    "NANDINA", "DESNAN", "CAP", "DESCAP", "SECC", "DESSEC",
    "PAIS", "DESPAIS", "AREA", "DESAREA", "OTROS",
    "MEDI", "DESMEDI", "VIASAL", "DESVIA",
    "DEPART", "DESDEP",
    "CUCI3", "DESCUCI3", "GCE3", "DESGCE3", "CIIUR3", "DESCIIU3",
    "CLACT", "CODACT2", "DESACT2",
    "TNT", "DESTNT", "CLTNT",
    "KILBRU", "KILNET", "FINO", "VALOR",
]

IMPORT_CANONICAL_COLUMNS: list[str] = [
    "GESTION", "MES",
    "ADUANA", "DESADU", "DEPTO", "DESDEPTO",
    "VIA", "DESVIA", "MEDIO", "DESMED",
    "PAIS", "DESPAI", "DESZON", "OTROS",
    "NANDINA", "DESNAN",
    "GCER3", "DESGCE", "CUODE", "DESCUO",
    "CIIUR3", "DESCIIU", "CUCIR3", "DESCUCI",
    "KILOS", "FRO", "FOB", "ADU", "PAG",
]

EXPORT_NUMERIC_COLUMNS: list[str] = [
    "ADUDES", "GESTION", "MES", "PAIS", "AREA", "MEDI", "VIASAL",
    "DEPART", "TNT", "KILBRU", "KILNET", "FINO", "VALOR",
]

IMPORT_NUMERIC_COLUMNS: list[str] = [
    "GESTION", "MES", "ADUANA", "DEPTO", "VIA", "MEDIO", "PAIS",
    "KILOS", "FRO", "FOB", "ADU", "PAG",
]

EXPORT_INE_TO_STAGING_MAP: dict[str, str] = {
    "GESTION": "gestion",
    "MES": "mes",
    "ADUDES": "codigo_aduana",
    "DESADU": "nombre_aduana",
    "FLUJO": "flujo_desc",
    "NANDINA": "codigo_nandina",
    "DESNAN": "descripcion_nandina",
    "CAP": "capitulo_nandina",
    "DESCAP": "descripcion_capitulo",
    "SECC": "seccion_nandina",
    "DESSEC": "descripcion_seccion",
    "PAIS": "codigo_pais_ine",
    "DESPAIS": "nombre_pais",
    "AREA": "codigo_area",
    "DESAREA": "zona_geoeconomica",
    "OTROS": "otras_zonas",
    "MEDI": "codigo_medio",
    "DESMEDI": "descripcion_medio",
    "VIASAL": "codigo_via",
    "DESVIA": "descripcion_via",
    "DEPART": "codigo_departamento",
    "DESDEP": "nombre_departamento",
    "CUCI3": "codigo_cuci",
    "DESCUCI3": "descripcion_cuci",
    "GCE3": "codigo_gce",
    "DESGCE3": "descripcion_gce",
    "CIIUR3": "codigo_ciiu",
    "DESCIIU3": "descripcion_ciiu",
    "CLACT": "clasificacion_actividad",
    "CODACT2": "codigo_actividad",
    "DESACT2": "descripcion_actividad",
    "TNT": "codigo_tnt",
    "DESTNT": "descripcion_tnt",
    "CLTNT": "clasificacion_tnt",
    "KILBRU": "peso_bruto_kg",
    "KILNET": "peso_neto_kg",
    "FINO": "contenido_fino",
    "VALOR": "valor_fob_usd",
}

IMPORT_INE_TO_STAGING_MAP: dict[str, str] = {
    "GESTION": "gestion",
    "MES": "mes",
    "ADUANA": "codigo_aduana",
    "DESADU": "nombre_aduana",
    "DEPTO": "codigo_departamento",
    "DESDEPTO": "nombre_departamento",
    "VIA": "codigo_via",
    "DESVIA": "descripcion_via",
    "MEDIO": "codigo_medio",
    "DESMED": "descripcion_medio",
    "PAIS": "codigo_pais_ine",
    "DESPAI": "nombre_pais",
    "DESZON": "zona_geoeconomica",
    "OTROS": "otras_zonas",
    "NANDINA": "codigo_nandina",
    "DESNAN": "descripcion_nandina",
    "GCER3": "codigo_gce",
    "DESGCE": "descripcion_gce",
    "CUODE": "codigo_cuode",
    "DESCUO": "descripcion_cuode",
    "CIIUR3": "codigo_ciiu",
    "DESCIIU": "descripcion_ciiu",
    "CUCIR3": "codigo_cuci",
    "DESCUCI": "descripcion_cuci",
    "KILOS": "peso_bruto_kg",
    "FRO": "valor_cif_frontera_usd",
    "FOB": "valor_fob_usd",
    "ADU": "valor_cif_frontera_bob",
    "PAG": "valor_gravamenes_bob",
}


# ---------------------------------------------------------------------------
# Lectura de formatos heterogéneos
# ---------------------------------------------------------------------------
def read_raw_file(
    file_path: str | Path,
    *,
    encoding: str | None = None,
    sheet_name: str | int | None = 0,
    **kwargs: Any,
) -> pd.DataFrame:
    """Lee archivos de datos crudos en formatos heterogéneos (Excel, CSV, DBF).

    Detecta la codificación automáticamente para archivos CSV mediante
    ``charset-normalizer`` si no se especifica un encoding.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Archivo no encontrado en la ruta: {path}")

    suffix = path.suffix.lower()

    if suffix in {".xlsx", ".xls"}:
        excel_data = pd.read_excel(path, sheet_name=sheet_name, **kwargs)
        if isinstance(excel_data, dict):
            return next(iter(excel_data.values())) if excel_data else pd.DataFrame()
        return excel_data

    if suffix == ".csv":
        if encoding is None:
            raw_bytes = path.read_bytes()
            sample = raw_bytes[: 1024 * 1024]
            detected = from_bytes(sample).best()
            encoding = detected.encoding if detected is not None else "utf-8"
        return pd.read_csv(path, encoding=encoding, **kwargs)

    if suffix == ".dbf":
        from dbfread import DBF

        dbf_table = DBF(path, encoding=encoding or "latin1", **kwargs)
        return pd.DataFrame(iter(dbf_table))

    raise ValueError(f"Extensión de archivo no soportada: {suffix}")


# ---------------------------------------------------------------------------
# Utilidades de nombres y cadenas
# ---------------------------------------------------------------------------
def to_snake_case(text: str) -> str:
    """Convierte un nombre de columna a formato snake_case limpio."""
    cleaned = re.sub(r"[^\w\s]", "", text.strip())
    subbed = re.sub(r"[\s\-]+", "_", cleaned)
    subbed = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", subbed)
    return subbed.lower().strip("_")


def normalize_column_names(
    df: pd.DataFrame,
    *,
    operation_type: str,
) -> pd.DataFrame:
    """Normaliza nombres de columnas de un DataFrame del INE resolviendo alias."""
    valid_types = {"exportaciones", "importaciones"}
    if operation_type not in valid_types:
        msg = f"operation_type debe ser uno de {valid_types}, recibido: {operation_type!r}"
        raise ValueError(msg)

    aliases = EXPORT_COLUMN_ALIASES if operation_type == "exportaciones" else IMPORT_COLUMN_ALIASES
    df = df.rename(columns=lambda c: c.strip() if isinstance(c, str) else c)
    rename_map = {old: new for old, new in aliases.items() if old in df.columns}
    if rename_map:
        df = df.rename(columns=rename_map)
    return df


def format_nandina(series: pd.Series) -> pd.Series:
    """Formatea códigos NANDINA a 10 dígitos de texto con ceros a la izquierda."""
    return (
        series.astype(str)
        .str.strip()
        .str.replace(r"\.0$", "", regex=True)
        .str.zfill(10)
    )


def parse_flujo(series: pd.Series) -> pd.DataFrame:
    """Extrae código numérico y descripción del campo FLUJO de exportaciones."""
    cleaned = series.astype(str).str.strip()
    parts = cleaned.str.split(" ", n=1, expand=True)
    if parts.shape[1] < 2:
        parts[1] = parts[0]
    parts.columns = ["flujo_codigo", "flujo_descripcion"]
    parts["flujo_codigo"] = pd.to_numeric(parts["flujo_codigo"], errors="coerce")
    return parts


def cast_numeric_columns(
    df: pd.DataFrame,
    columns: list[str],
) -> pd.DataFrame:
    """Convierte columnas específicas a tipo numérico float64."""
    df = df.copy()
    for col in columns:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def compute_null_report(df: pd.DataFrame) -> pd.DataFrame:
    """Genera un reporte del porcentaje de nulos por columna."""
    total = len(df)
    nulls = df.isnull().sum()
    report = pd.DataFrame({
        "columna": nulls.index,
        "nulos": nulls.values,
        "total": total,
        "porcentaje_nulos": (nulls.values / total * 100).round(2) if total > 0 else 0.0,
    })
    return report.sort_values("porcentaje_nulos", ascending=False).reset_index(drop=True)


def compare_headers_across_files(
    headers_by_file: dict[str, list[str]],
) -> dict[str, Any]:
    """Compara encabezados entre múltiples archivos para detectar variaciones."""
    if not headers_by_file:
        return {"all_consistent": True, "common_columns": [], "variations": {}, "reference_file": ""}

    files = list(headers_by_file.keys())
    ref_file = files[0]
    ref_set = set(headers_by_file[ref_file])
    all_sets = [set(h) for h in headers_by_file.values()]
    common = set.intersection(*all_sets) if all_sets else set()

    variations: dict[str, dict[str, list[str]]] = {}
    all_consistent = True

    for fname, headers in headers_by_file.items():
        current_set = set(headers)
        new_cols = sorted(current_set - ref_set)
        missing_cols = sorted(ref_set - current_set)
        if new_cols or missing_cols:
            all_consistent = False
            variations[fname] = {
                "columnas_nuevas": new_cols,
                "columnas_faltantes": missing_cols,
            }

    return {
        "all_consistent": all_consistent,
        "common_columns": sorted(common),
        "variations": variations,
        "reference_file": ref_file,
    }


# ---------------------------------------------------------------------------
# Transformaciones de negocio y derivadas
# ---------------------------------------------------------------------------
def derive_temporal_columns(
    df: pd.DataFrame,
    *,
    year_col: str = "gestion",
    month_col: str = "mes",
    date_col: str = "fecha",
) -> pd.DataFrame:
    """Calcula columnas temporales derivadas: anio, mes, trimestre y fecha YYYY-MM-01."""
    df = df.copy()

    # Si existe fecha pero no gestion/mes
    if date_col in df.columns and (year_col not in df.columns or month_col not in df.columns):
        dates_s = pd.Series(pd.to_datetime(df[date_col], errors="coerce"), index=df.index)
        df["anio"] = dates_s.dt.year.fillna(2000).astype("int64")
        df["mes"] = dates_s.dt.month.fillna(1).astype("int64")
    else:
        year_raw = df[year_col] if year_col in df.columns else 2000
        month_raw = df[month_col] if month_col in df.columns else 1
        year_s = pd.to_numeric(year_raw, errors="coerce")
        month_s = pd.to_numeric(month_raw, errors="coerce")
        df["anio"] = pd.Series(year_s, index=df.index).fillna(2000).astype("int64")
        df["mes"] = pd.Series(month_s, index=df.index).fillna(1).astype("int64")

    df["trimestre"] = ((df["mes"] - 1) // 3 + 1).astype("int64")

    # Formatear fecha representativa YYYY-MM-01
    formatted_dates = (
        df["anio"].astype(str)
        + "-"
        + df["mes"].astype(str).str.zfill(2)
        + "-01"
    )
    df["fecha"] = pd.Series(pd.to_datetime(formatted_dates), index=df.index).dt.date
    return df


def convert_fob_bob(
    valor_fob_usd: float | int | pd.Series | None,
    tc: float = OFFICIAL_EXCHANGE_RATE_BOB_USD,
) -> Any:
    """Convierte valor FOB en USD a Bolivianos (BOB) con el tipo de cambio oficial."""
    if isinstance(valor_fob_usd, pd.Series):
        numeric_series = pd.to_numeric(valor_fob_usd, errors="coerce")
        filled = pd.Series(numeric_series, index=valor_fob_usd.index).fillna(0.0)
        return (filled * tc).round(2)
    if valor_fob_usd is None:
        return 0.0
    val = float(valor_fob_usd)
    return round(val * tc, 2)


def deduplicate_records(
    df: pd.DataFrame,
    subset: list[str] | None = None,
) -> pd.DataFrame:
    """Deduplica registros en un DataFrame preservando la primera aparición."""
    return df.drop_duplicates(subset=subset, keep="first").reset_index(drop=True)


# ---------------------------------------------------------------------------
# Pipelines de limpieza canónicos
# ---------------------------------------------------------------------------
def clean_export_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Pipeline de limpieza básico para DataFrame de exportaciones."""
    df = normalize_column_names(df, operation_type="exportaciones")
    if "NANDINA" in df.columns:
        df["NANDINA"] = format_nandina(df["NANDINA"])
    df = cast_numeric_columns(df, EXPORT_NUMERIC_COLUMNS)
    text_cols = df.select_dtypes(include=["object", "string"]).columns
    for col in text_cols:
        df[col] = df[col].astype(str).str.strip()
    return df


def clean_import_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Pipeline de limpieza básico para DataFrame de importaciones."""
    df = normalize_column_names(df, operation_type="importaciones")
    if "NANDINA" in df.columns:
        df["NANDINA"] = format_nandina(df["NANDINA"])
    df = cast_numeric_columns(df, IMPORT_NUMERIC_COLUMNS)
    text_cols = df.select_dtypes(include=["object", "string"]).columns
    for col in text_cols:
        df[col] = df[col].astype(str).str.strip()
    return df


# ---------------------------------------------------------------------------
# Transformación integral a Staging y Modelo Estrella (Fact)
# ---------------------------------------------------------------------------
def transform_to_staging(
    df: pd.DataFrame,
    *,
    operation_type: str,
    filename: str = "",
    file_hash: str = "",
) -> pd.DataFrame:
    """Transforma un DataFrame crudo al esquema normalizado de Staging."""
    op_lower = operation_type.lower()
    is_exp = "exp" in op_lower
    op_canonical = "EXPORTACION" if is_exp else "IMPORTACION"

    # 1. Normalizar alias INE si vienen con columnas originales
    df_clean = normalize_column_names(df, operation_type="exportaciones" if is_exp else "importaciones")
    col_map = EXPORT_INE_TO_STAGING_MAP if is_exp else IMPORT_INE_TO_STAGING_MAP
    df_clean = df_clean.rename(columns={k: v for k, v in col_map.items() if k in df_clean.columns})

    # Si las columnas ya vienen en snake_case o parciales
    df_clean = df_clean.rename(columns=lambda c: to_snake_case(c))

    # 2. Parsing de FLUJO si existe
    flujo_col = "flujo" if "flujo" in df_clean.columns else ("flujo_desc" if "flujo_desc" in df_clean.columns else None)
    if flujo_col and "flujo_codigo" not in df_clean.columns:
        parsed_flujo = parse_flujo(df_clean[flujo_col])
        df_clean["flujo_codigo"] = parsed_flujo["flujo_codigo"]
        df_clean["flujo_desc"] = parsed_flujo["flujo_descripcion"]

    # 3. Formateo de NANDINA y jerarquías
    if "codigo_nandina" in df_clean.columns:
        df_clean["codigo_nandina"] = format_nandina(df_clean["codigo_nandina"])
        if "capitulo_nandina" not in df_clean.columns:
            df_clean["capitulo_nandina"] = df_clean["codigo_nandina"].str[:2]

    # 4. Columnas temporales
    df_clean = derive_temporal_columns(df_clean)

    # 5. Tipo de operación y metadatos de auditoría
    df_clean["tipo_operacion"] = op_canonical
    df_clean["nombre_archivo_origen"] = filename
    df_clean["hash_sha256"] = file_hash
    df_clean["fecha_ingesta"] = datetime.now(UTC)

    # 6. Deduplicación
    df_clean = deduplicate_records(df_clean)
    return df_clean


def transform_to_fact(
    df: pd.DataFrame,
    *,
    operation_type: str,
) -> pd.DataFrame:
    """Transforma un DataFrame al esquema analítico de la Tabla de Hechos."""
    op_lower = operation_type.lower()
    is_exp = "exp" in op_lower
    op_canonical = "EXPORTACION" if is_exp else "IMPORTACION"

    # Preparar base Staging
    stg = transform_to_staging(df, operation_type=operation_type)
    fact = pd.DataFrame()

    fact["id_transaccion"] = range(1, len(stg) + 1)
    fact["fecha"] = stg["fecha"]
    fact["codigo_nandina"] = format_nandina(stg.get("codigo_nandina", pd.Series([""] * len(stg))))

    # Mapeo de país a ISO 3166-1 alpha-3
    if "codigo_pais_ine" in stg.columns and stg["codigo_pais_ine"].notna().any():
        fact["pais_iso"] = stg["codigo_pais_ine"].apply(map_country_to_iso3)
    elif "pais_iso" in stg.columns and stg["pais_iso"].notna().any():
        fact["pais_iso"] = stg["pais_iso"].apply(map_country_to_iso3)
    elif "nombre_pais" in stg.columns and stg["nombre_pais"].notna().any():
        fact["pais_iso"] = stg["nombre_pais"].apply(map_country_to_iso3)
    else:
        fact["pais_iso"] = pd.Series(["ZZZ"] * len(stg))

    fact["id_departamento"] = pd.to_numeric(stg.get("codigo_departamento", stg.get("id_departamento")), errors="coerce")
    fact["id_via_transporte"] = pd.to_numeric(stg.get("codigo_via", stg.get("id_via_transporte")), errors="coerce")
    fact["id_aduana"] = pd.to_numeric(stg.get("codigo_aduana", stg.get("id_aduana")), errors="coerce")
    fact["tipo_operacion"] = op_canonical

    # Métricas monetarias y físicas
    val_fob = pd.to_numeric(stg.get("valor_fob_usd", 0.0), errors="coerce")
    fact["valor_fob_usd"] = pd.Series(val_fob, index=stg.index).fillna(0.0)
    fact["valor_cif_usd"] = pd.to_numeric(stg.get("valor_cif_frontera_usd", stg.get("valor_cif_usd")), errors="coerce")
    fact["valor_fob_bob"] = convert_fob_bob(fact["valor_fob_usd"])
    fact["peso_neto_kg"] = pd.to_numeric(stg.get("peso_neto_kg"), errors="coerce")
    fact["peso_bruto_kg"] = pd.to_numeric(stg.get("peso_bruto_kg"), errors="coerce")
    fact["contenido_fino"] = pd.to_numeric(stg.get("contenido_fino"), errors="coerce")

    # Columnas de partición y tiempo
    fact["anio"] = stg["anio"]
    fact["mes"] = stg["mes"]
    fact["trimestre"] = stg["trimestre"]

    return fact
