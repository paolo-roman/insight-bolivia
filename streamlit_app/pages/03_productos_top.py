"""InsightBolivia — Dashboard 03: Principales Productos de Exportación (Top NANDINA).

Módulo interactivo de visualización y análisis de los principales productos arancelarios exportados.
Consume exclusivamente la vista analítica pre-agregada `comercio_exterior.vw_top_productos_exportados`
en Google BigQuery, garantizando costo cero ($0 USD) y tiempos de carga óptimos.
"""

from __future__ import annotations

import logging
from datetime import datetime

import pandas as pd
import streamlit as st

from streamlit_app.components.productos_charts import (
    COLOR_EXPORT,
    COLOR_VOLUME,
    build_price_density_scatter,
    build_sector_distribution_chart,
    build_top_products_bar_chart,
    build_top_products_evolution_chart,
    compute_top_productos_kpis,
    format_currency_millions,
    format_weight_tonnes,
)
from streamlit_app.utils.bq_client import (
    get_available_date_range,
    get_top_productos,
)
from streamlit_app.utils.firestore_client import (
    get_session_id,
    log_ui_event,
)

logger = logging.getLogger("insight_bolivia.streamlit.productos_top")

__all__ = [
    "build_price_density_scatter",
    "build_sector_distribution_chart",
    "build_top_products_bar_chart",
    "build_top_products_evolution_chart",
    "compute_top_productos_kpis",
    "format_currency_millions",
    "format_weight_tonnes",
    "main",
]


def main() -> None:
    """Punto de entrada principal para el Dashboard 03: Productos Top."""
    st.set_page_config(
        page_title="InsightBolivia | Principales Productos Exportados",
        page_icon="📦",
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
        .badge-sector {
            background-color: rgba(245, 158, 11, 0.15);
            color: #FBBF24;
            padding: 3px 8px;
            border-radius: 12px;
            font-size: 0.75rem;
            font-weight: 600;
            border: 1px solid rgba(251, 191, 36, 0.3);
        }
        .badge-nandina {
            background-color: rgba(59, 130, 246, 0.15);
            color: #60A5FA;
            padding: 3px 8px;
            border-radius: 12px;
            font-size: 0.75rem;
            font-weight: 600;
            border: 1px solid rgba(96, 165, 250, 0.3);
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    session_id = get_session_id()
    log_ui_event(session_id=session_id, page="03_productos_top", event_type="page_view")

    st.markdown(
        '<div class="page-title">📦 Principales Productos de Exportación (NANDINA)</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="page-subtitle">Ranking arancelario, desagregación por sector económico, '
        'volumen físico y precios unitarios implícitos consumiendo la vista analítica '
        '<code>vw_top_productos_exportados</code>.</div>',
        unsafe_allow_html=True,
    )

    # --------------------------------------------------------------------------
    # Barra Lateral de Filtros
    # --------------------------------------------------------------------------
    with st.sidebar:
        st.markdown("### ⚙️ **Filtros de Productos**")

        # 1. Rango de Años
        min_date, max_date = get_available_date_range()
        available_years = list(range(max_date.year, min_date.year - 1, -1))
        year_options = ["Todas las Gestiones (Consolidado)"] + [str(y) for y in available_years]

        selected_year_str = st.selectbox(
            "Gestión Anual",
            options=year_options,
            index=0,
            help="Filtre por un año específico o analice el acumulado de todas las gestiones.",
        )
        selected_year = None if selected_year_str.startswith("Todas") else int(selected_year_str)

        # 2. Conmutador de Métrica Principal
        metric_label = st.radio(
            "Métrica Principal de Análisis",
            options=["Valor FOB (USD)", "Volumen Físico (Toneladas)"],
            index=0,
            help="Alterne entre la valoración monetaria en dólares o el volumen físico exportado.",
        )
        metric = "usd" if "USD" in metric_label else "volume"

        # 3. Top N Productos
        top_n = st.slider(
            "Top Productos en Ranking",
            min_value=5,
            max_value=10,
            value=10,
            step=1,
            help="Número de productos arancelarios a incluir en los gráficos y rankings.",
        )

        st.markdown("---")
        st.markdown("ℹ️ **Fuente:** `comercio_exterior.vw_top_productos_exportados`")
        st.markdown("⚡ **Costo de Consulta:** $0.00 USD (Capa Gratuita)")

    # --------------------------------------------------------------------------
    # Consulta a BigQuery (Cacheada @st.cache_data)
    # --------------------------------------------------------------------------
    with st.spinner("Consultando ranking de productos en BigQuery..."):
        df_raw = get_top_productos(year=selected_year, limit=10)

    if df_raw.empty:
        st.warning(
            f"⚠️ No se encontraron registros de productos exportados para la gestión '{selected_year_str}'. "
            "Intente seleccionar otra gestión anual."
        )
        return

    # Filtro adicional por sector económico en memoria
    all_sectors = (
        sorted(df_raw["sector_economico"].dropna().unique().tolist())
        if "sector_economico" in df_raw
        else []
    )

    with st.sidebar:
        st.markdown("### 🏷️ **Filtro por Sector Económico**")
        selected_sectors = st.multiselect(
            "Sectores Económicos",
            options=all_sectors,
            default=[],
            help="Dejar vacío para incluir todos los sectores (Hidrocarburos, Minería, Agroindustria, etc.).",
        )

    df_filtered: pd.DataFrame = df_raw.copy()
    if selected_sectors:
        df_filtered = pd.DataFrame(df_filtered[df_filtered["sector_economico"].isin(selected_sectors)])

    if df_filtered.empty:
        st.warning("⚠️ No existen productos para los sectores económicos seleccionados.")
        return

    # --------------------------------------------------------------------------
    # KPIs Ejecutivos
    # --------------------------------------------------------------------------
    kpis = compute_top_productos_kpis(df_filtered, metric=metric)
    kcol1, kcol2, kcol3, kcol4 = st.columns(4)

    is_usd = metric == "usd"
    val_color = COLOR_EXPORT if is_usd else COLOR_VOLUME
    main_val_str = (
        format_currency_millions(kpis["total_fob_usd"])
        if is_usd
        else format_weight_tonnes(kpis["total_peso_kg"])
    )
    main_title_str = "Total Exportado FOB" if is_usd else "Volumen Físico Total"
    sub_val_str = (
        f"{kpis['total_peso_ton']:,.0f} Toneladas"
        if is_usd
        else format_currency_millions(kpis["total_fob_usd"])
    )

    with kcol1:
        st.markdown(
            f"""
            <div class="metric-box">
                <div class="metric-title">{main_title_str}</div>
                <div class="metric-val" style="color: {val_color};">
                    {main_val_str}
                </div>
                <div style="font-size: 0.75rem; color: #94A3B8; margin-top: 4px;">
                    {sub_val_str}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with kcol2:
        top_name_short = (
            f"{kpis['top_producto_nombre'][:28]}..."
            if len(kpis["top_producto_nombre"]) > 28
            else kpis["top_producto_nombre"]
        )
        st.markdown(
            f"""
            <div class="metric-box">
                <div class="metric-title">Producto Líder (#1)</div>
                <div class="metric-val" style="font-size: 1.2rem;" title="{kpis['top_producto_nombre']}">
                    {top_name_short}
                </div>
                <div style="margin-top: 4px;">
                    <span class="badge-nandina">
                        NANDINA: {kpis['top_producto_nandina']} ({kpis['top_producto_pct']:.1f}%)
                    </span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with kcol3:
        st.markdown(
            f"""
            <div class="metric-box">
                <div class="metric-title">Sector Predominante</div>
                <div class="metric-val" style="font-size: 1.25rem;">
                    {kpis['top_sector_nombre']}
                </div>
                <div style="margin-top: 4px;">
                    <span class="badge-sector">{kpis['top_sector_pct']:.1f}% de participación</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with kcol4:
        st.markdown(
            f"""
            <div class="metric-box">
                <div class="metric-title">Precio Unitario Implícito</div>
                <div class="metric-val">
                    ${kpis['precio_medio_usd_kg']:,.2f} <span style="font-size: 0.85rem; color: #94A3B8;">USD/kg</span>
                </div>
                <div style="font-size: 0.75rem; color: #94A3B8; margin-top: 4px;">
                    {kpis['total_transacciones']:,} transacciones registradas
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("<br>", unsafe_allow_html=True)

    # --------------------------------------------------------------------------
    # Pestañas Analíticas Interactivas
    # --------------------------------------------------------------------------
    tab1, tab2, tab3, tab4 = st.tabs([
        "📊 Ranking Arancelario y Sectores",
        "⚖️ Valor vs. Volumen (Precio $/kg)",
        "📈 Evolución Histórica de Líderes",
        "📋 Ficha Arancelaria y Descargas",
    ])

    with tab1:
        rcol1, rcol2 = st.columns([3, 2])
        with rcol1:
            st.plotly_chart(
                build_top_products_bar_chart(df_filtered, metric=metric, top_n=top_n),
                use_container_width=True,
            )
        with rcol2:
            st.plotly_chart(
                build_sector_distribution_chart(df_filtered, metric=metric),
                use_container_width=True,
            )

    with tab2:
        st.plotly_chart(
            build_price_density_scatter(df_filtered),
            use_container_width=True,
        )
        st.info(
            "💡 **Interpretación de Precios Implícitos:** Los productos ubicados arriba y a la izquierda "
            "representan bienes de alto valor agregado unitario (ej. minerales concentrados, oro), mientras que "
            "los productos hacia la derecha representan grandes volúmenes a menor precio unitario "
            "(ej. gas natural, torta de soya)."
        )

    with tab3:
        st.plotly_chart(
            build_top_products_evolution_chart(df_raw, metric=metric, top_n=5),
            use_container_width=True,
        )
        st.caption(
            "📌 La **Evolución Histórica** ilustra la trayectoria interanual de los 5 productos líderes "
            "más exportados por Bolivia."
        )

    with tab4:
        st.markdown("### 📋 Directorio y Ficha Arancelaria de Productos Top")
        st.markdown("Explorador tabular con búsqueda arancelaria y exportación de microdatos:")

        search_query = st.text_input(
            "🔍 Buscar producto por descripción arancelaria o código NANDINA",
            value="",
            placeholder="Ej: Gas natural, Oro, Soya, Zinc, 2711210000...",
        )

        df_display = df_filtered.copy()
        if search_query.strip():
            sq = search_query.strip().lower()
            df_display = df_display[
                df_display["descripcion_producto"].astype(str).str.lower().str.contains(sq)
                | df_display["codigo_nandina"].astype(str).str.lower().str.contains(sq)
                | df_display["sector_economico"].astype(str).str.lower().str.contains(sq)
            ]

        # Calcular métricas derivadas para la tabla
        if "total_peso_neto_kg" in df_display:
            df_display["peso_ton"] = df_display["total_peso_neto_kg"] / 1_000.0

        if "total_fob_usd" in df_display and "total_peso_neto_kg" in df_display:
            df_display["precio_kg"] = (
                df_display["total_fob_usd"] / df_display["total_peso_neto_kg"].replace(0, float("nan"))
            ).fillna(0.0)

        st.dataframe(
            df_display,
            use_container_width=True,
            hide_index=True,
            column_config={
                "anio": st.column_config.NumberColumn("Año", format="%d", width="small"),
                "ranking": st.column_config.NumberColumn("Rank", format="#%d", width="small"),
                "codigo_nandina": st.column_config.TextColumn("Código NANDINA", width="medium"),
                "descripcion_producto": st.column_config.TextColumn("Descripción Arancelaria", width="large"),
                "sector_economico": st.column_config.TextColumn("Sector Económico", width="medium"),
                "total_fob_usd": st.column_config.NumberColumn(
                    "Valor FOB (USD)", format="$%.2f", width="medium"
                ),
                "peso_ton": st.column_config.NumberColumn(
                    "Volumen (Ton)", format="%.1f Ton", width="medium"
                ),
                "precio_kg": st.column_config.NumberColumn(
                    "Precio Implícito", format="$%.2f/kg", width="small"
                ),
                "num_transacciones": st.column_config.NumberColumn(
                    "Transacciones", format="%d", width="small"
                ),
            },
        )

        csv_data = df_display.to_csv(index=False).encode("utf-8-sig")
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        st.download_button(
            label="📥 Descargar CSV de Productos Top",
            data=csv_data,
            file_name=f"productos_top_exportados_{timestamp_str}.csv",
            mime="text/csv",
            help="Descarga los productos filtrados en formato CSV con codificación UTF-8 BOM.",
        )


if __name__ == "__main__":
    main()
