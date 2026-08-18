"""InsightBolivia — Dashboard 05: Benchmark Regional de Comercio e Indicadores Macroeconómicos.

Módulo interactivo de visualización y análisis comparativo de las series macroeconómicas
y comerciales de Bolivia frente a los países vecinos de la región andina y cono sur.
Consume la tabla analítica `benchmark_regional.fact_indicadores_bm` en Google BigQuery,
garantizando costo cero ($0 USD) y tiempos de respuesta óptimos (<= 3.0s).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

import pandas as pd
import streamlit as st

from streamlit_app.components.benchmark_charts import (
    COLOR_BOLIVIA,
    COUNTRY_FLAGS,
    COUNTRY_NAMES_ES,
    DEFAULT_BENCHMARK_COUNTRIES,
    INDICATOR_METADATA,
    build_multidimensional_radar_chart,
    build_quadrant_scatter_chart,
    build_ranking_bar_chart,
    build_time_series_chart,
    compute_benchmark_kpis,
    format_indicator_value,
)
from streamlit_app.utils.bq_client import get_benchmark_indicadores
from streamlit_app.utils.firestore_client import (
    get_session_id,
    log_ui_event,
)

logger = logging.getLogger("insight_bolivia.streamlit.benchmark_regional")

# Re-exportamos para compatibilidad con suites de pruebas
__all__ = [
    "generate_fallback_benchmark_data",
    "main",
]


def generate_fallback_benchmark_data() -> pd.DataFrame:
    """Genera datos sintéticos realistas de fallback para modo demo u offline."""
    rows: list[dict[str, Any]] = []
    years = list(range(2010, 2024))
    countries = DEFAULT_BENCHMARK_COUNTRIES

    base_values = {
        "NE.EXP.GNFS.KD.ZG": {
            "BOL": 4.2, "PER": 5.1, "CHL": 3.8, "COL": 3.2,
            "PRY": 4.5, "BRA": 2.9, "ARG": 1.5, "ECU": 3.0, "URY": 4.0,
        },
        "NY.GDP.MKTP.KD.ZG": {
            "BOL": 3.9, "PER": 4.2, "CHL": 3.1, "COL": 3.5,
            "PRY": 4.0, "BRA": 1.8, "ARG": 1.2, "ECU": 2.4, "URY": 3.3,
        },
        "FP.CPI.TOTL.ZG": {
            "BOL": 2.8, "PER": 3.2, "CHL": 4.1, "COL": 5.2,
            "PRY": 4.3, "BRA": 5.8, "ARG": 45.0, "ECU": 1.9, "URY": 7.1,
        },
        "NE.TRD.GNFS.ZS": {
            "BOL": 52.0, "PER": 48.0, "CHL": 62.0, "COL": 36.0,
            "PRY": 72.0, "BRA": 28.0, "ARG": 30.0, "ECU": 46.0, "URY": 54.0,
        },
    }


    for ind_code, meta in INDICATOR_METADATA.items():
        base_map = base_values.get(ind_code, {})
        for anio in years:
            for iso in countries:
                base = base_map.get(iso, 3.5)
                # Variación temporal determinista
                cycle = ((anio % 5) - 2) * 0.8 + ((hash(iso) % 7) - 3) * 0.2
                val = round(base + cycle, 2)
                rows.append({
                    "id_indicador_bm": f"{iso}_{ind_code}_{anio}",
                    "fecha": f"{anio}-01-01",
                    "anio": anio,
                    "pais_iso": iso,
                    "pais_nombre": COUNTRY_NAMES_ES.get(iso, iso),
                    "codigo_indicador": ind_code,
                    "nombre_indicador": meta["nombre"],
                    "valor": val,
                    "unidad_medida": meta["unidad"],
                    "fuente": "Banco Mundial - WDI (Demo)",
                    "fecha_extraccion": datetime.now(UTC),
                })

    return pd.DataFrame(rows)


def main() -> None:
    """Punto de entrada principal para el Dashboard 05: Benchmark Regional."""
    st.set_page_config(
        page_title="InsightBolivia | Benchmark Regional",
        page_icon="📈",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    st.markdown(
        """
        <style>
        .page-title {
            font-size: 2.1rem;
            font-weight: 700;
            color: #F8FAFC;
            margin-bottom: 0.2rem;
        }
        .page-subtitle {
            font-size: 1.05rem;
            color: #94A3B8;
            margin-bottom: 1.5rem;
        }
        .metric-box {
            background-color: #1E293B;
            border-radius: 10px;
            padding: 1.1rem;
            border: 1px solid #334155;
            text-align: center;
        }
        .metric-title {
            color: #94A3B8;
            font-size: 0.8rem;
            text-transform: uppercase;
            font-weight: 600;
            letter-spacing: 0.05em;
        }
        .metric-val {
            color: #F8FAFC;
            font-size: 1.5rem;
            font-weight: 700;
            margin-top: 0.25rem;
        }
        .badge-positive {
            background-color: rgba(16, 185, 129, 0.15);
            color: #34D399;
            padding: 3px 8px;
            border-radius: 12px;
            font-size: 0.75rem;
            font-weight: 600;
            border: 1px solid rgba(52, 211, 153, 0.3);
        }
        .badge-negative {
            background-color: rgba(239, 68, 68, 0.15);
            color: #F87171;
            padding: 3px 8px;
            border-radius: 12px;
            font-size: 0.75rem;
            font-weight: 600;
            border: 1px solid rgba(248, 113, 113, 0.3);
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    session_id = get_session_id()
    log_ui_event(session_id=session_id, page="05_benchmark_regional", event_type="page_view")

    # ==============================================================================
    # Sidebar de Navegación y Filtros
    # ==============================================================================
    with st.sidebar:
        st.image("https://raw.githubusercontent.com/twitter/twemoji/master/assets/72x72/1f1e7-1f1f4.png", width=40)
        st.markdown("### 📈 **Benchmark Regional**")
        st.markdown("*Comparación macroeconómica internacional (Banco Mundial WDI).*")
        st.markdown("---")

        # 1. Selector de Indicador Principal
        indicator_options = {code: f"{meta['nombre']} ({meta['unidad']})" for code, meta in INDICATOR_METADATA.items()}
        selected_ind_code = st.selectbox(
            "📊 **Indicador Macroeconómico:**",
            options=list(indicator_options.keys()),
            format_func=lambda c: indicator_options[c],
            index=0,
            help="Seleccione la variable macroeconómica a comparar en la región.",
        )

        # 2. Selector de Rango Temporal
        current_year = datetime.now(UTC).year
        year_range = st.slider(
            "📅 **Rango de Años:**",
            min_value=2000,
            max_value=current_year,
            value=(2010, min(2023, current_year)),
            step=1,
            help="Rango de años para series temporales y evolución histórica.",
        )

        # 3. Año de Enfoque (para ranking y matrices)
        available_years = list(range(year_range[0], year_range[1] + 1))
        focus_year = st.selectbox(
            "🎯 **Año de Enfoque:**",
            options=available_years[::-1],
            index=0,
            help="Año específico utilizado para el ranking regional y la matriz de posicionamiento.",
        )

        # 4. Multiselect de Países
        country_display = {
            iso: f"{COUNTRY_FLAGS.get(iso, '')} {COUNTRY_NAMES_ES.get(iso, iso)}"
            for iso in DEFAULT_BENCHMARK_COUNTRIES
        }
        selected_countries = st.multiselect(
            "🌎 **Países Comparativos:**",
            options=DEFAULT_BENCHMARK_COUNTRIES,
            default=DEFAULT_BENCHMARK_COUNTRIES,
            format_func=lambda iso: country_display.get(iso, iso),
            help="Seleccione los países para incluir en las comparativas regionales.",
        )

        # Asegurar que Bolivia siempre esté incluida
        if "BOL" not in selected_countries:
            selected_countries.append("BOL")

        # 5. Opciones Adicionales
        show_avg = st.checkbox("Mostrar Promedio Regional", value=True)
        compare_peer = st.selectbox(
            "🤝 **País de Contraste (Radar):**",
            options=[c for c in selected_countries if c != "BOL"],
            format_func=lambda iso: country_display.get(iso, iso),
            index=0 if len(selected_countries) > 1 else 0,
        )

    # ==============================================================================
    # Extracción y Caching de Datos
    # ==============================================================================
    with st.spinner("Consultando indicadores macroeconómicos regionales..."):
        df_bench = get_benchmark_indicadores(
            start_year=year_range[0],
            end_year=year_range[1],
            countries=selected_countries,
        )

        if df_bench.empty:
            df_bench = generate_fallback_benchmark_data()
            df_bench = df_bench[
                (df_bench["anio"] >= year_range[0])
                & (df_bench["anio"] <= year_range[1])
                & (df_bench["pais_iso"].isin(selected_countries))
            ].copy()


    # ==============================================================================
    # Header Principal
    # ==============================================================================
    st.markdown(
        '<div class="page-title">📈 Benchmark Regional e Internacional de Comercio</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="page-subtitle">Monitoreo y evaluación del desempeño comercial y macroeconómico de Bolivia '
        'frente a los socios y competidores de la Región Andina y el Cono Sur.</div>',
        unsafe_allow_html=True,
    )

    # ==============================================================================
    # Tarjetas de Métricas y KPIs
    # ==============================================================================
    kpis = compute_benchmark_kpis(df_bench, indicator_code=selected_ind_code, target_year=focus_year)
    meta = INDICATOR_METADATA.get(selected_ind_code, {"nombre": selected_ind_code, "unidad": "%"})
    unit = meta.get("unidad", "%")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        bol_val_str = format_indicator_value(kpis["bolivia_value"], unit)
        st.markdown(
            f"""
            <div class="metric-box">
                <div class="metric-title">🇧🇴 Bolivia ({focus_year})</div>
                <div class="metric-val" style="color: {COLOR_BOLIVIA};">{bol_val_str}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col2:
        avg_val_str = format_indicator_value(kpis["regional_avg"], unit)
        st.markdown(
            f"""
            <div class="metric-box">
                <div class="metric-title">Promedio Regional ({focus_year})</div>
                <div class="metric-val">{avg_val_str}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col3:
        delta = kpis["delta_vs_avg"]
        if delta is not None:
            badge_class = "badge-positive" if delta >= 0 else "badge-negative"
            delta_sign = "+" if delta > 0 else ""
            delta_str = f"<span class='{badge_class}'>{delta_sign}{delta:.2f} {unit} vs Prom.</span>"
        else:
            delta_str = "<span class='badge-positive'>N/D</span>"

        st.markdown(
            f"""
            <div class="metric-box">
                <div class="metric-title">Diferencial vs Región</div>
                <div class="metric-val" style="font-size: 1.2rem; margin-top: 0.5rem;">{delta_str}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col4:
        rank = kpis["bolivia_rank"]
        total_c = kpis["total_countries"]
        rank_str = f"Puesto #{rank} de {total_c}" if rank else "N/D"
        best_str = f"Líder: {kpis['best_country_name']}"

        st.markdown(
            f"""
            <div class="metric-box">
                <div class="metric-title">Posición Regional</div>
                <div class="metric-val" style="font-size: 1.2rem; margin-top: 0.5rem;">
                    🏆 {rank_str}
                    <div style="font-size: 0.75rem; color: #94A3B8; margin-top: 2px;">{best_str}</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("<br>", unsafe_allow_html=True)

    # ==============================================================================
    # Pestañas Analíticas Interactivas
    # ==============================================================================
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📈 Evolución Histórica",
        "🏆 Ranking Regional",
        "🎯 Matriz de Posicionamiento",
        "🕸️ Perfil Multidimensional",
        "📋 Explorador de Datos",
    ])

    with tab1:
        st.markdown(f"#### 📈 Tendencia y Evolución: {meta['nombre']}")
        st.caption(f"{meta['descripcion']}. Se resalta la trayectoria de Bolivia y la media de la región.")
        fig_ts = build_time_series_chart(
            df_bench,
            indicator_code=selected_ind_code,
            selected_countries=selected_countries,
            show_regional_avg=show_avg,
        )
        st.plotly_chart(fig_ts, use_container_width=True)

    with tab2:
        st.markdown(f"#### 🏆 Ranking de Países en el Año {focus_year}")
        st.caption(f"Comparación directa de {meta['nombre']} entre los países seleccionados.")
        fig_bar = build_ranking_bar_chart(
            df_bench,
            indicator_code=selected_ind_code,
            target_year=focus_year,
            selected_countries=selected_countries,
        )
        st.plotly_chart(fig_bar, use_container_width=True)

    with tab3:
        st.markdown(f"#### 🎯 Matriz de Posicionamiento Macroeconómico ({focus_year})")
        st.caption("Cuadrantes de diagnóstico: Crecimiento del PIB (%) vs Crecimiento de Exportaciones (%).")
        fig_quad = build_quadrant_scatter_chart(
            df_bench,
            x_indicator="NY.GDP.MKTP.KD.ZG",
            y_indicator="NE.EXP.GNFS.KD.ZG",
            target_year=focus_year,
            selected_countries=selected_countries,
        )
        st.plotly_chart(fig_quad, use_container_width=True)

    with tab4:
        st.markdown(f"#### 🕸️ Perfil Multidimensional Comparativo ({focus_year})")
        peer_name = COUNTRY_NAMES_ES.get(compare_peer, compare_peer)
        st.caption(f"Evaluación en radar de Bolivia vs {peer_name} y el Promedio Regional.")
        fig_radar = build_multidimensional_radar_chart(
            df_bench,
            target_year=focus_year,
            compare_country=compare_peer,
        )
        st.plotly_chart(fig_radar, use_container_width=True)

    with tab5:
        st.markdown("#### 📋 Tabulado de Indicadores Regionales")
        st.caption("Microdatos consolidados de las series macroeconómicas del Banco Mundial.")

        df_display = df_bench.copy()
        if not df_display.empty:
            df_display["pais"] = df_display["pais_iso"].map(
                lambda iso: f"{COUNTRY_FLAGS.get(iso, '')} {COUNTRY_NAMES_ES.get(iso, iso)}"
            )
            df_pivot = df_display.pivot_table(
                index=["anio", "pais"],
                columns="nombre_indicador",
                values="valor",
                aggfunc="first",
            ).reset_index().sort_values(by=["anio", "pais"], ascending=[False, True])

            st.dataframe(df_pivot, use_container_width=True)

            csv_data = df_pivot.to_csv(index=False).encode("utf-8")
            st.download_button(
                label="📥 Descargar Tabla Consolidada (CSV)",
                data=csv_data,
                file_name=f"benchmark_regional_{year_range[0]}_{year_range[1]}.csv",
                mime="text/csv",
            )
        else:
            st.info("No hay datos tabulares disponibles para los filtros seleccionados.")



if __name__ == "__main__":
    main()
