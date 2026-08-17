"""Pruebas unitarias para el módulo de carga de comercio exterior ``src.load_comercio_exterior``.

Valida las sentencias SCD Tipo 2 en `dim_producto`, upsert MERGE en
`fact_comercio_exterior`, y la orquestación end-to-end `load_comercio_exterior`.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.load import LoadError, LoadResult
from src.load_comercio_exterior import (
    load_comercio_exterior,
    merge_into_fact_comercio_exterior,
    sync_dim_producto_scd2,
)


@pytest.fixture
def sample_staging_df() -> pd.DataFrame:
    """Retorna un DataFrame sintético con el esquema de staging."""
    return pd.DataFrame(
        {
            "gestion": [2023, 2023],
            "mes": [1, 2],
            "fecha": ["2023-01-01", "2023-02-01"],
            "codigo_nandina": ["0901110000", "2611110000"],
            "descripcion_nandina": ["Café sin tostar", "Minerales de plomo"],
            "capitulo_nandina": ["09", "26"],
            "seccion_nandina": ["II", "V"],
            "codigo_pais_ine": [249, 63],
            "nombre_pais": ["ESTADOS UNIDOS", "ARGENTINA"],
            "codigo_departamento": [2, 3],
            "codigo_aduana": [101, 201],
            "codigo_via": [1, 2],
            "tipo_operacion": ["EXPORTACION", "EXPORTACION"],
            "valor_fob_usd": [15000.0, 32000.0],
            "peso_neto_kg": [1000.0, 2500.0],
            "peso_bruto_kg": [1050.0, 2600.0],
            "descripcion_actividad": ["Agricultura", "Minería"],
            "hash_sha256": ["test_hash_123", "test_hash_123"],
            "fecha_ingesta": ["2023-01-01T00:00:00Z", "2023-02-01T00:00:00Z"],
        }
    )


class TestSyncDimProductoSCD2:
    """Pruebas para el mantenimiento de SCD Tipo 2 en `dim_producto`."""

    def test_executes_scd2_merge_and_insert(self) -> None:
        mock_bq = MagicMock()
        mock_close_job = MagicMock()
        mock_close_job.num_dml_affected_rows = 1
        mock_insert_job = MagicMock()
        mock_insert_job.num_dml_affected_rows = 3

        mock_bq.query.side_effect = [mock_close_job, mock_insert_job]
        mock_bq.project = "insight-bolivia"

        stats = sync_dim_producto_scd2(client=mock_bq, hash_sha256="hash123")
        assert stats == {"closed_records": 1, "inserted_records": 3}
        assert mock_bq.query.call_count == 2
        mock_close_job.result.assert_called_once()
        mock_insert_job.result.assert_called_once()


class TestMergeIntoFactComercioExterior:
    """Pruebas para el upsert atómico en `fact_comercio_exterior`."""

    def test_executes_merge_and_returns_affected_rows(self) -> None:
        mock_bq = MagicMock()
        mock_job = MagicMock()
        mock_job.num_dml_affected_rows = 150
        mock_bq.query.return_value = mock_job
        mock_bq.project = "insight-bolivia"

        affected = merge_into_fact_comercio_exterior(client=mock_bq, hash_sha256="hash123")
        assert affected == 150
        mock_bq.query.assert_called_once()
        mock_job.result.assert_called_once()


class TestLoadComercioExteriorOrchestration:
    """Pruebas de orquestación completa del pipeline de carga."""

    @patch("src.load_comercio_exterior.sync_firestore_metadata", return_value=True)
    @patch("src.load_comercio_exterior.log_etl_execution", return_value="exec_success_123")
    @patch("src.load_comercio_exterior.merge_into_fact_comercio_exterior", return_value=2)
    @patch(
        "src.load_comercio_exterior.sync_dim_producto_scd2",
        return_value={"closed_records": 0, "inserted_records": 2},
    )
    @patch("src.load_comercio_exterior.load_to_staging", return_value=2)
    @patch("src.load_comercio_exterior.is_already_processed", return_value=False)
    def test_successful_end_to_end_load(
        self,
        mock_is_proc: MagicMock,
        mock_load_stg: MagicMock,
        mock_scd2: MagicMock,
        mock_merge: MagicMock,
        mock_log: MagicMock,
        mock_sync_fs: MagicMock,
        sample_staging_df: pd.DataFrame,
    ) -> None:
        mock_bq = MagicMock()
        mock_fs = MagicMock()

        result = load_comercio_exterior(
            df_staging=sample_staging_df,
            filename="exportaciones_2023.xlsx",
            file_hash="hash_abc",
            fecha_publicacion="2023-01-01",
            bq_client=mock_bq,
            fs_client=mock_fs,
        )

        assert isinstance(result, LoadResult)
        assert result.status == "SUCCESS"
        assert result.is_success is True
        assert result.records_staging == 2
        assert result.records_fact == 2
        assert result.sha256 == "hash_abc"
        mock_load_stg.assert_called_once()
        mock_scd2.assert_called_once()
        mock_merge.assert_called_once()
        mock_log.assert_called_once()
        mock_sync_fs.assert_called_once()

    @patch("src.load_comercio_exterior.log_etl_execution", return_value="exec_skipped_123")
    @patch("src.load_comercio_exterior.is_already_processed", return_value=True)
    def test_idempotent_skip_when_already_processed(
        self,
        mock_is_proc: MagicMock,
        mock_log: MagicMock,
        sample_staging_df: pd.DataFrame,
    ) -> None:
        mock_bq = MagicMock()
        mock_fs = MagicMock()

        result = load_comercio_exterior(
            df_staging=sample_staging_df,
            filename="exportaciones_2023.xlsx",
            file_hash="hash_already_done",
            force=False,
            bq_client=mock_bq,
            fs_client=mock_fs,
        )

        assert result.status == "SKIPPED"
        assert result.is_success is True
        assert result.records_staging == 0
        assert result.records_fact == 0
        mock_log.assert_called_once_with(
            nombre_archivo="exportaciones_2023.xlsx",
            hash_sha256="hash_already_done",
            estado="SKIPPED",
            registros_procesados=len(sample_staging_df),
            fecha_publicacion=None,
            client=mock_bq,
        )

    @patch("src.load_comercio_exterior.sync_firestore_metadata", return_value=True)
    @patch("src.load_comercio_exterior.log_etl_execution", return_value="exec_forced_123")
    @patch("src.load_comercio_exterior.merge_into_fact_comercio_exterior", return_value=2)
    @patch(
        "src.load_comercio_exterior.sync_dim_producto_scd2",
        return_value={"closed_records": 0, "inserted_records": 2},
    )
    @patch("src.load_comercio_exterior.load_to_staging", return_value=2)
    @patch("src.load_comercio_exterior.is_already_processed", return_value=True)
    def test_forced_reprocessing_bypasses_skip(
        self,
        mock_is_proc: MagicMock,
        mock_load_stg: MagicMock,
        mock_scd2: MagicMock,
        mock_merge: MagicMock,
        mock_log: MagicMock,
        mock_sync_fs: MagicMock,
        sample_staging_df: pd.DataFrame,
    ) -> None:
        mock_bq = MagicMock()
        mock_fs = MagicMock()

        result = load_comercio_exterior(
            df_staging=sample_staging_df,
            filename="exportaciones_2023.xlsx",
            file_hash="hash_already_done",
            force=True,
            bq_client=mock_bq,
            fs_client=mock_fs,
        )

        assert result.status == "SUCCESS"
        mock_load_stg.assert_called_once()
        mock_merge.assert_called_once()

    @patch("src.load_comercio_exterior.log_etl_execution", return_value="exec_failed_123")
    @patch("src.load_comercio_exterior.load_to_staging", side_effect=RuntimeError("BigQuery write error"))
    @patch("src.load_comercio_exterior.is_already_processed", return_value=False)
    def test_pipeline_failure_logs_failed_and_raises(
        self,
        mock_is_proc: MagicMock,
        mock_load_stg: MagicMock,
        mock_log: MagicMock,
        sample_staging_df: pd.DataFrame,
    ) -> None:
        mock_bq = MagicMock()
        mock_fs = MagicMock()

        with pytest.raises(LoadError, match="Error cargando comercio exterior"):
            load_comercio_exterior(
                df_staging=sample_staging_df,
                filename="exportaciones_2023.xlsx",
                file_hash="hash_fail",
                bq_client=mock_bq,
                fs_client=mock_fs,
            )

        mock_log.assert_called_once()
        assert mock_log.call_args[1]["estado"] == "FAILED"

    @patch("src.load_comercio_exterior.log_etl_execution", side_effect=RuntimeError("Logging failed"))
    @patch("src.load_comercio_exterior.load_to_staging", side_effect=RuntimeError("BigQuery write error"))
    @patch("src.load_comercio_exterior.is_already_processed", return_value=False)
    def test_pipeline_failure_with_log_error_still_raises(
        self,
        mock_is_proc: MagicMock,
        mock_load_stg: MagicMock,
        mock_log: MagicMock,
        sample_staging_df: pd.DataFrame,
    ) -> None:
        mock_bq = MagicMock()
        mock_fs = MagicMock()

        with pytest.raises(LoadError, match="Error cargando comercio exterior"):
            load_comercio_exterior(
                df_staging=sample_staging_df,
                filename="exportaciones_2023.xlsx",
                file_hash="hash_fail_double",
                bq_client=mock_bq,
                fs_client=mock_fs,
            )

    @patch("src.load_comercio_exterior.sync_firestore_metadata", side_effect=Exception("Firestore unavailable"))
    @patch("src.load_comercio_exterior.log_etl_execution", return_value="exec_ok_123")
    @patch("src.load_comercio_exterior.merge_into_fact_comercio_exterior", return_value=2)
    @patch(
        "src.load_comercio_exterior.sync_dim_producto_scd2",
        return_value={"closed_records": 0, "inserted_records": 2},
    )
    @patch("src.load_comercio_exterior.load_to_staging", return_value=2)
    @patch("src.load_comercio_exterior.is_already_processed", return_value=False)
    def test_firestore_warning_does_not_abort_bq_success(
        self,
        mock_is_proc: MagicMock,
        mock_load_stg: MagicMock,
        mock_scd2: MagicMock,
        mock_merge: MagicMock,
        mock_log: MagicMock,
        mock_sync_fs: MagicMock,
        sample_staging_df: pd.DataFrame,
    ) -> None:
        mock_bq = MagicMock()
        mock_fs = MagicMock()

        result = load_comercio_exterior(
            df_staging=sample_staging_df,
            filename="exportaciones_2023.xlsx",
            file_hash="hash_ok",
            bq_client=mock_bq,
            fs_client=mock_fs,
        )

        assert result.status == "SUCCESS"
        assert result.is_success is True
