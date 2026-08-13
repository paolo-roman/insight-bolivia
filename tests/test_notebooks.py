"""Pruebas unitarias y de integración para los notebooks de EDA y el orquestador.

Valida la generación, estructura de parámetros e integración con Papermill.
"""

from __future__ import annotations

from pathlib import Path

import nbformat
import papermill as pm
import pytest

NOTEBOOKS_DIR = Path(__file__).resolve().parent.parent / "notebooks"
PROJECT_ROOT = NOTEBOOKS_DIR.parent


class TestNotebookStructure:
    """Valida la existencia y formato de los notebooks de EDA."""

    @pytest.mark.parametrize(
        "notebook_name",
        [
            "00_orquestador_eda.ipynb",
            "01_eda_exportaciones.ipynb",
            "02_eda_importaciones.ipynb",
        ],
    )
    def test_notebook_file_exists_and_is_valid_json(self, notebook_name: str) -> None:
        nb_path = NOTEBOOKS_DIR / notebook_name
        assert nb_path.exists(), f"El notebook {notebook_name} no existe."
        nb = nbformat.read(str(nb_path), as_version=4)
        assert isinstance(nb, nbformat.NotebookNode)
        assert nb.nbformat == 4
        assert len(nb.cells) > 0
        assert nb.metadata.get("kernelspec", {}).get("name") == "python3"

    def test_exportaciones_parameters_tag(self) -> None:
        nb_path = NOTEBOOKS_DIR / "01_eda_exportaciones.ipynb"
        params = pm.inspect_notebook(str(nb_path))
        assert "FILE_PATH" in params

    def test_importaciones_parameters_tag(self) -> None:
        nb_path = NOTEBOOKS_DIR / "02_eda_importaciones.ipynb"
        params = pm.inspect_notebook(str(nb_path))
        assert "FILE_PATH" in params
        assert "MAX_ROWS" in params

    def test_orquestador_parameters_tag(self) -> None:
        nb_path = NOTEBOOKS_DIR / "00_orquestador_eda.ipynb"
        params = pm.inspect_notebook(str(nb_path))
        assert "IMPORT_MAX_ROWS" in params


class TestNotebookExecution:
    """Pruebas de ejecución de notebooks con Papermill."""

    def test_execute_exportaciones_notebook(self, tmp_path: Path) -> None:
        export_file = PROJECT_ROOT / "data" / "raw" / "comercio exterior" / "exportaciones" / "EXPORTACIONES 2021.xlsx"
        if not export_file.exists():
            pytest.skip("Archivo de exportación no encontrado en data/raw/")

        input_nb = NOTEBOOKS_DIR / "01_eda_exportaciones.ipynb"
        output_nb = tmp_path / "test_out_export.ipynb"

        res = pm.execute_notebook(
            str(input_nb),
            str(output_nb),
            parameters={"FILE_PATH": str(export_file)},
            kernel_name="python3",
            cwd=str(PROJECT_ROOT),
        )
        assert isinstance(res, nbformat.NotebookNode)
        assert output_nb.exists()
        assert len(res.cells) > 0

    def test_execute_importaciones_notebook_with_max_rows(self, tmp_path: Path) -> None:
        import_file = (
            PROJECT_ROOT / "data" / "raw" / "comercio exterior" / "importaciones" / "IMPORTACIONES_2021.xlsx"
        )
        if not import_file.exists():
            pytest.skip("Archivo de importación no encontrado en data/raw/")

        input_nb = NOTEBOOKS_DIR / "02_eda_importaciones.ipynb"
        output_nb = tmp_path / "test_out_import.ipynb"

        res = pm.execute_notebook(
            str(input_nb),
            str(output_nb),
            parameters={
                "FILE_PATH": str(import_file),
                "MAX_ROWS": 500,
            },
            kernel_name="python3",
            cwd=str(PROJECT_ROOT),
        )
        assert isinstance(res, nbformat.NotebookNode)
        assert output_nb.exists()
        assert len(res.cells) > 0
