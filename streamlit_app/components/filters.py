"""InsightBolivia — Componente reutilizable de filtros para el dashboard de Streamlit.

Permite seleccionar rangos temporales, departamentos de Bolivia, tipos de flujo
comercial y sectores económicos, encapsulando el estado en un dataclass `FilterState`
y registrando eventos en la colección `ui_analytics` de Firestore.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

import streamlit as st

from streamlit_app.utils.firestore_client import get_session_id, log_ui_event

# Lista oficial de los 9 departamentos de Bolivia
DEPARTAMENTOS_BOLIVIA: list[str] = [
    "Beni",
    "Chuquisaca",
    "Cochabamba",
    "La Paz",
    "Oruro",
    "Pando",
    "Potosí",
    "Santa Cruz",
    "Tarija",
]

# Sectores económicos representativos del comercio exterior boliviano
SECTORES_ECONOMICOS: list[str] = [
    "Hidrocarburos y Derivados",
    "Minerales y Metales",
    "Agricultura y Agroindustria",
    "Manufacturas y Bienes Industriales",
    "Bebidas y Tabacos",
    "Textiles y Confecciones",
    "Otros Productos",
]

FLOW_OPTIONS: dict[str, str] = {
    "Exportaciones (FOB)": "EXPORTACION",
    "Importaciones (CIF)": "IMPORTACION",
    "Todos los Flujos": "TODOS",
}


@dataclass(frozen=True)
class FilterState:
    """Estado inmutable de los filtros seleccionados por el usuario."""

    start_date: date
    end_date: date
    departamentos: list[str] = field(default_factory=list)
    flow: str = "EXPORTACION"
    sectores: list[str] = field(default_factory=list)
    search_term: str = ""

    @property
    def is_all_departments(self) -> bool:
        """Indica si se han seleccionado todos los departamentos o ninguno (nivel nacional)."""
        return len(self.departamentos) == 0 or len(self.departamentos) == len(DEPARTAMENTOS_BOLIVIA)

    def to_dict(self) -> dict[str, Any]:
        """Convierte el estado de filtros a un diccionario serializable."""
        return {
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "departamentos": self.departamentos,
            "flow": self.flow,
            "sectores": self.sectores,
            "search_term": self.search_term,
        }


def render_filters(
    page_name: str = "general",
    show_dates: bool = True,
    show_departments: bool = True,
    show_flow: bool = True,
    show_sectors: bool = False,
    show_search: bool = False,
    default_start_date: date | None = None,
    default_end_date: date | None = None,
    in_sidebar: bool = True,
    key_prefix: str = "filter",
) -> FilterState:
    """Renderiza el panel de filtros y retorna el estado seleccionado `FilterState`.

    Parameters
    ----------
    page_name:
        Nombre de la página activa para el registro de telemetría.
    show_dates:
        Si es True, muestra el selector de rango de fechas.
    show_departments:
        Si es True, muestra el selector de departamentos.
    show_flow:
        Si es True, muestra el selector de tipo de flujo comercial.
    show_sectors:
        Si es True, muestra el selector multiselección de sectores económicos.
    show_search:
        Si es True, muestra un campo de búsqueda textual.
    default_start_date:
        Fecha inicial por defecto (si es None, usa 2020-01-01).
    default_end_date:
        Fecha final por defecto (si es None, usa la fecha actual).
    in_sidebar:
        Si es True, renderiza los controles en `st.sidebar`; si no, en el contenedor activo.
    key_prefix:
        Prefijo único para evitar colisiones de claves en los widgets de Streamlit.

    Returns
    -------
    FilterState
        Instancia con las opciones seleccionadas.
    """
    target = st.sidebar if in_sidebar else st.container()

    today = date.today()
    init_start = default_start_date or date(2020, 1, 1)
    init_end = default_end_date or today

    selected_start = init_start
    selected_end = init_end
    selected_departments: list[str] = []
    selected_flow = "EXPORTACION"
    selected_sectors: list[str] = []
    search_term = ""

    with target:
        st.markdown("### 🔍 Filtros de Análisis")

        # 1. Rango de Fechas
        if show_dates:
            st.markdown("**Periodo Temporal**")
            date_range = st.date_input(
                "Rango de Fechas",
                value=(init_start, init_end),
                min_value=date(2000, 1, 1),
                max_value=today,
                key=f"{key_prefix}_date_range",
                help="Seleccione el rango de fechas para acotar las consultas.",
            )
            if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
                selected_start, selected_end = date_range[0], date_range[1]
            elif isinstance(date_range, (list, tuple)) and len(date_range) == 1:
                selected_start = selected_end = date_range[0]
            elif isinstance(date_range, date):
                selected_start = selected_end = date_range

        # 2. Tipo de Flujo Comercial
        if show_flow:
            st.markdown("**Flujo Comercial**")
            flow_label = st.radio(
                "Tipo de Flujo",
                options=list(FLOW_OPTIONS.keys()),
                index=0,
                key=f"{key_prefix}_flow_radio",
                horizontal=False,
                label_visibility="collapsed",
            )
            selected_flow = FLOW_OPTIONS.get(flow_label, "EXPORTACION")

        # 3. Departamentos de Bolivia
        if show_departments:
            st.markdown("**Departamentos**")
            select_all = st.checkbox(
                "Seleccionar todos los departamentos",
                value=True,
                key=f"{key_prefix}_all_depts",
            )
            if select_all:
                selected_departments = list(DEPARTAMENTOS_BOLIVIA)
            else:
                selected_departments = st.multiselect(
                    "Filtrar departamentos",
                    options=DEPARTAMENTOS_BOLIVIA,
                    default=["Santa Cruz", "La Paz", "Cochabamba"],
                    key=f"{key_prefix}_depts_select",
                    help="Seleccione uno o varios departamentos para acotar el análisis.",
                )

        # 4. Sectores Económicos (Opcional)
        if show_sectors:
            st.markdown("**Sectores Económicos**")
            selected_sectors = st.multiselect(
                "Sectores Económicos",
                options=SECTORES_ECONOMICOS,
                default=[],
                key=f"{key_prefix}_sectors_select",
                help="Filtrar por sectores económicos específicos.",
            )

        # 5. Búsqueda Textual (Opcional)
        if show_search:
            search_term = st.text_input(
                "Búsqueda por código NANDINA o palabra clave",
                value="",
                key=f"{key_prefix}_search_text",
                placeholder="Ej: Gas natural, Soya, Oro...",
            )

        st.markdown("---")

    state = FilterState(
        start_date=selected_start,
        end_date=selected_end,
        departamentos=selected_departments,
        flow=selected_flow,
        sectores=selected_sectors,
        search_term=search_term.strip(),
    )

    # Registro no bloqueante de telemetría de aplicación de filtros
    session_id = get_session_id()
    log_ui_event(
        session_id=session_id,
        page=page_name,
        event_type="filter_apply",
        event_data=state.to_dict(),
    )

    return state
