"""InsightBolivia — Componentes reutilizables de interfaz de usuario para Streamlit."""

from streamlit_app.components.descargas_helpers import (
    MAX_DOWNLOAD_RECORDS,
    build_export_filename,
    compute_export_summary,
    convert_df_to_csv,
    convert_df_to_excel,
)
from streamlit_app.components.filters import (
    DEPARTAMENTOS_BOLIVIA,
    FLOW_OPTIONS,
    FilterState,
    render_filters,
)
from streamlit_app.components.productos_charts import (
    COLOR_VOLUME,
    SECTOR_COLORS,
    build_price_density_scatter,
    build_sector_distribution_chart,
    build_top_products_bar_chart,
    build_top_products_evolution_chart,
    compute_top_productos_kpis,
    format_weight_tonnes,
)
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

__all__ = [
    "COLOR_EXPORT",
    "COLOR_IMPORT",
    "COLOR_VOLUME",
    "DEPARTAMENTOS_BOLIVIA",
    "FLOW_OPTIONS",
    "FilterState",
    "MAX_DOWNLOAD_RECORDS",
    "SECTOR_COLORS",
    "build_bloc_distribution_chart",
    "build_choropleth_map",
    "build_concentration_curve",
    "build_export_filename",
    "build_partner_evolution_chart",
    "build_price_density_scatter",
    "build_sector_distribution_chart",
    "build_top_partners_bar_chart",
    "build_top_products_bar_chart",
    "build_top_products_evolution_chart",
    "compute_export_summary",
    "compute_socios_kpis",
    "compute_top_productos_kpis",
    "convert_df_to_csv",
    "convert_df_to_excel",
    "format_currency_millions",
    "format_weight_tonnes",
    "render_filters",
]

