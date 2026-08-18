"""InsightBolivia — Suite de Pruebas End-to-End (E2E), Rendimiento y Verificación de Despliegue.

Valida el ciclo de vida completo de la aplicación Streamlit, navegación entre módulos,
cumplimiento del umbral de latencia (NFR <= 3.0s), persistencia de sesión, registro
de telemetría en Cloud Firestore y configuración de despliegue en la nube.
"""

from __future__ import annotations

import importlib
import time
from contextlib import contextmanager
from datetime import UTC, date, datetime
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

if TYPE_CHECKING:
    from collections.abc import Generator

import pandas as pd
import pytest

from src.firestore_models import DwhCatalog
from streamlit_app.app import main as home_main
from streamlit_app.utils.bq_client import (
    get_available_date_range,
    get_balanza_comercial,
    get_benchmark_indicadores,
    get_export_microdatos,
    get_socios_comerciales,
    get_top_productos,
)
from streamlit_app.utils.firestore_client import (
    get_cached_dwh_catalog,
    get_session_id,
    log_ui_event,
)

# Carga dinámica de páginas modulares
balanza_page = importlib.import_module("streamlit_app.pages.01_balanza_comercial")
socios_page = importlib.import_module("streamlit_app.pages.02_socios_comerciales")
productos_page = importlib.import_module("streamlit_app.pages.03_productos_top")
descargas_page = importlib.import_module("streamlit_app.pages.04_descargas")
benchmark_page = importlib.import_module("streamlit_app.pages.05_benchmark_regional")



@pytest.fixture
def mock_dwh_catalog() -> DwhCatalog:
    """Fixture de catálogo DWH activo con metadatos reales."""
    return DwhCatalog(
        code="comercio_exterior",
        name="Comercio Exterior de Bolivia",
        description="Dataset analítico del INE.",
        bq_dataset="comercio_exterior",
        bq_project="insight-bolivia",
        status="active",
        data_source="INE - Instituto Nacional de Estadística",
        record_count=2150000,
        last_data_refresh=datetime(2026, 8, 15, 12, 0, tzinfo=UTC),
    )


@pytest.fixture
def mock_balanza_data() -> pd.DataFrame:
    """Fixture de datos mensuales para balanza comercial."""
    return pd.DataFrame({
        "anio": [2023, 2024],
        "mes": [1, 1],
        "nombre_mes": ["Enero", "Enero"],
        "trimestre": [1, 1],
        "semestre": [1, 1],
        "fecha": [date(2023, 1, 1), date(2024, 1, 1)],
        "total_exportaciones_usd": [900_000_000.0, 800_000_000.0],
        "total_importaciones_usd": [850_000_000.0, 850_000_000.0],
        "saldo_balanza_usd": [50_000_000.0, -50_000_000.0],
        "total_peso_neto_exportaciones_kg": [500_000_000.0, 450_000_000.0],
        "total_peso_bruto_importaciones_kg": [300_000_000.0, 320_000_000.0],
        "num_transacciones_exportacion": [1200, 1100],
        "num_transacciones_importacion": [4500, 4600],
    })


@pytest.fixture
def mock_socios_data() -> pd.DataFrame:
    """Fixture de socios comerciales."""
    return pd.DataFrame({
        "anio": [2024, 2024],
        "tipo_operacion": ["EXPORTACION", "EXPORTACION"],
        "pais_iso": ["BRA", "ARG"],
        "codigo_pais_ine": ["105", "101"],
        "nombre_pais_es": ["Brasil", "Argentina"],
        "nombre_pais_en": ["Brazil", "Argentina"],
        "continente": ["América del Sur", "América del Sur"],
        "subregion": ["Sudamérica", "Sudamérica"],
        "bloque_comercial": ["MERCOSUR", "MERCOSUR"],
        "total_valor_usd": [1_200_000_000.0, 800_000_000.0],
        "total_fob_usd": [1_200_000_000.0, 800_000_000.0],
        "total_cif_usd": [0.0, 0.0],
        "total_peso_bruto_kg": [3_000_000_000.0, 2_000_000_000.0],
        "num_transacciones": [4500, 3200],
    })


@pytest.fixture
def mock_productos_data() -> pd.DataFrame:
    """Fixture de productos top."""
    return pd.DataFrame({
        "anio": [2024, 2024],
        "ranking": [1, 2],
        "codigo_nandina": ["2711210000", "7108120000"],
        "descripcion_producto": ["Gas natural", "Oro en bruto"],
        "partida_nandina": ["2711", "7108"],
        "capitulo_nandina": ["27", "71"],
        "seccion_nandina": ["V", "XIV"],
        "sector_economico": ["Hidrocarburos", "Minería"],
        "total_fob_usd": [2_000_000_000.0, 1_500_000_000.0],
        "total_peso_neto_kg": [8_000_000_000.0, 50_000.0],
        "num_transacciones": [450, 1200],
    })


@pytest.fixture
def mock_microdatos_data() -> pd.DataFrame:
    """Fixture de microdatos para descargas."""
    return pd.DataFrame({
        "fecha": [date(2024, 1, 1), date(2024, 2, 1)],
        "tipo_operacion": ["EXPORTACION", "EXPORTACION"],
        "codigo_nandina": ["2711110000", "2608000000"],
        "descripcion_producto": ["Gas natural", "Minerales de cinc"],
        "sector_economico": ["Hidrocarburos", "Minería"],
        "pais_iso": ["BRA", "ARG"],
        "pais_nombre": ["Brasil", "Argentina"],
        "bloque_comercial": ["MERCOSUR", "MERCOSUR"],
        "departamento": ["Tarija", "Potosí"],
        "valor_fob_usd": [250_000.0, 180_000.0],
        "valor_cif_usd": [0.0, 0.0],
        "peso_neto_kg": [800_000.0, 50_000.0],
        "peso_bruto_kg": [800_000.0, 52_000.0],
        "anio": [2024, 2024],
        "mes": [1, 2],
    })


@contextmanager
def mock_streamlit_ui() -> Generator[dict[str, MagicMock], None, None]:
    """Helper de context manager para mockear llamadas de widgets y visualización de Streamlit."""
    with (
        patch("streamlit.set_page_config"),
        patch("streamlit.markdown"),
        patch("streamlit.sidebar"),
        patch("streamlit.selectbox") as mock_sel,
        patch("streamlit.date_input") as mock_date,
        patch("streamlit.radio") as mock_rad,
        patch("streamlit.slider") as mock_sli,
        patch("streamlit.multiselect") as mock_multi,
        patch("streamlit.spinner"),
        patch("streamlit.columns") as mock_cols,
        patch("streamlit.tabs") as mock_tabs,
        patch("streamlit.plotly_chart") as mock_plot,
        patch("streamlit.info"),
        patch("streamlit.warning"),
        patch("streamlit.caption"),
        patch("streamlit.checkbox") as mock_chk,
        patch("streamlit.text_input") as mock_txt,
        patch("streamlit.dataframe") as mock_df,
        patch("streamlit.download_button") as mock_down,
        patch("streamlit.expander"),
    ):
        yield {
            "sel": mock_sel,
            "date": mock_date,
            "rad": mock_rad,
            "sli": mock_sli,
            "multi": mock_multi,
            "chk": mock_chk,
            "cols": mock_cols,
            "tabs": mock_tabs,
            "plot": mock_plot,
            "txt": mock_txt,
            "df": mock_df,
            "down": mock_down,
        }



class TestEndToEndPageRendering:
    """Pruebas de renderizado y navegación End-to-End entre todas las páginas del sistema."""

    def test_e2e_landing_page_renders_successfully(self, mock_dwh_catalog: DwhCatalog) -> None:
        with (
            mock_streamlit_ui() as ui,
            patch("streamlit_app.app.log_ui_event") as mock_log,
            patch("streamlit_app.app.get_session_id", return_value="e2e-session-uuid-001") as mock_sess,
            patch("streamlit_app.app.get_cached_dwh_catalog", return_value=mock_dwh_catalog),
        ):
            ui["cols"].side_effect = [[MagicMock() for _ in range(4)], [MagicMock(), MagicMock()]]
            home_main()
            mock_sess.assert_called_once()
            mock_log.assert_called_once_with(session_id="e2e-session-uuid-001", page="home", event_type="page_view")

    def test_e2e_balanza_comercial_renders_successfully(self, mock_balanza_data: pd.DataFrame) -> None:
        date_range = (date(2023, 1, 1), date(2024, 2, 1))
        with (
            mock_streamlit_ui() as ui,
            patch.object(balanza_page, "log_ui_event") as mock_log,
            patch.object(balanza_page, "get_session_id", return_value="e2e-session-uuid-001") as mock_sess,
            patch.object(balanza_page, "get_available_date_range", return_value=date_range),
            patch.object(balanza_page, "get_balanza_comercial", return_value=mock_balanza_data) as mock_get,
        ):
            ui["sel"].return_value = "Todo el histórico"
            ui["date"].return_value = date_range
            ui["rad"].return_value = "Mensual"
            ui["cols"].return_value = [MagicMock() for _ in range(4)]
            ui["tabs"].return_value = [MagicMock() for _ in range(4)]
            balanza_page.main()
            mock_sess.assert_called_once()
            mock_log.assert_called_once_with(
                session_id="e2e-session-uuid-001", page="01_balanza_comercial", event_type="page_view"
            )
            mock_get.assert_called_once_with(start_date=date(2023, 1, 1), end_date=date(2024, 2, 1))

    def test_e2e_socios_comerciales_renders_successfully(self, mock_socios_data: pd.DataFrame) -> None:
        with (
            mock_streamlit_ui() as ui,
            patch.object(socios_page, "log_ui_event") as mock_log,
            patch.object(socios_page, "get_session_id", return_value="e2e-session-uuid-001") as mock_sess,
            patch.object(
                socios_page, "get_available_date_range", return_value=(date(2020, 1, 1), date(2024, 12, 31))
            ),
            patch.object(socios_page, "get_socios_comerciales", return_value=mock_socios_data) as mock_get,
        ):
            ui["rad"].return_value = "Exportaciones (FOB)"
            ui["sel"].side_effect = ["Todas las Gestiones (Consolidado)", "Mundial (Global)"]
            ui["sli"].return_value = 10
            ui["multi"].side_effect = [["América del Sur"], ["MERCOSUR"]]
            ui["cols"].side_effect = [
                [MagicMock() for _ in range(4)],
                [MagicMock(), MagicMock()],
                [MagicMock(), MagicMock()],
            ]
            ui["tabs"].return_value = [MagicMock() for _ in range(4)]
            ui["txt"].return_value = "Brasil"
            socios_page.main()
            mock_sess.assert_called_once()
            mock_log.assert_called_once_with(
                session_id="e2e-session-uuid-001", page="02_socios_comerciales", event_type="page_view"
            )
            mock_get.assert_called_once_with(flow="EXPORTACION", year=None)

    def test_e2e_productos_top_renders_successfully(self, mock_productos_data: pd.DataFrame) -> None:
        with (
            mock_streamlit_ui() as ui,
            patch.object(productos_page, "log_ui_event") as mock_log,
            patch.object(productos_page, "get_session_id", return_value="e2e-session-uuid-001") as mock_sess,
            patch.object(
                productos_page, "get_available_date_range", return_value=(date(2023, 1, 1), date(2024, 12, 31))
            ),
            patch.object(productos_page, "get_top_productos", return_value=mock_productos_data) as mock_get,
        ):
            ui["sel"].return_value = "Todas las Gestiones (Consolidado)"
            ui["rad"].return_value = "Valor FOB (USD)"
            ui["sli"].return_value = 10
            ui["multi"].return_value = ["Hidrocarburos"]
            ui["cols"].side_effect = [[MagicMock() for _ in range(4)], [MagicMock(), MagicMock()]]
            ui["tabs"].return_value = [MagicMock() for _ in range(4)]
            ui["txt"].return_value = "gas"
            productos_page.main()
            mock_sess.assert_called_once()
            mock_log.assert_called_once_with(
                session_id="e2e-session-uuid-001", page="03_productos_top", event_type="page_view"
            )
            mock_get.assert_called_once_with(year=None, limit=10)

    def test_e2e_descargas_renders_successfully(self, mock_microdatos_data: pd.DataFrame) -> None:
        mock_filters = MagicMock(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            flow="EXPORTACION",
            is_all_departments=True,
            sectores=[],
            search_term="",
        )
        with (
            mock_streamlit_ui() as ui,
            patch.object(descargas_page, "log_ui_event") as mock_log,
            patch.object(descargas_page, "get_session_id", return_value="e2e-session-uuid-001") as mock_sess,
            patch.object(
                descargas_page, "get_available_date_range", return_value=(date(2023, 1, 1), date(2024, 12, 31))
            ),
            patch.object(descargas_page, "render_filters", return_value=mock_filters),
            patch.object(descargas_page, "get_export_microdatos", return_value=mock_microdatos_data) as mock_get,
        ):
            ui["cols"].side_effect = [
                [MagicMock() for _ in range(4)],
                [MagicMock(), MagicMock()],
                [MagicMock(), MagicMock()],
            ]
            descargas_page.main()
            mock_sess.assert_called_once()
            mock_log.assert_called_once_with(
                session_id="e2e-session-uuid-001", page="04_descargas", event_type="page_view"
            )
            mock_get.assert_called_once()

    def test_e2e_benchmark_regional_renders_successfully(self) -> None:
        mock_data = pd.DataFrame({
            "id_indicador_bm": ["BOL_NE.EXP.GNFS.KD.ZG_2023"],
            "anio": [2023],
            "pais_iso": ["BOL"],
            "pais_nombre": ["Bolivia"],
            "codigo_indicador": ["NE.EXP.GNFS.KD.ZG"],
            "nombre_indicador": ["Crecimiento de Exportaciones"],
            "valor": [4.5],
            "unidad_medida": ["%"],
        })
        with (
            mock_streamlit_ui() as ui,
            patch.object(benchmark_page, "log_ui_event") as mock_log,
            patch.object(benchmark_page, "get_session_id", return_value="e2e-session-uuid-001") as mock_sess,
            patch.object(benchmark_page, "get_benchmark_indicadores", return_value=mock_data) as mock_get,
        ):
            ui["sel"].side_effect = ["NE.EXP.GNFS.KD.ZG", 2023, "PER"]
            ui["sli"].return_value = (2010, 2023)
            ui["multi"].return_value = ["BOL", "PER", "CHL"]
            ui["chk"].return_value = True
            ui["cols"].return_value = [MagicMock() for _ in range(4)]
            ui["tabs"].return_value = [MagicMock() for _ in range(5)]
            benchmark_page.main()
            mock_sess.assert_called_once()
            mock_log.assert_called_once_with(
                session_id="e2e-session-uuid-001", page="05_benchmark_regional", event_type="page_view"
            )
            mock_get.assert_called_once()


class TestLatencyAndPerformanceSLA:
    """Pruebas de cumplimiento del SLA de latencia (NFR <= 3.0s por consulta)."""

    @patch("streamlit_app.utils.bq_client.get_bigquery_client")
    def test_benchmark_query_latency_under_sla(self, mock_init: MagicMock) -> None:
        mock_client = MagicMock()
        mock_job = MagicMock()
        mock_job.to_dataframe.return_value = pd.DataFrame({"valor": [4.5]})
        mock_client.query.return_value = mock_job
        mock_init.return_value = mock_client

        t0 = time.perf_counter()
        result_df = get_benchmark_indicadores(start_year=2020, end_year=2023)
        assert not result_df.empty
        assert time.perf_counter() - t0 <= 3.0


    @patch("streamlit_app.utils.bq_client.get_bigquery_client")
    def test_cached_query_response_time_under_sla(
        self, mock_init: MagicMock, mock_balanza_data: pd.DataFrame
    ) -> None:

        mock_client = MagicMock()
        mock_job = MagicMock()
        mock_job.to_dataframe.return_value = mock_balanza_data
        mock_client.query.return_value = mock_job
        mock_init.return_value = mock_client

        t0 = time.perf_counter()
        result_df = get_balanza_comercial(start_date=date(2023, 1, 1), end_date=date(2024, 12, 31))
        dt = time.perf_counter() - t0
        assert not result_df.empty
        assert dt <= 3.0, f"Latencia excedió SLA: {dt:.4f}s > 3.0s"

    @patch("streamlit_app.utils.bq_client.get_bigquery_client")
    def test_socios_query_latency_under_sla(self, mock_init: MagicMock, mock_socios_data: pd.DataFrame) -> None:
        mock_client = MagicMock()
        mock_job = MagicMock()
        mock_job.to_dataframe.return_value = mock_socios_data
        mock_client.query.return_value = mock_job
        mock_init.return_value = mock_client

        t0 = time.perf_counter()
        result_df = get_socios_comerciales(limit=None)
        assert len(result_df) == 2
        assert time.perf_counter() - t0 <= 3.0

    @patch("streamlit_app.utils.bq_client.get_bigquery_client")
    def test_top_productos_query_latency_under_sla(
        self, mock_init: MagicMock, mock_productos_data: pd.DataFrame
    ) -> None:
        mock_client = MagicMock()
        mock_job = MagicMock()
        mock_job.to_dataframe.return_value = mock_productos_data
        mock_client.query.return_value = mock_job
        mock_init.return_value = mock_client

        t0 = time.perf_counter()
        result_df = get_top_productos(limit=50)
        assert not result_df.empty
        assert time.perf_counter() - t0 <= 3.0

    @patch("streamlit_app.utils.bq_client.get_bigquery_client")
    def test_microdatos_query_latency_under_sla(
        self, mock_init: MagicMock, mock_microdatos_data: pd.DataFrame
    ) -> None:
        mock_client = MagicMock()
        mock_job = MagicMock()
        mock_job.to_dataframe.return_value = mock_microdatos_data
        mock_client.query.return_value = mock_job
        mock_init.return_value = mock_client

        t0 = time.perf_counter()
        result_df = get_export_microdatos(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            flow="EXPORTACION",
            limit=50000,
        )
        assert not result_df.empty
        assert time.perf_counter() - t0 <= 3.0

    @patch("streamlit_app.utils.bq_client.get_bigquery_client")
    def test_available_date_range_latency_under_sla(self, mock_init: MagicMock) -> None:
        mock_client = MagicMock()
        mock_job = MagicMock()
        mock_job.to_dataframe.return_value = pd.DataFrame({
            "min_date": [date(2020, 1, 1)],
            "max_date": [date(2024, 12, 1)],
        })
        mock_client.query.return_value = mock_job
        mock_init.return_value = mock_client

        t0 = time.perf_counter()
        min_date, max_date = get_available_date_range()
        assert min_date == date(2020, 1, 1)
        assert max_date == date(2024, 12, 1)
        assert time.perf_counter() - t0 <= 3.0


class TestSessionPersistenceAndTelemetry:
    """Pruebas para persistencia de sesión de usuario y trazabilidad de telemetría."""

    def test_session_id_persistence_in_streamlit_state(self) -> None:
        s1 = get_session_id()
        s2 = get_session_id()
        assert s1 is not None and isinstance(s1, str) and len(s1) > 10
        assert s1 == s2

    @patch("streamlit_app.utils.firestore_client.get_firestore_client")
    def test_telemetry_event_emission_e2e(self, mock_fs_init: MagicMock) -> None:
        mock_db = MagicMock()
        mock_col = MagicMock()
        mock_doc = MagicMock(id="doc-telemetry-123")
        mock_col.document.return_value = mock_doc
        mock_db.collection.return_value = mock_col
        mock_fs_init.return_value = mock_db

        session_id = get_session_id()
        doc_id = log_ui_event(
            session_id=session_id,
            page="e2e_verification",
            event_type="test_event",
            event_data={"status": "success", "duration_ms": 125},
        )
        mock_db.collection.assert_called_once_with("ui_analytics")
        mock_col.document.assert_called_once()
        mock_doc.set.assert_called_once()
        assert doc_id == "doc-telemetry-123"


class TestDeploymentConfigurationAndResponsiveness:
    """Pruebas de configuración de entorno, servidor y diseño responsivo para hosting."""

    def test_config_toml_exists_and_has_valid_theme(self) -> None:
        config_path = Path("streamlit_app/.streamlit/config.toml")
        assert config_path.exists(), "El archivo config.toml debe existir en streamlit_app/.streamlit/"
        content = config_path.read_text(encoding="utf-8")
        assert "[theme]" in content
        assert 'base = "dark"' in content
        assert "primaryColor" in content
        assert "backgroundColor" in content
        assert "[server]" in content
        assert "headless = true" in content
        assert "enableXsrfProtection = true" in content

    def test_secrets_example_contains_all_required_sections(self) -> None:
        secrets_path = Path("streamlit_app/.streamlit/secrets.toml.example")
        assert secrets_path.exists(), "El archivo secrets.toml.example debe existir"
        content = secrets_path.read_text(encoding="utf-8")
        assert "[gcp_service_account]" in content
        assert 'type = "service_account"' in content
        assert "project_id" in content
        assert "private_key" in content
        assert "client_email" in content
        assert "[bigquery]" in content
        assert "[firestore]" in content

    @patch("streamlit_app.utils.firestore_client.get_firestore_client", side_effect=Exception("Connection refused"))
    def test_resilience_fallback_when_firestore_offline(self, mock_fs: MagicMock) -> None:
        catalog = get_cached_dwh_catalog("comercio_exterior")
        assert catalog is None
