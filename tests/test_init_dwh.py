"""Pruebas unitarias para el módulo de aprovisionamiento de BigQuery (src/init_dwh.py).

Valida:
- Creación de los 4 datasets con expiraciones y etiquetas correspondientes.
- Ejecución idempotente de archivos DDL de tablas y vistas.
- Siembra de dimensiones estáticas (tiempo, departamentos, vía transporte, moneda, país).
- Manejo de modo simulación (--dry-run).
- Resiliencia y captura de excepciones en el pipeline de aprovisionamiento.
- Ejecución CLI de la función main().
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from google.cloud import bigquery

from src.init_dwh import (
    ProvisioningReport,
    create_datasets,
    execute_sql_file,
    main,
    provision_dwh,
    seed_dim_departamentos,
    seed_dim_moneda,
    seed_dim_pais,
    seed_dim_tiempo,
    seed_dim_via_transporte,
)


@pytest.fixture
def mock_bq_client() -> MagicMock:
    """Fixture con cliente simulado de BigQuery."""
    client = MagicMock(spec=bigquery.Client)
    client.project = "insight-bolivia"
    mock_job = MagicMock()
    mock_job.result.return_value = None
    client.query.return_value = mock_job
    client.create_dataset.return_value = None
    client.get_table.return_value = MagicMock()
    client.insert_rows_json.return_value = []
    return client


class TestCreateDatasets:
    """Pruebas para la función create_datasets."""

    def test_create_datasets_real_calls(self, mock_bq_client: MagicMock) -> None:
        created = create_datasets(mock_bq_client, "insight-bolivia", location="US", dry_run=False)
        assert len(created) == 4
        assert "staging" in created
        assert "comercio_exterior" in created
        assert "benchmark_regional" in created
        assert "operations" in created
        assert mock_bq_client.create_dataset.call_count == 4

    def test_create_datasets_dry_run(self, mock_bq_client: MagicMock) -> None:
        created = create_datasets(mock_bq_client, "insight-bolivia", location="US", dry_run=True)
        assert len(created) == 4
        mock_bq_client.create_dataset.assert_not_called()

    def test_create_datasets_exception_propagates(self, mock_bq_client: MagicMock) -> None:
        mock_bq_client.create_dataset.side_effect = RuntimeError("Quota exceeded")
        with pytest.raises(RuntimeError, match="Quota exceeded"):
            create_datasets(mock_bq_client, "insight-bolivia", location="US", dry_run=False)


class TestExecuteSqlFile:
    """Pruebas para execute_sql_file."""

    def test_execute_sql_file_success(self, tmp_path: Path, mock_bq_client: MagicMock) -> None:
        sql_file = tmp_path / "test.sql"
        sql_file.write_text("CREATE TABLE `insight-bolivia.staging.t` (x INT64);", encoding="utf-8")
        execute_sql_file(mock_bq_client, sql_file, "custom-project", dry_run=False)
        mock_bq_client.query.assert_called_once()
        called_sql = mock_bq_client.query.call_args[0][0]
        assert "custom-project.staging.t" in called_sql

    def test_execute_sql_file_dry_run(self, tmp_path: Path, mock_bq_client: MagicMock) -> None:
        sql_file = tmp_path / "test.sql"
        sql_file.write_text("SELECT 1;", encoding="utf-8")
        execute_sql_file(mock_bq_client, sql_file, "insight-bolivia", dry_run=True)
        mock_bq_client.query.assert_not_called()

    def test_execute_sql_file_missing_file_raises(self, mock_bq_client: MagicMock) -> None:
        non_existent = Path("non_existent_file.sql")
        with pytest.raises(FileNotFoundError):
            execute_sql_file(mock_bq_client, non_existent, "insight-bolivia")


class TestDimensionSeeding:
    """Pruebas para las funciones de siembra de dimensiones estáticas."""

    def test_seed_dim_tiempo(self, mock_bq_client: MagicMock) -> None:
        cnt = seed_dim_tiempo(mock_bq_client, "insight-bolivia", dry_run=False)
        assert cnt == 372
        mock_bq_client.query.assert_called_once()

    def test_seed_dim_tiempo_dry_run(self, mock_bq_client: MagicMock) -> None:
        cnt = seed_dim_tiempo(mock_bq_client, "insight-bolivia", dry_run=True)
        assert cnt == 372
        mock_bq_client.query.assert_not_called()

    def test_seed_dim_departamentos(self, mock_bq_client: MagicMock) -> None:
        cnt = seed_dim_departamentos(mock_bq_client, "insight-bolivia", dry_run=False)
        assert cnt == 9
        mock_bq_client.query.assert_called_once()

    def test_seed_dim_departamentos_dry_run(self, mock_bq_client: MagicMock) -> None:
        cnt = seed_dim_departamentos(mock_bq_client, "insight-bolivia", dry_run=True)
        assert cnt == 9
        mock_bq_client.query.assert_not_called()

    def test_seed_dim_via_transporte(self, mock_bq_client: MagicMock) -> None:
        cnt = seed_dim_via_transporte(mock_bq_client, "insight-bolivia", dry_run=False)
        assert cnt == 6
        mock_bq_client.query.assert_called_once()

    def test_seed_dim_via_transporte_dry_run(self, mock_bq_client: MagicMock) -> None:
        cnt = seed_dim_via_transporte(mock_bq_client, "insight-bolivia", dry_run=True)
        assert cnt == 6
        mock_bq_client.query.assert_not_called()

    def test_seed_dim_moneda(self, mock_bq_client: MagicMock) -> None:
        cnt = seed_dim_moneda(mock_bq_client, "insight-bolivia", dry_run=False)
        assert cnt == 3
        mock_bq_client.query.assert_called_once()

    def test_seed_dim_moneda_dry_run(self, mock_bq_client: MagicMock) -> None:
        cnt = seed_dim_moneda(mock_bq_client, "insight-bolivia", dry_run=True)
        assert cnt == 3
        mock_bq_client.query.assert_not_called()

    def test_seed_dim_pais(self, mock_bq_client: MagicMock) -> None:
        cnt = seed_dim_pais(mock_bq_client, "insight-bolivia", dry_run=False)
        assert cnt == 80
        mock_bq_client.get_table.assert_called_once()
        assert mock_bq_client.insert_rows_json.called

    def test_seed_dim_pais_dry_run(self, mock_bq_client: MagicMock) -> None:
        cnt = seed_dim_pais(mock_bq_client, "insight-bolivia", dry_run=True)
        assert cnt == 80
        mock_bq_client.insert_rows_json.assert_not_called()


class TestProvisionDwh:
    """Pruebas de integración del flujo integral provision_dwh."""

    def test_provision_dwh_dry_run(self) -> None:
        report = provision_dwh(project_id="insight-bolivia", dry_run=True)
        assert isinstance(report, ProvisioningReport)
        assert report.is_success
        assert len(report.datasets_created) == 4
        assert len(report.tables_created) == 12
        assert len(report.views_created) == 3
        assert "dim_tiempo" in report.dimensions_seeded
        assert "dim_pais" in report.dimensions_seeded

    def test_provision_dwh_with_mock_client(self, mock_bq_client: MagicMock) -> None:
        report = provision_dwh(
            project_id="insight-bolivia",
            client=mock_bq_client,
            dry_run=False,
            skip_dimensions=False,
        )
        assert report.is_success
        assert len(report.datasets_created) == 4
        assert len(report.tables_created) == 12
        assert len(report.views_created) == 3
        assert len(report.dimensions_seeded) == 5

    def test_provision_dwh_dataset_failure(self, mock_bq_client: MagicMock) -> None:
        mock_bq_client.create_dataset.side_effect = RuntimeError("Auth failed")
        report = provision_dwh(project_id="insight-bolivia", client=mock_bq_client)
        assert not report.is_success
        assert any("Fallo en creación de datasets" in err for err in report.errors)

    def test_provision_dwh_table_failure_recorded(self, mock_bq_client: MagicMock) -> None:
        # Falla al ejecutar la primera tabla
        mock_bq_client.query.side_effect = RuntimeError("Syntax error in table")
        report = provision_dwh(project_id="insight-bolivia", client=mock_bq_client)
        assert not report.is_success
        assert len(report.errors) > 0


class TestMainCli:
    """Pruebas de la interfaz CLI de inicialización."""

    def test_main_dry_run_success(self) -> None:
        exit_code = main(["--dry-run"])
        assert exit_code == 0

    @patch("src.init_dwh.provision_dwh")
    def test_main_failure_returns_1(self, mock_prov: MagicMock) -> None:
        mock_report = ProvisioningReport(project_id="test", errors=["Error fatal"])
        mock_prov.return_value = mock_report
        exit_code = main(["--project-id", "test"])
        assert exit_code == 1
