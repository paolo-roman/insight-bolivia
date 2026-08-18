"""InsightBolivia — Dashboard 01: Balanza Comercial Mensual.

Módulo interactivo de visualización y análisis de la Balanza Comercial de Bolivia.
Consume exclusivamente la vista pre-agregada `comercio_exterior.vw_balanza_comercial_mensual`
en Google BigQuery, garantizando costo cero ($0 USD) y tiempos de carga óptimos.
"""

from __future__ import annotations

import logging
from datetime import date, datetime

import pandas as pd
import streamlit as st

from streamlit_app.components.balanza_charts import (
    COLOR_EXPORT,
    COLOR_IMPORT,
    COLOR_SURPLUS,
    aggregate_balanza_data,
    build_annual_comparison_chart,
    build_balance_bar_chart,
    build_evolution_chart,
    build_volume_chart,
    compute_balanza_kpis,
    format_currency_millions,
)
from streamlit_app.utils.bq_client import (
    get_available_date_range,
    get_balanza_comercial,
)
from streamlit_app.utils.firestore_client import (
    get_session_id,
    log_ui_event,
)

logger = logging.getLogger("insight_bolivia.streamlit.balanza_comercial")

# Re-exportamos para compatibilidad
__all__ = [
    "aggregate_balanza_data",
    "build_annual_comparison_chart",
    "build_balance_bar_chart",
    "build_evolution_chart",
    "build_volume_chart",
    "compute_balanza_kpis",
    "format_currency_millions",
    "main",
]


def main() -> None:
    """Punto de entrada principal para el Dashboard 01: Balanza Comercial Mensual."""
    st.set_page_config(
        page_title="InsightBolivia | Balanza Comercial Mensual",
        page_icon="📊",
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
        .badge-surplus {
            background-color: rgba(16, 185, 129, 0.15);
            color: #34D399;
            padding: 3px 8px;
            border-radius: 12px;
            font-size: 0.75rem;
            font-weight: 600;
            border: 1px solid rgba(52, 211, 153, 0.3);
        }
        .badge-deficit {
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
    log_ui_event(session_id=session_id, page="01_balanza_comercial", event_type="page_view")

    st.markdown(
        '<div class="page-title">📊 Balanza Comercial Mensual de Bolivia</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="page-subtitle">Evolución histórica y mensual del saldo comercial, exportaciones FOB '
        'e importaciones CIF consumiendo la vista analítica <code>vw_balanza_comercial_mensual</code>.</div>',
        unsafe_allow_html=True,
    )

    with st.sidebar:
        st.markdown("### ⚙️ **Filtros de Balanza**")
        min_dwh_date, max_dwh_date = get_available_date_range()

        preset = st.selectbox(
            "Selección Rápida de Periodo",
            options=["Últimos 3 años", "Últimos 5 años", "Todo el histórico", "Rango Personalizado"],
            index=0,
            help="Seleccione un rango predefinido o personalice las fechas.",
        )

        today = date.today()
        if preset == "Últimos 3 años":
            default_start = date(today.year - 3, 1, 1)
            default_end = max_dwh_date
        elif preset == "Últimos 5 años":
            default_start = date(today.year - 5, 1, 1)
            default_end = max_dwh_date
        elif preset == "Todo el histórico":
            default_start = min_dwh_date
            default_end = max_dwh_date
        else:
            default_start = date(2020, 1, 1)
            default_end = max_dwh_date

        date_selection = st.date_input(
            "Periodo de Análisis",
            value=(default_start, default_end),
            min_value=min_dwh_date,
            max_value=max_dwh_date,
            help="Filtro estricto por fechas para optimizar el particionamiento de BigQuery.",
        )

        if isinstance(date_selection, (list, tuple)) and len(date_selection) == 2:
            start_date, end_date = date_selection[0], date_selection[1]
        elif isinstance(date_selection, (list, tuple)) and len(date_selection) == 1:
            start_date = end_date = date_selection[0]
        else:
            start_date = default_start
            end_date = default_end

        freq = st.radio(
            "Granularidad Temporal",
            options=["Mensual", "Trimestral", "Anual"],
            index=0,
            horizontal=True,
        )

        st.markdown("---")
        st.markdown("ℹ️ **Fuente:** `comercio_exterior.vw_balanza_comercial_mensual`")
        st.markdown("⚡ **Costo de Consulta:** $0.00 USD (Capa Gratuita)")

    with st.spinner("Consultando balanza comercial pre-agregada en BigQuery..."):
        df_raw = get_balanza_comercial(start_date=start_date, end_date=end_date)

    if df_raw.empty:
        st.warning(
            "⚠️ No se encontraron registros de balanza comercial para el rango seleccionado "
            f"({start_date} a {end_date}). Intente ampliar el periodo temporal."
        )
        return

    kpis = compute_balanza_kpis(df_raw)

    kcol1, kcol2, kcol3, kcol4 = st.columns(4)
    with kcol1:
        st.markdown(
            f"""
            <div class="metric-box">
                <div class="metric-title">Exportaciones FOB (USD)</div>
                <div class="metric-val" style="color: {COLOR_EXPORT};">
                    {format_currency_millions(kpis["total_exportaciones_usd"])}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with kcol2:
        st.markdown(
            f"""
            <div class="metric-box">
                <div class="metric-title">Importaciones CIF (USD)</div>
                <div class="metric-val" style="color: {COLOR_IMPORT};">
                    {format_currency_millions(kpis["total_importaciones_usd"])}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with kcol3:
        badge_class = "badge-surplus" if kpis["es_superavit"] else "badge-deficit"
        badge_text = "🟢 Superávit" if kpis["es_superavit"] else "🔴 Déficit"
        saldo_color = COLOR_SURPLUS if kpis["es_superavit"] else "#EF4444"
        st.markdown(
            f"""
            <div class="metric-box">
                <div class="metric-title">Saldo Comercial Acumulado</div>
                <div class="metric-val" style="color: {saldo_color};">
                    {format_currency_millions(kpis["saldo_balanza_usd"])}
                </div>
                <div style="margin-top: 4px;"><span class="{badge_class}">{badge_text}</span></div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with kcol4:
        st.markdown(
            f"""
            <div class="metric-box">
                <div class="metric-title">Tasa de Cobertura Comercial</div>
                <div class="metric-val">
                    {kpis["tasa_cobertura_pct"]:.1f} %
                </div>
                <div style="font-size: 0.75rem; color: #94A3B8; margin-top: 4px;">(FOB / CIF)</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("<br>", unsafe_allow_html=True)
    df_agg = aggregate_balanza_data(df_raw, freq=freq)

    tab1, tab2, tab3, tab4 = st.tabs([
        "📈 Evolución y Saldo Temporal",
        "📊 Comparativa Anual",
        "⚖️ Volumen Físico (Toneladas)",
        "📋 Explorador de Datos y Descargas",
    ])

    with tab1:
        st.plotly_chart(build_evolution_chart(df_agg), use_container_width=True)
        st.plotly_chart(build_balance_bar_chart(df_agg), use_container_width=True)

    with tab2:
        st.plotly_chart(build_annual_comparison_chart(df_raw), use_container_width=True)

    with tab3:
        st.plotly_chart(build_volume_chart(df_agg), use_container_width=True)

    with tab4:
        st.markdown("### 📋 Registro Detallado de Balanza Comercial")
        st.markdown("Consulte y exporte los registros históricos agregados del periodo seleccionado:")

        df_display = df_raw.copy()
        df_display["fecha"] = pd.DatetimeIndex(df_display["fecha"]).strftime("%Y-%m-%d")

        st.dataframe(
            df_display,
            use_container_width=True,
            hide_index=True,
            column_config={
                "fecha": st.column_config.DateColumn("Fecha", format="YYYY-MM-DD"),
                "anio": st.column_config.NumberColumn("Año", format="%d"),
                "mes": st.column_config.NumberColumn("Mes", format="%d"),
                "nombre_mes": "Nombre Mes",
                "total_exportaciones_usd": st.column_config.NumberColumn("Exportaciones (FOB USD)", format="$%.2f"),
                "total_importaciones_usd": st.column_config.NumberColumn("Importaciones (CIF USD)", format="$%.2f"),
                "saldo_balanza_usd": st.column_config.NumberColumn("Saldo Comercial (USD)", format="$%.2f"),
                "total_peso_neto_exportaciones_kg": st.column_config.NumberColumn(
                    "Peso Neto Exp (kg)", format="%.0f kg"
                ),
                "total_peso_bruto_importaciones_kg": st.column_config.NumberColumn(
                    "Peso Bruto Imp (kg)", format="%.0f kg"
                ),
            },
        )

        csv_data = df_display.to_csv(index=False).encode("utf-8-sig")
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        st.download_button(
            label="📥 Descargar CSV de Balanza Comercial",
            data=csv_data,
            file_name=f"balanza_comercial_bolivia_{timestamp_str}.csv",
            mime="text/csv",
            help="Descarga los datos filtrados en formato CSV con codificación UTF-8.",
        )


if __name__ == "__main__":
    main()
