"""InsightBolivia — Pruebas unitarias para el Dashboard 01: Balanza Comercial (`01_balanza_comercial.py`).

Verifica el cómputo de KPIs, agregación temporal por frecuencia, constructores de gráficos Plotly,
formato de monedas y renderizado integral del dashboard con mocks de Streamlit y BigQuery.
"""

from __future__ import annotations

import importlib
from datetime import date
from unittest.mock import MagicMock, patch

import pandas as pd
import plotly.graph_objects as go
import pytest

# Carga de utilidades y componentes analíticos
from streamlit_app.components.balanza_charts import (
    aggregate_balanza_data,
    build_annual_comparison_chart,
    build_balance_bar_chart,
    build_evolution_chart,
    build_volume_chart,
    compute_balanza_kpis,
    format_currency_millions,
)

# Carga dinámica del entrypoint de página Streamlit (prefijo numérico)
balanza_page = importlib.import_module("streamlit_app.pages.01_balanza_comercial")
main = balanza_page.main


@pytest.fixture
def sample_balanza_df() -> pd.DataFrame:
    """Fixture con registros representativos de la vista vw_balanza_comercial_mensual."""
    return pd.DataFrame({
        "anio": [2023, 2023, 2024, 2024],
        "mes": [1, 2, 1, 2],
        "nombre_mes": ["Enero", "Febrero", "Enero", "Febrero"],
        "trimestre": [1, 1, 1, 1],
        "semestre": [1, 1, 1, 1],
        "fecha": [date(2023, 1, 1), date(2023, 2, 1), date(2024, 1, 1), date(2024, 2, 1)],
        "total_exportaciones_usd": [900_000_000.0, 1_100_000_000.0, 800_000_000.0, 750_000_000.0],
        "total_importaciones_usd": [850_000_000.0, 950_000_000.0, 850_000_000.0, 800_000_000.0],
        "saldo_balanza_usd": [50_000_000.0, 150_000_000.0, -50_000_000.0, -50_000_000.0],
        "total_peso_neto_exportaciones_kg": [500_000_000.0, 600_000_000.0, 450_000_000.0, 400_000_000.0],
        "total_peso_bruto_importaciones_kg": [300_000_000.0, 350_000_000.0, 320_000_000.0, 310_000_000.0],
        "num_transacciones_exportacion": [1200, 1350, 1100, 1050],
        "num_transacciones_importacion": [4500, 4800, 4600, 4400],
    })


class TestFormattingHelpers:
    """Pruebas para funciones de formato de moneda y texto."""

    def test_format_currency_billions(self) -> None:
        assert format_currency_millions(1_500_000_000.0) == "$1.50 B"
        assert format_currency_millions(-2_345_000_000.0) == "$-2.35 B"

    def test_format_currency_millions(self) -> None:
        assert format_currency_millions(250_000_000.0) == "$250.00 M"
        assert format_currency_millions(-45_500_000.0) == "$-45.50 M"

    def test_format_currency_under_million(self) -> None:
        assert format_currency_millions(45_000.50) == "$45,000.50"
        assert format_currency_millions(0.0) == "$0.00"


class TestComputeBalanzaKpis:
    """Pruebas para cálculo de indicadores de balanza comercial."""

    def test_compute_kpis_with_data(self, sample_balanza_df: pd.DataFrame) -> None:
        kpis = compute_balanza_kpis(sample_balanza_df)
        assert kpis["total_exportaciones_usd"] == 3_550_000_000.0
        assert kpis["total_importaciones_usd"] == 3_450_000_000.0
        assert kpis["saldo_balanza_usd"] == 100_000_000.0
        assert kpis["es_superavit"] is True
        assert round(kpis["tasa_cobertura_pct"], 2) == 102.90
        assert kpis["total_peso_neto_exp_ton"] == 1_950_000.0
        assert kpis["total_peso_bruto_imp_ton"] == 1_280_000.0
        assert kpis["num_transacciones_exp"] == 4700
        assert kpis["num_transacciones_imp"] == 18300
        assert kpis["num_meses"] == 4

    def test_compute_kpis_empty_dataframe(self) -> None:
        empty_df = pd.DataFrame()
        kpis = compute_balanza_kpis(empty_df)
        assert kpis["total_exportaciones_usd"] == 0.0
        assert kpis["total_importaciones_usd"] == 0.0
        assert kpis["saldo_balanza_usd"] == 0.0
        assert kpis["tasa_cobertura_pct"] == 0.0
        assert kpis["num_meses"] == 0
        assert kpis["es_superavit"] is True

    def test_compute_kpis_deficit_and_zero_imports(self) -> None:
        df_zero_imp = pd.DataFrame({
            "total_exportaciones_usd": [100.0],
            "total_importaciones_usd": [0.0],
            "total_peso_neto_exportaciones_kg": [50.0],
            "total_peso_bruto_importaciones_kg": [0.0],
        })
        kpis = compute_balanza_kpis(df_zero_imp)
        assert kpis["tasa_cobertura_pct"] == 0.0
        assert kpis["saldo_balanza_usd"] == 100.0
        assert kpis["es_superavit"] is True

        df_deficit = pd.DataFrame({
            "total_exportaciones_usd": [100.0],
            "total_importaciones_usd": [300.0],
            "total_peso_neto_exportaciones_kg": [50.0],
            "total_peso_bruto_importaciones_kg": [200.0],
        })
        kpis_def = compute_balanza_kpis(df_deficit)
        assert kpis_def["saldo_balanza_usd"] == -200.0
        assert kpis_def["es_superavit"] is False


class TestAggregateBalanzaData:
    """Pruebas para agregación temporal por granularidad."""

    def test_aggregate_monthly(self, sample_balanza_df: pd.DataFrame) -> None:
        agg = aggregate_balanza_data(sample_balanza_df, freq="Mensual")
        assert len(agg) == 4
        assert "periodo_label" in agg.columns
        assert list(agg["periodo_label"]) == ["2023-01", "2023-02", "2024-01", "2024-02"]

    def test_aggregate_quarterly(self, sample_balanza_df: pd.DataFrame) -> None:
        agg = aggregate_balanza_data(sample_balanza_df, freq="Trimestral")
        assert len(agg) == 2
        assert "2023 - T1" in list(agg["periodo_label"])
        assert "2024 - T1" in list(agg["periodo_label"])

    def test_aggregate_annual(self, sample_balanza_df: pd.DataFrame) -> None:
        agg = aggregate_balanza_data(sample_balanza_df, freq="Anual")
        assert len(agg) == 2
        assert list(agg["periodo_label"]) == ["2023", "2024"]
        assert agg.loc[agg["anio"] == 2023, "total_exportaciones_usd"].iloc[0] == 2_000_000_000.0

    def test_aggregate_empty_dataframe(self) -> None:
        empty_df = pd.DataFrame()
        agg = aggregate_balanza_data(empty_df, freq="Mensual")
        assert agg.empty


class TestPlotlyChartBuilders:
    """Pruebas para la generación de gráficos Plotly."""

    def test_build_evolution_chart(self, sample_balanza_df: pd.DataFrame) -> None:
        agg = aggregate_balanza_data(sample_balanza_df, freq="Mensual")
        fig = build_evolution_chart(agg)
        assert isinstance(fig, go.Figure)
        data = list(fig.data)
        assert len(data) == 2  # Trace 0: Exportaciones, Trace 1: Importaciones
        assert getattr(data[0], "name", "") == "Exportaciones (FOB)"
        assert getattr(data[1], "name", "") == "Importaciones (CIF)"

    def test_build_evolution_chart_empty(self) -> None:
        fig = build_evolution_chart(pd.DataFrame())
        assert isinstance(fig, go.Figure)
        assert len(list(fig.data)) == 0

    def test_build_balance_bar_chart(self, sample_balanza_df: pd.DataFrame) -> None:
        agg = aggregate_balanza_data(sample_balanza_df, freq="Mensual")
        fig = build_balance_bar_chart(agg)
        assert isinstance(fig, go.Figure)
        data = list(fig.data)
        assert len(data) == 1
        assert getattr(data[0], "name", "") == "Saldo Comercial"

    def test_build_balance_bar_chart_empty(self) -> None:
        fig = build_balance_bar_chart(pd.DataFrame())
        assert isinstance(fig, go.Figure)
        assert len(list(fig.data)) == 0

    def test_build_annual_comparison_chart(self, sample_balanza_df: pd.DataFrame) -> None:
        fig = build_annual_comparison_chart(sample_balanza_df)
        assert isinstance(fig, go.Figure)
        assert len(list(fig.data)) == 2

    def test_build_annual_comparison_chart_empty_and_no_anio(self) -> None:
        fig_empty = build_annual_comparison_chart(pd.DataFrame())
        assert len(list(fig_empty.data)) == 0

        fig_no_anio = build_annual_comparison_chart(pd.DataFrame({"col": [1, 2]}))
        assert len(list(fig_no_anio.data)) == 0

    def test_build_volume_chart(self, sample_balanza_df: pd.DataFrame) -> None:
        agg = aggregate_balanza_data(sample_balanza_df, freq="Mensual")
        fig = build_volume_chart(agg)
        assert isinstance(fig, go.Figure)
        assert len(list(fig.data)) == 2

    def test_build_volume_chart_empty(self) -> None:
        fig = build_volume_chart(pd.DataFrame())
        assert isinstance(fig, go.Figure)
        assert len(list(fig.data)) == 0


class TestMainPageRendering:
    """Pruebas para el entrypoint main() del dashboard de Balanza Comercial."""

    @patch("streamlit.sidebar")
    @patch("streamlit.selectbox")
    @patch("streamlit.date_input")
    @patch("streamlit.radio")
    @patch("streamlit.columns")
    @patch("streamlit.tabs")
    @patch("streamlit.markdown")
    @patch("streamlit.plotly_chart")
    @patch("streamlit.dataframe")
    @patch("streamlit.download_button")
    @patch("streamlit.spinner")
    def test_main_renders_successfully_with_data(
        self,
        mock_spinner: MagicMock,
        mock_download: MagicMock,
        mock_dataframe: MagicMock,
        mock_plotly: MagicMock,
        mock_markdown: MagicMock,
        mock_tabs: MagicMock,
        mock_columns: MagicMock,
        mock_radio: MagicMock,
        mock_date_input: MagicMock,
        mock_selectbox: MagicMock,
        mock_sidebar: MagicMock,
        sample_balanza_df: pd.DataFrame,
    ) -> None:
        with (
            patch.object(balanza_page, "log_ui_event") as mock_log_event,
            patch.object(balanza_page, "get_session_id", return_value="test-balanza-session") as mock_get_session,
            patch.object(
                balanza_page,
                "get_available_date_range",
                return_value=(date(2020, 1, 1), date(2026, 12, 31)),
            ),
            patch.object(balanza_page, "get_balanza_comercial", return_value=sample_balanza_df) as mock_get_balanza,
        ):
            mock_selectbox.return_value = "Últimos 3 años"
            mock_date_input.return_value = (date(2023, 1, 1), date(2024, 2, 1))
            mock_radio.return_value = "Mensual"
            mock_columns.return_value = [MagicMock(), MagicMock(), MagicMock(), MagicMock()]
            mock_tabs.return_value = [MagicMock(), MagicMock(), MagicMock(), MagicMock()]

            main()

            mock_get_session.assert_called_once()
            mock_log_event.assert_called_once_with(
                session_id="test-balanza-session",
                page="01_balanza_comercial",
                event_type="page_view",
            )
            mock_get_balanza.assert_called_once_with(
                start_date=date(2023, 1, 1),
                end_date=date(2024, 2, 1),
            )
            mock_download.assert_called_once()

    @patch("streamlit.sidebar")
    @patch("streamlit.selectbox")
    @patch("streamlit.date_input")
    @patch("streamlit.radio")
    @patch("streamlit.warning")
    @patch("streamlit.spinner")
    def test_main_handles_empty_data(
        self,
        mock_spinner: MagicMock,
        mock_warning: MagicMock,
        mock_radio: MagicMock,
        mock_date_input: MagicMock,
        mock_selectbox: MagicMock,
        mock_sidebar: MagicMock,
    ) -> None:
        with (
            patch.object(balanza_page, "log_ui_event"),
            patch.object(balanza_page, "get_session_id", return_value="test-balanza-session"),
            patch.object(
                balanza_page,
                "get_available_date_range",
                return_value=(date(2020, 1, 1), date(2026, 12, 31)),
            ),
            patch.object(balanza_page, "get_balanza_comercial", return_value=pd.DataFrame()),
        ):
            mock_selectbox.return_value = "Últimos 5 años"
            mock_date_input.return_value = [date(2020, 1, 1)]  # Single date in list

            main()

            mock_warning.assert_called_once()

    @patch("streamlit.sidebar")
    @patch("streamlit.selectbox")
    @patch("streamlit.date_input")
    @patch("streamlit.radio")
    @patch("streamlit.warning")
    @patch("streamlit.spinner")
    def test_main_preset_branches(
        self,
        mock_spinner: MagicMock,
        mock_warning: MagicMock,
        mock_radio: MagicMock,
        mock_date_input: MagicMock,
        mock_selectbox: MagicMock,
        mock_sidebar: MagicMock,
    ) -> None:
        with (
            patch.object(balanza_page, "log_ui_event"),
            patch.object(balanza_page, "get_session_id", return_value="test-balanza-session"),
            patch.object(
                balanza_page,
                "get_available_date_range",
                return_value=(date(2020, 1, 1), date(2026, 12, 31)),
            ),
            patch.object(balanza_page, "get_balanza_comercial", return_value=pd.DataFrame()),
        ):
            for preset_choice in ["Todo el histórico", "Rango Personalizado"]:
                mock_selectbox.return_value = preset_choice
                mock_date_input.return_value = date(2022, 1, 1)
                main()

            assert mock_warning.call_count == 2
