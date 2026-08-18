"""InsightBolivia — Pruebas unitarias para el Dashboard 05: Benchmark Regional (`05_benchmark_regional.py`).

Verifica el cómputo de KPIs macroeconómicos, formateo dinámico según unidad, constructores
de gráficos Plotly (series temporales, ranking de barras, dispersión por cuadrantes, radar multidimensional),
generador de datos de fallback y renderizado integral del dashboard con mocks de Streamlit y BigQuery.
"""

from __future__ import annotations

import importlib
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import pytest

from streamlit_app.components.benchmark_charts import (
    COUNTRY_NAMES_ES,
    INDICATOR_METADATA,
    build_multidimensional_radar_chart,
    build_quadrant_scatter_chart,
    build_ranking_bar_chart,
    build_time_series_chart,
    compute_benchmark_kpis,
    format_indicator_value,
)

# Carga dinámica del módulo de página Streamlit
benchmark_page = importlib.import_module("streamlit_app.pages.05_benchmark_regional")
main = benchmark_page.main
generate_fallback_benchmark_data = benchmark_page.generate_fallback_benchmark_data


@pytest.fixture
def sample_benchmark_df() -> pd.DataFrame:
    """Fixture con registros representativos de la tabla fact_indicadores_bm."""
    rows = []


    values_map = {
        ("BOL", "NE.EXP.GNFS.KD.ZG", 2022): 8.5,
        ("BOL", "NE.EXP.GNFS.KD.ZG", 2023): 4.5,
        ("PER", "NE.EXP.GNFS.KD.ZG", 2023): 6.0,
        ("CHL", "NE.EXP.GNFS.KD.ZG", 2023): 2.0,
        ("COL", "NE.EXP.GNFS.KD.ZG", 2023): 3.0,
        ("PRY", "NE.EXP.GNFS.KD.ZG", 2023): 5.0,
        ("BRA", "NE.EXP.GNFS.KD.ZG", 2023): 1.5,
        ("ARG", "NE.EXP.GNFS.KD.ZG", 2023): -1.0,
        # PIB
        ("BOL", "NY.GDP.MKTP.KD.ZG", 2023): 3.1,
        ("PER", "NY.GDP.MKTP.KD.ZG", 2023): -0.5,
        ("CHL", "NY.GDP.MKTP.KD.ZG", 2023): 0.2,
        ("COL", "NY.GDP.MKTP.KD.ZG", 2023): 0.6,
        ("PRY", "NY.GDP.MKTP.KD.ZG", 2023): 4.7,
        ("BRA", "NY.GDP.MKTP.KD.ZG", 2023): 2.9,
        ("ARG", "NY.GDP.MKTP.KD.ZG", 2023): -1.6,
        # Inflación
        ("BOL", "FP.CPI.TOTL.ZG", 2023): 2.6,
        ("PER", "FP.CPI.TOTL.ZG", 2023): 6.3,
        ("CHL", "FP.CPI.TOTL.ZG", 2023): 7.6,
        ("COL", "FP.CPI.TOTL.ZG", 2023): 11.7,
        ("PRY", "FP.CPI.TOTL.ZG", 2023): 4.6,
        ("BRA", "FP.CPI.TOTL.ZG", 2023): 4.6,
        ("ARG", "FP.CPI.TOTL.ZG", 2023): 133.5,
        # Apertura
        ("BOL", "NE.TRD.GNFS.ZS", 2023): 54.0,
        ("PER", "NE.TRD.GNFS.ZS", 2023): 51.0,
        ("CHL", "NE.TRD.GNFS.ZS", 2023): 63.0,
        ("COL", "NE.TRD.GNFS.ZS", 2023): 38.0,
        ("PRY", "NE.TRD.GNFS.ZS", 2023): 75.0,
        ("BRA", "NE.TRD.GNFS.ZS", 2023): 29.0,
        ("ARG", "NE.TRD.GNFS.ZS", 2023): 31.0,
    }

    for (c, ind, y), val in values_map.items():
        rows.append({
            "id_indicador_bm": f"{c}_{ind}_{y}",
            "fecha": f"{y}-01-01",
            "anio": y,
            "pais_iso": c,
            "pais_nombre": COUNTRY_NAMES_ES.get(c, c),
            "codigo_indicador": ind,
            "nombre_indicador": INDICATOR_METADATA.get(ind, {}).get("nombre", ind),
            "valor": float(val),
            "unidad_medida": INDICATOR_METADATA.get(ind, {}).get("unidad", "%"),
            "fuente": "Banco Mundial - WDI",
            "fecha_extraccion": datetime.now(UTC),
        })

    return pd.DataFrame(rows)


class TestFormattingHelpers:
    """Pruebas unitarias para formateo dinámico de valores de indicadores."""

    def test_format_percentage_values(self) -> None:
        assert format_indicator_value(4.55, "%") == "+4.55%"
        assert format_indicator_value(-2.30, "%") == "-2.30%"
        assert format_indicator_value(0.0, "%") == "0.00%"

    def test_format_usd_billions(self) -> None:
        assert format_indicator_value(45_200_000_000.0, "USD") == "$45.20 B"
        assert format_indicator_value(1_500_000_000.0, "USD") == "$1.50 B"

    def test_format_usd_millions(self) -> None:
        assert format_indicator_value(850_000_000.0, "USD") == "$850.00 M"
        assert format_indicator_value(2_400_000.0, "USD") == "$2.40 M"

    def test_format_usd_small(self) -> None:
        assert format_indicator_value(500.50, "USD") == "$500.50"

    def test_format_nan_and_none(self) -> None:
        assert format_indicator_value(None, "%") == "N/D"
        assert format_indicator_value(float("nan"), "USD") == "N/D"
        assert format_indicator_value(np.nan, "%") == "N/D"

    def test_format_custom_unit(self) -> None:
        assert format_indicator_value(12.5, "kg") == "12.50 kg"


class TestComputeBenchmarkKpis:
    """Pruebas unitarias para el cómputo de métricas y rankings de benchmark."""

    def test_compute_kpis_with_data(self, sample_benchmark_df: pd.DataFrame) -> None:
        kpis = compute_benchmark_kpis(sample_benchmark_df, indicator_code="NE.EXP.GNFS.KD.ZG", target_year=2023)
        assert kpis["bolivia_value"] == 4.5
        assert kpis["target_year"] == 2023
        assert kpis["total_countries"] == 7
        assert round(kpis["regional_avg"], 2) == 3.0
        assert round(kpis["delta_vs_avg"], 2) == 1.5
        assert kpis["bolivia_rank"] == 3  # PER (6.0), PRY (5.0), BOL (4.5)
        assert kpis["best_country_iso"] == "PER"
        assert kpis["best_value"] == 6.0
        assert kpis["bolivia_prev_value"] == 8.5
        assert round(kpis["bolivia_yoy_delta"], 2) == -4.0

    def test_compute_kpis_empty_dataframe(self) -> None:
        empty_df = pd.DataFrame()
        kpis = compute_benchmark_kpis(empty_df, indicator_code="NE.EXP.GNFS.KD.ZG", target_year=2023)
        assert kpis["bolivia_value"] is None
        assert kpis["bolivia_rank"] is None
        assert kpis["total_countries"] == 0
        assert kpis["regional_avg"] == 0.0

    def test_compute_kpis_missing_year(self, sample_benchmark_df: pd.DataFrame) -> None:
        kpis = compute_benchmark_kpis(sample_benchmark_df, indicator_code="NE.EXP.GNFS.KD.ZG", target_year=1990)
        assert kpis["bolivia_value"] is None
        assert kpis["total_countries"] == 0

    def test_compute_kpis_without_bolivia(self, sample_benchmark_df: pd.DataFrame) -> None:
        df_no_bol = sample_benchmark_df[sample_benchmark_df["pais_iso"] != "BOL"].copy()
        kpis = compute_benchmark_kpis(df_no_bol, indicator_code="NE.EXP.GNFS.KD.ZG", target_year=2023)
        assert kpis["bolivia_value"] is None
        assert kpis["bolivia_rank"] is None
        assert kpis["total_countries"] == 6


class TestChartBuilders:
    """Pruebas unitarias para constructores de gráficos interactivos Plotly."""

    def test_build_time_series_chart_with_data(self, sample_benchmark_df: pd.DataFrame) -> None:
        fig = build_time_series_chart(
            sample_benchmark_df,
            indicator_code="NE.EXP.GNFS.KD.ZG",
            selected_countries=["BOL", "PER", "CHL"],
            show_regional_avg=True,
        )
        assert isinstance(fig, go.Figure)
        trace_names = [t.name for t in fig.data]
        assert "Promedio Regional" in trace_names
        assert "🇧🇴 Bolivia" in trace_names
        assert any("Perú" in str(name) for name in trace_names)

    def test_build_time_series_chart_empty(self) -> None:
        fig = build_time_series_chart(pd.DataFrame())
        assert isinstance(fig, go.Figure)

    def test_build_ranking_bar_chart_with_data(self, sample_benchmark_df: pd.DataFrame) -> None:
        fig = build_ranking_bar_chart(
            sample_benchmark_df,
            indicator_code="NE.EXP.GNFS.KD.ZG",
            target_year=2023,
            selected_countries=["BOL", "PER", "CHL", "COL", "PRY"],
        )
        assert isinstance(fig, go.Figure)
        assert len(fig.data) == 1
        assert fig.data[0].type == "bar"
        assert len(fig.data[0].x) == 5

    def test_build_ranking_bar_chart_empty(self) -> None:
        fig = build_ranking_bar_chart(pd.DataFrame())
        assert isinstance(fig, go.Figure)

    def test_build_quadrant_scatter_chart_with_data(self, sample_benchmark_df: pd.DataFrame) -> None:
        fig = build_quadrant_scatter_chart(
            sample_benchmark_df,
            x_indicator="NY.GDP.MKTP.KD.ZG",
            y_indicator="NE.EXP.GNFS.KD.ZG",
            target_year=2023,
            selected_countries=["BOL", "PER", "CHL", "COL"],
        )
        assert isinstance(fig, go.Figure)
        assert len(fig.data) >= 4
        assert fig.data[0].type == "scatter"

    def test_build_quadrant_scatter_chart_empty(self) -> None:
        fig = build_quadrant_scatter_chart(pd.DataFrame())
        assert isinstance(fig, go.Figure)

    def test_build_multidimensional_radar_chart_with_data(self, sample_benchmark_df: pd.DataFrame) -> None:
        fig = build_multidimensional_radar_chart(
            sample_benchmark_df,
            target_year=2023,
            compare_country="PER",
        )
        assert isinstance(fig, go.Figure)
        assert len(fig.data) == 3  # Promedio Regional, Perú, Bolivia
        assert fig.data[0].type == "scatterpolar"
        assert fig.data[1].type == "scatterpolar"
        assert fig.data[2].type == "scatterpolar"

    def test_build_multidimensional_radar_chart_empty(self) -> None:
        fig = build_multidimensional_radar_chart(pd.DataFrame())
        assert isinstance(fig, go.Figure)


class TestFallbackDataGenerator:
    """Pruebas para el generador determinista de datos de fallback/demo."""

    def test_generate_fallback_benchmark_data_structure(self) -> None:
        df = generate_fallback_benchmark_data()
        assert not df.empty
        assert "pais_iso" in df.columns
        assert "codigo_indicador" in df.columns
        assert "anio" in df.columns
        assert "valor" in df.columns
        assert "BOL" in df["pais_iso"].unique()
        assert "NE.EXP.GNFS.KD.ZG" in df["codigo_indicador"].unique()
        assert len(df["anio"].unique()) >= 10


class TestMainPageRendering:
    """Pruebas de renderizado de la página Streamlit con mocks."""

    def test_benchmark_regional_renders_successfully(self, sample_benchmark_df: pd.DataFrame) -> None:
        with (
            patch("streamlit.set_page_config") as mock_cfg,
            patch("streamlit.markdown"),
            patch("streamlit.sidebar"),
            patch("streamlit.image"),
            patch("streamlit.selectbox") as mock_sel,
            patch("streamlit.slider", return_value=(2010, 2023)),
            patch("streamlit.multiselect", return_value=["BOL", "PER", "CHL", "COL", "PRY"]),
            patch("streamlit.checkbox", return_value=True),
            patch("streamlit.spinner"),
            patch("streamlit.columns") as mock_cols,
            patch("streamlit.tabs") as mock_tabs,
            patch("streamlit.plotly_chart"),
            patch("streamlit.caption"),
            patch("streamlit.dataframe"),
            patch("streamlit.download_button"),
            patch.object(benchmark_page, "get_benchmark_indicadores", return_value=sample_benchmark_df),
            patch.object(benchmark_page, "log_ui_event") as mock_log,
            patch.object(benchmark_page, "get_session_id", return_value="sess-123"),
        ):
            mock_sel.side_effect = ["NE.EXP.GNFS.KD.ZG", 2023, "PER"]
            mock_cols.return_value = [MagicMock(), MagicMock(), MagicMock(), MagicMock()]
            mock_tabs.return_value = [MagicMock(), MagicMock(), MagicMock(), MagicMock(), MagicMock()]

            main()

            mock_cfg.assert_called_once()
            mock_log.assert_called_once_with(
                session_id="sess-123", page="05_benchmark_regional", event_type="page_view"
            )

    def test_benchmark_regional_renders_with_fallback_data(self) -> None:
        with (
            patch("streamlit.set_page_config"),
            patch("streamlit.markdown"),
            patch("streamlit.sidebar"),
            patch("streamlit.image"),
            patch("streamlit.selectbox") as mock_sel,
            patch("streamlit.slider", return_value=(2010, 2023)),
            patch("streamlit.multiselect", return_value=["BOL", "PER", "CHL"]),
            patch("streamlit.checkbox", return_value=True),
            patch("streamlit.spinner"),
            patch("streamlit.columns") as mock_cols,
            patch("streamlit.tabs") as mock_tabs,
            patch("streamlit.plotly_chart"),
            patch("streamlit.caption"),
            patch("streamlit.dataframe"),
            patch("streamlit.download_button"),
            patch.object(benchmark_page, "get_benchmark_indicadores", return_value=pd.DataFrame()),
            patch.object(benchmark_page, "log_ui_event"),
            patch.object(benchmark_page, "get_session_id", return_value="sess-fallback"),
        ):
            mock_sel.side_effect = ["NE.EXP.GNFS.KD.ZG", 2023, "PER"]
            mock_cols.return_value = [MagicMock(), MagicMock(), MagicMock(), MagicMock()]
            mock_tabs.return_value = [MagicMock(), MagicMock(), MagicMock(), MagicMock(), MagicMock()]

            main()


