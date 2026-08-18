"""InsightBolivia — Pruebas unitarias para el Dashboard 03: Productos Top (`03_productos_top.py`).

Verifica el cómputo de KPIs arancelarios, generadores de gráficos Plotly (ranking
horizontal USD/Volumen, distribución por sector, dispersión de precios FOB/kg y
evolución histórica interanual) y el renderizado integral del dashboard con mocks de Streamlit y BigQuery.
"""

from __future__ import annotations

import importlib
from datetime import date
from unittest.mock import MagicMock, patch

import pandas as pd
import plotly.graph_objects as go
import pytest

from streamlit_app.components.productos_charts import (
    build_price_density_scatter,
    build_sector_distribution_chart,
    build_top_products_bar_chart,
    build_top_products_evolution_chart,
    compute_top_productos_kpis,
    format_currency_millions,
    format_weight_tonnes,
)

# Carga dinámica del módulo de página Streamlit
productos_page = importlib.import_module("streamlit_app.pages.03_productos_top")
main = productos_page.main


@pytest.fixture
def sample_top_productos_df() -> pd.DataFrame:
    """Fixture con registros representativos de vw_top_productos_exportados."""
    return pd.DataFrame({
        "anio": [2023, 2023, 2024, 2024, 2024],
        "ranking": [1, 2, 1, 2, 3],
        "codigo_nandina": ["2711210000", "7108120000", "2711210000", "2304000000", "2608000000"],
        "descripcion_producto": [
            "Gas natural en estado gaseoso",
            "Oro en las demás formas en bruto",
            "Gas natural en estado gaseoso",
            "Tortas y demás residuos de soya",
            "Minerales de cinc y sus concentrados",
        ],
        "partida_nandina": ["2711", "7108", "2711", "2304", "2608"],
        "capitulo_nandina": ["27", "71", "27", "23", "26"],
        "seccion_nandina": ["V", "XIV", "V", "IV", "V"],
        "sector_economico": [
            "Hidrocarburos",
            "Minería",
            "Hidrocarburos",
            "Agroindustria",
            "Minería",
        ],
        "total_fob_usd": [
            2_000_000_000.0,
            1_500_000_000.0,
            1_800_000_000.0,
            1_100_000_000.0,
            900_000_000.0,
        ],
        "total_peso_neto_kg": [
            8_000_000_000.0,
            50_000.0,
            7_000_000_000.0,
            2_500_000_000.0,
            600_000_000.0,
        ],
        "num_transacciones": [1200, 450, 1100, 3200, 2100],
    })


class TestFormattingHelpers:
    """Pruebas para funciones auxiliares de formato."""

    def test_format_currency_billions(self) -> None:
        assert format_currency_millions(3_500_000_000.0) == "$3.50 B"
        assert format_currency_millions(-2_100_000_000.0) == "$-2.10 B"

    def test_format_currency_millions(self) -> None:
        assert format_currency_millions(850_000_000.0) == "$850.00 M"
        assert format_currency_millions(5_500_000.0) == "$5.50 M"

    def test_format_currency_under_million(self) -> None:
        assert format_currency_millions(45_000.0) == "$45,000.00"
        assert format_currency_millions(0.0) == "$0.00"

    def test_format_weight_tonnes(self) -> None:
        assert format_weight_tonnes(5_000_000_000.0) == "5.00 M Ton"
        assert format_weight_tonnes(5_000_000.0) == "5.00 k Ton"
        assert format_weight_tonnes(500_000.0) == "500.0 Ton"
        assert format_weight_tonnes(1_500.0) == "1.5 Ton"


class TestComputeTopProductosKpis:
    """Pruebas para el cálculo de indicadores ejecutivos de productos top."""

    def test_compute_kpis_usd_metric(self, sample_top_productos_df: pd.DataFrame) -> None:
        kpis = compute_top_productos_kpis(sample_top_productos_df, metric="usd")
        assert kpis["total_fob_usd"] == 7_300_000_000.0
        assert kpis["total_peso_kg"] == 18_100_050_000.0
        assert kpis["total_peso_ton"] == 18_100_050.0
        assert kpis["num_productos"] == 4
        assert kpis["top_producto_nombre"] == "Gas natural en estado gaseoso"
        assert kpis["top_producto_nandina"] == "2711210000"
        assert kpis["top_producto_fob_usd"] == 3_800_000_000.0
        assert round(kpis["top_producto_pct"], 2) == 52.05
        assert kpis["top_sector_nombre"] == "Hidrocarburos"
        assert kpis["top_sector_valor"] == 3_800_000_000.0
        assert round(kpis["top_sector_pct"], 2) == 52.05
        assert round(kpis["precio_medio_usd_kg"], 4) == round(7_300_000_000.0 / 18_100_050_000.0, 4)
        assert kpis["total_transacciones"] == 8050
        assert kpis["metric"] == "usd"

    def test_compute_kpis_volume_metric(self, sample_top_productos_df: pd.DataFrame) -> None:
        kpis = compute_top_productos_kpis(sample_top_productos_df, metric="volume")
        assert kpis["total_fob_usd"] == 7_300_000_000.0
        assert kpis["top_producto_nombre"] == "Gas natural en estado gaseoso"
        assert kpis["top_producto_peso_kg"] == 15_000_000_000.0
        assert round(kpis["top_producto_pct"], 2) == round(15_000_000_000.0 / 18_100_050_000.0 * 100.0, 2)
        assert kpis["top_sector_nombre"] == "Hidrocarburos"
        assert kpis["metric"] == "volume"

    def test_compute_kpis_empty_df(self) -> None:
        kpis = compute_top_productos_kpis(pd.DataFrame(), metric="usd")
        assert kpis["total_fob_usd"] == 0.0
        assert kpis["total_peso_kg"] == 0.0
        assert kpis["num_productos"] == 0
        assert kpis["top_producto_nombre"] == "Sin datos"
        assert kpis["top_sector_nombre"] == "Sin datos"
        assert kpis["precio_medio_usd_kg"] == 0.0

    def test_compute_kpis_missing_columns(self) -> None:
        partial_df = pd.DataFrame({
            "total_fob_usd": [100.0],
            "total_peso_neto_kg": [20.0],
        })
        kpis = compute_top_productos_kpis(partial_df, metric="usd")
        assert kpis["total_fob_usd"] == 100.0
        assert kpis["total_peso_kg"] == 20.0
        assert kpis["top_producto_nombre"] == "N/D"
        assert kpis["top_sector_nombre"] == "N/D"
        assert kpis["precio_medio_usd_kg"] == 5.0


class TestPlotlyTopProductosChartBuilders:
    """Pruebas para los generadores de gráficos Plotly."""

    def test_build_top_products_bar_chart_usd(self, sample_top_productos_df: pd.DataFrame) -> None:
        fig = build_top_products_bar_chart(sample_top_productos_df, metric="usd", top_n=10)
        assert isinstance(fig, go.Figure)
        assert len(fig.data) == 1
        assert fig.data[0].type == "bar"
        assert fig.data[0].orientation == "h"

    def test_build_top_products_bar_chart_volume(self, sample_top_productos_df: pd.DataFrame) -> None:
        fig = build_top_products_bar_chart(sample_top_productos_df, metric="volume", top_n=5)
        assert isinstance(fig, go.Figure)
        assert len(fig.data) == 1
        assert fig.data[0].type == "bar"

    def test_build_top_products_bar_chart_empty(self) -> None:
        fig = build_top_products_bar_chart(pd.DataFrame())
        assert isinstance(fig, go.Figure)
        assert len(fig.data) == 0

    def test_build_sector_distribution_chart_usd(self, sample_top_productos_df: pd.DataFrame) -> None:
        fig = build_sector_distribution_chart(sample_top_productos_df, metric="usd")
        assert isinstance(fig, go.Figure)
        assert len(fig.data) == 1
        assert fig.data[0].type == "pie"
        assert fig.data[0].hole == 0.55

    def test_build_sector_distribution_chart_volume(self, sample_top_productos_df: pd.DataFrame) -> None:
        fig = build_sector_distribution_chart(sample_top_productos_df, metric="volume")
        assert isinstance(fig, go.Figure)
        assert len(fig.data) == 1
        assert fig.data[0].type == "pie"

    def test_build_sector_distribution_chart_empty(self) -> None:
        fig = build_sector_distribution_chart(pd.DataFrame())
        assert isinstance(fig, go.Figure)
        assert len(fig.data) == 0

    def test_build_price_density_scatter(self, sample_top_productos_df: pd.DataFrame) -> None:
        fig = build_price_density_scatter(sample_top_productos_df)
        assert isinstance(fig, go.Figure)
        assert len(fig.data) > 0
        assert fig.data[0].type == "scatter"
        assert fig.data[0].mode == "markers+text"

    def test_build_price_density_scatter_empty(self) -> None:
        fig = build_price_density_scatter(pd.DataFrame())
        assert isinstance(fig, go.Figure)
        assert len(fig.data) == 0

    def test_build_top_products_evolution_chart_usd(self, sample_top_productos_df: pd.DataFrame) -> None:
        fig = build_top_products_evolution_chart(sample_top_productos_df, metric="usd", top_n=3)
        assert isinstance(fig, go.Figure)
        assert len(fig.data) > 0
        for trace in fig.data:
            assert trace.type == "scatter"

    def test_build_top_products_evolution_chart_volume(self, sample_top_productos_df: pd.DataFrame) -> None:
        fig = build_top_products_evolution_chart(sample_top_productos_df, metric="volume", top_n=3)
        assert isinstance(fig, go.Figure)
        assert len(fig.data) > 0

    def test_build_top_products_evolution_chart_empty(self) -> None:
        fig = build_top_products_evolution_chart(pd.DataFrame())
        assert isinstance(fig, go.Figure)
        assert len(fig.data) == 0


class TestProductosPageMain:
    """Pruebas de integración para la función main() de 03_productos_top.py."""

    @patch("streamlit.set_page_config")
    @patch("streamlit.markdown")
    @patch("streamlit.sidebar")
    @patch("streamlit.selectbox")
    @patch("streamlit.radio")
    @patch("streamlit.slider")
    @patch("streamlit.multiselect")
    @patch("streamlit.spinner")
    @patch("streamlit.columns")
    @patch("streamlit.tabs")
    @patch("streamlit.plotly_chart")
    @patch("streamlit.info")
    @patch("streamlit.caption")
    @patch("streamlit.text_input")
    @patch("streamlit.dataframe")
    @patch("streamlit.download_button")
    def test_main_renders_successfully_with_data(
        self,
        mock_download: MagicMock,
        mock_df: MagicMock,
        mock_text_input: MagicMock,
        mock_caption: MagicMock,
        mock_info: MagicMock,
        mock_plotly: MagicMock,
        mock_tabs: MagicMock,
        mock_columns: MagicMock,
        mock_spinner: MagicMock,
        mock_multiselect: MagicMock,
        mock_slider: MagicMock,
        mock_radio: MagicMock,
        mock_selectbox: MagicMock,
        mock_sidebar: MagicMock,
        mock_markdown: MagicMock,
        mock_set_page: MagicMock,
        sample_top_productos_df: pd.DataFrame,
    ) -> None:
        with (
            patch.object(productos_page, "log_ui_event") as mock_log,
            patch.object(productos_page, "get_session_id", return_value="session-test-123"),
            patch.object(
                productos_page,
                "get_available_date_range",
                return_value=(date(2023, 1, 1), date(2024, 12, 31)),
            ),
            patch.object(productos_page, "get_top_productos", return_value=sample_top_productos_df) as mock_get_top,
        ):
            mock_selectbox.return_value = "2024"
            mock_radio.return_value = "Valor FOB (USD)"
            mock_slider.return_value = 10
            mock_multiselect.return_value = []
            mock_columns.side_effect = [
                [MagicMock(), MagicMock(), MagicMock(), MagicMock()],
                [MagicMock(), MagicMock()],
            ]
            mock_tabs.return_value = [MagicMock(), MagicMock(), MagicMock(), MagicMock()]
            mock_text_input.return_value = ""

            main()

            mock_set_page.assert_called_once()
            mock_log.assert_called_once_with(
                session_id="session-test-123",
                page="03_productos_top",
                event_type="page_view",
            )
            mock_get_top.assert_called_once_with(year=2024, limit=10)
            mock_df.assert_called_once()
            mock_download.assert_called_once()

    @patch("streamlit.set_page_config")
    @patch("streamlit.markdown")
    @patch("streamlit.sidebar")
    @patch("streamlit.selectbox")
    @patch("streamlit.radio")
    @patch("streamlit.slider")
    @patch("streamlit.spinner")
    @patch("streamlit.warning")
    def test_main_handles_empty_bq_data(
        self,
        mock_warning: MagicMock,
        mock_spinner: MagicMock,
        mock_slider: MagicMock,
        mock_radio: MagicMock,
        mock_selectbox: MagicMock,
        mock_sidebar: MagicMock,
        mock_markdown: MagicMock,
        mock_set_page: MagicMock,
    ) -> None:
        with (
            patch.object(productos_page, "log_ui_event"),
            patch.object(productos_page, "get_session_id", return_value="session-test-123"),
            patch.object(
                productos_page,
                "get_available_date_range",
                return_value=(date(2020, 1, 1), date(2024, 12, 31)),
            ),
            patch.object(productos_page, "get_top_productos", return_value=pd.DataFrame()) as mock_get_top,
        ):
            mock_selectbox.return_value = "Todas las Gestiones (Consolidado)"
            mock_radio.return_value = "Valor FOB (USD)"
            mock_slider.return_value = 10

            main()
            mock_get_top.assert_called_once_with(year=None, limit=10)
            mock_warning.assert_called_once()

    @patch("streamlit.set_page_config")
    @patch("streamlit.markdown")
    @patch("streamlit.sidebar")
    @patch("streamlit.selectbox")
    @patch("streamlit.radio")
    @patch("streamlit.slider")
    @patch("streamlit.multiselect")
    @patch("streamlit.spinner")
    @patch("streamlit.warning")
    def test_main_handles_filtered_empty_data(
        self,
        mock_warning: MagicMock,
        mock_spinner: MagicMock,
        mock_multiselect: MagicMock,
        mock_slider: MagicMock,
        mock_radio: MagicMock,
        mock_selectbox: MagicMock,
        mock_sidebar: MagicMock,
        mock_markdown: MagicMock,
        mock_set_page: MagicMock,
        sample_top_productos_df: pd.DataFrame,
    ) -> None:
        with (
            patch.object(productos_page, "log_ui_event"),
            patch.object(productos_page, "get_session_id", return_value="session-test-123"),
            patch.object(
                productos_page,
                "get_available_date_range",
                return_value=(date(2023, 1, 1), date(2024, 12, 31)),
            ),
            patch.object(productos_page, "get_top_productos", return_value=sample_top_productos_df),
        ):
            mock_selectbox.return_value = "2024"
            mock_radio.return_value = "Volumen Físico (Toneladas)"
            mock_slider.return_value = 5
            mock_multiselect.return_value = ["Sector Inexistente"]

            main()
            mock_warning.assert_called_once()

    @patch("streamlit.set_page_config")
    @patch("streamlit.markdown")
    @patch("streamlit.sidebar")
    @patch("streamlit.selectbox")
    @patch("streamlit.radio")
    @patch("streamlit.slider")
    @patch("streamlit.multiselect")
    @patch("streamlit.spinner")
    @patch("streamlit.columns")
    @patch("streamlit.tabs")
    @patch("streamlit.plotly_chart")
    @patch("streamlit.info")
    @patch("streamlit.caption")
    @patch("streamlit.text_input")
    @patch("streamlit.dataframe")
    @patch("streamlit.download_button")
    def test_main_search_filter_and_download(
        self,
        mock_download: MagicMock,
        mock_df: MagicMock,
        mock_text_input: MagicMock,
        mock_caption: MagicMock,
        mock_info: MagicMock,
        mock_plotly: MagicMock,
        mock_tabs: MagicMock,
        mock_columns: MagicMock,
        mock_spinner: MagicMock,
        mock_multiselect: MagicMock,
        mock_slider: MagicMock,
        mock_radio: MagicMock,
        mock_selectbox: MagicMock,
        mock_sidebar: MagicMock,
        mock_markdown: MagicMock,
        mock_set_page: MagicMock,
        sample_top_productos_df: pd.DataFrame,
    ) -> None:
        with (
            patch.object(productos_page, "log_ui_event"),
            patch.object(productos_page, "get_session_id", return_value="session-test-123"),
            patch.object(
                productos_page,
                "get_available_date_range",
                return_value=(date(2023, 1, 1), date(2024, 12, 31)),
            ),
            patch.object(productos_page, "get_top_productos", return_value=sample_top_productos_df),
        ):
            mock_selectbox.return_value = "Todas las Gestiones (Consolidado)"
            mock_radio.return_value = "Volumen Físico (Toneladas)"
            mock_slider.return_value = 10
            mock_multiselect.return_value = ["Hidrocarburos"]
            mock_columns.side_effect = [
                [MagicMock(), MagicMock(), MagicMock(), MagicMock()],
                [MagicMock(), MagicMock()],
            ]
            mock_tabs.return_value = [MagicMock(), MagicMock(), MagicMock(), MagicMock()]
            mock_text_input.return_value = "gas"

            main()
            mock_df.assert_called_once()
            mock_download.assert_called_once()
