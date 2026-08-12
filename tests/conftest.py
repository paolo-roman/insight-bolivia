"""InsightBolivia — Fixtures compartidos para la suite de pruebas.

Proporciona rutas a archivos de datos sintéticos en ``tests/fixtures/``
y utilidades comunes de ayuda para la ejecución de la suite ``pytest``.

Los fixtures simulan casos borde reales del INE Bolivia:
* Archivos Excel válidos de exportaciones.
* Archivos CSV válidos de importaciones.
* Archivos vacíos (sin filas de datos).
* Archivos con encoding ISO-8859-1 (Latin-1).
"""

from __future__ import annotations

from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Directorio raíz de fixtures
# ---------------------------------------------------------------------------
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture()
def fixtures_dir() -> Path:
    """Retorna la ruta absoluta al directorio ``tests/fixtures/``."""
    return FIXTURES_DIR


@pytest.fixture()
def sample_exportaciones_path() -> Path:
    """Ruta al fixture Excel de exportaciones con datos válidos."""
    return FIXTURES_DIR / "sample_exportaciones.xlsx"


@pytest.fixture()
def sample_importaciones_path() -> Path:
    """Ruta al fixture CSV de importaciones con datos válidos (UTF-8)."""
    return FIXTURES_DIR / "sample_importaciones.csv"


@pytest.fixture()
def sample_empty_path() -> Path:
    """Ruta al fixture Excel vacío (solo encabezados, sin filas de datos)."""
    return FIXTURES_DIR / "sample_empty.xlsx"


@pytest.fixture()
def sample_bad_encoding_path() -> Path:
    """Ruta al fixture CSV con encoding ISO-8859-1 (Latin-1)."""
    return FIXTURES_DIR / "sample_bad_encoding.csv"
