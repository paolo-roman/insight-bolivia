"""InsightBolivia — Entrypoint raíz para despliegue en Streamlit Community Cloud.

Delega la ejecución al dashboard principal ubicado en `streamlit_app/app.py`.
"""

from __future__ import annotations

import runpy
import sys
from pathlib import Path

_ROOT_DIR = Path(__file__).resolve().parent
if str(_ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(_ROOT_DIR))

_TARGET_APP = _ROOT_DIR / "streamlit_app" / "app.py"

if _TARGET_APP.is_file():
    runpy.run_path(str(_TARGET_APP), run_name="__main__")
