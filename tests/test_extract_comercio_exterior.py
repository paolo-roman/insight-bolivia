"""Pruebas unitarias para el módulo ``src.extract_comercio_exterior``.

Valida el web scraping de recursos del portal del INE Bolivia,
creación de sesión HTTP resiliente, cálculo de hash SHA-256 en streaming,
descarga con manejo de Content-Disposition, tolerancia a fallos de red/SSL,
control de idempotencia y orquestación general.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest
import requests

from src.extract_comercio_exterior import (
    INE_EXPORTACIONES_URL,
    ExtractionMetadata,
    ExtractionSummary,
    ScrapedResource,
    _collect_existing_disk_hashes,
    _extract_filename_from_response,
    compute_sha256,
    create_resilient_session,
    download_resource,
    extract_comercio_exterior,
    scrape_ine_resources,
)

if TYPE_CHECKING:
    from pathlib import Path


# ---------------------------------------------------------------------------
# Tests: Dataclasses
# ---------------------------------------------------------------------------
class TestExtractDataclasses:
    """Pruebas para las estructuras de datos de extracción."""

    def test_scraped_resource_creation(self) -> None:
        res = ScrapedResource(
            title="EXPORTACIONES 2026",
            url="https://nube.ine.gob.bo/index.php/s/123/download",
            operation_type="exportaciones",
            is_dictionary=False,
            year=2026,
        )
        assert res.title == "EXPORTACIONES 2026"
        assert res.year == 2026
        assert not res.is_dictionary

    def test_extraction_metadata_defaults(self) -> None:
        res = ScrapedResource(
            title="TEST",
            url="https://example.com/test.xlsx",
            operation_type="exportaciones",
        )
        meta = ExtractionMetadata(resource=res)
        assert meta.status == "DOWNLOADED"
        assert meta.downloaded_at != ""
        parsed_dt = datetime.fromisoformat(meta.downloaded_at)
        assert parsed_dt is not None

    def test_extraction_summary_properties(self) -> None:
        res = ScrapedResource(title="R1", url="http://x", operation_type="exportaciones")
        meta1 = ExtractionMetadata(resource=res, status="DOWNLOADED")
        meta2 = ExtractionMetadata(resource=res, status="SKIPPED_EXISTING")
        meta3 = ExtractionMetadata(resource=res, status="FAILED", error_message="Timeout")

        summary = ExtractionSummary(
            total_scraped=3,
            downloaded=[meta1],
            skipped=[meta2],
            failed=[meta3],
        )
        assert summary.total_downloaded == 1
        assert summary.total_skipped == 1
        assert summary.total_failed == 1


# ---------------------------------------------------------------------------
# Tests: create_resilient_session & compute_sha256
# ---------------------------------------------------------------------------
class TestHttpAndCryptoUtilities:
    """Pruebas para utilidades HTTP y de hashing."""

    def test_create_resilient_session_default_headers(self) -> None:
        sess = create_resilient_session()
        assert "Mozilla" in str(sess.headers["User-Agent"])
        assert "https://" in sess.adapters
        assert "http://" in sess.adapters

    def test_create_resilient_session_custom_user_agent(self) -> None:
        custom_ua = "CustomAgent/1.0"
        sess = create_resilient_session(user_agent=custom_ua, max_retries=5, backoff_factor=0.5)
        assert str(sess.headers["User-Agent"]) == custom_ua

    def test_compute_sha256_success(self, tmp_path: Path) -> None:
        file = tmp_path / "test_hash.txt"
        file.write_bytes(b"InsightBolivia 2026")
        expected_hash = hashlib.sha256(b"InsightBolivia 2026").hexdigest()
        assert compute_sha256(file, chunk_size=4) == expected_hash

    def test_compute_sha256_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError, match="no existe"):
            compute_sha256(tmp_path / "nonexistent.txt")


# ---------------------------------------------------------------------------
# Tests: scrape_ine_resources
# ---------------------------------------------------------------------------
class TestScrapeIneResources:
    """Pruebas para el scraping de enlaces del portal del INE."""

    SAMPLE_HTML = """
    <html>
      <body>
        <a href="https://nube.ine.gob.bo/index.php/s/CKdL20Qa/download">DICCIONARIO BASE DE DATOS EXPORTACIONES</a>
        <a href="https://nube.ine.gob.bo/index.php/s/Jy9SGV9r/download">EXPORTACIONES ENE A JUN 2026p</a>
        <a href="https://nube.ine.gob.bo/index.php/s/Jy9SGV9r/download">EXPORTACIONES ENE A JUN 2026p DUP</a>
        <a href="https://nube.ine.gob.bo/index.php/s/GTrosVYk/download">EXPORTACIONES 2025p</a>
        <a href="/wp-content/uploads/2024/EXPORTACIONES_2024.xlsx">EXPORTACIONES 2024</a>
        <a href="https://www.facebook.com/ineboliviaoficial">Facebook</a>
        <a href="https://www.ine.gob.bo/index.php/instituto/preguntas-frecuentes/">Preguntas Frecuentes</a>
        <a href="">Empty Link</a>
        <a>No href</a>
      </body>
    </html>
    """

    def test_scrape_resources_filters_dictionaries_and_deduplicates(self) -> None:
        mock_response = MagicMock(spec=requests.Response)
        mock_response.status_code = 200
        mock_response.text = self.SAMPLE_HTML
        mock_response.raise_for_status.return_value = None

        mock_session = MagicMock(spec=requests.Session)
        mock_session.get.return_value = mock_response

        resources = scrape_ine_resources(
            INE_EXPORTACIONES_URL,
            operation_type="exportaciones",
            session=mock_session,
            exclude_dictionaries=True,
        )

        titles = [r.title for r in resources]
        assert "DICCIONARIO BASE DE DATOS EXPORTACIONES" not in titles
        assert "EXPORTACIONES ENE A JUN 2026p" in titles
        assert "EXPORTACIONES 2025p" in titles
        assert "EXPORTACIONES 2024" in titles
        assert len(resources) == 3

        r_2026 = next(r for r in resources if "2026" in r.title)
        assert r_2026.year == 2026

    def test_scrape_resources_includes_dictionaries_when_requested(self) -> None:
        mock_response = MagicMock(spec=requests.Response)
        mock_response.status_code = 200
        mock_response.text = self.SAMPLE_HTML
        mock_response.raise_for_status.return_value = None

        mock_session = MagicMock(spec=requests.Session)
        mock_session.get.return_value = mock_response

        resources = scrape_ine_resources(
            INE_EXPORTACIONES_URL,
            operation_type="exportaciones",
            session=mock_session,
            exclude_dictionaries=False,
        )

        assert len(resources) == 4
        dict_res = next(r for r in resources if "DICCIONARIO" in r.title)
        assert dict_res.is_dictionary is True

    def test_scrape_resources_handles_request_exception(self) -> None:
        mock_session = MagicMock(spec=requests.Session)
        mock_session.get.side_effect = requests.RequestException("Connection error")

        resources = scrape_ine_resources(
            INE_EXPORTACIONES_URL,
            session=mock_session,
        )
        assert resources == []


# ---------------------------------------------------------------------------
# Tests: _extract_filename_from_response
# ---------------------------------------------------------------------------
class TestExtractFilenameFromResponse:
    """Pruebas para extracción y saneamiento de nombres de archivo."""

    def test_parses_content_disposition_quoted(self) -> None:
        res = ScrapedResource(title="Title", url="https://example.com/file", operation_type="exportaciones")
        resp = MagicMock(spec=requests.Response)
        resp.headers = {"Content-Disposition": 'attachment; filename="EXPORTACIONES_2026.xlsx"'}

        filename = _extract_filename_from_response(resp, res)
        assert filename == "EXPORTACIONES_2026.xlsx"

    def test_parses_content_disposition_url_encoded(self) -> None:
        res = ScrapedResource(title="Title", url="https://example.com/file", operation_type="exportaciones")
        resp = MagicMock(spec=requests.Response)
        resp.headers = {"Content-Disposition": 'attachment; filename="EXPORTACIONES%202026p.xlsx"'}

        filename = _extract_filename_from_response(resp, res)
        assert filename == "EXPORTACIONES 2026p.xlsx"

    def test_falls_back_to_url_path_when_no_header(self) -> None:
        res = ScrapedResource(
            title="Title",
            url="https://example.com/data/archivo_2025.xlsx",
            operation_type="exportaciones",
        )
        resp = MagicMock(spec=requests.Response)
        resp.headers = {}

        filename = _extract_filename_from_response(resp, res)
        assert filename == "archivo_2025.xlsx"

    def test_falls_back_to_resource_title_when_url_is_download(self) -> None:
        res = ScrapedResource(
            title="EXPORTACIONES 2023",
            url="https://nube.ine.gob.bo/s/xyz/download",
            operation_type="exportaciones",
        )
        resp = MagicMock(spec=requests.Response)
        resp.headers = {}

        filename = _extract_filename_from_response(resp, res)
        assert filename == "EXPORTACIONES 2023.xlsx"


# ---------------------------------------------------------------------------
# Tests: download_resource & idempotencia
# ---------------------------------------------------------------------------
class TestDownloadResource:
    """Pruebas para descarga y control de idempotencia."""

    def test_download_new_file_success(self, tmp_path: Path) -> None:
        content = b"Mock Excel Binary Data 2026"
        expected_hash = hashlib.sha256(content).hexdigest()

        mock_resp = MagicMock()
        mock_resp.headers = {"Content-Disposition": 'attachment; filename="DATA_2026.xlsx"'}
        mock_resp.iter_content.return_value = [content]
        mock_resp.raise_for_status.return_value = None
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.__exit__.return_value = None

        mock_session = MagicMock(spec=requests.Session)
        mock_session.get.return_value = mock_resp

        res = ScrapedResource(
            title="DATA 2026",
            url="https://nube.ine.gob.bo/s/123/download",
            operation_type="exportaciones",
        )

        meta = download_resource(
            res,
            output_dir=tmp_path,
            known_hashes=set(),
            session=mock_session,
        )

        assert meta.status == "DOWNLOADED"
        assert meta.filename == "DATA_2026.xlsx"
        assert meta.hash_sha256 == expected_hash
        assert meta.file_path is not None
        assert meta.file_path.exists()
        assert meta.file_path.read_bytes() == content
        assert meta.file_size_bytes == len(content)

    def test_download_overwrites_existing_file_if_new_hash(self, tmp_path: Path) -> None:
        existing_file = tmp_path / "DATA_2026.xlsx"
        existing_file.write_bytes(b"Old content")

        new_content = b"Updated New Content 2026"
        new_hash = hashlib.sha256(new_content).hexdigest()

        mock_resp = MagicMock()
        mock_resp.headers = {"Content-Disposition": 'attachment; filename="DATA_2026.xlsx"'}
        mock_resp.iter_content.return_value = [new_content]
        mock_resp.raise_for_status.return_value = None
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.__exit__.return_value = None

        mock_session = MagicMock(spec=requests.Session)
        mock_session.get.return_value = mock_resp

        res = ScrapedResource(
            title="DATA 2026",
            url="https://nube.ine.gob.bo/s/123/download",
            operation_type="exportaciones",
        )

        meta = download_resource(
            res,
            output_dir=tmp_path,
            known_hashes=set(),
            session=mock_session,
        )

        assert meta.status == "DOWNLOADED"
        assert meta.hash_sha256 == new_hash
        assert existing_file.read_bytes() == new_content

    def test_download_skips_when_hash_is_known(self, tmp_path: Path) -> None:
        content = b"Existing File Content"
        known_hash = hashlib.sha256(content).hexdigest()

        mock_resp = MagicMock()
        mock_resp.headers = {"Content-Disposition": 'attachment; filename="DATA_OLD.xlsx"'}
        mock_resp.iter_content.return_value = [content]
        mock_resp.raise_for_status.return_value = None
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.__exit__.return_value = None

        mock_session = MagicMock(spec=requests.Session)
        mock_session.get.return_value = mock_resp

        res = ScrapedResource(
            title="DATA OLD",
            url="https://nube.ine.gob.bo/s/old/download",
            operation_type="exportaciones",
        )

        meta = download_resource(
            res,
            output_dir=tmp_path,
            known_hashes={known_hash},
            session=mock_session,
        )

        assert meta.status == "SKIPPED_EXISTING"
        assert meta.hash_sha256 == known_hash
        assert meta.file_path is None
        assert list(tmp_path.glob("*.xlsx")) == []

    def test_download_handles_network_error(self, tmp_path: Path) -> None:
        mock_session = MagicMock(spec=requests.Session)
        mock_session.get.side_effect = requests.RequestException("SSL Certificate Verification Error")

        res = ScrapedResource(
            title="DATA FAIL",
            url="https://nube.ine.gob.bo/s/fail/download",
            operation_type="exportaciones",
        )

        meta = download_resource(
            res,
            output_dir=tmp_path,
            known_hashes=set(),
            session=mock_session,
        )

        assert meta.status == "FAILED"
        assert "SSL Certificate" in (meta.error_message or "")
        assert meta.file_path is None

    def test_download_cleans_temp_file_on_streaming_failure(self, tmp_path: Path) -> None:
        def _failing_iter(**_kwargs: object):
            yield b"First partial chunk"
            msg = "Connection reset by peer mid-stream"
            raise requests.exceptions.ChunkedEncodingError(msg)

        mock_resp = MagicMock()
        mock_resp.headers = {"Content-Disposition": 'attachment; filename="BROKEN.xlsx"'}
        mock_resp.iter_content.side_effect = _failing_iter
        mock_resp.raise_for_status.return_value = None
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.__exit__.return_value = None

        mock_session = MagicMock(spec=requests.Session)
        mock_session.get.return_value = mock_resp

        res = ScrapedResource(title="BROKEN", url="https://ine/broken", operation_type="exportaciones")
        meta = download_resource(res, output_dir=tmp_path, session=mock_session)

        assert meta.status == "FAILED"
        assert "Connection reset" in (meta.error_message or "")
        assert len(list(tmp_path.iterdir())) == 0


# ---------------------------------------------------------------------------
# Tests: _collect_existing_disk_hashes & extract_comercio_exterior
# ---------------------------------------------------------------------------
class TestExtractComercioExteriorOrchestration:
    """Pruebas para el orquestador general de extracción."""

    def test_collect_existing_disk_hashes(self, tmp_path: Path) -> None:
        f1 = tmp_path / "file1.xlsx"
        f1.write_bytes(b"content 1")
        f2 = tmp_path / "file2.csv"
        f2.write_bytes(b"content 2")
        f3 = tmp_path / "ignored.txt"
        f3.write_bytes(b"content 3")

        hashes = _collect_existing_disk_hashes(tmp_path)
        assert len(hashes) == 2
        assert hashlib.sha256(b"content 1").hexdigest() in hashes
        assert hashlib.sha256(b"content 2").hexdigest() in hashes

    def test_collect_existing_disk_hashes_handles_unreadable_file(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        f = tmp_path / "corrupt.xlsx"
        f.write_bytes(b"broken")

        def _raise_error(*_args: object, **_kwargs: object) -> str:
            msg = "Read error"
            raise PermissionError(msg)

        monkeypatch.setattr("src.extract_comercio_exterior.compute_sha256", _raise_error)
        hashes = _collect_existing_disk_hashes(tmp_path)
        assert hashes == set()

    def test_extract_comercio_exterior_full_flow(self, tmp_path: Path) -> None:
        res1 = ScrapedResource(title="EXP 2026", url="https://ine/exp2026", operation_type="exportaciones")
        res2 = ScrapedResource(title="IMP 2026", url="https://ine/imp2026", operation_type="importaciones")
        res3 = ScrapedResource(title="FAIL 2026", url="https://ine/fail2026", operation_type="exportaciones")

        with patch("src.extract_comercio_exterior.scrape_ine_resources") as mock_scrape, patch(
            "src.extract_comercio_exterior.download_resource"
        ) as mock_download:
            mock_scrape.side_effect = lambda url, **kw: [res1, res3] if "export" in url else [res2]

            meta1 = ExtractionMetadata(
                resource=res1, filename="EXP_2026.xlsx", hash_sha256="hash1", status="DOWNLOADED"
            )
            meta2 = ExtractionMetadata(
                resource=res2, filename="IMP_2026.xlsx", hash_sha256="hash2", status="SKIPPED_EXISTING"
            )
            meta3 = ExtractionMetadata(
                resource=res3, filename="FAIL.xlsx", hash_sha256="", status="FAILED", error_message="Net error"
            )
            mock_download.side_effect = [meta1, meta3, meta2]

            summary = extract_comercio_exterior(
                sources={
                    "exportaciones": "https://test.ine/exportaciones",
                    "importaciones": "https://test.ine/importaciones",
                },
                output_base_dir=tmp_path,
                known_hashes=["hash_previo"],
            )

            assert summary.total_scraped == 3
            assert summary.total_downloaded == 1
            assert summary.total_skipped == 1
            assert summary.total_failed == 1

    def test_extract_comercio_exterior_default_sources_and_auto_hashes(self, tmp_path: Path) -> None:
        with patch("src.extract_comercio_exterior.scrape_ine_resources") as mock_scrape, patch(
            "src.extract_comercio_exterior.download_resource"
        ):
            mock_scrape.return_value = []

            summary = extract_comercio_exterior(output_base_dir=tmp_path)
            assert summary.total_scraped == 0
            assert mock_scrape.call_count == 2
