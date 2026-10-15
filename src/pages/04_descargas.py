"""InsightBolivia — Proxy para Módulo 04: Centro de Descargas."""

from __future__ import annotations

import runpy
from pathlib import Path

_TARGET = Path(__file__).resolve().parent.parent.parent / "streamlit_app" / "pages" / "04_descargas.py"
if _TARGET.is_file():
    runpy.run_path(str(_TARGET), run_name="__main__")
