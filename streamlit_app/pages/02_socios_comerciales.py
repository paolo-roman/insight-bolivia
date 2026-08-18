"""InsightBolivia — Dashboard 02: Socios Comerciales y Bloques de Integración.

Módulo interactivo de visualización y análisis geoespacial del comercio exterior de Bolivia.
Consume exclusivamente la vista analítica pre-agregada `comercio_exterior.vw_socios_comerciales`
en Google BigQuery, garantizando costo cero ($0 USD) y tiempos de carga óptimos.
"""

from __future__ import annotations

import logging
from datetime import datetime

import pandas as pd
import streamlit as st

from streamlit_app.components.socios_charts import (
    COLOR_EXPORT,
    COLOR_IMPORT,
    build_bloc_distribution_chart,
    build_choropleth_map,
    build_concentration_curve,
    build_partner_evolution_chart,
    build_top_partners_bar_chart,
    compute_socios_kpis,
    format_currency_millions,
)
from streamlit_app.utils.bq_client import (
    get_available_date_range,
    get_socios_comerciales,
)
from streamlit_app.utils.firestore_client import (
    get_session_id,
    log_ui_event,
)

logger = logging.getLogger("insight_bolivia.streamlit.socios_comerciales")

# Mapeo de alcance geográfico para Plotly Geo
SCOPE_MAP: dict[str, str] = {
    "Mundial (Global)": "world",
    "América del Sur (Sudamérica)": "south america",
    "América del Norte": "north america",
    "Europa": "europe",
    "Asia": "asia",
    "África": "africa",
}

__all__ = [
    "build_bloc_distribution_chart",
    "build_choropleth_map",
    "build_concentration_curve",
    "build_partner_evolution_chart",
    "build_top_partners_bar_chart",
    "compute_socios_kpis",
    "format_currency_millions",
    "main",
]


def main() -> None:
    """Punto de entrada principal para el Dashboard 02: Socios Comerciales."""
    st.set_page_config(
        page_title="InsightBolivia | Socios Comerciales y Bloques",
        page_icon="🌎",
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
        .badge-country {
            background-color: rgba(59, 130, 246, 0.15);
            color: #60A5FA;
            padding: 3px 8px;
            border-radius: 12px;
            font-size: 0.75rem;
            font-weight: 600;
            border: 1px solid rgba(96, 165, 250, 0.3);
        }
        .badge-bloc {
            background-color: rgba(245, 158, 11, 0.15);
            color: #FBBF24;
            padding: 3px 8px;
            border-radius: 12px;
            font-size: 0.75rem;
            font-weight: 600;
            border: 1px solid rgba(251, 191, 36, 0.3);
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    session_id = get_session_id()
    log_ui_event(session_id=session_id, page="02_socios_comerciales", event_type="page_view")

    st.markdown(
        '<div class="page-title">🌎 Principales Socios Comerciales y Bloques de Integración</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="page-subtitle">Distribución geográfica, flujos bilaterales e intercambio comercial '
        'de Bolivia por país y bloque económico consumiendo la vista analítica '
        '<code>vw_socios_comerciales</code>.</div>',
        unsafe_allow_html=True,
    )

    # --------------------------------------------------------------------------
    # Barra Lateral de Filtros
    # --------------------------------------------------------------------------
    with st.sidebar:
        st.markdown("### ⚙️ **Filtros de Socios**")

        # 1. Tipo de Operación
        flow_label = st.radio(
            "Flujo Comercial",
            options=["Exportaciones (FOB)", "Importaciones (CIF)"],
            index=0,
            help="Seleccione si desea analizar los países de destino (Exportaciones) o de origen (Importaciones).",
        )
        flow = "EXPORTACION" if "Exportaciones" in flow_label else "IMPORTACION"

        # 2. Rango de Años
        min_date, max_date = get_available_date_range()
        available_years = list(range(max_date.year, min_date.year - 1, -1))
        year_options = ["Todas las Gestiones (Consolidado)"] + [str(y) for y in available_years]

        selected_year_str = st.selectbox(
            "Gestión Anual",
            options=year_options,
            index=0,
            help="Filtre por un año específico o analice todo el histórico acumulado.",
        )
        selected_year = None if selected_year_str.startswith("Todas") else int(selected_year_str)

        # 3. Enfoque Geográfico para el Mapa
        scope_choice = st.selectbox(
            "Enfoque Geográfico del Mapa",
            options=list(SCOPE_MAP.keys()),
            index=0,
            help="Ajusta el zoom y encuadre territorial del mapa coroplético.",
        )
        plotly_scope = SCOPE_MAP.get(scope_choice, "world")

        # 4. Top N Países
        top_n = st.slider(
            "Top Países en Rankings",
            min_value=5,
            max_value=30,
            value=10,
            step=5,
            help="Número de socios comerciales a incluir en los gráficos de barras y tablas resumidas.",
        )

        st.markdown("---")
        st.markdown("ℹ️ **Fuente:** `comercio_exterior.vw_socios_comerciales`")
        st.markdown("⚡ **Costo de Consulta:** $0.00 USD (Capa Gratuita)")

    # --------------------------------------------------------------------------
    # Consulta a BigQuery (Cacheada @st.cache_data)
    # --------------------------------------------------------------------------
    with st.spinner("Consultando socios comerciales en BigQuery..."):
        df_raw = get_socios_comerciales(flow=flow, year=selected_year)

    if df_raw.empty:
        st.warning(
            f"⚠️ No se encontraron registros de socios comerciales para el flujo '{flow}' "
            f"y gestión '{selected_year_str}'. Intente seleccionar otra gestión."
        )
        return

    # Filtros adicionales en memoria (Continente / Bloque Comercial)
    all_continents = sorted(df_raw["continente"].dropna().unique().tolist()) if "continente" in df_raw else []
    all_blocs = sorted(df_raw["bloque_comercial"].dropna().unique().tolist()) if "bloque_comercial" in df_raw else []

    with st.sidebar:
        st.markdown("### 🌐 **Filtros por Bloque y Región**")
        selected_continents = st.multiselect(
            "Filtrar por Continente",
            options=all_continents,
            default=[],
            help="Dejar vacío para incluir todos los continentes.",
        )
        selected_blocs = st.multiselect(
            "Filtrar por Bloque Comercial",
            options=all_blocs,
            default=[],
            help="Dejar vacío para incluir todos los bloques comerciales (MERCOSUR, CAN, UE, etc.).",
        )

    df_filtered: pd.DataFrame = df_raw.copy()
    if selected_continents:
        df_filtered = pd.DataFrame(df_filtered[df_filtered["continente"].isin(selected_continents)])
    if selected_blocs:
        df_filtered = pd.DataFrame(df_filtered[df_filtered["bloque_comercial"].isin(selected_blocs)])

    if df_filtered.empty:
        st.warning("⚠️ No existen registros que coincidan con la combinación de continentes y bloques seleccionados.")
        return

    # --------------------------------------------------------------------------
    # KPIs Principales
    # --------------------------------------------------------------------------
    kpis = compute_socios_kpis(df_filtered, flow=flow)
    kcol1, kcol2, kcol3, kcol4 = st.columns(4)

    val_color = COLOR_EXPORT if flow == "EXPORTACION" else COLOR_IMPORT
    val_title = "Total Exportaciones FOB" if flow == "EXPORTACION" else "Total Importaciones CIF"

    with kcol1:
        st.markdown(
            f"""
            <div class="metric-box">
                <div class="metric-title">{val_title}</div>
                <div class="metric-val" style="color: {val_color};">
                    {format_currency_millions(kpis["total_valor_usd"])}
                </div>
                <div style="font-size: 0.75rem; color: #94A3B8; margin-top: 4px;">
                    {kpis["total_peso_ton"]:,.0f} Toneladas
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with kcol2:
        st.markdown(
            f"""
            <div class="metric-box">
                <div class="metric-title">Países Socios Activos</div>
                <div class="metric-val">
                    {kpis["num_paises"]}
                </div>
                <div style="font-size: 0.75rem; color: #94A3B8; margin-top: 4px;">
                    {kpis["total_transacciones"]:,} transacciones
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with kcol3:
        st.markdown(
            f"""
            <div class="metric-box">
                <div class="metric-title">Socio Comercial Principal</div>
                <div class="metric-val" style="font-size: 1.25rem;">
                    {kpis["top_pais_nombre"]}
                </div>
                <div style="margin-top: 4px;">
                    <span class="badge-country">{kpis["top_pais_pct"]:.1f}% del total ({kpis["top_pais_iso"]})</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with kcol4:
        st.markdown(
            f"""
            <div class="metric-box">
                <div class="metric-title">Bloque de Integración Líder</div>
                <div class="metric-val" style="font-size: 1.25rem;">
                    {kpis["top_bloque_nombre"]}
                </div>
                <div style="margin-top: 4px;">
                    <span class="badge-bloc">{kpis["top_bloque_pct"]:.1f}% cuota de mercado</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("<br>", unsafe_allow_html=True)

    # --------------------------------------------------------------------------
    # Pestañas de Visualización y Análisis
    # --------------------------------------------------------------------------
    tab1, tab2, tab3, tab4 = st.tabs([
        "🌎 Mapa Global y Distribución",
        "📊 Ranking de Países y Bloques",
        "📈 Concentración y Tendencias",
        "📋 Directorio y Descargas",
    ])

    with tab1:
        st.plotly_chart(
            build_choropleth_map(df_filtered, flow=flow, scope=plotly_scope),
            use_container_width=True,
        )
        st.info(
            f"💡 **Interpretación del Mapa:** Cada país está coloreado según el volumen total en USD "
            f"({flow_label}) comerciado con Bolivia. Pase el cursor sobre cualquier territorio para ver el detalle "
            "de valor, peso en toneladas, bloque de integración y cuota porcentual."
        )

    with tab2:
        rcol1, rcol2 = st.columns([3, 2])
        with rcol1:
            st.plotly_chart(
                build_top_partners_bar_chart(df_filtered, top_n=top_n, flow=flow),
                use_container_width=True,
            )
        with rcol2:
            st.plotly_chart(
                build_bloc_distribution_chart(df_filtered, flow=flow),
                use_container_width=True,
            )

    with tab3:
        ccol1, ccol2 = st.columns(2)
        with ccol1:
            st.plotly_chart(build_concentration_curve(df_filtered), use_container_width=True)
            st.caption(
                "📌 La **Curva de Concentración (Pareto)** muestra el grado de diversificación comercial. "
                "Si pocos países acumulan más del 80% del valor, existe una alta dependencia externa."
            )
        with ccol2:
            st.plotly_chart(build_partner_evolution_chart(df_raw, top_n=5), use_container_width=True)
            st.caption(
                "📌 La **Evolución Histórica** permite comparar las tendencias interanuales de los 5 socios "
                "con mayor volumen comercial acumulado."
            )

    with tab4:
        st.markdown("### 📋 Directorio Detallado de Socios Comerciales")
        st.markdown("Explorador tabular con búsqueda y exportación de datos de intercambio bilateral:")

        search_query = st.text_input(
            "🔍 Buscar país por nombre o código ISO",
            value="",
            placeholder="Ej: Brasil, China, USA, BRA, ARG...",
        )

        df_display = df_filtered.copy()
        if search_query.strip():
            sq = search_query.strip().lower()
            df_display = df_display[
                df_display["nombre_pais_es"].astype(str).str.lower().str.contains(sq)
                | df_display["pais_iso"].astype(str).str.lower().str.contains(sq)
            ]

        # Calcular participación sobre el total mostrado
        total_disp = df_display["total_valor_usd"].sum() if "total_valor_usd" in df_display else 0.0
        if total_disp > 0:
            df_display["pct_participacion"] = (df_display["total_valor_usd"] / total_disp) * 100.0
        else:
            df_display["pct_participacion"] = 0.0

        if "total_peso_bruto_kg" in df_display:
            df_display["peso_ton"] = df_display["total_peso_bruto_kg"] / 1_000.0

        st.dataframe(
            df_display,
            use_container_width=True,
            hide_index=True,
            column_config={
                "pais_iso": st.column_config.TextColumn("ISO-3", width="small"),
                "nombre_pais_es": st.column_config.TextColumn("País", width="medium"),
                "continente": st.column_config.TextColumn("Continente", width="medium"),
                "bloque_comercial": st.column_config.TextColumn("Bloque Comercial", width="medium"),
                "total_valor_usd": st.column_config.NumberColumn(
                    "Valor Total (USD)", format="$%.2f", width="medium"
                ),
                "pct_participacion": st.column_config.NumberColumn(
                    "Participación", format="%.2f %%", width="small"
                ),
                "peso_ton": st.column_config.NumberColumn(
                    "Volumen (Ton)", format="%.1f Ton", width="medium"
                ),
                "num_transacciones": st.column_config.NumberColumn(
                    "Transacciones", format="%d", width="small"
                ),
            },
        )

        csv_data = df_display.to_csv(index=False).encode("utf-8-sig")
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        st.download_button(
            label="📥 Descargar CSV de Socios Comerciales",
            data=csv_data,
            file_name=f"socios_comerciales_{flow.lower()}_{timestamp_str}.csv",
            mime="text/csv",
            help="Descarga los datos filtrados en formato CSV con codificación UTF-8 BOM.",
        )


if __name__ == "__main__":
    main()
