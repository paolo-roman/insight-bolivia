"""InsightBolivia — Pruebas unitarias para el componente de filtros (`filters.py`).

Verifica la estructura de datos `FilterState`, opciones predeterminadas de departamentos y flujos,
renderizado interactivo y emisión de eventos a Firestore.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

from streamlit_app.components.filters import (
    DEPARTAMENTOS_BOLIVIA,
    FLOW_OPTIONS,
    SECTORES_ECONOMICOS,
    FilterState,
    render_filters,
)


class TestFilterState:
    """Pruebas para el dataclass FilterState."""

    def test_filter_state_creation_and_defaults(self) -> None:
        state = FilterState(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
        )
        assert state.start_date == date(2024, 1, 1)
        assert state.end_date == date(2024, 12, 31)
        assert state.departamentos == []
        assert state.flow == "EXPORTACION"
        assert state.sectores == []
        assert state.search_term == ""
        assert state.is_all_departments is True

    def test_is_all_departments_property(self) -> None:
        state_partial = FilterState(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            departamentos=["La Paz", "Santa Cruz"],
        )
        assert state_partial.is_all_departments is False

        state_all = FilterState(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            departamentos=list(DEPARTAMENTOS_BOLIVIA),
        )
        assert state_all.is_all_departments is True

    def test_to_dict_serialization(self) -> None:
        state = FilterState(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            departamentos=["Oruro"],
            flow="IMPORTACION",
            sectores=["Minerales y Metales"],
            search_term="Estaño",
        )
        d = state.to_dict()
        assert d["start_date"] == "2024-01-01"
        assert d["end_date"] == "2024-12-31"
        assert d["departamentos"] == ["Oruro"]
        assert d["flow"] == "IMPORTACION"
        assert d["sectores"] == ["Minerales y Metales"]
        assert d["search_term"] == "Estaño"


class TestRenderFilters:
    """Pruebas para la función render_filters."""

    @patch("streamlit_app.components.filters.log_ui_event")
    @patch("streamlit_app.components.filters.get_session_id", return_value="test-session")
    @patch("streamlit.sidebar")
    @patch("streamlit.date_input")
    @patch("streamlit.radio")
    @patch("streamlit.checkbox")
    @patch("streamlit.multiselect")
    @patch("streamlit.text_input")
    def test_render_filters_all_enabled(
        self,
        mock_text: MagicMock,
        mock_multiselect: MagicMock,
        mock_checkbox: MagicMock,
        mock_radio: MagicMock,
        mock_date: MagicMock,
        mock_sidebar: MagicMock,
        mock_session: MagicMock,
        mock_log_event: MagicMock,
    ) -> None:
        mock_date.return_value = (date(2023, 1, 1), date(2023, 12, 31))
        mock_radio.return_value = "Exportaciones (FOB)"
        mock_checkbox.return_value = False
        mock_multiselect.side_effect = [
            ["La Paz", "Cochabamba"],  # Departamentos
            ["Hidrocarburos y Derivados"],  # Sectores
        ]
        mock_text.return_value = " Gas Natural "

        state = render_filters(
            page_name="01_balanza",
            show_dates=True,
            show_departments=True,
            show_flow=True,
            show_sectors=True,
            show_search=True,
            in_sidebar=True,
        )

        assert state.start_date == date(2023, 1, 1)
        assert state.end_date == date(2023, 12, 31)
        assert state.departamentos == ["La Paz", "Cochabamba"]
        assert state.flow == "EXPORTACION"
        assert state.sectores == ["Hidrocarburos y Derivados"]
        assert state.search_term == "Gas Natural"

        mock_log_event.assert_called_once_with(
            session_id="test-session",
            page="01_balanza",
            event_type="filter_apply",
            event_data=state.to_dict(),
        )

    @patch("streamlit_app.components.filters.log_ui_event")
    @patch("streamlit_app.components.filters.get_session_id", return_value="test-session")
    @patch("streamlit.date_input")
    @patch("streamlit.radio")
    @patch("streamlit.checkbox")
    def test_render_filters_all_departments_checked(
        self,
        mock_checkbox: MagicMock,
        mock_radio: MagicMock,
        mock_date: MagicMock,
        mock_session: MagicMock,
        mock_log_event: MagicMock,
    ) -> None:
        mock_date.return_value = date(2025, 5, 1)  # Single date returned
        mock_radio.return_value = "Importaciones (CIF)"
        mock_checkbox.return_value = True  # Select all departments

        state = render_filters(
            page_name="02_socios",
            show_dates=True,
            show_departments=True,
            show_flow=True,
            in_sidebar=False,
        )

        assert state.start_date == date(2025, 5, 1)
        assert state.end_date == date(2025, 5, 1)
        assert len(state.departamentos) == len(DEPARTAMENTOS_BOLIVIA)
        assert state.flow == "IMPORTACION"
        assert state.is_all_departments is True


class TestFilterConstants:
    """Pruebas para listas maestras y constantes de filtros."""

    def test_departamentos_count(self) -> None:
        assert len(DEPARTAMENTOS_BOLIVIA) == 9
        assert "Santa Cruz" in DEPARTAMENTOS_BOLIVIA
        assert "La Paz" in DEPARTAMENTOS_BOLIVIA
        assert "Cochabamba" in DEPARTAMENTOS_BOLIVIA

    def test_sectores_economicos(self) -> None:
        assert len(SECTORES_ECONOMICOS) >= 5
        assert "Hidrocarburos y Derivados" in SECTORES_ECONOMICOS
        assert "Minerales y Metales" in SECTORES_ECONOMICOS

    def test_flow_options(self) -> None:
        assert "Exportaciones (FOB)" in FLOW_OPTIONS
        assert "Importaciones (CIF)" in FLOW_OPTIONS
        assert FLOW_OPTIONS["Exportaciones (FOB)"] == "EXPORTACION"
        assert FLOW_OPTIONS["Importaciones (CIF)"] == "IMPORTACION"
