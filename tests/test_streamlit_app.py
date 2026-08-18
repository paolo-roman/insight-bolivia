"""InsightBolivia — Pruebas unitarias para el punto de entrada principal (`app.py`).

Verifica la inicialización del landing page, consulta y renderizado de métricas
desde el catálogo Firestore y emisión de eventos de telemetría de navegación.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from src.firestore_models import DwhCatalog
from streamlit_app.app import main


class TestStreamlitAppMain:
    """Pruebas para el entrypoint y landing page."""

    @patch("streamlit_app.app.log_ui_event")
    @patch("streamlit_app.app.get_session_id", return_value="test-app-session")
    @patch("streamlit_app.app.get_cached_dwh_catalog")
    @patch("streamlit.sidebar")
    @patch("streamlit.columns")
    @patch("streamlit.markdown")
    @patch("streamlit.expander")
    def test_main_renders_with_catalog_data(
        self,
        mock_expander: MagicMock,
        mock_markdown: MagicMock,
        mock_columns: MagicMock,
        mock_sidebar: MagicMock,
        mock_get_catalog: MagicMock,
        mock_get_session: MagicMock,
        mock_log_event: MagicMock,
    ) -> None:
        mock_columns.side_effect = [
            [MagicMock(), MagicMock(), MagicMock(), MagicMock()],  # 4 KPI columns
            [MagicMock(), MagicMock()],  # 2 module columns
        ]
        mock_get_catalog.return_value = DwhCatalog(
            code="comercio_exterior",
            name="Comercio Exterior de Bolivia",
            description="Datos del INE.",
            bq_dataset="comercio_exterior",
            bq_project="insight-bolivia",
            status="active",
            data_source="INE - Instituto Nacional de Estadística",
            record_count=2150000,
            last_data_refresh=datetime(2026, 8, 15, 12, 0, tzinfo=UTC),
        )

        main()

        mock_get_session.assert_called_once()
        mock_log_event.assert_called_once_with(
            session_id="test-app-session",
            page="home",
            event_type="page_view",
        )
        mock_get_catalog.assert_called_once_with("comercio_exterior")

    @patch("streamlit_app.app.log_ui_event")
    @patch("streamlit_app.app.get_session_id", return_value="test-app-session")
    @patch("streamlit_app.app.get_cached_dwh_catalog")
    @patch("streamlit.sidebar")
    @patch("streamlit.columns")
    @patch("streamlit.markdown")
    @patch("streamlit.expander")
    def test_main_renders_with_catalog_fallback_demo(
        self,
        mock_expander: MagicMock,
        mock_markdown: MagicMock,
        mock_columns: MagicMock,
        mock_sidebar: MagicMock,
        mock_get_catalog: MagicMock,
        mock_get_session: MagicMock,
        mock_log_event: MagicMock,
    ) -> None:
        mock_columns.side_effect = [
            [MagicMock(), MagicMock(), MagicMock(), MagicMock()],
            [MagicMock(), MagicMock()],
        ]
        mock_get_catalog.return_value = None  # Simulates Firestore offline

        main()

        mock_get_session.assert_called_once()
        mock_log_event.assert_called_once_with(
            session_id="test-app-session",
            page="home",
            event_type="page_view",
        )
        mock_get_catalog.assert_called_once_with("comercio_exterior")
