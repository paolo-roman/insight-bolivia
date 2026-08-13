"""Pruebas unitarias para el módulo ``src.extract``.

Valida la lectura de archivos Excel/CSV del INE Bolivia,
detección de encoding, extracción de metadatos y listado de archivos.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import openpyxl
import pandas as pd
import pytest

from src.extract import (
    _read_csv_with_encoding,
    get_excel_metadata,
    list_raw_files,
    read_ine_excel,
)

if TYPE_CHECKING:
    from pathlib import Path

# ---------------------------------------------------------------------------
# Helpers: crear archivos temporales de prueba
# ---------------------------------------------------------------------------

def _create_test_xlsx(path: Path, headers: list[str], rows: list[list]) -> Path:
    """Crea un archivo Excel de prueba."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "TestData"
    ws.append(headers)
    for row in rows:
        ws.append(row)
    wb.save(path)
    return path


def _create_test_csv(path: Path, content: str, *, encoding: str = "utf-8") -> Path:
    """Crea un archivo CSV de prueba."""
    if encoding == "utf-8":
        path.write_text(content, encoding=encoding)
    else:
        path.write_bytes(content.encode(encoding))
    return path


# ---------------------------------------------------------------------------
# Tests: read_ine_excel
# ---------------------------------------------------------------------------

class TestReadIneExcel:
    """Pruebas para ``read_ine_excel``."""

    def test_reads_xlsx_returns_dataframe(self, tmp_path: Path) -> None:
        xlsx = _create_test_xlsx(
            tmp_path / "test.xlsx",
            ["GESTION", "MES", "NANDINA", "VALOR"],
            [[2021, 1, "0901110000", 125000.50]],
        )
        df = read_ine_excel(xlsx)
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 1
        assert list(df.columns) == ["GESTION", "MES", "NANDINA", "VALOR"]

    def test_reads_all_as_string_dtype(self, tmp_path: Path) -> None:
        """Debe leer todo como string para preservar ceros a la izquierda."""
        xlsx = _create_test_xlsx(
            tmp_path / "test.xlsx",
            ["NANDINA", "VALOR"],
            [["0901110000", 125000]],
        )
        df = read_ine_excel(xlsx)
        # dtype=str, debe ser tipo string (object o StringDtype)
        assert pd.api.types.is_string_dtype(df["NANDINA"])
        assert df["NANDINA"].iloc[0] == "0901110000"

    def test_respects_max_rows(self, tmp_path: Path) -> None:
        xlsx = _create_test_xlsx(
            tmp_path / "test.xlsx",
            ["A", "B"],
            [[1, 2], [3, 4], [5, 6], [7, 8], [9, 10]],
        )
        df = read_ine_excel(xlsx, max_rows=2)
        assert len(df) == 2

    def test_raises_for_missing_file(self) -> None:
        with pytest.raises(FileNotFoundError, match="Archivo no encontrado"):
            read_ine_excel("nonexistent.xlsx")

    def test_raises_for_unsupported_extension(self, tmp_path: Path) -> None:
        bad_file = tmp_path / "test.json"
        bad_file.write_text("{}")
        with pytest.raises(ValueError, match="Extensión no soportada"):
            read_ine_excel(bad_file)

    def test_reads_csv_utf8(self, tmp_path: Path) -> None:
        csv_file = _create_test_csv(
            tmp_path / "test.csv",
            "NANDINA,VALOR\n0901110000,125000\n",
        )
        df = read_ine_excel(csv_file)
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 1


class TestReadCsvWithEncoding:
    """Pruebas para ``_read_csv_with_encoding``."""

    def test_reads_utf8_csv(self, tmp_path: Path) -> None:
        csv_file = _create_test_csv(
            tmp_path / "utf8.csv",
            "col1,col2\nvalor,café\n",
        )
        df = _read_csv_with_encoding(csv_file)
        assert "café" in df["col2"].values

    def test_reads_latin1_csv(self, tmp_path: Path) -> None:
        csv_file = _create_test_csv(
            tmp_path / "latin1.csv",
            "col1,col2\nvalor,caf\xe9\n",
            encoding="iso-8859-1",
        )
        df = _read_csv_with_encoding(csv_file)
        assert len(df) == 1

    def test_respects_max_rows(self, tmp_path: Path) -> None:
        content = "A,B\n1,2\n3,4\n5,6\n"
        csv_file = _create_test_csv(tmp_path / "test.csv", content)
        df = _read_csv_with_encoding(csv_file, max_rows=1)
        assert len(df) == 1

    def test_raises_when_encoding_detection_fails(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        csv_file = tmp_path / "corrupt.csv"
        csv_file.write_bytes(b"\xff\xfe\x00\x00_invalid")

        import charset_normalizer

        class DummyMatches:
            def best(self):
                return None

        monkeypatch.setattr(charset_normalizer, "from_bytes", lambda _: DummyMatches())
        with pytest.raises(ValueError, match="No se pudo detectar el encoding"):
            _read_csv_with_encoding(csv_file)


# ---------------------------------------------------------------------------
# Tests: get_excel_metadata
# ---------------------------------------------------------------------------

class TestGetExcelMetadata:
    """Pruebas para ``get_excel_metadata``."""

    def test_returns_metadata_dict(self, tmp_path: Path) -> None:
        xlsx = _create_test_xlsx(
            tmp_path / "meta_test.xlsx",
            ["GESTION", "MES", "NANDINA"],
            [[2021, 1, "0901110000"]],
        )
        meta = get_excel_metadata(xlsx)
        assert meta["filename"] == "meta_test.xlsx"
        assert meta["n_columns"] == 3
        assert meta["headers"] == ["GESTION", "MES", "NANDINA"]
        assert "file_size_mb" in meta
        assert isinstance(meta["sheet_names"], list)

    def test_raises_for_missing_file(self) -> None:
        with pytest.raises(FileNotFoundError):
            get_excel_metadata("nonexistent.xlsx")


# ---------------------------------------------------------------------------
# Tests: list_raw_files
# ---------------------------------------------------------------------------

class TestListRawFiles:
    """Pruebas para ``list_raw_files``."""

    def test_lists_xlsx_files_excluding_diccionario(self, tmp_path: Path) -> None:
        (tmp_path / "EXPORTACIONES 2021.xlsx").write_bytes(b"dummy")
        (tmp_path / "EXPORTACIONES 2022.xlsx").write_bytes(b"dummy")
        (tmp_path / "DICCIONARIO BD-EXPORTACION.xlsx").write_bytes(b"dummy")

        files = list_raw_files(tmp_path)
        names = [f.name for f in files]
        assert "EXPORTACIONES 2021.xlsx" in names
        assert "EXPORTACIONES 2022.xlsx" in names
        assert "DICCIONARIO BD-EXPORTACION.xlsx" not in names

    def test_returns_sorted_list(self, tmp_path: Path) -> None:
        (tmp_path / "C.xlsx").write_bytes(b"dummy")
        (tmp_path / "A.xlsx").write_bytes(b"dummy")
        (tmp_path / "B.xlsx").write_bytes(b"dummy")

        files = list_raw_files(tmp_path, exclude_pattern="ZZZZZ")
        names = [f.name for f in files]
        assert names == ["A.xlsx", "B.xlsx", "C.xlsx"]

    def test_raises_for_missing_directory(self) -> None:
        with pytest.raises(FileNotFoundError, match="Directorio no encontrado"):
            list_raw_files("nonexistent_dir")

    def test_filters_by_extension(self, tmp_path: Path) -> None:
        (tmp_path / "data.xlsx").write_bytes(b"dummy")
        (tmp_path / "data.csv").write_bytes(b"dummy")

        xlsx_files = list_raw_files(tmp_path, extension=".xlsx", exclude_pattern="ZZZZZ")
        csv_files = list_raw_files(tmp_path, extension=".csv", exclude_pattern="ZZZZZ")

        assert len(xlsx_files) == 1
        assert len(csv_files) == 1
