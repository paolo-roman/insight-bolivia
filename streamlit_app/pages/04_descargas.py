"""InsightBolivia — Dashboard 04: Descargas de Datos y Microdatos de Comercio Exterior.

Módulo interactivo para la exportación estructurada de transacciones y microdatos de
comercio exterior de Bolivia en formatos CSV (UTF-8 con BOM) y Excel (.xlsx).

Garantiza la estabilidad de la plataforma en la capa gratuita de Streamlit Cloud (1 GB RAM)
imponiendo un límite de seguridad estricto de 50,000 registros por descarga y exigiendo la
aplicación obligatoria de filtros temporales sobre las particiones de Google BigQuery.
"""

from __future__ import annotations

import logging
from datetime import datetime

import streamlit as st

from streamlit_app.components.descargas_helpers import (
    MAX_DOWNLOAD_RECORDS,
    build_export_filename,
    compute_export_summary,
    convert_df_to_csv,
    convert_df_to_excel,
    format_currency_millions,
    format_weight_tonnes,
)
from streamlit_app.components.filters import render_filters
from streamlit_app.utils.bq_client import (
    get_available_date_range,
    get_export_microdatos,
)
from streamlit_app.utils.firestore_client import (
    get_session_id,
    log_ui_event,
)

logger = logging.getLogger("insight_bolivia.streamlit.descargas")

__all__ = [
    "MAX_DOWNLOAD_RECORDS",
    "build_export_filename",
    "compute_export_summary",
    "convert_df_to_csv",
    "convert_df_to_excel",
    "format_currency_millions",
    "format_weight_tonnes",
    "main",
]


def main() -> None:
    """Punto de entrada principal para el Módulo 04: Descargas de Datos."""
    st.set_page_config(
        page_title="InsightBolivia | Centro de Descargas",
        page_icon="📥",
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
        .security-alert {
            background-color: rgba(239, 68, 68, 0.12);
            border: 1px solid #EF4444;
            border-radius: 10px;
            padding: 1.2rem;
            color: #FCA5A5;
            margin-bottom: 1.5rem;
        }
        .security-success {
            background-color: rgba(16, 185, 129, 0.12);
            border: 1px solid #10B981;
            border-radius: 10px;
            padding: 1.2rem;
            color: #6EE7B7;
            margin-bottom: 1.5rem;
        }
        .export-card {
            background: linear-gradient(135deg, #1E293B 0%, #0F172A 100%);
            border: 1px solid #334155;
            border-radius: 12px;
            padding: 1.5rem;
            margin-bottom: 1.5rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # 1. Telemetría de Navegación
    session_id = get_session_id()
    log_ui_event(session_id=session_id, page="04_descargas", event_type="page_view")

    # 2. Rangos de Fecha Disponibles en DWH
    min_date, max_date = get_available_date_range()

    # 3. Barra Lateral de Filtros Obligatorios
    filters = render_filters(
        page_name="04_descargas",
        show_dates=True,
        show_departments=True,
        show_flow=True,
        show_sectors=True,
        show_search=True,
        default_start_date=min_date,
        default_end_date=max_date,
        in_sidebar=True,
        key_prefix="descargas",
    )

    # 4. Header Principal
    st.markdown(
        '<div class="page-title">📥 Centro de Descargas y Microdatos de Comercio Exterior</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="page-subtitle">Exportación parametrizada de transacciones comerciales en '
        'formatos CSV y Excel con límites de seguridad para investigación y análisis cuantitativo.</div>',
        unsafe_allow_html=True,
    )

    # 5. Validación de Filtros Obligatorios
    if not filters.start_date or not filters.end_date:
        st.warning("⚠️ Debe seleccionar un rango de fechas válido en el panel lateral para consultar datos.")
        return

    # 6. Consulta de Microdatos en BigQuery (con límite de seguridad 50,001)
    departamentos_arg = None if filters.is_all_departments else filters.departamentos
    sectores_arg = filters.sectores if filters.sectores else None
    search_arg = filters.search_term if filters.search_term else None

    with st.spinner("Consultando registros en Google BigQuery..."):
        df = get_export_microdatos(
            start_date=filters.start_date,
            end_date=filters.end_date,
            flow=filters.flow,
            departamentos=departamentos_arg,
            sectores=sectores_arg,
            search_term=search_arg,
            limit=MAX_DOWNLOAD_RECORDS + 1,
        )

    summary = compute_export_summary(df)

    # 7. Evaluación del Límite de Seguridad (50,000 registros)
    if summary["excede_limite"]:
        log_ui_event(
            session_id=session_id,
            page="04_descargas",
            event_type="limit_exceeded",
            event_data={
                "total_registros_detectados": summary["total_registros"],
                "limite_maximo": MAX_DOWNLOAD_RECORDS,
                "filtros": filters.to_dict(),
            },
        )

        st.markdown(
            f"""
            <div class="security-alert">
                <div style="font-weight: 700; font-size: 1.1rem; margin-bottom: 0.4rem;">
                    🚫 Límite de Seguridad Superado ({summary['total_registros']:,} registros)
                </div>
                <div>
                    La consulta supera el límite estricto de <strong>50,000 registros por descarga</strong>
                    establecido para proteger la memoria de Streamlit Cloud (~1 GB RAM) y optimizar los tiempos.
                </div>
                <div style="margin-top: 0.6rem; font-size: 0.95rem;">
                    <strong>Acción requerida:</strong> Por favor, acote el rango de fechas, seleccione departamentos
                    específicos o filtre por sector económico en el panel lateral para habilitar la descarga.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Vista previa informativa acotada a las primeras 50 filas
        st.markdown("### 👁️ Vista Previa Parcial (Primeros 50 registros)")
        st.caption("La descarga del dataset completo permanecerá bloqueada hasta acotar los filtros.")
        preview_df = df.head(50)
        st.dataframe(
            preview_df,
            use_container_width=True,
            hide_index=True,
        )
        return

    # 8. Si no hay registros
    if summary["total_registros"] == 0:
        st.info("ℹ️ No se encontraron registros de comercio exterior para los filtros seleccionados.")
        return

    # 9. Consulta Válida dentro del Límite (1 <= N <= 50,000)
    st.markdown(
        f"""
        <div class="security-success">
            <div style="font-weight: 700; font-size: 1.05rem; margin-bottom: 0.2rem;">
                ✅ Consulta Válida: {summary['total_registros']:,} registros listos para exportar
            </div>
            <div style="font-size: 0.9rem;">
                Los datos cumplen con el límite de seguridad (&le; {MAX_DOWNLOAD_RECORDS:,} registros).
                Seleccione el formato deseado a continuación.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


    # Tarjetas de Resumen
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(
            f"""
            <div class="metric-box">
                <div class="metric-title">Total Registros</div>
                <div class="metric-val">{summary['total_registros']:,}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            f"""
            <div class="metric-box">
                <div class="metric-title">Valor FOB Total (USD)</div>
                <div class="metric-val">{format_currency_millions(summary['total_fob_usd'])}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with c3:
        st.markdown(
            f"""
            <div class="metric-box">
                <div class="metric-title">Valor CIF Total (USD)</div>
                <div class="metric-val">{format_currency_millions(summary['total_cif_usd'])}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with c4:
        st.markdown(
            f"""
            <div class="metric-box">
                <div class="metric-title">Peso Neto Total</div>
                <div class="metric-val">{format_weight_tonnes(summary['total_peso_neto_kg'])}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("<br>", unsafe_allow_html=True)

    # 10. Botones de Exportación (CSV y Excel)
    csv_filename = build_export_filename(
        flow=filters.flow,
        start_date=filters.start_date,
        end_date=filters.end_date,
        extension="csv",
    )
    excel_filename = build_export_filename(
        flow=filters.flow,
        start_date=filters.start_date,
        end_date=filters.end_date,
        extension="xlsx",
    )

    csv_data = convert_df_to_csv(df)
    excel_data = convert_df_to_excel(df, sheet_name="InsightBolivia_Comercio")

    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        st.download_button(
            label=f"📥 Descargar CSV ({summary['total_registros']:,} filas)",
            data=csv_data,
            file_name=csv_filename,
            mime="text/csv",
            use_container_width=True,
            key="btn_download_csv",
            help="Descarga el dataset en formato CSV con codificación UTF-8 BOM para compatibilidad con Excel.",
        )
    with col_btn2:
        st.download_button(
            label=f"📊 Descargar Excel .xlsx ({summary['total_registros']:,} filas)",
            data=excel_data,
            file_name=excel_filename,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
            key="btn_download_excel",
            help="Descarga el dataset en formato Microsoft Excel (.xlsx) estructurado.",
        )

    st.markdown("---")

    # 11. Tabla de Vista Previa Interactiva
    st.markdown("### 📋 Vista Previa de Datos (Primeros 100 registros)")
    st.caption("Se muestran hasta 100 filas de la consulta. La descarga contendrá la totalidad del dataset filtrado.")

    preview_df = df.head(100)
    st.dataframe(
        preview_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "fecha": st.column_config.DateColumn("Fecha", format="YYYY-MM-DD"),
            "anio": st.column_config.NumberColumn("Año", format="%d"),
            "mes": st.column_config.NumberColumn("Mes", format="%d"),
            "tipo_operacion": st.column_config.TextColumn("Flujo"),
            "codigo_nandina": st.column_config.TextColumn("NANDINA"),
            "descripcion_producto": st.column_config.TextColumn("Descripción de Producto"),
            "sector_economico": st.column_config.TextColumn("Sector"),
            "pais_iso": st.column_config.TextColumn("ISO"),
            "pais_nombre": st.column_config.TextColumn("País"),
            "bloque_comercial": st.column_config.TextColumn("Bloque"),
            "departamento": st.column_config.TextColumn("Departamento"),
            "valor_fob_usd": st.column_config.NumberColumn("FOB (USD)", format="$%.2f"),
            "valor_cif_usd": st.column_config.NumberColumn("CIF (USD)", format="$%.2f"),
            "peso_neto_kg": st.column_config.NumberColumn("Peso Neto (kg)", format="%.1f kg"),
            "peso_bruto_kg": st.column_config.NumberColumn("Peso Bruto (kg)", format="%.1f kg"),
        },
    )

    st.markdown("---")

    # 12. Diccionario de Datos y Especificaciones
    with st.expander("📖 Diccionario de Datos y Metadatos de Exportación"):
        st.markdown(
            """
            | Campo | Tipo | Descripción |
            | :--- | :--- | :--- |
            | `fecha` | `DATE` | Fecha representativa del registro mensual (YYYY-MM-01). |
            | `anio` | `INT64` | Año de la operación comercial. |
            | `mes` | `INT64` | Mes del año (1 a 12). |
            | `tipo_operacion` | `STRING` | `EXPORTACION` (FOB) o `IMPORTACION` (CIF). |
            | `codigo_nandina` | `STRING` | Código arancelario NANDINA oficial de 10 dígitos. |
            | `descripcion_producto` | `STRING` | Glosa o descripción arancelaria según NANDINA. |
            | `sector_economico` | `STRING` | Sector de actividad económica agrupado. |
            | `pais_iso` | `STRING` | Código internacional de país ISO 3166-1 alpha-3. |
            | `pais_nombre` | `STRING` | Nombre oficial del país socio en español. |
            | `bloque_comercial` | `STRING` | Bloque de integración económica principal (ej: MERCOSUR, CAN, UE). |
            | `departamento` | `STRING` | Departamento de Bolivia de origen territorial o destino aduanero. |
            | `valor_fob_usd` | `NUMERIC` | Valor FOB de la mercancía en dólares americanos (USD). |
            | `valor_cif_usd` | `NUMERIC` | Valor CIF frontera en dólares americanos (USD, importaciones). |
            | `peso_neto_kg` | `NUMERIC` | Peso neto en kilogramos. |
            | `peso_bruto_kg` | `NUMERIC` | Peso bruto en kilogramos. |
            """
        )
        st.caption(f"Generado por InsightBolivia — {datetime.now().year}. Datos oficiales del INE Bolivia.")


if __name__ == "__main__":
    main()
