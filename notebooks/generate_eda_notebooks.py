"""Genera los 3 notebooks de EDA para comercio exterior.

Ejecutar con: uv run python notebooks/generate_eda_notebooks.py
"""

from __future__ import annotations

from pathlib import Path

import nbformat

NOTEBOOKS_DIR = Path(__file__).resolve().parent

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _md(source: str) -> nbformat.NotebookNode:
    """Crea una celda Markdown."""
    return nbformat.v4.new_markdown_cell(source.strip())


def _code(source: str, *, tags: list[str] | None = None) -> nbformat.NotebookNode:
    """Crea una celda de código."""
    cell = nbformat.v4.new_code_cell(source.strip())
    if tags:
        cell.metadata["tags"] = tags
    return cell


def _save(nb: nbformat.NotebookNode, name: str) -> None:
    path = NOTEBOOKS_DIR / name
    with path.open("w", encoding="utf-8") as f:
        nbformat.write(nb, f)
    print(f"  [OK] {name}")


# ===========================================================================
# Notebook 1: EDA Exportaciones (parametrizado)
# ===========================================================================

def generate_eda_exportaciones() -> None:
    nb = nbformat.v4.new_notebook()
    nb.metadata["kernelspec"] = {
        "display_name": "Python 3",
        "language": "python",
        "name": "python3",
    }

    nb.cells = [
        _md("""# EDA — Exportaciones de Comercio Exterior (INE Bolivia)

Análisis exploratorio de **un archivo individual** de exportaciones del INE.

**Uso:** Este notebook recibe un parámetro `FILE_PATH` con la ruta al archivo `.xlsx`.
Se puede ejecutar directamente o mediante el notebook orquestador con `papermill`.
"""),

        # --- Celda de parámetros (papermill) ---
        _code("""# Parámetro de entrada — ruta al archivo de exportaciones
# Esta celda es inyectada por papermill cuando se ejecuta desde el orquestador.
FILE_PATH = r"data/raw/comercio exterior/exportaciones/EXPORTACIONES 2021.xlsx"
""", tags=["parameters"]),

        _md("## 1. Configuración e Importaciones"),
        _code("""import sys
from pathlib import Path

import pandas as pd

# Asegurar que src/ es importable
PROJECT_ROOT = Path.cwd()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.extract import read_ine_excel, get_excel_metadata
from src.transform import (
    normalize_column_names,
    format_nandina,
    parse_flujo,
    cast_numeric_columns,
    clean_export_dataframe,
    compute_null_report,
    compare_headers_across_files,
    EXPORT_CANONICAL_COLUMNS,
    EXPORT_NUMERIC_COLUMNS,
)
from src.validate import run_export_validations

pd.set_option("display.max_columns", 50)
pd.set_option("display.max_colwidth", 80)

filepath = Path(FILE_PATH)
print(f"Archivo: {filepath.name}")
print(f"Ruta completa: {filepath.resolve()}")
"""),

        _md("## 2. Metadatos del Archivo"),
        _code("""meta = get_excel_metadata(filepath)

print(f"Archivo:       {meta['filename']}")
print(f"Tamaño:        {meta['file_size_mb']} MB")
print(f"Hojas:         {meta['sheet_names']}")
print(f"Hoja activa:   {meta['active_sheet']}")
print(f"Columnas ({meta['n_columns']}):")
for i, col in enumerate(meta['headers'], 1):
    print(f"  {i:2d}. {col}")
"""),

        _md("## 3. Carga y Limpieza de Datos"),
        _code("""# Leer archivo completo (dtype=str para preservar ceros en NANDINA)
df_raw = read_ine_excel(filepath)
print(f"Shape crudo: {df_raw.shape}")
print(f"Columnas: {list(df_raw.columns)}")
df_raw.head(3)
"""),

        _code("""# Aplicar pipeline de limpieza completo
df = clean_export_dataframe(df_raw)
print(f"Shape limpio: {df.shape}")
print(f"Columnas normalizadas: {list(df.columns)}")
df.dtypes
"""),

        _md("## 4. Análisis del Código NANDINA"),
        _code("""nandina = df["NANDINA"]
print(f"Tipo de dato predominante: {nandina.dtype}")
print(f"Valores únicos: {nandina.nunique()}")
print(f"Longitud (value_counts):")
print(nandina.str.len().value_counts().sort_index())
print(f"\\nRegistros con cero a la izquierda: {(nandina.str[0] == '0').sum()}")
print(f"Porcentaje: {(nandina.str[0] == '0').mean() * 100:.1f}%")
print(f"\\nMuestras con cero a la izquierda:")
print(nandina[nandina.str[0] == '0'].head(10).tolist())
"""),

        _md("## 5. Análisis del Campo FLUJO"),
        _code("""if "FLUJO" in df.columns:
    print("Valores únicos de FLUJO:")
    print(df["FLUJO"].value_counts())
    print()
    flujo_parsed = parse_flujo(df["FLUJO"])
    print("FLUJO parseado:")
    print(flujo_parsed.drop_duplicates())
"""),

        _md("## 6. Estadísticas de Valores y Pesos"),
        _code("""numeric_cols = ["VALOR", "KILBRU", "KILNET", "FINO"]
existing = [c for c in numeric_cols if c in df.columns]
print("Estadísticas descriptivas de columnas numéricas:")
df[existing].describe().round(2)
"""),

        _code("""# Verificar coherencia: KILBRU >= KILNET
if "KILBRU" in df.columns and "KILNET" in df.columns:
    mask = df["KILBRU"].notna() & df["KILNET"].notna()
    violations = df.loc[mask, "KILBRU"] < df.loc[mask, "KILNET"]
    print(f"Registros donde KILBRU < KILNET: {violations.sum()} de {mask.sum()}")
    if violations.sum() > 0:
        print("Muestras de violaciones:")
        print(df.loc[violations[violations].index, ["NANDINA", "DESNAN", "KILBRU", "KILNET"]].head())
"""),

        _md("## 7. Reporte de Nulos"),
        _code("""null_report = compute_null_report(df)
print("Reporte de nulos (ordenado por % descendente):")
# Mostrar solo columnas con nulos > 0
with_nulls = null_report[null_report["nulos"] > 0]
if with_nulls.empty:
    print("¡Sin nulos!")
else:
    print(with_nulls.to_string(index=False))
"""),

        _md("## 8. Validaciones de Calidad"),
        _code("""results = run_export_validations(df)
print("Resultados de validación:")
print("-" * 60)
for r in results:
    status = "✅ PASS" if r.passed else "❌ FAIL"
    print(f"{status} | {r.rule_name}: {r.message}")
    if r.details:
        for k, v in r.details.items():
            print(f"         {k}: {v}")
    print()
"""),

        _md("## 9. Distribución por País y Departamento"),
        _code("""if "DESPAIS" in df.columns:
    print("Top 15 países destino (por número de registros):")
    print(df["DESPAIS"].value_counts().head(15))

if "DESDEP" in df.columns:
    print("\\nRegistros por departamento de origen:")
    print(df["DESDEP"].value_counts())
"""),

        _md("## 10. Resumen del Archivo"),
        _code("""print(f"=" * 60)
print(f"RESUMEN: {filepath.name}")
print(f"=" * 60)
print(f"  Filas:              {len(df):,}")
print(f"  Columnas:           {len(df.columns)}")
if "GESTION" in df.columns:
    print(f"  Gestión(es):        {sorted(df['GESTION'].dropna().unique())}")
if "MES" in df.columns:
    print(f"  Meses:              {sorted(df['MES'].dropna().unique())}")
if "NANDINA" in df.columns:
    print(f"  Productos únicos:   {df['NANDINA'].nunique():,}")
if "DESPAIS" in df.columns:
    print(f"  Países destino:     {df['DESPAIS'].nunique()}")
if "VALOR" in df.columns:
    print(f"  Valor FOB total:    USD {df['VALOR'].sum():,.2f}")
print(f"  Validaciones:       {sum(1 for r in results if r.passed)}/{len(results)} pasaron")
"""),
    ]

    _save(nb, "01_eda_exportaciones.ipynb")


# ===========================================================================
# Notebook 2: EDA Importaciones (parametrizado)
# ===========================================================================

def generate_eda_importaciones() -> None:
    nb = nbformat.v4.new_notebook()
    nb.metadata["kernelspec"] = {
        "display_name": "Python 3",
        "language": "python",
        "name": "python3",
    }

    nb.cells = [
        _md("""# EDA — Importaciones de Comercio Exterior (INE Bolivia)

Análisis exploratorio de **un archivo individual** de importaciones del INE.

**Uso:** Este notebook recibe un parámetro `FILE_PATH` con la ruta al archivo `.xlsx`.
Se puede ejecutar directamente o mediante el notebook orquestador con `papermill`.

**Nota:** Los archivos de importaciones son significativamente más grandes (~400k filas, ~60 MB).
Se puede limitar la carga con el parámetro `MAX_ROWS`.
"""),

        # --- Celda de parámetros ---
        _code("""# Parámetros de entrada — inyectados por papermill
FILE_PATH = r"data/raw/comercio exterior/importaciones/IMPORTACIONES_2021.xlsx"
MAX_ROWS = None  # None = leer todo; usar un número para limitar (ej: 50000)
""", tags=["parameters"]),

        _md("## 1. Configuración e Importaciones"),
        _code("""import sys
from pathlib import Path

import pandas as pd

# Asegurar que src/ es importable
PROJECT_ROOT = Path.cwd()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.extract import read_ine_excel, get_excel_metadata
from src.transform import (
    normalize_column_names,
    format_nandina,
    cast_numeric_columns,
    clean_import_dataframe,
    compute_null_report,
    IMPORT_CANONICAL_COLUMNS,
    IMPORT_NUMERIC_COLUMNS,
)
from src.validate import run_import_validations

pd.set_option("display.max_columns", 50)
pd.set_option("display.max_colwidth", 80)

filepath = Path(FILE_PATH)
print(f"Archivo: {filepath.name}")
print(f"MAX_ROWS: {MAX_ROWS if MAX_ROWS else 'Sin límite'}")
"""),

        _md("## 2. Metadatos del Archivo"),
        _code("""meta = get_excel_metadata(filepath)

print(f"Archivo:       {meta['filename']}")
print(f"Tamaño:        {meta['file_size_mb']} MB")
print(f"Hojas:         {meta['sheet_names']}")
print(f"Hoja activa:   {meta['active_sheet']}")
print(f"Columnas ({meta['n_columns']}):")
for i, col in enumerate(meta['headers'], 1):
    print(f"  {i:2d}. {col}")
"""),

        _md("## 3. Carga y Limpieza de Datos"),
        _code("""df_raw = read_ine_excel(filepath, max_rows=MAX_ROWS)
print(f"Shape crudo: {df_raw.shape}")
df_raw.head(3)
"""),

        _code("""df = clean_import_dataframe(df_raw)
print(f"Shape limpio: {df.shape}")
df.dtypes
"""),

        _md("## 4. Análisis del Código NANDINA"),
        _code("""nandina = df["NANDINA"]
print(f"Tipo de dato: {nandina.dtype}")
print(f"Valores únicos: {nandina.nunique()}")
print(f"Longitud (value_counts):")
print(nandina.str.len().value_counts().sort_index())
print(f"\\nRegistros con cero a la izquierda: {(nandina.str[0] == '0').sum()}")
print(f"Porcentaje: {(nandina.str[0] == '0').mean() * 100:.1f}%")
"""),

        _md("## 5. Análisis de Valores Monetarios y Tipo de Cambio"),
        _code("""value_cols = ["FOB", "FRO", "ADU", "PAG"]
existing = [c for c in value_cols if c in df.columns]
print("Estadísticas de columnas monetarias:")
df[existing].describe().round(2)
"""),

        _code("""# Verificar tipo de cambio BOB/USD (esperado: 6.96)
if "ADU" in df.columns and "FRO" in df.columns:
    mask = df["FRO"].notna() & df["ADU"].notna() & (df["FRO"] > 0)
    if mask.sum() > 0:
        ratio = df.loc[mask, "ADU"] / df.loc[mask, "FRO"]
        print(f"Tipo de cambio ADU/FRO (CIF BOB / CIF USD):")
        print(f"  Media:    {ratio.mean():.4f}")
        print(f"  Mediana:  {ratio.median():.4f}")
        print(f"  Min:      {ratio.min():.4f}")
        print(f"  Max:      {ratio.max():.4f}")
        print(f"  Esperado: 6.96")
        outliers = ratio[(ratio < 6.86) | (ratio > 7.06)]
        print(f"  Outliers (fuera de 6.86-7.06): {len(outliers)} de {mask.sum()}")
"""),

        _md("## 6. Análisis de Peso (KILOS)"),
        _code("""if "KILOS" in df.columns:
    kilos = df["KILOS"]
    print(f"Estadísticas de KILOS (peso bruto):")
    print(kilos.describe().round(2))
    print(f"\\nRegistros con KILOS = 0: {(kilos == 0).sum()}")
    print(f"Registros con KILOS < 0: {(kilos < 0).sum()}")
"""),

        _md("## 7. Reporte de Nulos"),
        _code("""null_report = compute_null_report(df)
with_nulls = null_report[null_report["nulos"] > 0]
if with_nulls.empty:
    print("¡Sin nulos!")
else:
    print("Columnas con nulos:")
    print(with_nulls.to_string(index=False))
"""),

        _md("## 8. Validaciones de Calidad"),
        _code("""results = run_import_validations(df)
print("Resultados de validación:")
print("-" * 60)
for r in results:
    status = "✅ PASS" if r.passed else "❌ FAIL"
    print(f"{status} | {r.rule_name}: {r.message}")
    if r.details:
        for k, v in r.details.items():
            print(f"         {k}: {v}")
    print()
"""),

        _md("## 9. Distribución por País, Aduana y Departamento"),
        _code("""if "DESPAI" in df.columns:
    print("Top 15 países origen (por número de registros):")
    print(df["DESPAI"].value_counts().head(15))

if "DESADU" in df.columns:
    print("\\nRegistros por aduana de ingreso:")
    print(df["DESADU"].value_counts())

if "DESDEPTO" in df.columns:
    print("\\nRegistros por departamento:")
    print(df["DESDEPTO"].value_counts())
"""),

        _md("## 10. Resumen del Archivo"),
        _code("""print(f"=" * 60)
print(f"RESUMEN: {filepath.name}")
print(f"=" * 60)
rows_label = f"{len(df):,}" + (" (limitado)" if MAX_ROWS else "")
print(f"  Filas:              {rows_label}")
print(f"  Columnas:           {len(df.columns)}")
if "GESTION" in df.columns:
    print(f"  Gestión(es):        {sorted(df['GESTION'].dropna().unique())}")
if "MES" in df.columns:
    print(f"  Meses:              {sorted(df['MES'].dropna().unique())}")
if "NANDINA" in df.columns:
    print(f"  Productos únicos:   {df['NANDINA'].nunique():,}")
if "DESPAI" in df.columns:
    print(f"  Países origen:      {df['DESPAI'].nunique()}")
if "FOB" in df.columns:
    print(f"  Valor FOB total:    USD {df['FOB'].sum():,.2f}")
if "FRO" in df.columns:
    print(f"  Valor CIF total:    USD {df['FRO'].sum():,.2f}")
print(f"  Validaciones:       {sum(1 for r in results if r.passed)}/{len(results)} pasaron")
"""),
    ]

    _save(nb, "02_eda_importaciones.ipynb")


# ===========================================================================
# Notebook 0: Orquestador
# ===========================================================================

def generate_orquestador() -> None:
    nb = nbformat.v4.new_notebook()
    nb.metadata["kernelspec"] = {
        "display_name": "Python 3",
        "language": "python",
        "name": "python3",
    }

    nb.cells = [
        _md("""# Orquestador EDA — Comercio Exterior (INE Bolivia)

Este notebook ejecuta automáticamente los notebooks de EDA individuales
(`01_eda_exportaciones.ipynb` y `02_eda_importaciones.ipynb`) sobre
**todos los archivos** de datos raw, usando [papermill](https://papermill.readthedocs.io/).

Cada ejecución genera un notebook de salida con los resultados en
`notebooks/output/`.

## Uso

```bash
# Desde la raíz del proyecto:
uv run jupyter notebook notebooks/00_orquestador_eda.ipynb
```
"""),

        _code("""# Parámetros del orquestador
# MAX_ROWS para importaciones (None = leer todo; usar número para limitar)
IMPORT_MAX_ROWS = 50000  # Limitar a 50k filas por defecto (archivos de ~400k filas)
""", tags=["parameters"]),

        _md("## 1. Configuración"),
        _code("""import sys
from pathlib import Path
from datetime import datetime

import papermill as pm

PROJECT_ROOT = Path.cwd()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.extract import list_raw_files

NOTEBOOKS_DIR = PROJECT_ROOT / "notebooks"
OUTPUT_DIR = NOTEBOOKS_DIR / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

EXPORT_NOTEBOOK = str(NOTEBOOKS_DIR / "01_eda_exportaciones.ipynb")
IMPORT_NOTEBOOK = str(NOTEBOOKS_DIR / "02_eda_importaciones.ipynb")

print(f"Directorio de salida: {OUTPUT_DIR}")
print(f"Timestamp: {datetime.now().isoformat()}")
"""),

        _md("## 2. Descubrir Archivos de Datos"),
        _code("""DATA_DIR = PROJECT_ROOT / "data" / "raw" / "comercio exterior"

export_files = list_raw_files(DATA_DIR / "exportaciones")
import_files = list_raw_files(DATA_DIR / "importaciones")

print(f"Archivos de exportaciones ({len(export_files)}):")
for f in export_files:
    print(f"  - {f.name} ({f.stat().st_size / 1024 / 1024:.1f} MB)")

print(f"\\nArchivos de importaciones ({len(import_files)}):")
for f in import_files:
    print(f"  - {f.name} ({f.stat().st_size / 1024 / 1024:.1f} MB)")
"""),

        _md("## 3. Ejecutar EDA de Exportaciones"),
        _code("""export_results = []

for filepath in export_files:
    output_name = f"eda_export_{filepath.stem.lower().replace(' ', '_')}.ipynb"
    output_path = str(OUTPUT_DIR / output_name)

    print(f"\\n{'=' * 60}")
    print(f"Ejecutando EDA: {filepath.name}")
    print(f"Salida: {output_name}")
    print(f"{'=' * 60}")

    try:
        pm.execute_notebook(
            EXPORT_NOTEBOOK,
            output_path,
            parameters={"FILE_PATH": str(filepath)},
            kernel_name="python3",
        )
        export_results.append({"file": filepath.name, "status": "OK", "output": output_name})
        print(f"  ✅ Completado")
    except Exception as e:
        export_results.append({"file": filepath.name, "status": "ERROR", "error": str(e)})
        print(f"  ❌ Error: {e}")

print(f"\\nExportaciones procesadas: {len(export_results)}")
"""),

        _md("## 4. Ejecutar EDA de Importaciones"),
        _code("""import_results = []

for filepath in import_files:
    output_name = f"eda_import_{filepath.stem.lower().replace(' ', '_')}.ipynb"
    output_path = str(OUTPUT_DIR / output_name)

    print(f"\\n{'=' * 60}")
    print(f"Ejecutando EDA: {filepath.name}")
    print(f"Salida: {output_name}")
    print(f"MAX_ROWS: {IMPORT_MAX_ROWS}")
    print(f"{'=' * 60}")

    try:
        pm.execute_notebook(
            IMPORT_NOTEBOOK,
            output_path,
            parameters={
                "FILE_PATH": str(filepath),
                "MAX_ROWS": IMPORT_MAX_ROWS,
            },
            kernel_name="python3",
        )
        import_results.append({"file": filepath.name, "status": "OK", "output": output_name})
        print(f"  ✅ Completado")
    except Exception as e:
        import_results.append({"file": filepath.name, "status": "ERROR", "error": str(e)})
        print(f"  ❌ Error: {e}")

print(f"\\nImportaciones procesadas: {len(import_results)}")
"""),

        _md("## 5. Resumen de Ejecución"),
        _code("""import pandas as pd

print("=" * 60)
print("RESUMEN DE EJECUCIÓN")
print("=" * 60)

all_results = (
    [{"tipo": "Exportación", **r} for r in export_results]
    + [{"tipo": "Importación", **r} for r in import_results]
)
df_results = pd.DataFrame(all_results)
print(df_results[["tipo", "file", "status"]].to_string(index=False))

ok_count = sum(1 for r in all_results if r["status"] == "OK")
err_count = sum(1 for r in all_results if r["status"] == "ERROR")
print(f"\\nTotal: {ok_count} exitosos, {err_count} con errores de {len(all_results)} archivos")
print(f"\\nNotebooks de salida en: {OUTPUT_DIR}")
"""),
    ]

    _save(nb, "00_orquestador_eda.ipynb")


# ===========================================================================
# Main
# ===========================================================================

def main() -> None:
    print("Generando notebooks de EDA...")
    generate_eda_exportaciones()
    generate_eda_importaciones()
    generate_orquestador()
    print("[DONE] Todos los notebooks generados exitosamente.")


if __name__ == "__main__":
    main()
