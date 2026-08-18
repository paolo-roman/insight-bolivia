"""InsightBolivia — Pruebas unitarias para el Dashboard 04: Descargas de Datos (`04_descargas.py`).

Verifica la serialización a CSV/Excel, cálculo de resúmenes de integridad, control estricto
del límite de seguridad de 50,000 registros y renderizado del módulo con mocks de Streamlit.
"""

from __future__ import annotations

import importlib
import io
from datetime import date
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from streamlit_app.components.descargas_helpers import (
    MAX_DOWNLOAD_RECORDS,
    build_export_filename,
    compute_export_summary,
    convert_df_to_csv,
    convert_df_to_excel,
    format_currency_millions,
    format_weight_tonnes,
)

# Carga dinámica del módulo de página Streamlit (prefijo numérico)
descargas_page = importlib.import_module("streamlit_app.pages.04_descargas")
main = descargas_page.main


@pytest.fixture
def sample_microdatos_df() -> pd.DataFrame:
    """Fixture con microdatos representativos para exportación."""
    return pd.DataFrame({
        "fecha": [date(2024, 1, 1), date(2024, 1, 1), date(2024, 2, 1)],
        "anio": [2024, 2024, 2024],
        "mes": [1, 1, 2],
        "tipo_operacion": ["EXPORTACION", "EXPORTACION", "IMPORTACION"],
        "codigo_nandina": ["2711110000", "1201900000", "2710120000"],
        "descripcion_producto": ["Gas natural licuado", "Habas de soya", "Gasolinas sin plomo"],
        "sector_economico": ["Hidrocarburos y Derivados", "Agricultura y Agroindustria", "Hidrocarburos y Derivados"],
        "pais_iso": ["BRA", "ARG", "USA"],
        "pais_nombre": ["Brasil", "Argentina", "Estados Unidos"],
        "bloque_comercial": ["MERCOSUR", "MERCOSUR", "NAFTA / USMCA"],
        "departamento": ["Santa Cruz", "Santa Cruz", "La Paz"],
        "valor_fob_usd": [150_000_000.0, 80_000_000.0, 0.0],
        "valor_cif_usd": [0.0, 0.0, 45_000_000.0],
        "peso_neto_kg": [200_000_000.0, 100_000_000.0, 30_000_000.0],
        "peso_bruto_kg": [210_000_000.0, 105_000_000.0, 32_000_000.0],
    })


class TestDescargasHelpers:
    """Pruebas unitarias para las funciones de serialización y utilidades de descargas."""

    def test_convert_df_to_csv_success(self, sample_microdatos_df: pd.DataFrame) -> None:
        csv_bytes = convert_df_to_csv(sample_microdatos_df)
        assert isinstance(csv_bytes, bytes)
        assert len(csv_bytes) > 0
        # Verificar que contiene UTF-8 BOM
        assert csv_bytes.startswith(b"\xef\xbb\xbf")
        text = csv_bytes.decode("utf-8-sig")
        assert "2711110000" in text
        assert "Gas natural licuado" in text
        assert "Brasil" in text

    def test_convert_df_to_csv_empty(self) -> None:
        assert convert_df_to_csv(pd.DataFrame()) == b""

    def test_convert_df_to_excel_success(self, sample_microdatos_df: pd.DataFrame) -> None:
        excel_bytes = convert_df_to_excel(sample_microdatos_df, sheet_name="Comercio")
        assert isinstance(excel_bytes, bytes)
        assert len(excel_bytes) > 0

        # Leer de vuelta el archivo Excel desde bytes
        read_df = pd.read_excel(io.BytesIO(excel_bytes), sheet_name="Comercio")
        assert len(read_df) == 3
        assert "codigo_nandina" in read_df.columns
        assert read_df.iloc[0]["codigo_nandina"] == 2711110000 or str(read_df.iloc[0]["codigo_nandina"]) == "2711110000"

    def test_convert_df_to_excel_empty(self) -> None:
        assert convert_df_to_excel(pd.DataFrame()) == b""

    def test_build_export_filename(self) -> None:
        fname_csv = build_export_filename(
            flow="EXPORTACION",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            extension="csv",
        )
        assert fname_csv == "insight_bolivia_comercio_exportacion_2024-01-01_2024-12-31.csv"

        fname_xlsx = build_export_filename(
            flow="TODOS",
            start_date="2023-01-01",
            end_date="2023-06-30",
            extension=".xlsx",
        )
        assert fname_xlsx == "insight_bolivia_comercio_todos_2023-01-01_2023-06-30.xlsx"

        fname_default = build_export_filename(flow="", start_date=None, end_date=None)
        assert fname_default == "insight_bolivia_comercio_general_inicio_fin.csv"

    def test_format_currency_millions(self) -> None:
        assert format_currency_millions(2_500_000_000.0) == "$2.50 B"
        assert format_currency_millions(15_000_000.0) == "$15.00 M"
        assert format_currency_millions(4500.50) == "$4,500.50"

    def test_format_weight_tonnes(self) -> None:
        assert format_weight_tonnes(2_500_000_000.0) == "2.50 M Ton"
        assert format_weight_tonnes(5_000_000.0) == "5.00 k Ton"
        assert format_weight_tonnes(50_000.0) == "50.0 Ton"


class TestComputeExportSummary:
    """Pruebas para el cálculo de resumen e indicadores de seguridad."""

    def test_compute_summary_valid_df(self, sample_microdatos_df: pd.DataFrame) -> None:
        summary = compute_export_summary(sample_microdatos_df)
        assert summary["total_registros"] == 3
        assert summary["total_fob_usd"] == 230_000_000.0
        assert summary["total_cif_usd"] == 45_000_000.0
        assert summary["total_peso_neto_kg"] == 330_000_000.0
        assert summary["total_peso_neto_ton"] == 330_000.0
        assert summary["num_paises_unicos"] == 3
        assert summary["num_productos_unicos"] == 3
        assert summary["num_departamentos_unicos"] == 2
        assert summary["excede_limite"] is False

    def test_compute_summary_empty_df(self) -> None:
        summary = compute_export_summary(pd.DataFrame())
        assert summary["total_registros"] == 0
        assert summary["total_fob_usd"] == 0.0
        assert summary["total_cif_usd"] == 0.0
        assert summary["excede_limite"] is False

    def test_compute_summary_exceeds_limit(self) -> None:
        large_df = pd.DataFrame({"valor_fob_usd": [10.0] * (MAX_DOWNLOAD_RECORDS + 10)})
        summary = compute_export_summary(large_df)
        assert summary["total_registros"] == MAX_DOWNLOAD_RECORDS + 10
        assert summary["excede_limite"] is True


class TestDescargasPageRendering:
    """Pruebas de integración del flujo de renderizado del módulo de descargas con mocks de Streamlit."""

    def test_main_render_success_within_limit(
        self,
        sample_microdatos_df: pd.DataFrame,
    ) -> None:
        mock_filters = MagicMock()
        mock_filters.start_date = date(2024, 1, 1)
        mock_filters.end_date = date(2024, 12, 31)
        mock_filters.flow = "EXPORTACION"
        mock_filters.is_all_departments = True
        mock_filters.departamentos = []
        mock_filters.sectores = []
        mock_filters.search_term = ""
        mock_filters.to_dict.return_value = {"start_date": "2024-01-01"}

        with (
            patch.object(descargas_page, "get_session_id", return_value="sess-test-123") as mock_get_session,
            patch.object(descargas_page, "log_ui_event") as mock_log_event,
            patch.object(
                descargas_page,
                "get_available_date_range",
                return_value=(date(2024, 1, 1), date(2024, 12, 31)),
            ),
            patch.object(descargas_page, "render_filters", return_value=mock_filters) as mock_render_filters,
            patch.object(
                descargas_page,
                "get_export_microdatos",
                return_value=sample_microdatos_df,
            ) as mock_get_microdatos,
            patch("streamlit.set_page_config") as mock_set_page,
            patch("streamlit.download_button") as mock_download_btn,
            patch("streamlit.dataframe") as mock_dataframe,
        ):
            main()

            mock_get_session.assert_called_once()
            mock_log_event.assert_called_once_with(
                session_id="sess-test-123",
                page="04_descargas",
                event_type="page_view",
            )
            mock_render_filters.assert_called_once()
            mock_set_page.assert_called_once()

            mock_get_microdatos.assert_called_once_with(
                start_date=date(2024, 1, 1),
                end_date=date(2024, 12, 31),
                flow="EXPORTACION",
                departamentos=None,
                sectores=None,
                search_term=None,
                limit=MAX_DOWNLOAD_RECORDS + 1,
            )
            # Dos botones de descarga: CSV y Excel
            assert mock_download_btn.call_count == 2
            mock_dataframe.assert_called_once()

    def test_main_render_exceeds_limit_shows_alert(self) -> None:
        mock_filters = MagicMock()
        mock_filters.start_date = date(2024, 1, 1)
        mock_filters.end_date = date(2024, 12, 31)
        mock_filters.flow = "EXPORTACION"
        mock_filters.is_all_departments = False
        mock_filters.departamentos = ["Santa Cruz"]
        mock_filters.sectores = ["Hidrocarburos y Derivados"]
        mock_filters.search_term = "Gas"
        mock_filters.to_dict.return_value = {"flow": "EXPORTACION"}

        # Simular DataFrame que supera el límite
        oversized_df = pd.DataFrame({
            "fecha": [date(2024, 1, 1)] * (MAX_DOWNLOAD_RECORDS + 5),
            "valor_fob_usd": [100.0] * (MAX_DOWNLOAD_RECORDS + 5),
        })

        with (
            patch.object(descargas_page, "get_session_id", return_value="sess-test-123"),
            patch.object(descargas_page, "log_ui_event") as mock_log_event,
            patch.object(
                descargas_page,
                "get_available_date_range",
                return_value=(date(2024, 1, 1), date(2024, 12, 31)),
            ),
            patch.object(descargas_page, "render_filters", return_value=mock_filters),
            patch.object(descargas_page, "get_export_microdatos", return_value=oversized_df),
            patch("streamlit.download_button") as mock_download_btn,
            patch("streamlit.dataframe") as mock_df,
        ):
            main()

            # No debe mostrar los botones de descarga completa
            mock_download_btn.assert_not_called()
            # Muestra la vista previa acotada
            mock_df.assert_called_once()
            # Verifica que se registró evento de telemetría de límite excedido
            mock_log_event.assert_any_call(
                session_id="sess-test-123",
                page="04_descargas",
                event_type="limit_exceeded",
                event_data={
                    "total_registros_detectados": MAX_DOWNLOAD_RECORDS + 5,
                    "limite_maximo": MAX_DOWNLOAD_RECORDS,
                    "filtros": {"flow": "EXPORTACION"},
                },
            )

    def test_main_render_empty_result(self) -> None:
        mock_filters = MagicMock()
        mock_filters.start_date = date(2024, 1, 1)
        mock_filters.end_date = date(2024, 12, 31)
        mock_filters.flow = "TODOS"
        mock_filters.is_all_departments = True
        mock_filters.sectores = []
        mock_filters.search_term = ""

        with (
            patch.object(descargas_page, "get_session_id", return_value="sess-test-123"),
            patch.object(descargas_page, "log_ui_event"),
            patch.object(
                descargas_page,
                "get_available_date_range",
                return_value=(date(2024, 1, 1), date(2024, 12, 31)),
            ),
            patch.object(descargas_page, "render_filters", return_value=mock_filters),
            patch.object(descargas_page, "get_export_microdatos", return_value=pd.DataFrame()),
            patch("streamlit.info") as mock_info,
            patch("streamlit.download_button") as mock_download_btn,
        ):
            main()
            mock_info.assert_called_once()
            mock_download_btn.assert_not_called()

    def test_main_render_missing_dates(self) -> None:
        mock_filters = MagicMock()
        mock_filters.start_date = None
        mock_filters.end_date = None

        with (
            patch.object(descargas_page, "get_session_id", return_value="sess-test-123"),
            patch.object(descargas_page, "log_ui_event"),
            patch.object(
                descargas_page,
                "get_available_date_range",
                return_value=(date(2024, 1, 1), date(2024, 12, 31)),
            ),
            patch.object(descargas_page, "render_filters", return_value=mock_filters),
            patch("streamlit.warning") as mock_warning,
        ):
            main()
            mock_warning.assert_called_once()

