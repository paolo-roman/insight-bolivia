"""InsightBolivia — Componentes y gráficos para el Dashboard de Socios Comerciales.

Contiene funciones de agregación geográfica, cálculo de KPIs y generadores de
gráficos Plotly (mapa coroplético mundial, ranking horizontal, distribución por
bloques y evolución histórica) para el módulo `02_socios_comerciales.py`.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import plotly.graph_objects as go

# ==============================================================================
# Paleta de Colores y Estilos UI
# ==============================================================================
COLOR_EXPORT = "#10B981"  # Verde esmeralda para Exportaciones (FOB)
COLOR_IMPORT = "#3B82F6"  # Azul ultramar para Importaciones (CIF)
COLOR_ACCENT = "#F59E0B"  # Ámbar para destaques secundarios
COLOR_BORDER = "#334155"  # Borde sutil Slate

COLORSCALE_EXPORT = [
    [0.0, "#064E3B"],
    [0.2, "#047857"],
    [0.4, "#059669"],
    [0.7, "#10B981"],
    [0.9, "#34D399"],
    [1.0, "#6EE7B7"],
]
COLORSCALE_IMPORT = [
    [0.0, "#1E3A8A"],
    [0.2, "#1D4ED8"],
    [0.4, "#2563EB"],
    [0.7, "#3B82F6"],
    [0.9, "#60A5FA"],
    [1.0, "#93C5FD"],
]

BLOC_COLORS: dict[str, str] = {
    "MERCOSUR": "#10B981",
    "CAN": "#F59E0B",
    "Unión Europea": "#3B82F6",
    "ALADI": "#8B5CF6",
    "NAFTA / USMCA": "#EC4899",
    "APEC": "#14B8A6",
    "Otros": "#64748B",
}


def format_currency_millions(val: float) -> str:
    """Formatea un valor numérico a notación de millones o billones de USD."""
    if abs(val) >= 1_000_000_000:
        return f"${val / 1_000_000_000:,.2f} B"
    if abs(val) >= 1_000_000:
        return f"${val / 1_000_000:,.2f} M"
    return f"${val:,.2f}"


def compute_socios_kpis(df: pd.DataFrame, flow: str = "EXPORTACION") -> dict[str, Any]:
    """Calcula indicadores clave (KPIs) de socios comerciales."""
    if df.empty:
        return {
            "total_valor_usd": 0.0,
            "num_paises": 0,
            "top_pais_nombre": "Sin datos",
            "top_pais_iso": "---",
            "top_pais_valor": 0.0,
            "top_pais_pct": 0.0,
            "top_bloque_nombre": "Sin datos",
            "top_bloque_valor": 0.0,
            "top_bloque_pct": 0.0,
            "total_peso_ton": 0.0,
            "total_transacciones": 0,
            "flow": flow,
        }

    val_col = "total_valor_usd" if "total_valor_usd" in df else "total_fob_usd"
    total_val = float(df[val_col].sum()) if val_col in df else 0.0
    num_paises = df["pais_iso"].nunique() if "pais_iso" in df else len(df)

    top_pais_nombre, top_pais_iso, top_pais_valor, top_pais_pct = "N/D", "---", 0.0, 0.0
    if "nombre_pais_es" in df and val_col in df:
        country_df = pd.DataFrame(df.groupby(["nombre_pais_es", "pais_iso"], as_index=False)[val_col].sum())
        if not country_df.empty:
            top_country_row = country_df.sort_values(by=val_col, ascending=False).iloc[0]
            top_pais_nombre = str(top_country_row["nombre_pais_es"])
            top_pais_iso = str(top_country_row["pais_iso"])
            top_pais_valor = float(top_country_row[val_col])
            top_pais_pct = (top_pais_valor / total_val * 100.0) if total_val > 0 else 0.0

    top_bloque_nombre, top_bloque_valor, top_bloque_pct = "N/D", 0.0, 0.0
    if "bloque_comercial" in df and val_col in df:
        bloc_df = pd.DataFrame(df.groupby("bloque_comercial", as_index=False)[val_col].sum())
        if not bloc_df.empty:
            top_bloc_row = bloc_df.sort_values(by=val_col, ascending=False).iloc[0]
            top_bloque_nombre = str(top_bloc_row["bloque_comercial"])
            top_bloque_valor = float(top_bloc_row[val_col])
            top_bloque_pct = (top_bloque_valor / total_val * 100.0) if total_val > 0 else 0.0

    total_peso_ton = (float(df["total_peso_bruto_kg"].sum()) / 1_000.0) if "total_peso_bruto_kg" in df else 0.0
    total_trans = int(df["num_transacciones"].sum()) if "num_transacciones" in df else 0

    return {
        "total_valor_usd": total_val,
        "num_paises": num_paises,
        "top_pais_nombre": top_pais_nombre,
        "top_pais_iso": top_pais_iso,
        "top_pais_valor": top_pais_valor,
        "top_pais_pct": top_pais_pct,
        "top_bloque_nombre": top_bloque_nombre,
        "top_bloque_valor": top_bloque_valor,
        "top_bloque_pct": top_bloque_pct,
        "total_peso_ton": total_peso_ton,
        "total_transacciones": total_trans,
        "flow": flow,
    }


def build_choropleth_map(
    df: pd.DataFrame,
    flow: str = "EXPORTACION",
    scope: str = "world",
) -> go.Figure:
    """Construye un mapa coroplético mundial interactivo con Plotly."""
    fig = go.Figure()

    if df.empty or "pais_iso" not in df:
        fig.update_layout(
            template="plotly_dark",
            title="Sin datos disponibles para el mapa",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
        )
        return fig

    val_col = "total_valor_usd" if "total_valor_usd" in df else "total_fob_usd"
    agg_cols: dict[str, str] = {val_col: "sum"}
    if "total_peso_bruto_kg" in df:
        agg_cols["total_peso_bruto_kg"] = "sum"
    if "num_transacciones" in df:
        agg_cols["num_transacciones"] = "sum"

    for c in ["nombre_pais_es", "continente", "bloque_comercial"]:
        if c in df.columns:
            agg_cols[c] = "first"

    df_map = pd.DataFrame(df.groupby("pais_iso", as_index=False).agg(agg_cols))
    total_flow_val = df_map[val_col].sum()
    df_map["pct_share"] = (df_map[val_col] / total_flow_val * 100.0) if total_flow_val > 0 else 0.0
    df_map["peso_ton"] = (df_map["total_peso_bruto_kg"] / 1_000.0) if "total_peso_bruto_kg" in df_map else 0.0

    if "num_transacciones" not in df_map:
        df_map["num_transacciones"] = 0
    if "continente" not in df_map:
        df_map["continente"] = "N/D"
    if "bloque_comercial" not in df_map:
        df_map["bloque_comercial"] = "N/D"
    if "nombre_pais_es" not in df_map:
        df_map["nombre_pais_es"] = df_map["pais_iso"]

    colorscale = COLORSCALE_EXPORT if flow.upper() == "EXPORTACION" else COLORSCALE_IMPORT
    colorbar_title = "FOB (USD)" if flow.upper() == "EXPORTACION" else "CIF (USD)"

    custom_data = np.stack(
        (
            df_map["pct_share"],
            df_map["continente"],
            df_map["bloque_comercial"],
            df_map["peso_ton"],
            df_map["num_transacciones"],
        ),
        axis=-1,
    )

    hover_template = (
        "<b>%{text} (%{location})</b><br>"
        "Valor Comercial: $%{z:,.2f}<br>"
        "Participación: %{customdata[0]:.2f}%<br>"
        "Continente: %{customdata[1]}<br>"
        "Bloque: %{customdata[2]}<br>"
        "Volumen Físico: %{customdata[3]:,.1f} Ton<br>"
        "Transacciones: %{customdata[4]:,d}<extra></extra>"
    )

    fig.add_trace(
        go.Choropleth(
            locations=df_map["pais_iso"],
            z=df_map[val_col],
            text=df_map["nombre_pais_es"],
            customdata=custom_data,
            locationmode="ISO-3",
            colorscale=colorscale,
            autocolorscale=False,
            marker_line_color="#334155",
            marker_line_width=0.6,
            colorbar={
                "title": {"text": colorbar_title, "font": {"color": "#F8FAFC", "size": 11}},
                "tickprefix": "$",
                "tickfont": {"color": "#94A3B8"},
                "len": 0.75,
                "thickness": 14,
            },
            hovertemplate=hover_template,
        )
    )

    flow_label = "Destino (Exportaciones FOB)" if flow.upper() == "EXPORTACION" else "Origen (Importaciones CIF)"
    fig.update_layout(
        template="plotly_dark",
        title={
            "text": f"<b>Mapa Global de Socios Comerciales de Bolivia — {flow_label}</b>",
            "x": 0.01,
            "font": {"size": 15, "color": "#F8FAFC"},
        },
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin={"l": 0, "r": 0, "t": 45, "b": 0},
        geo={
            "showframe": False,
            "showcoastlines": True,
            "coastlinecolor": "#475569",
            "showland": True,
            "landcolor": "#1E293B",
            "showocean": True,
            "oceancolor": "#0B132B",
            "showlakes": True,
            "lakecolor": "#0B132B",
            "showcountries": True,
            "countrycolor": "#334155",
            "projection_type": "natural earth",
            "scope": scope,
            "bgcolor": "rgba(0,0,0,0)",
        },
    )
    return fig


def build_top_partners_bar_chart(
    df: pd.DataFrame,
    top_n: int = 15,
    flow: str = "EXPORTACION",
) -> go.Figure:
    """Construye un gráfico de barras horizontales con el ranking de principales socios."""
    fig = go.Figure()

    if df.empty:
        fig.update_layout(
            template="plotly_dark",
            title="Sin datos disponibles para el ranking",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
        )
        return fig

    val_col = "total_valor_usd" if "total_valor_usd" in df else "total_fob_usd"
    country_col = "nombre_pais_es" if "nombre_pais_es" in df else "pais_iso"

    agg = pd.DataFrame(df.groupby([country_col, "pais_iso"], as_index=False)[val_col].sum())
    total_val = agg[val_col].sum()
    agg["pct"] = (agg[val_col] / total_val * 100.0) if total_val > 0 else 0.0
    agg = agg.sort_values(by=val_col, ascending=False).head(top_n).iloc[::-1]

    bar_color = COLOR_EXPORT if flow.upper() == "EXPORTACION" else COLOR_IMPORT
    text_labels = [f"{format_currency_millions(v)} ({p:.1f}%)" for v, p in zip(agg[val_col], agg["pct"], strict=False)]

    fig.add_trace(
        go.Bar(
            y=agg[country_col] + " (" + agg["pais_iso"] + ")",
            x=agg[val_col],
            orientation="h",
            marker_color=bar_color,
            text=text_labels,
            textposition="auto",
            textfont={"color": "#FFFFFF", "size": 11},
            hovertemplate="<b>%{y}</b><br>Total Comercializado: $%{x:,.2f}<extra></extra>",
        )
    )

    fig.update_layout(
        template="plotly_dark",
        title={"text": f"<b>Top {top_n} Principales Socios Comerciales</b>", "x": 0.01},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin={"l": 40, "r": 20, "t": 50, "b": 40},
        xaxis={"showgrid": True, "gridcolor": COLOR_BORDER, "title": "Valor en USD", "tickprefix": "$"},
        yaxis={"showgrid": False, "title": ""},
    )
    return fig


def build_bloc_distribution_chart(
    df: pd.DataFrame,
    flow: str = "EXPORTACION",  # noqa: ARG001
) -> go.Figure:
    """Construye un gráfico de Donut de distribución por Bloque de Integración Comercial."""
    fig = go.Figure()

    if df.empty or "bloque_comercial" not in df:
        fig.update_layout(
            template="plotly_dark",
            title="Sin datos de bloques comerciales",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
        )
        return fig

    val_col = "total_valor_usd" if "total_valor_usd" in df else "total_fob_usd"
    bloc_agg = pd.DataFrame(df.groupby("bloque_comercial", as_index=False)[val_col].sum())
    bloc_agg = bloc_agg.sort_values(by=val_col, ascending=False)

    colors = [BLOC_COLORS.get(b, "#64748B") for b in bloc_agg["bloque_comercial"]]

    fig.add_trace(
        go.Pie(
            labels=bloc_agg["bloque_comercial"],
            values=bloc_agg[val_col],
            hole=0.45,
            marker={"colors": colors, "line": {"color": "#1E293B", "width": 2}},
            textinfo="label+percent",
            hovertemplate="<b>%{label}</b><br>Total: $%{value:,.2f}<br>Participación: %{percent}<extra></extra>",
        )
    )

    fig.update_layout(
        template="plotly_dark",
        title={"text": "<b>Participación por Bloque Comercial de Integración</b>", "x": 0.01},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin={"l": 20, "r": 20, "t": 50, "b": 30},
        legend={"orientation": "h", "yanchor": "bottom", "y": -0.2, "xanchor": "center", "x": 0.5},
    )
    return fig


def build_partner_evolution_chart(
    df: pd.DataFrame,
    top_n: int = 5,
) -> go.Figure:
    """Construye un gráfico multilínea de tendencias anuales de los principales socios."""
    fig = go.Figure()

    if df.empty or "anio" not in df:
        fig.update_layout(
            template="plotly_dark",
            title="Sin datos históricos suficientes para mostrar evolución",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
        )
        return fig

    val_col = "total_valor_usd" if "total_valor_usd" in df else "total_fob_usd"
    country_col = "nombre_pais_es" if "nombre_pais_es" in df else "pais_iso"

    top_countries = (
        pd.DataFrame(df.groupby(country_col)[val_col].sum())
        .sort_values(by=val_col, ascending=False)
        .head(top_n)
        .index.tolist()
    )

    df_filtered = df[df[country_col].isin(top_countries)]
    pivot_df = df_filtered.pivot_table(
        index="anio",
        columns=country_col,
        values=val_col,
        aggfunc="sum",
        fill_value=0.0,
    ).reset_index()

    palette = ["#10B981", "#3B82F6", "#F59E0B", "#8B5CF6", "#EC4899", "#14B8A6"]
    for i, country in enumerate(top_countries):
        if country in pivot_df.columns:
            color = palette[i % len(palette)]
            fig.add_trace(
                go.Scatter(
                    x=pivot_df["anio"].astype(str),
                    y=pivot_df[country],
                    name=str(country),
                    mode="lines+markers",
                    line={"color": color, "width": 2.5},
                    marker={"size": 6, "color": color},
                    hovertemplate=f"<b>{country}</b> (Año %{{x}})<br>Total: $%{{y:,.2f}}<extra></extra>",
                )
            )

    fig.update_layout(
        template="plotly_dark",
        title={"text": f"<b>Evolución Histórica de los Top {top_n} Socios Comerciales</b>", "x": 0.01},
        hovermode="x unified",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "right", "x": 1},
        margin={"l": 40, "r": 20, "t": 60, "b": 40},
        xaxis={"title": "Gestión Anual", "gridcolor": COLOR_BORDER},
        yaxis={"title": "Valor en USD", "tickprefix": "$", "gridcolor": COLOR_BORDER},
    )
    return fig


def build_concentration_curve(df: pd.DataFrame) -> go.Figure:
    """Construye una curva de Pareto para analizar la concentración del comercio."""
    fig = go.Figure()

    if df.empty:
        fig.update_layout(
            template="plotly_dark",
            title="Sin datos para la curva de concentración",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
        )
        return fig

    val_col = "total_valor_usd" if "total_valor_usd" in df else "total_fob_usd"
    country_col = "nombre_pais_es" if "nombre_pais_es" in df else "pais_iso"

    agg = pd.DataFrame(df.groupby(country_col, as_index=False)[val_col].sum()).sort_values(by=val_col, ascending=False)
    total_val = agg[val_col].sum()

    if total_val == 0 or len(agg) == 0:
        return fig

    agg["cum_val"] = agg[val_col].cumsum()
    agg["cum_pct"] = agg["cum_val"] / total_val * 100.0
    agg["ranking"] = np.arange(1, len(agg) + 1)

    fig.add_trace(
        go.Scatter(
            x=agg["ranking"],
            y=agg["cum_pct"],
            name="% Acumulado de Comercio",
            mode="lines+markers",
            line={"color": "#10B981", "width": 3},
            fill="tozeroy",
            fillcolor="rgba(16, 185, 129, 0.1)",
            hovertemplate="Top %{x} países acumulan el <b>%{y:.1f}%</b> del total<extra></extra>",
        )
    )

    fig.add_hline(
        y=80,
        line_dash="dash",
        line_color="#F59E0B",
        line_width=1.5,
        annotation_text="Umbral Pareto 80%",
        annotation_position="bottom right",
    )

    fig.update_layout(
        template="plotly_dark",
        title={"text": "<b>Curva de Concentración de Socios Comerciales (Pareto)</b>", "x": 0.01},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin={"l": 40, "r": 20, "t": 50, "b": 40},
        xaxis={"title": "Número de Países Acumulados (Ranking)", "gridcolor": COLOR_BORDER},
        yaxis={
            "title": "% Acumulado del Comercio",
            "ticksuffix": "%",
            "range": [0, 105],
            "gridcolor": COLOR_BORDER,
        },
    )
    return fig
