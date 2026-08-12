"""Genera archivos fixture sintéticos para la suite de pruebas de InsightBolivia.

Crea datos anonimizados que simulan los casos borde del INE Bolivia:
- sample_exportaciones.xlsx  — Excel con registros válidos de exportaciones.
- sample_importaciones.csv   — CSV UTF-8 con registros válidos de importaciones.
- sample_empty.xlsx          — Excel con solo encabezados, sin filas de datos.
- sample_bad_encoding.csv    — CSV con encoding ISO-8859-1 (Latin-1).

Ejecutar con: uv run python tests/generate_fixtures.py
"""

from __future__ import annotations

from pathlib import Path

import openpyxl

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"

# ---------------------------------------------------------------------------
# Columnas del esquema de comercio exterior (basadas en config.yaml)
# ---------------------------------------------------------------------------
COLUMNS = [
    "fecha",
    "codigo_nandina",
    "descripcion_nandina",
    "pais_iso",
    "pais_nombre",
    "tipo_operacion",
    "valor_fob_usd",
    "peso_bruto_kg",
    "peso_neto_kg",
    "id_departamento",
    "id_via_transporte",
    "id_aduana",
]


def _generate_sample_exportaciones() -> None:
    """Genera ``sample_exportaciones.xlsx`` con 5 registros válidos."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Exportaciones"
    ws.append(COLUMNS)

    rows = [
        [
            "2025-01-15", "0901110000", "Cafe sin tostar sin descafeinar",
            "US", "Estados Unidos", "EXPORTACION",
            125000.50, 45000.0, 42000.0, 1, 1, 1,
        ],
        [
            "2025-01-15", "2611110000", "Minerales de estano concentrados",
            "CN", "China", "EXPORTACION",
            890000.00, 150000.0, 148000.0, 5, 2, 3,
        ],
        [
            "2025-02-20", "0801220000", "Nueces de Brasil sin cascara",
            "DE", "Alemania", "EXPORTACION",
            67500.75, 12000.0, 11500.0, 8, 3, 2,
        ],
        [
            "2025-02-20", "7108120000", "Oro en las demas formas en bruto",
            "AE", "Emiratos Arabes Unidos", "EXPORTACION",
            2500000.00, 50.0, 48.0, 3, 3, 5,
        ],
        [
            "2025-03-10", "1507100000", "Aceite de soja en bruto",
            "CO", "Colombia", "EXPORTACION",
            340000.25, 200000.0, 195000.0, 7, 1, 4,
        ],
    ]
    for row in rows:
        ws.append(row)

    output_path = FIXTURES_DIR / "sample_exportaciones.xlsx"
    wb.save(output_path)
    print(f"  [OK] {output_path.name} ({len(rows)} registros)")


def _generate_sample_importaciones() -> None:
    """Genera ``sample_importaciones.csv`` en UTF-8 con 5 registros válidos."""
    rows = [
        [
            "2025-01-10", "8703230000", "Vehiculos para transporte",
            "JP", "Japon", "IMPORTACION",
            "45000.00", "1500.0", "1400.0", "3", "3", "1",
        ],
        [
            "2025-01-10", "3004900000", "Medicamentos terapeuticos",
            "IN", "India", "IMPORTACION",
            "120000.50", "5000.0", "4800.0", "3", "3", "1",
        ],
        [
            "2025-02-15", "8471300000", "Maquinas portatiles",
            "CN", "China", "IMPORTACION",
            "85000.00", "2000.0", "1800.0", "3", "3", "2",
        ],
        [
            "2025-02-15", "1001190000", "Trigo duro para siembra",
            "AR", "Argentina", "IMPORTACION",
            "250000.00", "500000.0", "498000.0", "7", "1", "4",
        ],
        [
            "2025-03-05", "2710192100", "Diesel oil (gasoil)",
            "US", "Estados Unidos", "IMPORTACION",
            "1800000.00", "3000000.0", "2950000.0", "7", "2", "3",
        ],
    ]

    header = ",".join(COLUMNS)
    lines = [header] + [",".join(row) for row in rows]
    content = "\n".join(lines) + "\n"

    output_path = FIXTURES_DIR / "sample_importaciones.csv"
    output_path.write_text(content, encoding="utf-8")
    print(f"  [OK] {output_path.name} ({len(rows)} registros, UTF-8)")


def _generate_sample_empty() -> None:
    """Genera ``sample_empty.xlsx`` con encabezados pero sin filas de datos."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Vacio"
    ws.append(COLUMNS)

    output_path = FIXTURES_DIR / "sample_empty.xlsx"
    wb.save(output_path)
    print(f"  [OK] {output_path.name} (0 registros, solo encabezados)")


def _generate_sample_bad_encoding() -> None:
    """Genera ``sample_bad_encoding.csv`` en ISO-8859-1."""
    rows = [
        [
            "2025-01-20", "0901110000", "Caf\xe9 sin tostar",
            "US", "Estados Unidos", "EXPORTACION",
            "75000.00", "30000.0", "28000.0", "1", "1", "1",
        ],
        [
            "2025-01-20", "2301200000", "Harina de crust\xe1ceos",
            "PE", "Per\xfa", "IMPORTACION",
            "42000.50", "8000.0", "7500.0", "3", "2", "2",
        ],
        [
            "2025-02-28", "0801220000", "Nueces del Brasil",
            "FR", "Francia", "EXPORTACION",
            "95000.00", "15000.0", "14200.0", "8", "3", "5",
        ],
    ]

    header = ",".join(COLUMNS)
    lines = [header] + [",".join(row) for row in rows]
    content = "\n".join(lines) + "\n"

    output_path = FIXTURES_DIR / "sample_bad_encoding.csv"
    output_path.write_bytes(content.encode("iso-8859-1"))
    print(f"  [OK] {output_path.name} ({len(rows)} registros, ISO-8859-1)")


def main() -> None:
    """Genera todos los fixtures sintéticos."""
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)

    # Remover .gitkeep si existe (ya no es necesario con archivos reales)
    gitkeep = FIXTURES_DIR / ".gitkeep"
    if gitkeep.exists():
        gitkeep.unlink()

    print("Generando fixtures sintéticos de prueba...")
    _generate_sample_exportaciones()
    _generate_sample_importaciones()
    _generate_sample_empty()
    _generate_sample_bad_encoding()
    print("[DONE] Todos los fixtures generados exitosamente.")


if __name__ == "__main__":
    main()
