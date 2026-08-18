"""InsightBolivia — Componentes y utilidades auxiliares para exportación de datos.

Proporciona funciones para:
- Conversión en memoria a CSV (con codificación UTF-8 BOM para compatibilidad con Excel).
- Conversión en memoria a hojas de cálculo Excel (.xlsx) usando openpyxl.
- Cálculo de métricas y resumen de datasets a exportar.
- Generación de nombres de archivo estandarizados con metadatos de filtros.
"""

from __future__ import annotations

import io
import logging
from datetime import date
from typing import Any

import pandas as pd

logger = logging.getLogger("insight_bolivia.streamlit.descargas_helpers")

# Límite máximo estricto de registros por descarga para prevenir errores de OOM
MAX_DOWNLOAD_RECORDS: int = 50_000


def convert_df_to_csv(df: pd.DataFrame) -> bytes:
    """Convierte un DataFrame de pandas a bytes CSV con codificación UTF-8 BOM (utf-8-sig).

    La codificación UTF-8 con BOM asegura que caracteres especiales, tildes y la letra 'ñ'
    se visualicen correctamente en Microsoft Excel y herramientas de hoja de cálculo.

    Parameters
    ----------
    df:
        DataFrame a serializar.

    Returns
    -------
    bytes
        Contenido del archivo CSV en bytes.
    """
    if df.empty:
        return b""
    return df.to_csv(index=False).encode("utf-8-sig")


def convert_df_to_excel(
    df: pd.DataFrame,
    sheet_name: str = "ComercioExterior",
) -> bytes:
    """Convierte un DataFrame de pandas a un archivo binario Excel (.xlsx) en memoria.

    Parameters
    ----------
    df:
        DataFrame a serializar.
    sheet_name:
        Nombre de la pestaña u hoja de cálculo dentro del libro Excel.

    Returns
    -------
    bytes
        Contenido del archivo Excel (.xlsx) en formato binario.
    """
    if df.empty:
        return b""

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name=sheet_name, index=False)
    return output.getvalue()


def build_export_filename(
    flow: str = "EXPORTACION",
    start_date: date | str | None = None,
    end_date: date | str | None = None,
    extension: str = "csv",
) -> str:
    """Construye un nombre de archivo normalizado y descriptivo para la exportación.

    Ejemplo: ``insight_bolivia_comercio_exportacion_2024-01-01_2024-12-31.csv``

    Parameters
    ----------
    flow:
        Tipo de flujo ('EXPORTACION', 'IMPORTACION', 'TODOS').
    start_date:
        Fecha inicial del filtro.
    end_date:
        Fecha final del filtro.
    extension:
        Extensión del archivo sin punto ('csv' o 'xlsx').

    Returns
    -------
    str
        Nombre de archivo normalizado.
    """
    clean_flow = flow.lower().replace(" ", "_") if flow else "general"
    s_str = start_date.isoformat() if isinstance(start_date, date) else (start_date or "inicio")
    e_str = end_date.isoformat() if isinstance(end_date, date) else (end_date or "fin")
    ext = extension.lstrip(".")

    return f"insight_bolivia_comercio_{clean_flow}_{s_str}_{e_str}.{ext}"


def format_currency_millions(amount: float) -> str:
    """Formatea valores monetarios en USD a millones o billones con sufijo descriptivo."""
    if abs(amount) >= 1_000_000_000:
        return f"${amount / 1_000_000_000:.2f} B"
    if abs(amount) >= 1_000_000:
        return f"${amount / 1_000_000:.2f} M"
    return f"${amount:,.2f}"


def format_weight_tonnes(weight_kg: float) -> str:
    """Formatea kilogramos a toneladas métricas con sufijo legible."""
    tonnes = weight_kg / 1000.0
    if tonnes >= 1_000_000:
        return f"{tonnes / 1_000_000:.2f} M Ton"
    if tonnes >= 1000:
        return f"{tonnes / 1000:.2f} k Ton"
    return f"{tonnes:,.1f} Ton"


def compute_export_summary(df: pd.DataFrame) -> dict[str, Any]:
    """Calcula indicadores agregados y resumen de integridad del dataset a exportar.

    Parameters
    ----------
    df:
        DataFrame con los microdatos filtrados.

    Returns
    -------
    dict[str, Any]
        Diccionario con conteos, montos FOB/CIF, pesos y número de países/partidas únicas.
    """
    if df.empty:
        return {
            "total_registros": 0,
            "total_fob_usd": 0.0,
            "total_cif_usd": 0.0,
            "total_peso_neto_kg": 0.0,
            "total_peso_bruto_kg": 0.0,
            "total_peso_neto_ton": 0.0,
            "total_peso_bruto_ton": 0.0,
            "num_paises_unicos": 0,
            "num_productos_unicos": 0,
            "num_departamentos_unicos": 0,
            "excede_limite": False,
        }

    total_rows = len(df)
    fob = float(df["valor_fob_usd"].sum()) if "valor_fob_usd" in df.columns else 0.0
    cif = float(df["valor_cif_usd"].sum()) if "valor_cif_usd" in df.columns else 0.0
    peso_neto = float(df["peso_neto_kg"].sum()) if "peso_neto_kg" in df.columns else 0.0
    peso_bruto = float(df["peso_bruto_kg"].sum()) if "peso_bruto_kg" in df.columns else 0.0

    paises_unicos = df["pais_iso"].nunique() if "pais_iso" in df.columns else 0
    productos_unicos = df["codigo_nandina"].nunique() if "codigo_nandina" in df.columns else 0
    depts_unicos = df["departamento"].nunique() if "departamento" in df.columns else 0


    return {
        "total_registros": total_rows,
        "total_fob_usd": fob,
        "total_cif_usd": cif,
        "total_peso_neto_kg": peso_neto,
        "total_peso_bruto_kg": peso_bruto,
        "total_peso_neto_ton": peso_neto / 1000.0,
        "total_peso_bruto_ton": peso_bruto / 1000.0,
        "num_paises_unicos": paises_unicos,
        "num_productos_unicos": productos_unicos,
        "num_departamentos_unicos": depts_unicos,
        "excede_limite": total_rows > MAX_DOWNLOAD_RECORDS,
    }
