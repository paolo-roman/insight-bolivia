"""InsightBolivia — Pruebas unitarias para el script orquestador principal (src/main.py).

Valida el parseo CLI, filtrado por fecha, descubrimiento, ciclo E2E de procesamiento,
abortos ante fallos de calidad GX, modo --dry-run, modo --force-reprocess y códigos de salida.
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.extract_comercio_exterior import ExtractionMetadata, ExtractionSummary, ScrapedResource
from src.load_comercio_exterior import LoadResult
from src.main import (
    FileProcessingResult,
    PipelineExecutionSummary,
    _discover_files_to_process,
    build_arg_parser,
    filter_dataframe_by_date,
    main,
    parse_date_range,
    process_single_file,
    run_etl_pipeline,
)
from src.validate import GXValidationReport

if TYPE_CHECKING:
    from pathlib import Path


class TestCLIParser:
    """Pruebas para build_arg_parser()."""

    def test_default_arguments(self) -> None:
        args = build_arg_parser().parse_args([])
        assert args.force_reprocess is False and args.dry_run is False
        assert args.date_range is None and args.operation == "all"
        assert args.skip_extract is False and args.file is None
        assert args.raw_dir is None and args.skip_validation is False
        assert args.strict_env is False and args.log_level is None and args.log_format is None

    def test_custom_flags_parsing(self) -> None:
        args = build_arg_parser().parse_args([
            "--force-reprocess",
            "--dry-run",
            "--date-range", "2024-01:2024-06",
            "--operation", "exportaciones",
            "--skip-extract",
            "--file", "data/custom.xlsx",
            "--raw-dir", "custom/raw/path",
            "--skip-validation",
            "--strict-env",
            "--log-level", "DEBUG",
            "--log-format", "text",
        ])
        assert args.force_reprocess is True and args.dry_run is True
        assert args.date_range == "2024-01:2024-06" and args.operation == "exportaciones"
        assert args.skip_extract is True and args.file == "data/custom.xlsx"
        assert args.raw_dir == "custom/raw/path" and args.skip_validation is True
        assert args.strict_env is True and args.log_level == "DEBUG" and args.log_format == "text"


class TestDateRangeAndFiltering:
    """Pruebas para parse_date_range() y filter_dataframe_by_date()."""

    def test_parse_none_or_empty(self) -> None:
        assert parse_date_range(None) == (None, None)
        assert parse_date_range("   ") == (None, None)

    def test_parse_single_year_and_months(self) -> None:
        start, end = parse_date_range("2024")
        assert start == datetime(2024, 1, 1, tzinfo=UTC)
        assert end == datetime(2024, 12, 31, 23, 59, 59, tzinfo=UTC)

        s_m, e_m = parse_date_range("2024-05")
        assert s_m == datetime(2024, 5, 1, tzinfo=UTC)
        assert e_m == datetime(2024, 5, 31, 23, 59, 59, tzinfo=UTC)

        s_dec, e_dec = parse_date_range("2024-12")
        assert s_dec == datetime(2024, 12, 1, tzinfo=UTC)
        assert e_dec == datetime(2024, 12, 31, 23, 59, 59, tzinfo=UTC)

    def test_parse_invalid_month_raises(self) -> None:
        with pytest.raises(ValueError, match="Mes inválido"):
            parse_date_range("2024-13")

    def test_parse_single_date_and_ranges(self) -> None:
        s_d, e_d = parse_date_range("2024-06-15")
        assert s_d == datetime(2024, 6, 15, tzinfo=UTC) and e_d == datetime(2024, 6, 15, tzinfo=UTC)

        s_c, e_c = parse_date_range("2024-01-01:2024-06-30")
        assert s_c == datetime(2024, 1, 1, tzinfo=UTC) and e_c == datetime(2024, 6, 30, tzinfo=UTC)

        s_dot, e_dot = parse_date_range("2024-01-01..2024-12-31")
        assert s_dot == datetime(2024, 1, 1, tzinfo=UTC) and e_dot == datetime(2024, 12, 31, tzinfo=UTC)

        s_op1, e_op1 = parse_date_range("2024-01-01:")
        assert s_op1 == datetime(2024, 1, 1, tzinfo=UTC) and e_op1 is None

        s_op2, e_op2 = parse_date_range(":2024-12-31")
        assert s_op2 is None and e_op2 == datetime(2024, 12, 31, tzinfo=UTC)

    def test_parse_start_after_end_raises(self) -> None:
        with pytest.raises(ValueError, match="no puede ser posterior"):
            parse_date_range("2024-12-31:2024-01-01")

    def test_filter_dataframe(self) -> None:
        assert filter_dataframe_by_date(pd.DataFrame(), datetime(2024, 1, 1, tzinfo=UTC), None).empty

        df_f = pd.DataFrame({"fecha": ["2023-12-01", "2024-03-01", "2024-07-01", "2025-01-01"], "v": [1, 2, 3, 4]})
        res_f = filter_dataframe_by_date(df_f, datetime(2024, 1, 1, tzinfo=UTC), datetime(2024, 12, 31, tzinfo=UTC))
        assert len(res_f) == 2 and res_f["v"].tolist() == [2, 3]

        df_g = pd.DataFrame({"gestion": [2022, 2023, 2024, 2025], "v": [1, 2, 3, 4]})
        res_g = filter_dataframe_by_date(df_g, datetime(2023, 1, 1, tzinfo=UTC), datetime(2024, 12, 31, tzinfo=UTC))
        assert len(res_g) == 2 and res_g["gestion"].tolist() == [2023, 2024]

        df_nc = pd.DataFrame({"colA": [1, 2]})
        assert len(filter_dataframe_by_date(df_nc, datetime(2024, 1, 1, tzinfo=UTC), None)) == 2


class TestProcessSingleFile:
    """Pruebas para process_single_file()."""

    def test_file_not_found(self, tmp_path: Path) -> None:
        opts = argparse.Namespace(force_reprocess=False, dry_run=False, skip_validation=False)
        res = process_single_file(tmp_path / "miss.xlsx", "exportaciones", opts)
        assert res.status == "ERROR" and "no encontrado" in (res.error_message or "").lower()

    @patch("src.main.is_already_processed", return_value=True)
    def test_already_processed_skipped(self, mock_is_proc: MagicMock, tmp_path: Path) -> None:
        tf = tmp_path / "sample.xlsx"
        tf.write_bytes(b"content")
        opts = argparse.Namespace(force_reprocess=False, dry_run=False, skip_validation=False)
        res = process_single_file(tf, "exportaciones", opts, bq_client=MagicMock())
        assert res.status == "SKIPPED"

    @patch("src.main.is_already_processed", side_effect=Exception("BQ Error"))
    @patch("src.main.read_raw_file")
    @patch("src.main.transform_to_staging")
    @patch("src.main.transform_to_fact")
    @patch("src.main.validate_transformed_data")
    @patch("src.main.load_comercio_exterior")
    def test_full_pipeline_with_date_filter(
        self,
        mock_load: MagicMock,
        mock_val: MagicMock,
        mock_tf_fact: MagicMock,
        mock_tf_stg: MagicMock,
        mock_read: MagicMock,
        mock_is_proc: MagicMock,
        tmp_path: Path,
    ) -> None:
        tf = tmp_path / "sample.xlsx"
        tf.write_bytes(b"dummy")
        mock_read.return_value = pd.DataFrame({"fecha": ["2024-05-01"]})
        mock_tf_stg.return_value = pd.DataFrame({"fecha": ["2024-05-01"]})
        mock_tf_fact.return_value = pd.DataFrame({"fecha": ["2024-05-01"]})
        mock_val.return_value = GXValidationReport(
            success=True, suite_name="t", total_expectations=1, successful_expectations=1, failed_expectations=0
        )
        mock_load.return_value = LoadResult(
            status="SUCCESS",
            records_staging=1,
            records_fact=1,
            sha256="a",
            execution_id="1",
            duration_seconds=0.1,
        )

        opts = argparse.Namespace(force_reprocess=False, dry_run=False, skip_validation=False)
        res = process_single_file(
            tf,
            "exportaciones",
            opts,
            bq_client=MagicMock(),
            start_date=datetime(2024, 1, 1, tzinfo=UTC),
            end_date=datetime(2024, 12, 31, tzinfo=UTC),
        )
        assert res.status == "SUCCESS"
        mock_load.assert_called_once()

    @patch("src.main.read_raw_file")
    @patch("src.main.transform_to_staging")
    def test_empty_staging_after_filtering_is_skipped(
        self,
        mock_stg: MagicMock,
        mock_read: MagicMock,
        tmp_path: Path,
    ) -> None:
        tf = tmp_path / "sample.xlsx"
        tf.write_bytes(b"c")
        mock_read.return_value = pd.DataFrame({"fecha": ["2020-01-01"]})
        mock_stg.return_value = pd.DataFrame({"fecha": ["2020-01-01"]})
        opts = argparse.Namespace(force_reprocess=True, dry_run=False, skip_validation=False)
        res = process_single_file(
            tf,
            "exportaciones",
            opts,
            start_date=datetime(2024, 1, 1, tzinfo=UTC),
        )
        assert res.status == "SKIPPED"

    @patch("src.main.read_raw_file")
    @patch("src.main.transform_to_staging")
    @patch("src.main.transform_to_fact")
    @patch("src.main.validate_transformed_data")
    @patch("src.main.load_comercio_exterior")
    def test_validation_failure_aborts_load(
        self,
        mock_load: MagicMock,
        mock_val: MagicMock,
        mock_fact: MagicMock,
        mock_stg: MagicMock,
        mock_read: MagicMock,
        tmp_path: Path,
    ) -> None:
        tf = tmp_path / "sample.xlsx"
        tf.write_bytes(b"c")
        mock_read.return_value = pd.DataFrame({"a": [1]})
        mock_stg.return_value = pd.DataFrame({"a": [1]})
        mock_fact.return_value = pd.DataFrame({"a": [1]})
        mock_val.return_value = GXValidationReport(
            success=False,
            suite_name="s",
            total_expectations=2,
            successful_expectations=1,
            failed_expectations=1,
            summary_message="Fallo",
        )
        opts = argparse.Namespace(force_reprocess=True, dry_run=False, skip_validation=False)
        res = process_single_file(tf, "exportaciones", opts)
        assert res.status == "VALIDATION_FAILED" and res.validation_passed is False
        mock_load.assert_not_called()

    @patch("src.main.read_raw_file")
    @patch("src.main.transform_to_staging")
    @patch("src.main.transform_to_fact")
    @patch("src.main.load_comercio_exterior")
    def test_skip_validation_flag_skips_gx_check(
        self,
        mock_load: MagicMock,
        mock_fact: MagicMock,
        mock_stg: MagicMock,
        mock_read: MagicMock,
        tmp_path: Path,
    ) -> None:
        tf = tmp_path / "sample.xlsx"
        tf.write_bytes(b"c")
        mock_read.return_value = pd.DataFrame({"a": [1]})
        mock_stg.return_value = pd.DataFrame({"a": [1]})
        mock_fact.return_value = pd.DataFrame({"a": [1]})
        mock_load.return_value = LoadResult(
            status="SUCCESS",
            records_staging=1,
            records_fact=1,
            sha256="a",
            execution_id="1",
            duration_seconds=0.1,
        )

        opts = argparse.Namespace(force_reprocess=True, dry_run=False, skip_validation=True)
        res = process_single_file(tf, "exportaciones", opts)
        assert res.status == "SUCCESS" and res.validation_passed is True

    @patch("src.main.read_raw_file")
    @patch("src.main.transform_to_staging")
    @patch("src.main.transform_to_fact")
    @patch("src.main.validate_transformed_data")
    @patch("src.main.load_comercio_exterior")
    def test_dry_run_skips_load(
        self,
        mock_load: MagicMock,
        mock_val: MagicMock,
        mock_fact: MagicMock,
        mock_stg: MagicMock,
        mock_read: MagicMock,
        tmp_path: Path,
    ) -> None:
        tf = tmp_path / "sample.xlsx"
        tf.write_bytes(b"c")
        mock_read.return_value = pd.DataFrame({"a": [1]})
        mock_stg.return_value = pd.DataFrame({"a": [1]})
        mock_fact.return_value = pd.DataFrame({"a": [1]})
        mock_val.return_value = GXValidationReport(
            success=True,
            suite_name="s",
            total_expectations=1,
            successful_expectations=1,
            failed_expectations=0,
        )

        opts = argparse.Namespace(force_reprocess=False, dry_run=True, skip_validation=False)
        res = process_single_file(tf, "exportaciones", opts)
        assert res.status == "DRY_RUN" and res.validation_passed is True
        mock_load.assert_not_called()

    @patch("src.main.read_raw_file", side_effect=ValueError("Corrupto"))
    def test_read_exception_returns_error(self, mock_read: MagicMock, tmp_path: Path) -> None:
        tf = tmp_path / "corrupt.xlsx"
        tf.write_bytes(b"c")
        opts = argparse.Namespace(force_reprocess=True, dry_run=False, skip_validation=False)
        res = process_single_file(tf, "exportaciones", opts)
        assert res.status == "ERROR" and "Corrupto" in (res.error_message or "")


class TestFileDiscoveryAndPipeline:
    """Pruebas para _discover_files_to_process() y run_etl_pipeline()."""

    def test_discover_custom_files(self, tmp_path: Path) -> None:
        imp = tmp_path / "importaciones_2024.csv"
        imp.write_text("d", encoding="utf-8")
        opts_imp = argparse.Namespace(file=str(imp), operation="all", skip_extract=False)
        assert _discover_files_to_process(opts_imp, tmp_path)[0][1] == "importaciones"

        exp = tmp_path / "exportaciones_2024.xlsx"
        exp.write_bytes(b"d")
        opts_exp = argparse.Namespace(file=str(exp), operation="all", skip_extract=False)
        assert _discover_files_to_process(opts_exp, tmp_path)[0][1] == "exportaciones"

        gen = tmp_path / "generic.xlsx"
        gen.write_bytes(b"d")
        opts_gen = argparse.Namespace(file=str(gen), operation="importaciones", skip_extract=False)
        assert _discover_files_to_process(opts_gen, tmp_path)[0][1] == "importaciones"

    @patch("src.main.extract_comercio_exterior")
    def test_discover_via_scraping(self, mock_extract: MagicMock, tmp_path: Path) -> None:
        exp_f = tmp_path / "exp.xlsx"
        imp_f = tmp_path / "imp.csv"
        exp_f.write_bytes(b"d")
        imp_f.write_text("d", encoding="utf-8")

        mock_extract.return_value = ExtractionSummary(
            total_scraped=2,
            downloaded=[
                ExtractionMetadata(
                    resource=ScrapedResource("Exp", "u1", "exportaciones"), file_path=exp_f, status="DOWNLOADED"
                ),
                ExtractionMetadata(
                    resource=ScrapedResource("Imp", "u2", "importaciones"), file_path=imp_f, status="DOWNLOADED"
                ),
            ],
        )
        files = _discover_files_to_process(argparse.Namespace(file=None, operation="all", skip_extract=False), tmp_path)
        assert len(files) == 2

        mock_extract.return_value = ExtractionSummary(
            total_scraped=1,
            downloaded=[
                ExtractionMetadata(
                    resource=ScrapedResource("Imp", "u2", "importaciones"), file_path=imp_f, status="DOWNLOADED"
                )
            ],
        )
        opts_imp = argparse.Namespace(file=None, operation="importaciones", skip_extract=False)
        files_imp = _discover_files_to_process(opts_imp, tmp_path)
        assert len(files_imp) == 1

    def test_discover_local_files_when_skip_extract(self, tmp_path: Path) -> None:
        d = tmp_path / "exportaciones"
        d.mkdir(parents=True)
        (d / "exp_2024.xlsx").write_bytes(b"d")
        files = _discover_files_to_process(argparse.Namespace(file=None, operation="all", skip_extract=True), tmp_path)
        assert len(files) == 1

    def test_run_etl_pipeline_no_files_found(self, tmp_path: Path) -> None:
        opts = argparse.Namespace(
            file=None,
            operation="all",
            skip_extract=True,
            raw_dir=str(tmp_path),
            dry_run=False,
            force_reprocess=False,
            date_range=None,
            strict_env=False,
            log_level="INFO",
            log_format="text",
        )
        summary = run_etl_pipeline(opts)
        assert summary.total_files == 0 and summary.is_success is True

    @patch("src.main.process_single_file")
    def test_run_etl_pipeline_aggregates_summary(self, mock_proc: MagicMock, tmp_path: Path) -> None:
        exp_dir = tmp_path / "exportaciones"
        exp_dir.mkdir(parents=True, exist_ok=True)
        (exp_dir / "f1.xlsx").write_bytes(b"1")
        (exp_dir / "f2.xlsx").write_bytes(b"2")
        (exp_dir / "f3.xlsx").write_bytes(b"3")

        mock_proc.side_effect = [
            FileProcessingResult(exp_dir / "f1.xlsx", "exportaciones", "h1", status="SUCCESS"),
            FileProcessingResult(exp_dir / "f2.xlsx", "exportaciones", "h2", status="SKIPPED"),
            FileProcessingResult(exp_dir / "f3.xlsx", "exportaciones", "h3", status="VALIDATION_FAILED"),
        ]

        opts = argparse.Namespace(
            file=None,
            operation="exportaciones",
            skip_extract=True,
            raw_dir=str(tmp_path),
            dry_run=False,
            force_reprocess=False,
            date_range=None,
            strict_env=False,
            log_level="INFO",
            log_format="json",
        )
        summary = run_etl_pipeline(opts)
        assert summary.total_files == 3 and summary.successful_files == 1
        assert summary.skipped_files == 1 and summary.failed_files == 1 and summary.is_success is False

    @patch("src.main.validate_mandatory_env_vars", side_effect=ValueError("Missing BQ_PROJECT_ID"))
    def test_run_etl_pipeline_strict_env_validation(self, mock_val: MagicMock, tmp_path: Path) -> None:
        opts = argparse.Namespace(
            file=None,
            operation="all",
            skip_extract=True,
            raw_dir=str(tmp_path),
            dry_run=False,
            force_reprocess=False,
            date_range=None,
            strict_env=True,
            log_level="INFO",
            log_format="text",
        )
        with pytest.raises(ValueError, match="Missing BQ_PROJECT_ID"):
            run_etl_pipeline(opts)


class TestMainEntrypoint:
    """Pruebas para main() e integración con CLI."""

    @patch("src.main.run_etl_pipeline")
    def test_main_success_exit_code_zero(self, mock_run: MagicMock) -> None:
        mock_run.return_value = PipelineExecutionSummary(total_files=1, successful_files=1, failed_files=0)
        assert main(["--dry-run"]) == 0

    @patch("src.main.run_etl_pipeline")
    def test_main_failure_exit_code_one(self, mock_run: MagicMock) -> None:
        mock_run.return_value = PipelineExecutionSummary(total_files=1, successful_files=0, failed_files=1)
        assert main(["--dry-run"]) == 1

    @patch("src.main.run_etl_pipeline", side_effect=RuntimeError("Fallo inesperado"))
    def test_main_unhandled_exception_returns_one(self, mock_run: MagicMock) -> None:
        assert main(["--dry-run"]) == 1

    @patch("src.main.get_settings", side_effect=Exception("No settings"))
    @patch("src.main.run_etl_pipeline")
    def test_main_fallback_when_settings_fail(self, mock_run: MagicMock, mock_settings: MagicMock) -> None:
        mock_run.return_value = PipelineExecutionSummary(total_files=0, failed_files=0)
        assert main([]) == 0

    @patch("sys.exit")
    def test_main_execution_block(self, mock_exit: MagicMock, tmp_path: Path) -> None:
        import runpy

        with (
            patch.object(sys, "argv", ["src/main.py", "--dry-run", "--skip-extract", "--raw-dir", str(tmp_path)]),
            patch.dict(sys.modules),
        ):
            sys.modules.pop("src.main", None)
            runpy.run_module("src.main", run_name="__main__")
        mock_exit.assert_called_once_with(0)



