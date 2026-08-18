"""InsightBolivia — Pruebas unitarias para el Dashboard 02: Socios Comerciales (`02_socios_comerciales.py`).

Verifica el cómputo de KPIs, generadores de gráficos Plotly (mapa coroplético,
ranking de países, distribución de bloques, evolución histórica, curva de Pareto)
y renderizado integral del dashboard con mocks de Streamlit y BigQuery.
"""

from __future__ import annotations

import importlib
from datetime import date
from unittest.mock import MagicMock, patch

import pandas as pd
import plotly.graph_objects as go
import pytest

from streamlit_app.components.socios_charts import (
    build_bloc_distribution_chart,
    build_choropleth_map,
    build_concentration_curve,
    build_partner_evolution_chart,
    build_top_partners_bar_chart,
    compute_socios_kpis,
    format_currency_millions,
)

# Carga dinámica del módulo de página Streamlit
socios_page = importlib.import_module("streamlit_app.pages.02_socios_comerciales")
main = socios_page.main


@pytest.fixture
def sample_socios_df() -> pd.DataFrame:
    """Fixture con registros representativos de vw_socios_comerciales."""
    return pd.DataFrame({
        "anio": [2023, 2023, 2024, 2024, 2024],
        "tipo_operacion": ["EXPORTACION", "EXPORTACION", "EXPORTACION", "EXPORTACION", "EXPORTACION"],
        "pais_iso": ["BRA", "ARG", "BRA", "CHN", "USA"],
        "codigo_pais_ine": ["105", "101", "105", "304", "201"],
        "nombre_pais_es": ["Brasil", "Argentina", "Brasil", "China", "Estados Unidos"],
        "nombre_pais_en": ["Brazil", "Argentina", "Brazil", "China", "United States"],
        "continente": ["América del Sur", "América del Sur", "América del Sur", "Asia", "América del Norte"],
        "subregion": ["Sudamérica", "Sudamérica", "Sudamérica", "Asia Oriental", "Norteamérica"],
        "bloque_comercial": ["MERCOSUR", "MERCOSUR", "MERCOSUR", "APEC", "NAFTA / USMCA"],
        "total_valor_usd": [1_200_000_000.0, 800_000_000.0, 1_400_000_000.0, 900_000_000.0, 500_000_000.0],
        "total_fob_usd": [1_200_000_000.0, 800_000_000.0, 1_400_000_000.0, 900_000_000.0, 500_000_000.0],
        "total_cif_usd": [0.0, 0.0, 0.0, 0.0, 0.0],
        "total_peso_bruto_kg": [3_000_000_000.0, 2_000_000_000.0, 3_500_000_000.0, 1_000_000_000.0, 400_000_000.0],
        "num_transacciones": [4500, 3200, 5100, 1800, 1200],
    })


class TestFormattingHelpers:
    """Pruebas para funciones de formato de moneda y texto."""

    def test_format_currency_billions(self) -> None:
        assert format_currency_millions(2_600_000_000.0) == "$2.60 B"
        assert format_currency_millions(-1_400_000_000.0) == "$-1.40 B"

    def test_format_currency_millions(self) -> None:
        assert format_currency_millions(450_000_000.0) == "$450.00 M"
        assert format_currency_millions(1_500_000.0) == "$1.50 M"

    def test_format_currency_under_million(self) -> None:
        assert format_currency_millions(75_000.50) == "$75,000.50"
        assert format_currency_millions(0.0) == "$0.00"


class TestComputeSociosKpis:
    """Pruebas para el cálculo de indicadores de socios comerciales."""

    def test_compute_kpis_with_data(self, sample_socios_df: pd.DataFrame) -> None:
        kpis = compute_socios_kpis(sample_socios_df, flow="EXPORTACION")
        assert kpis["total_valor_usd"] == 4_800_000_000.0
        assert kpis["num_paises"] == 4  # BRA, ARG, CHN, USA
        assert kpis["top_pais_nombre"] == "Brasil"
        assert kpis["top_pais_iso"] == "BRA"
        assert kpis["top_pais_valor"] == 2_600_000_000.0
        assert round(kpis["top_pais_pct"], 2) == 54.17
        assert kpis["top_bloque_nombre"] == "MERCOSUR"
        assert kpis["top_bloque_valor"] == 3_400_000_000.0
        assert round(kpis["top_bloque_pct"], 2) == 70.83
        assert kpis["total_peso_ton"] == 9_900_000.0
        assert kpis["total_transacciones"] == 15800
        assert kpis["flow"] == "EXPORTACION"

    def test_compute_kpis_empty_df(self) -> None:
        kpis = compute_socios_kpis(pd.DataFrame(), flow="IMPORTACION")
        assert kpis["total_valor_usd"] == 0.0
        assert kpis["num_paises"] == 0
        assert kpis["top_pais_nombre"] == "Sin datos"
        assert kpis["top_bloque_nombre"] == "Sin datos"
        assert kpis["flow"] == "IMPORTACION"

    def test_compute_kpis_missing_columns(self) -> None:
        minimal_df = pd.DataFrame({
            "total_fob_usd": [100.0, 200.0],
            "pais_iso": ["BRA", "ARG"],
        })
        kpis = compute_socios_kpis(minimal_df)
        assert kpis["total_valor_usd"] == 300.0
        assert kpis["num_paises"] == 2
        assert kpis["total_peso_ton"] == 0.0
        assert kpis["total_transacciones"] == 0
        assert kpis["top_pais_nombre"] == "N/D"
        assert kpis["top_bloque_nombre"] == "N/D"


class TestPlotlySociosChartBuilders:
    """Pruebas para los generadores de gráficos interactivos Plotly."""

    def test_build_choropleth_map_export(self, sample_socios_df: pd.DataFrame) -> None:
        fig = build_choropleth_map(sample_socios_df, flow="EXPORTACION", scope="world")
        assert isinstance(fig, go.Figure)
        assert len(list(fig.data)) == 1
        trace = fig.data[0]
        assert isinstance(trace, go.Choropleth)
        assert list(trace.locations) == ["ARG", "BRA", "CHN", "USA"]

    def test_build_choropleth_map_import(self, sample_socios_df: pd.DataFrame) -> None:
        fig = build_choropleth_map(sample_socios_df, flow="IMPORTACION", scope="south america")
        assert isinstance(fig, go.Figure)
        assert len(list(fig.data)) == 1

    def test_build_choropleth_map_empty(self) -> None:
        fig = build_choropleth_map(pd.DataFrame())
        assert isinstance(fig, go.Figure)
        assert len(list(fig.data)) == 0

        fig_no_iso = build_choropleth_map(pd.DataFrame({"val": [1, 2]}))
        assert len(list(fig_no_iso.data)) == 0

    def test_build_top_partners_bar_chart(self, sample_socios_df: pd.DataFrame) -> None:
        fig = build_top_partners_bar_chart(sample_socios_df, top_n=3, flow="EXPORTACION")
        assert isinstance(fig, go.Figure)
        assert len(list(fig.data)) == 1
        trace = fig.data[0]
        assert isinstance(trace, go.Bar)
        assert len(trace.x) == 3  # Top 3

    def test_build_top_partners_bar_chart_empty(self) -> None:
        fig = build_top_partners_bar_chart(pd.DataFrame())
        assert isinstance(fig, go.Figure)
        assert len(list(fig.data)) == 0

    def test_build_bloc_distribution_chart(self, sample_socios_df: pd.DataFrame) -> None:
        fig = build_bloc_distribution_chart(sample_socios_df, flow="EXPORTACION")
        assert isinstance(fig, go.Figure)
        assert len(list(fig.data)) == 1
        trace = fig.data[0]
        assert isinstance(trace, go.Pie)
        assert "MERCOSUR" in list(trace.labels)

    def test_build_bloc_distribution_chart_empty(self) -> None:
        fig = build_bloc_distribution_chart(pd.DataFrame())
        assert isinstance(fig, go.Figure)
        assert len(list(fig.data)) == 0

    def test_build_partner_evolution_chart(self, sample_socios_df: pd.DataFrame) -> None:
        fig = build_partner_evolution_chart(sample_socios_df, top_n=3)
        assert isinstance(fig, go.Figure)
        assert len(list(fig.data)) >= 2  # multiple lines for top countries

    def test_build_partner_evolution_chart_empty_or_no_anio(self) -> None:
        fig_empty = build_partner_evolution_chart(pd.DataFrame())
        assert len(list(fig_empty.data)) == 0

        fig_no_anio = build_partner_evolution_chart(pd.DataFrame({"val": [1, 2]}))
        assert len(list(fig_no_anio.data)) == 0

    def test_build_concentration_curve(self, sample_socios_df: pd.DataFrame) -> None:
        fig = build_concentration_curve(sample_socios_df)
        assert isinstance(fig, go.Figure)
        assert len(list(fig.data)) == 1
        trace = fig.data[0]
        assert getattr(trace, "name", "") == "% Acumulado de Comercio"

    def test_build_concentration_curve_empty_or_zero(self) -> None:
        fig_empty = build_concentration_curve(pd.DataFrame())
        assert len(list(fig_empty.data)) == 0

        df_zero = pd.DataFrame({"nombre_pais_es": ["A", "B"], "total_valor_usd": [0.0, 0.0]})
        fig_zero = build_concentration_curve(df_zero)
        assert len(list(fig_zero.data)) == 0


class TestSociosPageMain:
    """Pruebas para el entrypoint main() del dashboard de Socios Comerciales."""

    @patch("streamlit.sidebar")
    @patch("streamlit.radio")
    @patch("streamlit.selectbox")
    @patch("streamlit.slider")
    @patch("streamlit.multiselect")
    @patch("streamlit.columns")
    @patch("streamlit.tabs")
    @patch("streamlit.markdown")
    @patch("streamlit.plotly_chart")
    @patch("streamlit.info")
    @patch("streamlit.caption")
    @patch("streamlit.text_input")
    @patch("streamlit.dataframe")
    @patch("streamlit.download_button")
    @patch("streamlit.spinner")
    def test_main_renders_successfully_with_data(
        self,
        mock_spinner: MagicMock,
        mock_download: MagicMock,
        mock_dataframe: MagicMock,
        mock_text_input: MagicMock,
        mock_caption: MagicMock,
        mock_info: MagicMock,
        mock_plotly: MagicMock,
        mock_markdown: MagicMock,
        mock_tabs: MagicMock,
        mock_columns: MagicMock,
        mock_multiselect: MagicMock,
        mock_slider: MagicMock,
        mock_selectbox: MagicMock,
        mock_radio: MagicMock,
        mock_sidebar: MagicMock,
        sample_socios_df: pd.DataFrame,
    ) -> None:
        with (
            patch.object(socios_page, "log_ui_event") as mock_log_event,
            patch.object(socios_page, "get_session_id", return_value="test-socios-session") as mock_get_session,
            patch.object(
                socios_page,
                "get_available_date_range",
                return_value=(date(2020, 1, 1), date(2026, 12, 31)),
            ),
            patch.object(socios_page, "get_socios_comerciales", return_value=sample_socios_df) as mock_get_socios,
        ):
            mock_radio.return_value = "Exportaciones (FOB)"
            mock_selectbox.side_effect = [
                "Todas las Gestiones (Consolidado)",  # Year
                "Mundial (Global)",  # Scope
            ]
            mock_slider.return_value = 10
            mock_multiselect.side_effect = [
                ["América del Sur"],  # Continents
                ["MERCOSUR"],  # Blocs
            ]
            mock_columns.side_effect = [
                [MagicMock(), MagicMock(), MagicMock(), MagicMock()],  # 4 KPI columns
                [MagicMock(), MagicMock()],  # Tab 2 (ranking + bloc)
                [MagicMock(), MagicMock()],  # Tab 3 (pareto + evolution)
            ]
            mock_tabs.return_value = [MagicMock(), MagicMock(), MagicMock(), MagicMock()]
            mock_text_input.return_value = "Brasil"

            main()

            mock_get_session.assert_called_once()
            mock_log_event.assert_called_once_with(
                session_id="test-socios-session",
                page="02_socios_comerciales",
                event_type="page_view",
            )
            mock_get_socios.assert_called_once_with(flow="EXPORTACION", year=None)
            mock_download.assert_called_once()

    @patch("streamlit.sidebar")
    @patch("streamlit.radio")
    @patch("streamlit.selectbox")
    @patch("streamlit.slider")
    @patch("streamlit.warning")
    @patch("streamlit.spinner")
    def test_main_handles_empty_bq_data(
        self,
        mock_spinner: MagicMock,
        mock_warning: MagicMock,
        mock_slider: MagicMock,
        mock_selectbox: MagicMock,
        mock_radio: MagicMock,
        mock_sidebar: MagicMock,
    ) -> None:
        with (
            patch.object(socios_page, "log_ui_event"),
            patch.object(socios_page, "get_session_id", return_value="test-socios-session"),
            patch.object(
                socios_page,
                "get_available_date_range",
                return_value=(date(2020, 1, 1), date(2026, 12, 31)),
            ),
            patch.object(socios_page, "get_socios_comerciales", return_value=pd.DataFrame()),
        ):
            mock_radio.return_value = "Importaciones (CIF)"
            mock_selectbox.side_effect = [
                "2024",  # Year
                "Europa",  # Scope
            ]
            mock_slider.return_value = 15

            main()

            mock_warning.assert_called_once()

    @patch("streamlit.sidebar")
    @patch("streamlit.radio")
    @patch("streamlit.selectbox")
    @patch("streamlit.slider")
    @patch("streamlit.multiselect")
    @patch("streamlit.warning")
    @patch("streamlit.spinner")
    def test_main_handles_filtered_empty_data(
        self,
        mock_spinner: MagicMock,
        mock_warning: MagicMock,
        mock_multiselect: MagicMock,
        mock_slider: MagicMock,
        mock_selectbox: MagicMock,
        mock_radio: MagicMock,
        mock_sidebar: MagicMock,
        sample_socios_df: pd.DataFrame,
    ) -> None:
        with (
            patch.object(socios_page, "log_ui_event"),
            patch.object(socios_page, "get_session_id", return_value="test-socios-session"),
            patch.object(
                socios_page,
                "get_available_date_range",
                return_value=(date(2020, 1, 1), date(2026, 12, 31)),
            ),
            patch.object(socios_page, "get_socios_comerciales", return_value=sample_socios_df),
        ):
            mock_radio.return_value = "Exportaciones (FOB)"
            mock_selectbox.side_effect = ["2023", "Mundial (Global)"]
            mock_slider.return_value = 10
            mock_multiselect.side_effect = [
                ["África"],  # Continents that don't match sample_socios_df
                [],
            ]

            main()

            mock_warning.assert_called_once()

    @patch("streamlit.sidebar")
    @patch("streamlit.radio")
    @patch("streamlit.selectbox")
    @patch("streamlit.slider")
    @patch("streamlit.multiselect")
    @patch("streamlit.columns")
    @patch("streamlit.tabs")
    @patch("streamlit.markdown")
    @patch("streamlit.plotly_chart")
    @patch("streamlit.info")
    @patch("streamlit.caption")
    @patch("streamlit.text_input")
    @patch("streamlit.dataframe")
    @patch("streamlit.download_button")
    @patch("streamlit.spinner")
    def test_main_search_filter_zero_results(
        self,
        mock_spinner: MagicMock,
        mock_download: MagicMock,
        mock_dataframe: MagicMock,
        mock_text_input: MagicMock,
        mock_caption: MagicMock,
        mock_info: MagicMock,
        mock_plotly: MagicMock,
        mock_markdown: MagicMock,
        mock_tabs: MagicMock,
        mock_columns: MagicMock,
        mock_multiselect: MagicMock,
        mock_slider: MagicMock,
        mock_selectbox: MagicMock,
        mock_radio: MagicMock,
        mock_sidebar: MagicMock,
        sample_socios_df: pd.DataFrame,
    ) -> None:
        with (
            patch.object(socios_page, "log_ui_event"),
            patch.object(socios_page, "get_session_id", return_value="test-socios-session"),
            patch.object(
                socios_page,
                "get_available_date_range",
                return_value=(date(2020, 1, 1), date(2026, 12, 31)),
            ),
            patch.object(socios_page, "get_socios_comerciales", return_value=sample_socios_df),
        ):
            mock_radio.return_value = "Importaciones (CIF)"
            mock_selectbox.side_effect = ["Todas las Gestiones (Consolidado)", "Mundial (Global)"]
            mock_slider.return_value = 10
            mock_multiselect.side_effect = [[], []]
            mock_columns.side_effect = [
                [MagicMock(), MagicMock(), MagicMock(), MagicMock()],
                [MagicMock(), MagicMock()],
                [MagicMock(), MagicMock()],
            ]
            mock_tabs.return_value = [MagicMock(), MagicMock(), MagicMock(), MagicMock()]
            mock_text_input.return_value = "PaisInexistente12345"

            main()

            mock_dataframe.assert_called_once()
            mock_download.assert_called_once()

    def test_build_choropleth_map_missing_optional_cols(self) -> None:
        df_sparse = pd.DataFrame({
            "pais_iso": ["BRA", "ARG"],
            "total_valor_usd": [1000.0, 500.0],
        })
        fig = build_choropleth_map(df_sparse, flow="EXPORTACION")
        assert isinstance(fig, go.Figure)
        assert len(list(fig.data)) == 1

