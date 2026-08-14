"""Pruebas unitarias para los scripts DDL de BigQuery.

Valida:
- Existencia y lectura de sql/ddl/00_create_datasets.sql.
- Definición formal de los 4 datasets principales (staging, comercio_exterior, benchmark_regional, operations).
- Política de retención de 180 días en staging y persistencia indefinida en comercio_exterior.
- Inclusión de comandos de aprovisionamiento bq mk y configuración de alerta $0 USD de Google Cloud Billing.
"""

from __future__ import annotations

from pathlib import Path


class TestCreateDatasetsDDL:
    """Verifica la sintaxis, contenido y políticas en 00_create_datasets.sql."""

    @property
    def ddl_path(self) -> Path:
        candidates = [
            Path.cwd() / "sql" / "ddl" / "00_create_datasets.sql",
            Path.cwd() / "insight-bolivia" / "sql" / "ddl" / "00_create_datasets.sql",
            Path(__file__).resolve().parent.parent / "sql" / "ddl" / "00_create_datasets.sql",
        ]
        for p in candidates:
            if p.exists():
                return p.resolve()
        raise FileNotFoundError("No se encontró sql/ddl/00_create_datasets.sql")

    def test_ddl_file_exists_and_is_not_empty(self) -> None:
        path = self.ddl_path
        assert path.exists()
        assert path.is_file()
        assert path.stat().st_size > 500

    def test_ddl_defines_all_four_datasets(self) -> None:
        content = self.ddl_path.read_text(encoding="utf-8")
        expected_datasets = [
            "`insight-bolivia.staging`",
            "`insight-bolivia.comercio_exterior`",
            "`insight-bolivia.benchmark_regional`",
            "`insight-bolivia.operations`",
        ]
        for ds in expected_datasets:
            assert f"CREATE SCHEMA IF NOT EXISTS {ds}" in content, (
                f"Falta la sentencia CREATE SCHEMA para {ds}"
            )

    def test_staging_dataset_has_180_days_retention(self) -> None:
        content = self.ddl_path.read_text(encoding="utf-8")
        assert "default_table_expiration_days = 180" in content
        assert "default_partition_expiration_days = 180" in content

    def test_comercio_exterior_has_no_expiration(self) -> None:
        content = self.ddl_path.read_text(encoding="utf-8")
        # Localizar el bloque del dataset comercio_exterior
        ce_idx = content.find("`insight-bolivia.comercio_exterior`")
        assert ce_idx != -1
        # El bloque de comercio_exterior no debe contener expiration
        next_schema_idx = content.find("`insight-bolivia.benchmark_regional`")
        ce_block = content[ce_idx:next_schema_idx]
        assert "default_table_expiration_days" not in ce_block
        assert "default_partition_expiration_days" not in ce_block

    def test_ddl_includes_bq_cli_commands(self) -> None:
        content = self.ddl_path.read_text(encoding="utf-8")
        assert "bq --location=US mk --dataset" in content
        assert "insight-bolivia:staging" in content
        assert "insight-bolivia:comercio_exterior" in content
        assert "insight-bolivia:benchmark_regional" in content
        assert "insight-bolivia:operations" in content
        assert "--default_table_expiration=15552000" in content

    def test_ddl_includes_billing_budget_alert_instructions(self) -> None:
        content = self.ddl_path.read_text(encoding="utf-8")
        assert "gcloud billing budgets create" in content
        assert "Alerta Presupuesto $0 USD" in content
        assert "Always Free Tier" in content
