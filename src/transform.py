"""Módulo de transformación de datos de comercio exterior.

Normaliza formatos heterogéneos de los archivos Excel del INE Bolivia,
estandariza nombres de columnas (que varían entre años), formatea códigos
NANDINA a 10 dígitos con ceros a la izquierda, y prepara DataFrames
limpios para análisis y carga posterior a BigQuery.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

# ---------------------------------------------------------------------------
# Mapeo de variaciones de nombres de columnas entre años (exportaciones)
# ---------------------------------------------------------------------------
# Algunos años del INE renombran columnas arbitrariamente.
# Este mapeo normaliza todas las variantes al nombre canónico.
EXPORT_COLUMN_ALIASES: dict[str, str] = {
    # Vía de salida: 2022 usa VIASAL2/DESVIA2
    "VIASAL2": "VIASAL",
    "DESVIA2": "DESVIA",
    # Clasificación CUCI: 2026 usa CUCIR3
    "CUCIR3": "CUCI3",
    # GCE: 2026 usa GCE en vez de GCE3
    "GCE": "GCE3",
    # CIIU: 2026 usa CIIU3 en vez de CIIUR3
    "CIIU3": "CIIUR3",
}

IMPORT_COLUMN_ALIASES: dict[str, str] = {
    # Las importaciones son consistentes entre años (2021-2026),
    # pero incluimos el mapeo por si surgen variantes futuras.
}

# ---------------------------------------------------------------------------
# Esquema canónico de columnas
# ---------------------------------------------------------------------------
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


def normalize_column_names(
    df: pd.DataFrame,
    *,
    operation_type: str,
) -> pd.DataFrame:
    """Normaliza nombres de columnas de un DataFrame del INE.

    Aplica el mapeo de alias para resolver variaciones entre años
    (ej: ``VIASAL2`` → ``VIASAL`` en exportaciones 2022).

    Parameters
    ----------
    df:
        DataFrame crudo leído del archivo Excel del INE.
    operation_type:
        ``"exportaciones"`` o ``"importaciones"``.

    Returns
    -------
    pd.DataFrame
        DataFrame con columnas renombradas a nombres canónicos.

    Raises
    ------
    ValueError
        Si ``operation_type`` no es válido.
    """
    valid_types = {"exportaciones", "importaciones"}
    if operation_type not in valid_types:
        msg = f"operation_type debe ser uno de {valid_types}, recibido: {operation_type!r}"
        raise ValueError(msg)

    aliases = EXPORT_COLUMN_ALIASES if operation_type == "exportaciones" else IMPORT_COLUMN_ALIASES

    # Aplicar strip a los nombres de columnas (algunos tienen espacios al final)
    df = df.rename(columns=lambda c: c.strip() if isinstance(c, str) else c)

    # Aplicar mapeo de alias
    rename_map = {old: new for old, new in aliases.items() if old in df.columns}
    if rename_map:
        df = df.rename(columns=rename_map)

    return df


def format_nandina(series: pd.Series) -> pd.Series:
    """Formatea códigos NANDINA a 10 dígitos con ceros a la izquierda.

    El código NANDINA (Nomenclatura Común de los Países Miembros de la
    Comunidad Andina) debe ser siempre una cadena de 10 dígitos.
    Algunos archivos pueden almacenar el valor como numérico, perdiendo
    ceros a la izquierda (ej: ``901110000`` en vez de ``0901110000``).

    Parameters
    ----------
    series:
        Serie de pandas con códigos NANDINA.

    Returns
    -------
    pd.Series
        Serie con códigos formateados a 10 caracteres con ``zfill(10)``.
    """
    return (
        series
        .astype(str)
        .str.strip()
        .str.replace(r"\.0$", "", regex=True)  # Remover .0 de conversiones float
        .str.zfill(10)
    )


def parse_flujo(series: pd.Series) -> pd.DataFrame:
    """Extrae código numérico y descripción del campo FLUJO de exportaciones.

    El campo FLUJO del INE combina código y texto en un solo string:
    ``"1 EXPORTACIONES"``, ``"2 REEXPORTACIONES"``, ``"3 EFECTOS PRESONALES"``.

    Parameters
    ----------
    series:
        Serie de pandas con valores del campo FLUJO.

    Returns
    -------
    pd.DataFrame
        DataFrame con columnas ``flujo_codigo`` (int) y ``flujo_descripcion`` (str).
    """
    cleaned = series.astype(str).str.strip()
    parts = cleaned.str.split(" ", n=1, expand=True)
    parts.columns = ["flujo_codigo", "flujo_descripcion"]
    parts["flujo_codigo"] = pd.to_numeric(parts["flujo_codigo"], errors="coerce")
    return parts


def cast_numeric_columns(
    df: pd.DataFrame,
    columns: list[str],
) -> pd.DataFrame:
    """Convierte columnas específicas a tipo numérico (float64).

    Maneja valores nulos y strings que no se pueden convertir
    (los reemplaza por ``NaN``).

    Parameters
    ----------
    df:
        DataFrame de entrada.
    columns:
        Lista de nombres de columnas a convertir.

    Returns
    -------
    pd.DataFrame
        DataFrame con las columnas especificadas convertidas a float64.
    """
    df = df.copy()
    for col in columns:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def compute_null_report(df: pd.DataFrame) -> pd.DataFrame:
    """Genera un reporte de porcentaje de nulos por columna.

    Parameters
    ----------
    df:
        DataFrame de entrada.

    Returns
    -------
    pd.DataFrame
        DataFrame con columnas ``columna``, ``nulos``, ``total``,
        ``porcentaje_nulos``, ordenado de mayor a menor porcentaje.
    """
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
    """Compara encabezados entre múltiples archivos para detectar variaciones.

    Parameters
    ----------
    headers_by_file:
        Diccionario ``{nombre_archivo: [lista_de_encabezados]}``.

    Returns
    -------
    dict
        Diccionario con:
        - ``all_consistent`` (bool): si todos los archivos tienen las mismas columnas.
        - ``common_columns`` (list): columnas presentes en todos los archivos.
        - ``variations`` (dict): por cada archivo, columnas nuevas o faltantes vs referencia.
        - ``reference_file`` (str): archivo usado como referencia.
    """
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
# Columnas numéricas por tipo de operación
# ---------------------------------------------------------------------------
EXPORT_NUMERIC_COLUMNS: list[str] = [
    "ADUDES", "GESTION", "MES", "PAIS", "AREA", "MEDI", "VIASAL",
    "DEPART", "TNT", "KILBRU", "KILNET", "FINO", "VALOR",
]

IMPORT_NUMERIC_COLUMNS: list[str] = [
    "GESTION", "MES", "ADUANA", "DEPTO", "VIA", "MEDIO", "PAIS",
    "KILOS", "FRO", "FOB", "ADU", "PAG",
]


def clean_export_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Pipeline completo de limpieza para un DataFrame de exportaciones.

    Aplica en secuencia:
    1. Normalización de nombres de columnas
    2. Formato de NANDINA a 10 dígitos
    3. Conversión de columnas numéricas
    4. Strip de espacios en columnas de texto

    Parameters
    ----------
    df:
        DataFrame crudo de exportaciones.

    Returns
    -------
    pd.DataFrame
        DataFrame limpio y normalizado.
    """
    df = normalize_column_names(df, operation_type="exportaciones")
    if "NANDINA" in df.columns:
        df["NANDINA"] = format_nandina(df["NANDINA"])
    df = cast_numeric_columns(df, EXPORT_NUMERIC_COLUMNS)
    # Strip espacios en columnas de texto
    text_cols = df.select_dtypes(include=["object", "string"]).columns
    for col in text_cols:
        df[col] = df[col].str.strip()
    return df


def clean_import_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Pipeline completo de limpieza para un DataFrame de importaciones.

    Aplica en secuencia:
    1. Normalización de nombres de columnas
    2. Formato de NANDINA a 10 dígitos
    3. Conversión de columnas numéricas
    4. Strip de espacios en columnas de texto

    Parameters
    ----------
    df:
        DataFrame crudo de importaciones.

    Returns
    -------
    pd.DataFrame
        DataFrame limpio y normalizado.
    """
    df = normalize_column_names(df, operation_type="importaciones")
    if "NANDINA" in df.columns:
        df["NANDINA"] = format_nandina(df["NANDINA"])
    df = cast_numeric_columns(df, IMPORT_NUMERIC_COLUMNS)
    # Strip espacios en columnas de texto
    text_cols = df.select_dtypes(include=["object", "string"]).columns
    for col in text_cols:
        df[col] = df[col].str.strip()
    return df
