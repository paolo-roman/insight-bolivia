"""InsightBolivia — Pruebas unitarias para proxies de navegación de Streamlit.

Valida que tanto los proxies en src/pages/ como en pages/ y app.py raíz deleguen
adecuadamente la ejecución a streamlit_app/app.py y streamlit_app/pages/*.
"""

from __future__ import annotations

import runpy
from pathlib import Path
from unittest.mock import patch

from src.main import _delegate_to_streamlit_app, _is_running_in_streamlit


class TestStreamlitDelegationInMain:
    """Pruebas para funciones de detección y delegación a Streamlit en src/main.py."""

    def test_is_running_in_streamlit_false_in_bare_mode(self) -> None:
        assert _is_running_in_streamlit() is False

    @patch("streamlit.runtime.exists", return_value=True)
    def test_is_running_in_streamlit_true_when_runtime_active(self, mock_exists: object) -> None:
        assert _is_running_in_streamlit() is True

    @patch("runpy.run_path")
    def test_delegate_to_streamlit_app_calls_run_path(self, mock_run_path: object) -> None:
        _delegate_to_streamlit_app()
        assert mock_run_path.called  # type: ignore[attr-defined]


class TestStreamlitPagesProxies:
    """Pruebas de ejecución para los archivos proxy en src/pages/ y pages/."""

    SRC_PAGES = [
        "src/pages/01_balanza_comercial.py",
        "src/pages/02_socios_comerciales.py",
        "src/pages/03_productos_top.py",
        "src/pages/04_descargas.py",
        "src/pages/05_benchmark_regional.py",
    ]

    ROOT_PAGES = [
        "pages/01_balanza_comercial.py",
        "pages/02_socios_comerciales.py",
        "pages/03_productos_top.py",
        "pages/04_descargas.py",
        "pages/05_benchmark_regional.py",
    ]

    @patch("runpy.run_path")
    def test_src_pages_proxies_delegate_successfully(self, mock_run_path: object) -> None:
        for page_rel in self.SRC_PAGES:
            mock_run_path.reset_mock()  # type: ignore[attr-defined]
            page_path = Path(page_rel)
            assert page_path.exists(), f"El proxy {page_rel} debe existir"
            runpy.run_path(str(page_path), run_name="__main__")
            assert mock_run_path.called, f"{page_rel} no invocó runpy.run_path"  # type: ignore[attr-defined]

    @patch("runpy.run_path")
    def test_root_pages_proxies_delegate_successfully(self, mock_run_path: object) -> None:
        for page_rel in self.ROOT_PAGES:
            mock_run_path.reset_mock()  # type: ignore[attr-defined]
            page_path = Path(page_rel)
            assert page_path.exists(), f"El proxy {page_rel} debe existir"
            runpy.run_path(str(page_path), run_name="__main__")
            assert mock_run_path.called, f"{page_rel} no invocó runpy.run_path"  # type: ignore[attr-defined]

    @patch("runpy.run_path")
    def test_root_app_delegates_successfully(self, mock_run_path: object) -> None:
        app_path = Path("app.py")
        assert app_path.exists(), "El entrypoint app.py en la raíz debe existir"
        runpy.run_path(str(app_path), run_name="__main__")
        assert mock_run_path.called  # type: ignore[attr-defined]
