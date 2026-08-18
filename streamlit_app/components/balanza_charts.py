"""InsightBolivia — Componentes y gráficos para el Dashboard de Balanza Comercial.

Contiene funciones de agregación, cálculo de KPIs y generadores de gráficos Plotly
para el módulo `01_balanza_comercial.py`.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import plotly.graph_objects as go

# ==============================================================================
# Paleta de Colores y Estilos UI
# ==============================================================================
COLOR_EXPORT = "#10B981"  # Verde esmeralda para Exportaciones (FOB)
COLOR_IMPORT = "#3B82F6"  # Azul para Importaciones (CIF)
COLOR_SURPLUS = "#10B981"  # Verde para Superávit
COLOR_DEFICIT = "#EF4444"  # Rojo para Déficit
COLOR_BORDER = "#334155"  # Borde sutil


def format_currency_millions(val: float) -> str:
    """Formatea un valor en dólares a notación resumida en millones o billones de USD."""
    if abs(val) >= 1_000_000_000:
        return f"${val / 1_000_000_000:,.2f} B"
    if abs(val) >= 1_000_000:
        return f"${val / 1_000_000:,.2f} M"
    return f"${val:,.2f}"


def compute_balanza_kpis(df: pd.DataFrame) -> dict[str, Any]:
    """Calcula las métricas e indicadores clave de rendimiento (KPIs) de la balanza comercial.

    Parameters
    ----------
    df:
        DataFrame con registros de la vista `vw_balanza_comercial_mensual`.

    Returns
    -------
    dict[str, Any]
        Diccionario con totales agregados, saldo, tasa de cobertura y métricas físicas.
    """
    if df.empty:
        return {
            "total_exportaciones_usd": 0.0,
            "total_importaciones_usd": 0.0,
            "saldo_balanza_usd": 0.0,
            "tasa_cobertura_pct": 0.0,
            "total_peso_neto_exp_ton": 0.0,
            "total_peso_bruto_imp_ton": 0.0,
            "num_transacciones_exp": 0,
            "num_transacciones_imp": 0,
            "num_meses": 0,
            "es_superavit": True,
        }

    total_exp = float(df["total_exportaciones_usd"].sum())
    total_imp = float(df["total_importaciones_usd"].sum())
    saldo = total_exp - total_imp

    # Tasa de cobertura comercial: (Exportaciones / Importaciones) * 100
    tasa_cobertura = (total_exp / total_imp * 100.0) if total_imp > 0 else 0.0

    # Conversión de kg a toneladas métricas
    peso_exp_ton = float(df["total_peso_neto_exportaciones_kg"].sum()) / 1_000.0
    peso_imp_ton = float(df["total_peso_bruto_importaciones_kg"].sum()) / 1_000.0

    trans_exp = int(df["num_transacciones_exportacion"].sum()) if "num_transacciones_exportacion" in df else 0
    trans_imp = int(df["num_transacciones_importacion"].sum()) if "num_transacciones_importacion" in df else 0

    return {
        "total_exportaciones_usd": total_exp,
        "total_importaciones_usd": total_imp,
        "saldo_balanza_usd": saldo,
        "tasa_cobertura_pct": tasa_cobertura,
        "total_peso_neto_exp_ton": peso_exp_ton,
        "total_peso_bruto_imp_ton": peso_imp_ton,
        "num_transacciones_exp": trans_exp,
        "num_transacciones_imp": trans_imp,
        "num_meses": len(df),
        "es_superavit": saldo >= 0,
    }


def aggregate_balanza_data(df: pd.DataFrame, freq: str = "Mensual") -> pd.DataFrame:
    """Agrega los datos de balanza comercial según la periodicidad seleccionada.

    Parameters
    ----------
    df:
        DataFrame con registros mensuales.
    freq:
        Frecuencia de agregación: ``'Mensual'``, ``'Trimestral'`` o ``'Anual'``.

    Returns
    -------
    pd.DataFrame
        DataFrame agrupado con fechas de referencia y totales consolidados.
    """
    if df.empty:
        return df.copy()

    df_work = df.copy()
    if not pd.api.types.is_datetime64_any_dtype(df_work["fecha"]):
        df_work["fecha"] = pd.to_datetime(df_work["fecha"])

    if freq == "Anual":
        grouped = (
            df_work.groupby("anio", as_index=False)
            .agg({
                "total_exportaciones_usd": "sum",
                "total_importaciones_usd": "sum",
                "saldo_balanza_usd": "sum",
                "total_peso_neto_exportaciones_kg": "sum",
                "total_peso_bruto_importaciones_kg": "sum",
                "num_transacciones_exportacion": "sum",
                "num_transacciones_importacion": "sum",
            })
            .sort_values("anio")
        )
        grouped["periodo_label"] = grouped["anio"].astype(str)
        grouped["fecha_ref"] = pd.to_datetime(grouped["anio"].astype(str) + "-01-01")
        return grouped

    if freq == "Trimestral":
        grouped = (
            df_work.groupby(["anio", "trimestre"], as_index=False)
            .agg({
                "total_exportaciones_usd": "sum",
                "total_importaciones_usd": "sum",
                "saldo_balanza_usd": "sum",
                "total_peso_neto_exportaciones_kg": "sum",
                "total_peso_bruto_importaciones_kg": "sum",
                "num_transacciones_exportacion": "sum",
                "num_transacciones_importacion": "sum",
            })
            .sort_values(["anio", "trimestre"])
        )
        grouped["periodo_label"] = grouped["anio"].astype(str) + " - T" + grouped["trimestre"].astype(str)
        month_start = (grouped["trimestre"] - 1) * 3 + 1
        grouped["fecha_ref"] = pd.to_datetime(
            grouped["anio"].astype(str) + "-" + month_start.astype(str).str.zfill(2) + "-01"
        )
        return grouped

    # Mensual por defecto
    df_work["periodo_label"] = pd.DatetimeIndex(df_work["fecha"]).strftime("%Y-%m")
    df_work["fecha_ref"] = pd.to_datetime(df_work["fecha"])
    return df_work.sort_values("fecha_ref")


def build_evolution_chart(df: pd.DataFrame) -> go.Figure:
    """Construye el gráfico de líneas comparativo de Exportaciones (FOB) vs Importaciones (CIF)."""
    fig = go.Figure()

    if df.empty:
        fig.update_layout(
            template="plotly_dark",
            title="Sin datos disponibles para el periodo seleccionado",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
        )
        return fig

    x_col = df["periodo_label"] if "periodo_label" in df else df["fecha"]

    # Línea de Exportaciones
    fig.add_trace(
        go.Scatter(
            x=x_col,
            y=df["total_exportaciones_usd"],
            name="Exportaciones (FOB)",
            mode="lines+markers",
            line={"color": COLOR_EXPORT, "width": 3, "shape": "spline"},
            marker={"size": 6, "color": COLOR_EXPORT},
            fill="tozeroy",
            fillcolor="rgba(16, 185, 129, 0.08)",
            hovertemplate="<b>%{x}</b><br>Exportaciones FOB: $%{y:,.2f}<extra></extra>",
        )
    )

    # Línea de Importaciones
    fig.add_trace(
        go.Scatter(
            x=x_col,
            y=df["total_importaciones_usd"],
            name="Importaciones (CIF)",
            mode="lines+markers",
            line={"color": COLOR_IMPORT, "width": 3, "shape": "spline"},
            marker={"size": 6, "color": COLOR_IMPORT},
            fill="tozeroy",
            fillcolor="rgba(59, 130, 246, 0.08)",
            hovertemplate="<b>%{x}</b><br>Importaciones CIF: $%{y:,.2f}<extra></extra>",
        )
    )

    fig.update_layout(
        template="plotly_dark",
        title={"text": "<b>Evolución Temporal de Exportaciones FOB vs. Importaciones CIF</b>", "x": 0.01},
        hovermode="x unified",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "right", "x": 1},
        margin={"l": 40, "r": 20, "t": 60, "b": 40},
        xaxis={"showgrid": True, "gridcolor": COLOR_BORDER, "title": ""},
        yaxis={
            "showgrid": True,
            "gridcolor": COLOR_BORDER,
            "title": "Valor en USD",
            "tickprefix": "$",
        },
    )
    return fig


def build_balance_bar_chart(df: pd.DataFrame) -> go.Figure:
    """Construye el gráfico de barras interactivo del Saldo Comercial (Superávit / Déficit)."""
    fig = go.Figure()

    if df.empty:
        fig.update_layout(
            template="plotly_dark",
            title="Sin datos disponibles para el periodo seleccionado",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
        )
        return fig

    x_col = df["periodo_label"] if "periodo_label" in df else df["fecha"]
    colors = [COLOR_SURPLUS if val >= 0 else COLOR_DEFICIT for val in df["saldo_balanza_usd"]]

    fig.add_trace(
        go.Bar(
            x=x_col,
            y=df["saldo_balanza_usd"],
            name="Saldo Comercial",
            marker_color=colors,
            hovertemplate="<b>%{x}</b><br>Saldo Comercial: $%{y:,.2f}<extra></extra>",
        )
    )

    # Línea de referencia en cero
    fig.add_hline(
        y=0,
        line_dash="dash",
        line_color="#94A3B8",
        line_width=1.5,
        annotation_text="Equilibrio Comercial ($0)",
        annotation_position="bottom right",
    )

    fig.update_layout(
        template="plotly_dark",
        title={"text": "<b>Saldo de Balanza Comercial (Superávit 🟢 / Déficit 🔴)</b>", "x": 0.01},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin={"l": 40, "r": 20, "t": 60, "b": 40},
        xaxis={"showgrid": True, "gridcolor": COLOR_BORDER, "title": ""},
        yaxis={
            "showgrid": True,
            "gridcolor": COLOR_BORDER,
            "title": "Saldo Neto en USD",
            "tickprefix": "$",
        },
    )
    return fig


def build_annual_comparison_chart(df: pd.DataFrame) -> go.Figure:
    """Construye un gráfico de barras agrupadas comparativo anual de Exportaciones e Importaciones."""
    fig = go.Figure()

    if df.empty:
        return fig

    if "anio" in df:
        annual = (
            df.groupby("anio", as_index=False)
            .agg({"total_exportaciones_usd": "sum", "total_importaciones_usd": "sum", "saldo_balanza_usd": "sum"})
            .sort_values("anio")
        )
    else:
        return fig

    fig.add_trace(
        go.Bar(
            x=annual["anio"].astype(str),
            y=annual["total_exportaciones_usd"],
            name="Exportaciones FOB",
            marker_color=COLOR_EXPORT,
            hovertemplate="Año %{x}<br>Exportaciones: $%{y:,.2f}<extra></extra>",
        )
    )

    fig.add_trace(
        go.Bar(
            x=annual["anio"].astype(str),
            y=annual["total_importaciones_usd"],
            name="Importaciones CIF",
            marker_color=COLOR_IMPORT,
            hovertemplate="Año %{x}<br>Importaciones: $%{y:,.2f}<extra></extra>",
        )
    )

    fig.update_layout(
        barmode="group",
        template="plotly_dark",
        title={"text": "<b>Comparativa Anual Consolidada: Exportaciones vs. Importaciones</b>", "x": 0.01},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "right", "x": 1},
        margin={"l": 40, "r": 20, "t": 60, "b": 40},
        xaxis={"title": "Gestión Anual", "gridcolor": COLOR_BORDER},
        yaxis={"title": "Valor Acumulado en USD", "tickprefix": "$", "gridcolor": COLOR_BORDER},
    )
    return fig


def build_volume_chart(df: pd.DataFrame) -> go.Figure:
    """Construye un gráfico de evolución de peso físico en Miles de Toneladas Métricas."""
    fig = go.Figure()

    if df.empty:
        return fig

    x_col = df["periodo_label"] if "periodo_label" in df else df["fecha"]
    exp_ton = df["total_peso_neto_exportaciones_kg"] / 1_000_000.0  # Miles de toneladas (kTon)
    imp_ton = df["total_peso_bruto_importaciones_kg"] / 1_000_000.0

    fig.add_trace(
        go.Scatter(
            x=x_col,
            y=exp_ton,
            name="Exportaciones (Peso Neto)",
            mode="lines+markers",
            line={"color": "#10B981", "width": 2.5},
            hovertemplate="<b>%{x}</b><br>Peso Neto Exp: %{y:,.2f} kTon<extra></extra>",
        )
    )

    fig.add_trace(
        go.Scatter(
            x=x_col,
            y=imp_ton,
            name="Importaciones (Peso Bruto)",
            mode="lines+markers",
            line={"color": "#F59E0B", "width": 2.5},
            hovertemplate="<b>%{x}</b><br>Peso Bruto Imp: %{y:,.2f} kTon<extra></extra>",
        )
    )

    fig.update_layout(
        template="plotly_dark",
        title={"text": "<b>Volumen Físico de Comercio Exterior (Miles de Toneladas Métricas)</b>", "x": 0.01},
        hovermode="x unified",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "right", "x": 1},
        margin={"l": 40, "r": 20, "t": 60, "b": 40},
        xaxis={"gridcolor": COLOR_BORDER},
        yaxis={"title": "Miles de Toneladas (kTon)", "gridcolor": COLOR_BORDER},
    )
    return fig
