"""InsightBolivia — Componentes y gráficos para el Dashboard de Productos Top.

Contiene funciones de agregación por producto arancelario, cálculo de KPIs y
generadores de gráficos Plotly (ranking horizontal conmutador USD/Volumen,
distribución por sector económico, diagrama de dispersión de precio unitario FOB/kg
y evolución histórica interanual) para el módulo `03_productos_top.py`.
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
COLOR_VOLUME = "#06B6D4"  # Cian para Volumen Físico (kg / Ton)
COLOR_ACCENT = "#F59E0B"  # Ámbar
COLOR_BORDER = "#334155"  # Borde Slate

SECTOR_COLORS: dict[str, str] = {
    "Hidrocarburos": "#F59E0B",
    "Minería": "#EAB308",
    "Agroindustria": "#10B981",
    "Industria Manufacturera": "#3B82F6",
    "Agropecuario": "#84CC16",
    "Otros": "#8B5CF6",
}


def format_currency_millions(val: float) -> str:
    """Formatea un valor numérico a notación de millones o billones de USD."""
    if abs(val) >= 1_000_000_000:
        return f"${val / 1_000_000_000:,.2f} B"
    if abs(val) >= 1_000_000:
        return f"${val / 1_000_000:,.2f} M"
    return f"${val:,.2f}"


def format_weight_tonnes(val_kg: float) -> str:
    """Formatea un peso en kilogramos a notación de Toneladas o Millones de Toneladas."""
    val_ton = val_kg / 1_000.0
    if abs(val_ton) >= 1_000_000:
        return f"{val_ton / 1_000_000:,.2f} M Ton"
    if abs(val_ton) >= 1_000:
        return f"{val_ton / 1_000:,.2f} k Ton"
    return f"{val_ton:,.1f} Ton"


def compute_top_productos_kpis(
    df: pd.DataFrame,
    metric: str = "usd",
) -> dict[str, Any]:
    """Calcula indicadores ejecutivos (KPIs) a partir de los datos de productos top."""
    if df.empty:
        return {
            "total_fob_usd": 0.0,
            "total_peso_kg": 0.0,
            "total_peso_ton": 0.0,
            "num_productos": 0,
            "top_producto_nombre": "Sin datos",
            "top_producto_nandina": "---",
            "top_producto_fob_usd": 0.0,
            "top_producto_peso_kg": 0.0,
            "top_producto_pct": 0.0,
            "top_sector_nombre": "Sin datos",
            "top_sector_valor": 0.0,
            "top_sector_pct": 0.0,
            "precio_medio_usd_kg": 0.0,
            "total_transacciones": 0,
            "metric": metric,
        }

    total_fob = float(df["total_fob_usd"].sum()) if "total_fob_usd" in df else 0.0
    total_peso_kg = float(df["total_peso_neto_kg"].sum()) if "total_peso_neto_kg" in df else 0.0
    total_peso_ton = total_peso_kg / 1_000.0
    num_prods = df["codigo_nandina"].nunique() if "codigo_nandina" in df else len(df)
    total_tx = int(df["num_transacciones"].sum()) if "num_transacciones" in df else 0

    target_col = "total_fob_usd" if metric == "usd" else "total_peso_neto_kg"
    base_total = total_fob if metric == "usd" else total_peso_kg

    top_prod_nom, top_prod_nandina = "N/D", "---"
    top_prod_fob, top_prod_peso, top_prod_pct = 0.0, 0.0, 0.0

    if "codigo_nandina" in df and target_col in df:
        val_cols = [c for c in ["total_fob_usd", "total_peso_neto_kg"] if c in df]
        p_grp = pd.DataFrame(df.groupby(["codigo_nandina", "descripcion_producto"], as_index=False)[val_cols].sum())
        p_grp = p_grp.sort_values(by=target_col, ascending=False)
        if not p_grp.empty:
            l_row = p_grp.iloc[0]
            top_prod_nandina = str(l_row["codigo_nandina"])
            top_prod_nom = str(l_row["descripcion_producto"])
            top_prod_fob = float(l_row.get("total_fob_usd", 0.0))
            top_prod_peso = float(l_row.get("total_peso_neto_kg", 0.0))
            l_val = top_prod_fob if metric == "usd" else top_prod_peso
            top_prod_pct = (l_val / base_total * 100.0) if base_total > 0 else 0.0

    top_sec_nom, top_sec_val, top_sec_pct = "N/D", 0.0, 0.0
    if "sector_economico" in df and target_col in df:
        s_grp = pd.DataFrame(df.groupby("sector_economico", as_index=False)[target_col].sum())
        s_grp = s_grp.sort_values(by=target_col, ascending=False)
        if not s_grp.empty:
            s_row = s_grp.iloc[0]
            top_sec_nom = str(s_row["sector_economico"])
            top_sec_val = float(s_row[target_col])
            top_sec_pct = (top_sec_val / base_total * 100.0) if base_total > 0 else 0.0

    precio_medio = (total_fob / total_peso_kg) if total_peso_kg > 0 else 0.0

    return {
        "total_fob_usd": total_fob,
        "total_peso_kg": total_peso_kg,
        "total_peso_ton": total_peso_ton,
        "num_productos": num_prods,
        "top_producto_nombre": top_prod_nom,
        "top_producto_nandina": top_prod_nandina,
        "top_producto_fob_usd": top_prod_fob,
        "top_producto_peso_kg": top_prod_peso,
        "top_producto_pct": top_prod_pct,
        "top_sector_nombre": top_sec_nom,
        "top_sector_valor": top_sec_val,
        "top_sector_pct": top_sec_pct,
        "precio_medio_usd_kg": precio_medio,
        "total_transacciones": total_tx,
        "metric": metric,
    }


def build_top_products_bar_chart(
    df: pd.DataFrame,
    metric: str = "usd",
    top_n: int = 10,
) -> go.Figure:
    """Genera un gráfico de barras horizontales estilizado para los Top N productos."""
    fig = go.Figure()
    if df.empty:
        fig.add_annotation(
            text="Sin registros disponibles para el criterio seleccionado",
            showarrow=False,
            font={"size": 14, "color": "#94A3B8"},
        )
        fig.update_layout(template="plotly_dark", height=420)
        return fig

    agg_dict = {
        c: "sum" for c in ["total_fob_usd", "total_peso_neto_kg", "num_transacciones"] if c in df
    }
    grp_cols = ["codigo_nandina", "descripcion_producto"]
    if "sector_economico" in df:
        grp_cols.append("sector_economico")

    grouped = pd.DataFrame(df.groupby(grp_cols, as_index=False).agg(agg_dict))
    is_usd = metric == "usd"
    sort_col = "total_fob_usd" if is_usd else "total_peso_neto_kg"

    if sort_col not in grouped:
        return fig

    ranked = grouped.sort_values(by=sort_col, ascending=True).tail(top_n)
    y_labels = [f"{str(d)[:45]}..." if len(str(d)) > 45 else str(d) for d in ranked["descripcion_producto"]]
    x_vals = ranked["total_fob_usd"] if is_usd else (ranked["total_peso_neto_kg"] / 1_000.0)

    colors = [
        SECTOR_COLORS.get(str(s), "#64748B")
        for s in (ranked["sector_economico"] if "sector_economico" in ranked else ["Otros"] * len(ranked))
    ]

    fob_vals = ranked.get("total_fob_usd", [0.0] * len(ranked))
    kg_vals = ranked.get("total_peso_neto_kg", [1.0] * len(ranked))
    precios = [(f / k) if k > 0 else 0.0 for f, k in zip(fob_vals, kg_vals, strict=False)]

    customdata = np.stack(
        (
            ranked["codigo_nandina"],
            ranked["sector_economico"] if "sector_economico" in ranked else ["N/D"] * len(ranked),
            ranked["total_fob_usd"] if "total_fob_usd" in ranked else [0.0] * len(ranked),
            (ranked["total_peso_neto_kg"] / 1_000.0) if "total_peso_neto_kg" in ranked else [0.0] * len(ranked),
            precios,
        ),
        axis=-1,
    )

    hover_tpl = (
        "<b>%{y}</b><br>Código NANDINA: <b>%{customdata[0]}</b><br>Sector: <b>%{customdata[1]}</b><br>"
        "Valor FOB: <b>$%{customdata[2]:,.2f} USD</b><br>Volumen: <b>%{customdata[3]:,.1f} Ton</b><br>"
        "Precio Implícito: <b>$%{customdata[4]:,.2f} USD/kg</b><extra></extra>"
    )

    fig.add_trace(
        go.Bar(
            y=y_labels,
            x=x_vals,
            orientation="h",
            marker={"color": colors, "line": {"color": COLOR_BORDER, "width": 1}},
            customdata=customdata,
            hovertemplate=hover_tpl,
            text=[f"${v / 1_000_000:,.1f}M" if is_usd else f"{v:,.0f} Ton" for v in x_vals],
            textposition="auto",
        )
    )

    x_title = "Valor Exportado FOB (USD)" if is_usd else "Volumen Físico (Toneladas Métricas)"
    fig.update_layout(
        title=f"<b>Top {top_n} Productos ({'Valor FOB' if is_usd else 'Volumen Físico'})</b>",
        xaxis={"title": x_title, "gridcolor": "#334155", "showgrid": True},
        yaxis={"title": "", "autorange": True},
        template="plotly_dark",
        plot_bgcolor="#0F172A",
        paper_bgcolor="#1E293B",
        margin={"l": 20, "r": 20, "t": 50, "b": 30},
        height=460,
    )
    return fig


def build_sector_distribution_chart(
    df: pd.DataFrame,
    metric: str = "usd",
) -> go.Figure:
    """Genera un gráfico tipo Donut de distribución de exportaciones top por sector."""
    fig = go.Figure()
    if df.empty or "sector_economico" not in df:
        fig.add_annotation(
            text="Sin datos sectoriales disponibles",
            showarrow=False,
            font={"size": 14, "color": "#94A3B8"},
        )
        fig.update_layout(template="plotly_dark", height=380)
        return fig

    is_usd = metric == "usd"
    val_col = "total_fob_usd" if is_usd else "total_peso_neto_kg"
    if val_col not in df:
        return fig

    sec_df = pd.DataFrame(df.groupby("sector_economico", as_index=False)[val_col].sum()).sort_values(
        by=val_col, ascending=False
    )
    colors = [SECTOR_COLORS.get(str(s), "#64748B") for s in sec_df["sector_economico"]]

    val_fmt = "Valor FOB: <b>$%{value:,.2f} USD</b>" if is_usd else "Volumen: <b>%{value:,.0f} kg</b>"
    fig.add_trace(
        go.Pie(
            labels=sec_df["sector_economico"],
            values=sec_df[val_col],
            hole=0.55,
            marker={"colors": colors, "line": {"color": "#1E293B", "width": 2}},
            textinfo="percent+label",
            textposition="outside",
            hovertemplate=f"<b>%{{label}}</b><br>{val_fmt}<br>Participación: <b>%{{percent}}</b><extra></extra>",
        )
    )

    metric_lbl = "Valor FOB" if is_usd else "Volumen"
    fig.update_layout(
        title=f"<b>Distribución Sectorial ({metric_lbl})</b>",
        template="plotly_dark",
        plot_bgcolor="#0F172A",
        paper_bgcolor="#1E293B",
        showlegend=True,
        legend={"orientation": "h", "y": -0.1, "x": 0.5, "xanchor": "center"},
        margin={"l": 20, "r": 20, "t": 50, "b": 50},
        height=380,
    )
    return fig


def build_price_density_scatter(df: pd.DataFrame) -> go.Figure:
    """Genera un gráfico de dispersión Valor FOB (USD) vs. Volumen (Ton) con precio $/kg."""
    fig = go.Figure()
    if df.empty:
        fig.add_annotation(
            text="Sin registros disponibles para el diagrama de dispersión",
            showarrow=False,
            font={"size": 14, "color": "#94A3B8"},
        )
        fig.update_layout(template="plotly_dark", height=420)
        return fig

    grp_cols = ["codigo_nandina", "descripcion_producto"]
    if "sector_economico" in df:
        grp_cols.append("sector_economico")

    grouped = pd.DataFrame(df.groupby(grp_cols, as_index=False).agg({
        "total_fob_usd": "sum",
        "total_peso_neto_kg": "sum",
    }))
    grouped["volumen_ton"] = grouped["total_peso_neto_kg"] / 1_000.0
    grouped["precio_usd_kg"] = np.where(
        grouped["total_peso_neto_kg"] > 0,
        grouped["total_fob_usd"] / grouped["total_peso_neto_kg"],
        0.0,
    )

    sector_col = "sector_economico" if "sector_economico" in grouped else None
    sectors = grouped[sector_col].unique() if sector_col else ["Otros"]

    for sec in sectors:
        s_df = pd.DataFrame(grouped[grouped[sector_col] == sec]) if sector_col else grouped
        color = SECTOR_COLORS.get(str(sec), "#64748B")
        customdata = np.stack(
            (
                s_df["codigo_nandina"],
                s_df["descripcion_producto"],
                s_df["total_fob_usd"],
                s_df["volumen_ton"],
                s_df["precio_usd_kg"],
            ),
            axis=-1,
        )

        hover_tpl = (
            f"<b>%{{customdata[1]}}</b><br>Código NANDINA: <b>%{{customdata[0]}}</b><br>Sector: <b>{sec}</b><br>"
            "Valor FOB: <b>$%{customdata[2]:,.2f} USD</b><br>Volumen: <b>%{customdata[3]:,.1f} Ton</b><br>"
            "Precio Unitario Implícito: <b>$%{customdata[4]:,.2f} USD/kg</b><extra></extra>"
        )

        fig.add_trace(
            go.Scatter(
                x=s_df["volumen_ton"],
                y=s_df["total_fob_usd"],
                mode="markers+text",
                name=str(sec),
                text=[str(c) for c in s_df["codigo_nandina"]],
                textposition="top center",
                marker={
                    "size": np.clip(np.log1p(s_df["precio_usd_kg"]) * 8 + 8, 10, 40),
                    "color": color,
                    "opacity": 0.85,
                    "line": {"color": "#F8FAFC", "width": 1},
                },
                customdata=customdata,
                hovertemplate=hover_tpl,
            )
        )

    fig.update_layout(
        title="<b>Relación Valor FOB (USD) vs. Volumen Físico (Toneladas)</b>",
        xaxis={"title": "Volumen Físico (Toneladas)", "gridcolor": "#334155", "type": "log"},
        yaxis={"title": "Valor Exportado FOB (USD)", "gridcolor": "#334155", "type": "log"},
        template="plotly_dark",
        plot_bgcolor="#0F172A",
        paper_bgcolor="#1E293B",
        legend={"orientation": "h", "y": -0.15, "x": 0.5, "xanchor": "center"},
        margin={"l": 20, "r": 20, "t": 50, "b": 50},
        height=450,
    )
    return fig


def build_top_products_evolution_chart(
    df: pd.DataFrame,
    metric: str = "usd",
    top_n: int = 5,
) -> go.Figure:
    """Genera un gráfico multiserie de la evolución histórica interanual de los Top N productos."""
    fig = go.Figure()
    if df.empty or "anio" not in df:
        fig.add_annotation(
            text="Sin registros interanuales suficientes para trazar la evolución histórica",
            showarrow=False,
            font={"size": 14, "color": "#94A3B8"},
        )
        fig.update_layout(template="plotly_dark", height=420)
        return fig

    is_usd = metric == "usd"
    val_col = "total_fob_usd" if is_usd else "total_peso_neto_kg"

    top_codes = (
        pd.Series(df.groupby("codigo_nandina")[val_col].sum())
        .sort_values(ascending=False)
        .head(top_n)
        .index.tolist()
    )

    palette = ["#10B981", "#3B82F6", "#F59E0B", "#EC4899", "#8B5CF6", "#14B8A6"]

    for idx, code in enumerate(top_codes):
        prod_df = pd.DataFrame(df[df["codigo_nandina"] == code]).sort_values(by="anio")
        if prod_df.empty:
            continue

        prod_desc = str(prod_df.iloc[0]["descripcion_producto"])
        label = f"{prod_desc[:30]}... ({code})" if len(prod_desc) > 30 else f"{prod_desc} ({code})"
        color = palette[idx % len(palette)]
        y_vals = prod_df["total_fob_usd"] if is_usd else (prod_df["total_peso_neto_kg"] / 1_000.0)
        val_hover = "Valor FOB: <b>$%{y:,.2f} USD</b>" if is_usd else "Volumen: <b>%{y:,.1f} Ton</b>"

        fig.add_trace(
            go.Scatter(
                x=prod_df["anio"],
                y=y_vals,
                mode="lines+markers",
                name=label,
                line={"color": color, "width": 3},
                marker={"size": 7, "color": color},
                hovertemplate=f"<b>{label}</b><br>Año: <b>%{{x}}</b><br>{val_hover}<extra></extra>",
            )
        )

    y_title = "Valor FOB (USD)" if is_usd else "Volumen (Toneladas)"
    fig.update_layout(
        title=f"<b>Evolución Interanual de Top {top_n} Productos ({'Valor FOB' if is_usd else 'Volumen'})</b>",
        xaxis={"title": "Gestión Anual", "gridcolor": "#334155", "dtick": 1},
        yaxis={"title": y_title, "gridcolor": "#334155", "showgrid": True},
        template="plotly_dark",
        plot_bgcolor="#0F172A",
        paper_bgcolor="#1E293B",
        legend={"orientation": "h", "y": -0.2, "x": 0.5, "xanchor": "center"},
        margin={"l": 20, "r": 20, "t": 50, "b": 60},
        height=450,
    )
    return fig
