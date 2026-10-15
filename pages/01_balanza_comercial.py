"""InsightBolivia — Proxy raíz para Módulo 01: Balanza Comercial Mensual."""

from __future__ import annotations

import runpy
from pathlib import Path

_TARGET = Path(__file__).resolve().parent.parent / "streamlit_app" / "pages" / "01_balanza_comercial.py"
if _TARGET.is_file():
    runpy.run_path(str(_TARGET), run_name="__main__")
