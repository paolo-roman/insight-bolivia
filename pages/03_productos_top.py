"""InsightBolivia — Proxy raíz para Módulo 03: Productos Principales."""

from __future__ import annotations

import runpy
from pathlib import Path

_TARGET = Path(__file__).resolve().parent.parent / "streamlit_app" / "pages" / "03_productos_top.py"
if _TARGET.is_file():
    runpy.run_path(str(_TARGET), run_name="__main__")
