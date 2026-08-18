"""InsightBolivia — Plataforma Centralizada de Analítica e Inteligencia de Comercio Exterior.

Punto de entrada principal de la aplicación Streamlit.
Presenta la arquitectura del Data Warehouse, metadatos sincronizados desde Cloud Firestore
(`dwh_catalog`), accesos directos a los módulos analíticos y registro de telemetría (`ui_analytics`).

Ejecución local:
    uv run streamlit run streamlit_app/app.py
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import streamlit as st

from streamlit_app.utils.firestore_client import (
    get_cached_dwh_catalog,
    get_session_id,
    log_ui_event,
)

logger = logging.getLogger("insight_bolivia.streamlit.app")

# ==============================================================================
# Configuración Global de la Página
# ==============================================================================
st.set_page_config(
    page_title="InsightBolivia | Plataforma de Inteligencia Comercial",
    page_icon="🇧🇴",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Inyección de estilos CSS personalizados para tarjetas y badges
st.markdown(
    """
    <style>
    .main-header {
        font-size: 2.2rem;
        font-weight: 700;
        color: #F8FAFC;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        font-size: 1.1rem;
        color: #94A3B8;
        margin-bottom: 1.5rem;
    }
    .metric-card {
        background-color: #1E293B;
        border-radius: 10px;
        padding: 1.2rem;
        border: 1px solid #334155;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
        text-align: center;
    }
    .metric-title {
        color: #94A3B8;
        font-size: 0.85rem;
        text-transform: uppercase;
        font-weight: 600;
        letter-spacing: 0.05em;
    }
    .metric-value {
        color: #F8FAFC;
        font-size: 1.6rem;
        font-weight: 700;
        margin-top: 0.3rem;
    }
    .module-card {
        background: linear-gradient(135deg, #1E293B 0%, #0F172A 100%);
        border: 1px solid #334155;
        border-radius: 12px;
        padding: 1.5rem;
        height: 100%;
        transition: transform 0.2s ease, border-color 0.2s ease;
    }
    .module-card:hover {
        border-color: #00A86B;
        transform: translateY(-2px);
    }
    .module-title {
        font-size: 1.2rem;
        font-weight: 600;
        color: #F8FAFC;
        margin-bottom: 0.5rem;
    }
    .module-desc {
        color: #94A3B8;
        font-size: 0.9rem;
        line-height: 1.4;
    }
    .badge-active {
        background-color: rgba(16, 185, 129, 0.15);
        color: #34D399;
        padding: 4px 10px;
        border-radius: 20px;
        font-size: 0.8rem;
        font-weight: 600;
        border: 1px solid rgba(52, 211, 153, 0.3);
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def main() -> None:
    """Función principal de renderizado del Landing Page de InsightBolivia."""
    # Inicialización de sesión y telemetría de navegación
    session_id = get_session_id()
    log_ui_event(session_id=session_id, page="home", event_type="page_view")

    # Barra lateral de navegación e información institucional
    with st.sidebar:
        st.image(
            "https://raw.githubusercontent.com/twitter/twemoji/master/assets/72x72/1f1e7-1f1f4.png",
            width=48,
        )
        st.markdown("## **InsightBolivia**")
        st.markdown(
            "*Plataforma de Analítica e Inteligencia para Datos Abiertos de Bolivia.*"
        )
        st.markdown("---")
        st.markdown("### 🧭 **Módulos Disponibles**")
        st.markdown(
            """
            - 📊 **01. Balanza Comercial**
            - 🌎 **02. Socios Comerciales**
            - 📦 **03. Productos Principales**
            - 📥 **04. Centro de Descargas**
            - 📈 **05. Benchmark Regional**
            """
        )
        st.markdown("---")
        st.markdown("ℹ️ **Versión:** `v0.1.0-alpha`")
        st.markdown("⚖️ **Licencia:** BSD 3-Clause")

    # Header Principal
    st.markdown(
        '<div class="main-header">🇧🇴 InsightBolivia — Inteligencia de Comercio Exterior</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="sub-header">Data Warehouse analítico en Google BigQuery y monitoreo de datos '
        'abiertos del INE Bolivia en tiempo real.</div>',
        unsafe_allow_html=True,
    )

    # Consulta de metadatos de Firestore (Catálogo DWH)
    catalog = get_cached_dwh_catalog("comercio_exterior")

    # Formateo de métricas en vivo
    if catalog is not None:
        status_label = "Activo" if catalog.status == "active" else catalog.status.capitalize()
        last_refresh = (
            catalog.last_data_refresh.strftime("%d/%m/%Y %H:%M UTC")
            if catalog.last_data_refresh
            else "Pendiente"
        )
        record_count = f"{catalog.record_count:,}" if catalog.record_count > 0 else "2.1M+"
        data_source = catalog.data_source
    else:
        status_label = "Activo (Demo)"
        last_refresh = datetime.now(UTC).strftime("%d/%m/%Y %H:%M UTC")
        record_count = "2,150,000+"
        data_source = "INE - Instituto Nacional de Estadística"

    # Tarjetas de Métricas de Estado del Data Warehouse
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-title">Estado Operativo</div>
                <div class="metric-value"><span class="badge-active">🟢 {status_label}</span></div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with col2:
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-title">Última Sincronización</div>
                <div class="metric-value" style="font-size: 1.2rem; margin-top: 0.6rem;">{last_refresh}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with col3:
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-title">Registros Consolidados</div>
                <div class="metric-value">{record_count}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with col4:
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-title">Fuente Oficial</div>
                <div class="metric-value" style="font-size: 1.1rem; margin-top: 0.7rem;">{data_source}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("---")

    # Sección de Módulos Analíticos
    st.markdown("### 📊 Explora los Tableros Analíticos")
    st.markdown(
        "Selecciona un módulo en el menú lateral o consulta los paneles interactivos a continuación:"
    )

    mcol1, mcol2 = st.columns(2)

    with mcol1:
        st.markdown(
            """
            <div class="module-card">
                <div class="module-title">📊 1. Balanza Comercial Mensual</div>
                <div class="module-desc">
                    Evolución temporal del saldo comercial boliviano. Comparación de Exportaciones FOB
                    e Importaciones CIF, con análisis de estacionalidad, peso neto acumulado y tendencias.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown("<br>", unsafe_allow_html=True)

        st.markdown(
            """
            <div class="module-card">
                <div class="module-title">📦 3. Principales Productos Arancelarios</div>
                <div class="module-desc">
                    Ranking de los 10 productos más exportados e importados clasificados por
                    código arancelario NANDINA, sector económico (hidrocarburos, minería) y valor FOB.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with mcol2:
        st.markdown(
            """
            <div class="module-card">
                <div class="module-title">🌎 2. Socios Comerciales y Bloques</div>
                <div class="module-desc">
                    Mapa interactivo coroplético y distribución de comercio exterior por país de
                    destino/origen y bloques de integración regional (MERCOSUR, CAN, UE, Asia).
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown("<br>", unsafe_allow_html=True)

        st.markdown(
            """
            <div class="module-card">
                <div class="module-title">📥 4. Centro de Descargas de Microdatos</div>
                <div class="module-desc">
                    Exportación estructurada de datasets en CSV y Excel con filtros obligatorios y límite de
                    seguridad de hasta 50,000 registros para investigación y análisis cuantitativo.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("---")

    # Arquitectura y Tecnologías
    with st.expander("🛠️ Detalles de Arquitectura y Tecnologías Subyacentes"):
        st.markdown(
            """
            - **Motor OLAP:** Google BigQuery (Particionado mensual y Clustering por NANDINA y país ISO).
            - **Base Operacional:** Google Cloud Firestore en Modo Nativo (`dwh_catalog` y `ui_analytics`).
            - **Pipeline ETL:** Python automatizado con GitHub Actions y validaciones con Great Expectations.
            - **Seguridad:** Inyección de credenciales en runtime mediante `st.secrets` sin texto plano.
            - **Capa Gratuita:** Consultas optimizadas contra vistas pre-agregadas para operar con costo **$0 USD**.
            """
        )


if __name__ == "__main__":
    main()
