"""InsightBolivia — Componentes y gráficos para el Dashboard de Benchmark Regional.

Contiene funciones de agregación, cálculo de KPIs y generadores de gráficos Plotly
para el módulo `05_benchmark_regional.py`.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import plotly.graph_objects as go

# ==============================================================================
# Constantes, Metadatos de Indicadores y Paletas de Colores
# ==============================================================================
DEFAULT_BENCHMARK_COUNTRIES: list[str] = [
    "BOL", "PER", "CHL", "COL", "PRY", "BRA", "ARG", "ECU", "URY"
]

COUNTRY_NAMES_ES: dict[str, str] = {
    "BOL": "Bolivia", "PER": "Perú", "CHL": "Chile", "COL": "Colombia",
    "PRY": "Paraguay", "BRA": "Brasil", "ARG": "Argentina", "ECU": "Ecuador",
    "URY": "Uruguay", "VEN": "Venezuela", "MEX": "México",
}

COUNTRY_FLAGS: dict[str, str] = {
    "BOL": "🇧🇴", "PER": "🇵🇪", "CHL": "🇨🇱", "COL": "🇨🇴", "PRY": "🇵🇾",
    "BRA": "🇧🇷", "ARG": "🇦🇷", "ECU": "🇪🇨", "URY": "🇺🇾", "VEN": "🇻🇪", "MEX": "🇲🇽",
}

COUNTRY_COLORS: dict[str, str] = {
    "BOL": "#10B981", "PER": "#EF4444", "CHL": "#3B82F6", "COL": "#F59E0B",
    "PRY": "#8B5CF6", "BRA": "#06B6D4", "ARG": "#EC4899", "ECU": "#14B8A6",
    "URY": "#6366F1", "VEN": "#F97316", "MEX": "#84CC16",
}

COLOR_BOLIVIA = "#10B981"
COLOR_REGIONAL_AVG = "#94A3B8"
COLOR_BACKGROUND = "#0F172A"
COLOR_CARD = "#1E293B"
COLOR_GRID = "#334155"

INDICATOR_METADATA: dict[str, dict[str, str]] = {
    "NE.EXP.GNFS.KD.ZG": {
        "nombre": "Crecimiento de Exportaciones",
        "unidad": "%",
        "descripcion": "Tasa anual de crecimiento de exportaciones de bienes y servicios",
    },
    "NY.GDP.MKTP.KD.ZG": {
        "nombre": "Crecimiento del PIB",
        "unidad": "%",
        "descripcion": "Tasa anual de crecimiento porcentual del PIB",
    },
    "FP.CPI.TOTL.ZG": {
        "nombre": "Inflación al Consumidor",
        "unidad": "%",
        "descripcion": "Tasa de inflación anual según el IPC",
    },
    "NE.TRD.GNFS.ZS": {
        "nombre": "Apertura Comercial",
        "unidad": "% del PIB",
        "descripcion": "Comercio exterior total como % del PIB",
    },
    "NY.GDP.MKTP.CD": {
        "nombre": "PIB a Precios Actuales",
        "unidad": "USD",
        "descripcion": "PIB en dólares corrientes",
    },
    "NE.EXP.GNFS.CD": {
        "nombre": "Exportaciones Totales",
        "unidad": "USD",
        "descripcion": "Exportaciones en dólares corrientes",
    },
    "NE.IMP.GNFS.CD": {
        "nombre": "Importaciones Totales",
        "unidad": "USD",
        "descripcion": "Importaciones en dólares corrientes",
    },
    "NE.IMP.GNFS.KD.ZG": {
        "nombre": "Crecimiento de Importaciones",
        "unidad": "%",
        "descripcion": "Tasa anual de crecimiento de importaciones",
    },
}


def format_indicator_value(val: float | None, unit: str = "%") -> str:
    """Formatea un valor de indicador macroeconómico según su unidad de medida."""
    if val is None or (isinstance(val, (float, int)) and (np.isnan(val) or pd.isna(val))):
        return "N/D"
    if unit in ("%", "% del PIB"):
        return f"{val:+.2f}%" if abs(val) > 0.001 else f"{val:.2f}%"
    if unit == "USD":
        abs_val = abs(val)
        if abs_val >= 1_000_000_000:
            return f"${val / 1_000_000_000:,.2f} B"
        if abs_val >= 1_000_000:
            return f"${val / 1_000_000:,.2f} M"
        return f"${val:,.2f}"
    return f"{val:,.2f} {unit}"


def compute_benchmark_kpis(
    df: pd.DataFrame,
    indicator_code: str = "NE.EXP.GNFS.KD.ZG",
    target_year: int = 2023,
) -> dict[str, Any]:
    """Calcula las métricas de desempeño y comparación regional de Bolivia."""
    default_result: dict[str, Any] = {
        "bolivia_value": None, "regional_avg": 0.0, "delta_vs_avg": None,
        "bolivia_rank": None, "total_countries": 0, "best_country_iso": "N/D",
        "best_country_name": "N/D", "best_value": None, "bolivia_prev_value": None,
        "bolivia_yoy_delta": None, "unit": INDICATOR_METADATA.get(indicator_code, {}).get("unidad", "%"),
        "indicator_name": INDICATOR_METADATA.get(indicator_code, {}).get("nombre", indicator_code),
        "target_year": target_year,
    }
    if df.empty:
        return default_result

    df_ind = df[df["codigo_indicador"] == indicator_code]
    if df_ind.empty:
        return default_result

    df_year = df_ind[df_ind["anio"] == target_year].dropna(subset=["valor"])
    if df_year.empty:
        return default_result

    regional_avg = float(df_year["valor"].mean())
    default_result["regional_avg"] = regional_avg
    default_result["total_countries"] = len(df_year)

    df_sorted = df_year.sort_values(by="valor", ascending=False).reset_index(drop=True)
    best_row = df_sorted.iloc[0]
    default_result["best_country_iso"] = str(best_row["pais_iso"])
    default_result["best_country_name"] = str(best_row.get("pais_nombre", best_row["pais_iso"]))
    default_result["best_value"] = float(best_row["valor"])

    bol_row = df_year[df_year["pais_iso"] == "BOL"]
    if not bol_row.empty:
        bol_val = float(bol_row.iloc[0]["valor"])
        default_result["bolivia_value"] = bol_val
        default_result["delta_vs_avg"] = bol_val - regional_avg
        rank_idx = df_sorted.index[df_sorted["pais_iso"] == "BOL"].tolist()
        if rank_idx:
            default_result["bolivia_rank"] = rank_idx[0] + 1

    df_prev = df_ind[(df_ind["anio"] == target_year - 1) & (df_ind["pais_iso"] == "BOL")]
    if not df_prev.empty and pd.notna(df_prev.iloc[0]["valor"]):
        bol_prev = float(df_prev.iloc[0]["valor"])
        default_result["bolivia_prev_value"] = bol_prev
        if default_result["bolivia_value"] is not None:
            default_result["bolivia_yoy_delta"] = default_result["bolivia_value"] - bol_prev

    return default_result


def build_time_series_chart(
    df: pd.DataFrame,
    indicator_code: str = "NE.EXP.GNFS.KD.ZG",
    selected_countries: list[str] | None = None,
    show_regional_avg: bool = True,
) -> go.Figure:
    """Genera un gráfico interactivo multilínea de evolución temporal del indicador."""
    fig = go.Figure()
    if df.empty:
        fig.update_layout(paper_bgcolor=COLOR_CARD, plot_bgcolor=COLOR_BACKGROUND)
        return fig

    countries = selected_countries or DEFAULT_BENCHMARK_COUNTRIES
    df_ind = df[(df["codigo_indicador"] == indicator_code) & (df["pais_iso"].isin(countries))].copy()
    if df_ind.empty:
        return fig

    meta = INDICATOR_METADATA.get(indicator_code, {"nombre": indicator_code, "unidad": "%"})
    unit = meta.get("unidad", "%")

    if show_regional_avg:
        df_avg = pd.DataFrame(df_ind.groupby("anio", as_index=False)["valor"].mean()).sort_values(by="anio")
        fig.add_trace(go.Scatter(
            x=df_avg["anio"], y=df_avg["valor"], mode="lines", name="Promedio Regional",
            line={"color": COLOR_REGIONAL_AVG, "width": 2, "dash": "dash"},
            hovertemplate="<b>Promedio Regional</b><br>Año: %{x}<br>Valor: %{y:.2f} " + unit + "<extra></extra>",
        ))

    for c_iso in countries:
        if c_iso == "BOL":
            continue
        df_c = df_ind[df_ind["pais_iso"] == c_iso].sort_values(by="anio")
        if df_c.empty:
            continue
        c_name = COUNTRY_NAMES_ES.get(c_iso, c_iso)
        c_flag = COUNTRY_FLAGS.get(c_iso, "")
        c_color = COUNTRY_COLORS.get(c_iso, "#64748B")
        fig.add_trace(go.Scatter(
            x=df_c["anio"], y=df_c["valor"], mode="lines+markers", name=f"{c_flag} {c_name}",
            line={"color": c_color, "width": 1.8}, marker={"size": 4, "color": c_color},
            hovertemplate=f"<b>{c_flag} {c_name}</b><br>Año: %{{x}}<br>Valor: %{{y:.2f}} {unit}<extra></extra>",
        ))

    df_bol = df_ind[df_ind["pais_iso"] == "BOL"].sort_values(by="anio")
    if not df_bol.empty:
        fig.add_trace(go.Scatter(
            x=df_bol["anio"], y=df_bol["valor"], mode="lines+markers", name="🇧🇴 Bolivia",
            line={"color": COLOR_BOLIVIA, "width": 3.8}, marker={"size": 8, "color": COLOR_BOLIVIA},
            hovertemplate=f"<b>🇧🇴 Bolivia</b><br>Año: %{{x}}<br>Valor: %{{y:.2f}} {unit}<extra></extra>",
        ))

    title_text = f"<b>Evolución Comparativa: {meta['nombre']}</b> ({unit})"
    fig.update_layout(
        title={"text": title_text, "font": {"color": "#F8FAFC", "size": 16}},
        paper_bgcolor=COLOR_CARD, plot_bgcolor=COLOR_BACKGROUND, font={"color": "#94A3B8"},
        xaxis={"gridcolor": COLOR_GRID, "title": "Año", "dtick": 1 if len(df_ind["anio"].unique()) <= 15 else 2},
        yaxis={"gridcolor": COLOR_GRID, "title": f"{meta['nombre']} ({unit})", "zerolinecolor": "#475569"},
        hovermode="x unified", legend={"orientation": "h", "y": -0.2, "x": 0.5, "xanchor": "center"},
        margin={"l": 40, "r": 20, "t": 60, "b": 60},
    )
    return fig


def build_ranking_bar_chart(
    df: pd.DataFrame,
    indicator_code: str = "NE.EXP.GNFS.KD.ZG",
    target_year: int = 2023,
    selected_countries: list[str] | None = None,
) -> go.Figure:
    """Genera un gráfico de barras horizontales ordenado con ranking regional."""
    fig = go.Figure()
    if df.empty:
        return fig

    countries = selected_countries or DEFAULT_BENCHMARK_COUNTRIES
    mask = (
        (df["codigo_indicador"] == indicator_code)
        & (df["anio"] == target_year)
        & (df["pais_iso"].isin(countries))
    )
    df_f = df[mask].copy()
    df_f = df_f[df_f["valor"].notna()]
    if df_f.empty:
        return fig

    df_sorted = df_f.sort_values(by="valor", ascending=True)
    meta = INDICATOR_METADATA.get(indicator_code, {"nombre": indicator_code, "unidad": "%"})
    unit = meta.get("unidad", "%")

    bar_colors = [
        COLOR_BOLIVIA if iso == "BOL" else COUNTRY_COLORS.get(iso, "#64748B")
        for iso in df_sorted["pais_iso"]
    ]
    labels = [
        f"{COUNTRY_FLAGS.get(iso, '')} {COUNTRY_NAMES_ES.get(iso, iso)}"
        for iso in df_sorted["pais_iso"]
    ]

    fig.add_trace(go.Bar(
        y=labels, x=df_sorted["valor"], orientation="h",
        marker={"color": bar_colors, "line": {"color": "#1E293B", "width": 1}},
        text=[f"{v:.2f} {unit}" for v in df_sorted["valor"]], textposition="auto",
        hovertemplate="<b>%{y}</b><br>Valor: %{x:.2f} " + unit + "<extra></extra>",
    ))

    avg_val = float(df_sorted["valor"].mean())
    fig.add_vline(
        x=avg_val, line_dash="dash", line_color=COLOR_REGIONAL_AVG,
        annotation_text=f"Promedio: {avg_val:.2f} {unit}", annotation_position="top right",
        annotation_font_color=COLOR_REGIONAL_AVG,
    )
    title_text = f"<b>Ranking Regional ({target_year}): {meta['nombre']}</b>"
    fig.update_layout(
        title={"text": title_text, "font": {"color": "#F8FAFC", "size": 15}},
        paper_bgcolor=COLOR_CARD, plot_bgcolor=COLOR_BACKGROUND, font={"color": "#94A3B8"},
        xaxis={"gridcolor": COLOR_GRID, "title": f"Valor ({unit})"}, yaxis={"gridcolor": "rgba(0,0,0,0)"},
        margin={"l": 120, "r": 30, "t": 50, "b": 40},
    )
    return fig


def build_quadrant_scatter_chart(
    df: pd.DataFrame,
    x_indicator: str = "NY.GDP.MKTP.KD.ZG",
    y_indicator: str = "NE.EXP.GNFS.KD.ZG",
    target_year: int = 2023,
    selected_countries: list[str] | None = None,
) -> go.Figure:
    """Genera una matriz de dispersión en 4 cuadrantes (ej: Crecimiento PIB vs Crecimiento Exportaciones)."""
    fig = go.Figure()
    if df.empty:
        return fig

    countries = selected_countries or DEFAULT_BENCHMARK_COUNTRIES
    df_y = df[(df["anio"] == target_year) & (df["pais_iso"].isin(countries))].copy()
    df_x = df_y[df_y["codigo_indicador"] == x_indicator][["pais_iso", "valor"]].rename(columns={"valor": "x_val"})
    df_y_val = df_y[df_y["codigo_indicador"] == y_indicator][["pais_iso", "valor"]].rename(columns={"valor": "y_val"})
    merged = pd.merge(df_x, df_y_val, on="pais_iso").dropna()
    if merged.empty:
        return fig

    meta_x = INDICATOR_METADATA.get(x_indicator, {"nombre": x_indicator, "unidad": "%"})
    meta_y = INDICATOR_METADATA.get(y_indicator, {"nombre": y_indicator, "unidad": "%"})
    x_mean = float(merged["x_val"].mean())
    y_mean = float(merged["y_val"].mean())

    fig.add_vline(x=x_mean, line_dash="dot", line_color=COLOR_GRID)
    fig.add_hline(y=y_mean, line_dash="dot", line_color=COLOR_GRID)

    for _, row in merged.iterrows():
        c_iso = str(row["pais_iso"])
        is_bol = c_iso == "BOL"
        c_name = COUNTRY_NAMES_ES.get(c_iso, c_iso)
        c_flag = COUNTRY_FLAGS.get(c_iso, "")
        c_color = COLOR_BOLIVIA if is_bol else COUNTRY_COLORS.get(c_iso, "#64748B")
        hover_str = (
            f"<b>{c_flag} {c_name} ({target_year})</b><br>"
            f"{meta_x['nombre']}: %{{x:.2f}} {meta_x['unidad']}<br>"
            f"{meta_y['nombre']}: %{{y:.2f}} {meta_y['unidad']}<extra></extra>"
        )
        fig.add_trace(go.Scatter(
            x=[row["x_val"]], y=[row["y_val"]], mode="markers+text", name=f"{c_flag} {c_name}",
            text=[f"<b>{c_flag} {c_name}</b>" if is_bol else f"{c_flag} {c_iso}"], textposition="top center",
            marker={
                "size": 16 if is_bol else 11, "color": c_color,
                "line": {"color": "#FFFFFF" if is_bol else "#1E293B", "width": 2 if is_bol else 1},
            },
            hovertemplate=hover_str,
        ))

    title_text = f"<b>Posicionamiento Macroeconómico ({target_year}): {meta_x['nombre']} vs {meta_y['nombre']}</b>"
    fig.update_layout(
        title={"text": title_text, "font": {"color": "#F8FAFC", "size": 15}},
        paper_bgcolor=COLOR_CARD, plot_bgcolor=COLOR_BACKGROUND, font={"color": "#94A3B8"},
        xaxis={"gridcolor": COLOR_GRID, "title": f"{meta_x['nombre']} ({meta_x['unidad']})"},
        yaxis={"gridcolor": COLOR_GRID, "title": f"{meta_y['nombre']} ({meta_y['unidad']})"},
        showlegend=False, margin={"l": 50, "r": 30, "t": 60, "b": 50},
    )
    return fig


def build_multidimensional_radar_chart(
    df: pd.DataFrame,
    target_year: int = 2023,
    compare_country: str = "PER",
) -> go.Figure:
    """Genera un gráfico de radar comparando el perfil multidimensional de Bolivia vs un país par."""
    fig = go.Figure()
    if df.empty:
        return fig

    radar_indicators = ["NE.EXP.GNFS.KD.ZG", "NY.GDP.MKTP.KD.ZG", "FP.CPI.TOTL.ZG", "NE.TRD.GNFS.ZS"]
    categories = [INDICATOR_METADATA.get(code, {}).get("nombre", code) for code in radar_indicators]
    df_y = df[(df["anio"] == target_year) & (df["codigo_indicador"].isin(radar_indicators))].copy()
    if df_y.empty:
        return fig

    def get_values_for_country(c_iso: str) -> list[float]:
        vals = []
        for code in radar_indicators:
            sub = df_y[(df_y["pais_iso"] == c_iso) & (df_y["codigo_indicador"] == code)]
            vals.append(float(sub.iloc[0]["valor"]) if not sub.empty and pd.notna(sub.iloc[0]["valor"]) else 0.0)
        return vals + [vals[0]]

    avg_vals = [
        float(df_y[df_y["codigo_indicador"] == code]["valor"].mean())
        if not df_y[df_y["codigo_indicador"] == code].empty else 0.0
        for code in radar_indicators
    ]
    avg_vals.append(avg_vals[0])
    radar_cats = categories + [categories[0]]

    fig.add_trace(go.Scatterpolar(
        r=avg_vals, theta=radar_cats, fill="toself", name="Promedio Regional",
        line={"color": COLOR_REGIONAL_AVG, "dash": "dash"}, fillcolor="rgba(148, 163, 184, 0.15)"
    ))
    comp_vals = get_values_for_country(compare_country)
    comp_name = COUNTRY_NAMES_ES.get(compare_country, compare_country)
    fig.add_trace(go.Scatterpolar(
        r=comp_vals, theta=radar_cats, fill="toself",
        name=f"{COUNTRY_FLAGS.get(compare_country, '')} {comp_name}",
        line={"color": COUNTRY_COLORS.get(compare_country, '#3B82F6')},
        fillcolor="rgba(59, 130, 246, 0.2)"
    ))
    bol_vals = get_values_for_country("BOL")
    fig.add_trace(go.Scatterpolar(
        r=bol_vals, theta=radar_cats, fill="toself", name="🇧🇴 Bolivia",
        line={"color": COLOR_BOLIVIA, "width": 2.5}, fillcolor="rgba(16, 185, 129, 0.25)"
    ))

    fig.update_layout(
        polar={
            "bgcolor": COLOR_BACKGROUND,
            "radialaxis": {"visible": True, "gridcolor": COLOR_GRID, "linecolor": COLOR_GRID},
            "angularaxis": {"gridcolor": COLOR_GRID, "linecolor": COLOR_GRID}
        },
        paper_bgcolor=COLOR_CARD, font={"color": "#94A3B8"},
        title={
            "text": f"<b>Perfil Macroeconómico Multidimensional ({target_year})</b>",
            "font": {"color": "#F8FAFC", "size": 15},
        },
        legend={"orientation": "h", "y": -0.15, "x": 0.5, "xanchor": "center"},
        margin={"l": 40, "r": 40, "t": 50, "b": 50},
    )
    return fig


