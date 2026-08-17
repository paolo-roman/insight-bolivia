"""Pruebas unitarias para los scripts DDL de BigQuery.

Valida:
- Existencia y lectura de sql/ddl/00_create_datasets.sql.
- Definición formal de los 4 datasets principales (staging, comercio_exterior, benchmark_regional, operations).
- Política de retención de 180 días en staging y persistencia indefinida en comercio_exterior.
- Inclusión de comandos de aprovisionamiento bq mk y configuración de alerta $0 USD de Google Cloud Billing.
- Existencia, sintaxis y estructura de los 9 scripts DDL del Modelo en Estrella (TICK-EP3-002):
  1. create_stg_comercio_exterior.sql
  2. create_dim_producto.sql
  3. create_dim_pais.sql
  4. create_dim_tiempo.sql
  5. create_dim_departamento.sql
  6. create_dim_via_transporte.sql
  7. create_dim_aduana.sql
  8. create_dim_moneda.sql
  9. create_fact_comercio_exterior.sql
"""

from __future__ import annotations

from pathlib import Path

import pytest


def get_ddl_file(filename: str) -> Path:
    """Helper para resolver la ruta absoluta de un archivo DDL."""
    candidates = [
        Path.cwd() / "sql" / "ddl" / filename,
        Path.cwd() / "insight-bolivia" / "sql" / "ddl" / filename,
        Path(__file__).resolve().parent.parent / "sql" / "ddl" / filename,
    ]
    for p in candidates:
        if p.exists():
            return p.resolve()
    raise FileNotFoundError(f"No se encontró sql/ddl/{filename}")


class TestCreateDatasetsDDL:
    """Verifica la sintaxis, contenido y políticas en 00_create_datasets.sql."""

    @property
    def ddl_path(self) -> Path:
        return get_ddl_file("00_create_datasets.sql")

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
        ce_idx = content.find("`insight-bolivia.comercio_exterior`")
        assert ce_idx != -1
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


class TestStarSchemaDDLFilesExist:
    """Verifica la existencia y tamaño mínimo de los 9 scripts DDL del modelo en estrella."""

    EXPECTED_FILES = [
        "create_stg_comercio_exterior.sql",
        "create_dim_producto.sql",
        "create_dim_pais.sql",
        "create_dim_tiempo.sql",
        "create_dim_departamento.sql",
        "create_dim_via_transporte.sql",
        "create_dim_aduana.sql",
        "create_dim_moneda.sql",
        "create_fact_comercio_exterior.sql",
    ]

    @pytest.mark.parametrize("filename", EXPECTED_FILES)
    def test_ddl_file_exists_and_is_not_empty(self, filename: str) -> None:
        path = get_ddl_file(filename)
        assert path.exists(), f"El archivo {filename} no existe."
        assert path.is_file(), f"{filename} no es un archivo regular."
        assert path.stat().st_size > 200, f"{filename} es demasiado pequeño o está vacío."


class TestStgComercioExteriorDDL:
    """Verifica la definición de stg_comercio_exterior en el dataset staging."""

    @pytest.fixture
    def content(self) -> str:
        return get_ddl_file("create_stg_comercio_exterior.sql").read_text(encoding="utf-8")

    def test_table_declaration(self, content: str) -> None:
        expected = "CREATE TABLE IF NOT EXISTS `insight-bolivia.staging.stg_comercio_exterior`"
        assert expected in content

    def test_monthly_partitioning(self, content: str) -> None:
        assert "PARTITION BY DATE_TRUNC(fecha, MONTH)" in content

    def test_contains_canonical_and_business_columns(self, content: str) -> None:
        expected_columns = [
            "gestion INT64",
            "mes INT64",
            "fecha DATE",
            "flujo_codigo INT64",
            "flujo_desc STRING",
            "tipo_operacion STRING",
            "codigo_nandina STRING",
            "codigo_pais_ine INT64",
            "valor_fob_usd NUMERIC",
            "valor_cif_frontera_usd NUMERIC",
            "valor_cif_frontera_bob NUMERIC",
            "valor_gravamenes_bob NUMERIC",
            "peso_bruto_kg NUMERIC",
            "peso_neto_kg NUMERIC",
            "contenido_fino NUMERIC",
            "hash_sha256 STRING",
            "fecha_ingesta TIMESTAMP",
        ]
        for col in expected_columns:
            assert col in content, f"Columna esperada '{col}' no encontrada en stg_comercio_exterior."


class TestDimProductoDDL:
    """Verifica la definición de dim_producto y soporte para SCD Tipo 2."""

    @pytest.fixture
    def content(self) -> str:
        return get_ddl_file("create_dim_producto.sql").read_text(encoding="utf-8")

    def test_table_declaration(self, content: str) -> None:
        expected = "CREATE TABLE IF NOT EXISTS `insight-bolivia.comercio_exterior.dim_producto`"
        assert expected in content

    def test_clustering(self, content: str) -> None:
        assert "CLUSTER BY codigo_nandina" in content

    def test_scd_type_2_columns(self, content: str) -> None:
        assert "vigente_desde DATE NOT NULL" in content
        assert "vigente_hasta DATE" in content
        assert "es_vigente BOOL NOT NULL" in content

    def test_nandina_hierarchy_columns(self, content: str) -> None:
        assert "codigo_nandina STRING NOT NULL" in content
        assert "descripcion_producto STRING" in content
        assert "partida_nandina STRING" in content
        assert "capitulo_nandina STRING" in content
        assert "seccion_nandina STRING" in content
        assert "sector_economico STRING" in content


class TestDimPaisDDL:
    """Verifica la definición de dim_pais y mapeo INE a ISO."""

    @pytest.fixture
    def content(self) -> str:
        return get_ddl_file("create_dim_pais.sql").read_text(encoding="utf-8")

    def test_table_declaration(self, content: str) -> None:
        expected = "CREATE TABLE IF NOT EXISTS `insight-bolivia.comercio_exterior.dim_pais`"
        assert expected in content

    def test_clustering(self, content: str) -> None:
        assert "CLUSTER BY pais_iso" in content

    def test_country_mapping_columns(self, content: str) -> None:
        assert "pais_iso STRING NOT NULL" in content
        assert "codigo_pais_ine INT64" in content
        assert "nombre_pais_es STRING" in content
        assert "continente STRING" in content
        assert "subregion STRING" in content
        assert "bloque_comercial STRING" in content


class TestDimTiempoDDL:
    """Verifica la definición de dim_tiempo estática."""

    @pytest.fixture
    def content(self) -> str:
        return get_ddl_file("create_dim_tiempo.sql").read_text(encoding="utf-8")

    def test_table_declaration(self, content: str) -> None:
        expected = "CREATE TABLE IF NOT EXISTS `insight-bolivia.comercio_exterior.dim_tiempo`"
        assert expected in content

    def test_clustering(self, content: str) -> None:
        assert "CLUSTER BY fecha" in content

    def test_temporal_attributes(self, content: str) -> None:
        assert "fecha DATE NOT NULL" in content
        assert "anio INT64 NOT NULL" in content
        assert "mes INT64 NOT NULL" in content
        assert "trimestre INT64 NOT NULL" in content
        assert "semestre INT64 NOT NULL" in content
        assert "nombre_mes STRING NOT NULL" in content
        assert "es_fin_de_anio BOOL NOT NULL" in content


class TestDimDepartamentoDDL:
    """Verifica la definición de dim_departamento_origen_destino."""

    @pytest.fixture
    def content(self) -> str:
        return get_ddl_file("create_dim_departamento.sql").read_text(encoding="utf-8")

    def test_table_declaration(self, content: str) -> None:
        expected = (
            "CREATE TABLE IF NOT EXISTS "
            "`insight-bolivia.comercio_exterior.dim_departamento_origen_destino`"
        )
        assert expected in content

    def test_clustering(self, content: str) -> None:
        assert "CLUSTER BY id_departamento" in content

    def test_department_columns(self, content: str) -> None:
        assert "id_departamento INT64 NOT NULL" in content
        assert "codigo_departamento STRING" in content
        assert "nombre_departamento STRING NOT NULL" in content
        assert "region_geografica STRING" in content


class TestDimViaTransporteDDL:
    """Verifica la definición de dim_via_transporte."""

    @pytest.fixture
    def content(self) -> str:
        return get_ddl_file("create_dim_via_transporte.sql").read_text(encoding="utf-8")

    def test_table_declaration(self, content: str) -> None:
        expected = "CREATE TABLE IF NOT EXISTS `insight-bolivia.comercio_exterior.dim_via_transporte`"
        assert expected in content

    def test_clustering(self, content: str) -> None:
        assert "CLUSTER BY id_via_transporte" in content

    def test_columns(self, content: str) -> None:
        assert "id_via_transporte INT64 NOT NULL" in content
        assert "codigo_via INT64" in content
        assert "descripcion STRING NOT NULL" in content
        assert "medio_transporte STRING" in content


class TestDimAduanaDDL:
    """Verifica la definición de dim_aduana con SCD Tipo 2."""

    @pytest.fixture
    def content(self) -> str:
        return get_ddl_file("create_dim_aduana.sql").read_text(encoding="utf-8")

    def test_table_declaration(self, content: str) -> None:
        expected = "CREATE TABLE IF NOT EXISTS `insight-bolivia.comercio_exterior.dim_aduana`"
        assert expected in content

    def test_scd_type_2(self, content: str) -> None:
        assert "vigente_desde DATE NOT NULL" in content
        assert "vigente_hasta DATE" in content
        assert "es_vigente BOOL NOT NULL" in content

    def test_customs_columns(self, content: str) -> None:
        assert "id_aduana INT64 NOT NULL" in content
        assert "codigo_aduana INT64" in content
        assert "nombre_aduana STRING NOT NULL" in content
        assert "ciudad STRING" in content
        assert "departamento STRING" in content
        assert "tipo STRING" in content


class TestDimMonedaDDL:
    """Verifica la definición de dim_moneda con SCD Tipo 2."""

    @pytest.fixture
    def content(self) -> str:
        return get_ddl_file("create_dim_moneda.sql").read_text(encoding="utf-8")

    def test_table_declaration(self, content: str) -> None:
        expected = "CREATE TABLE IF NOT EXISTS `insight-bolivia.comercio_exterior.dim_moneda`"
        assert expected in content

    def test_scd_type_2(self, content: str) -> None:
        assert "vigente_desde DATE NOT NULL" in content
        assert "vigente_hasta DATE" in content
        assert "es_vigente BOOL NOT NULL" in content

    def test_currency_columns(self, content: str) -> None:
        assert "codigo_moneda STRING NOT NULL" in content
        assert "nombre_moneda STRING NOT NULL" in content
        assert "tipo_cambio_a_usd NUMERIC NOT NULL" in content
        assert "fecha_tipo_cambio DATE NOT NULL" in content


class TestFactComercioExteriorDDL:
    """Verifica la tabla de hechos fact_comercio_exterior."""

    @pytest.fixture
    def content(self) -> str:
        return get_ddl_file("create_fact_comercio_exterior.sql").read_text(encoding="utf-8")

    def test_table_declaration(self, content: str) -> None:
        expected = "CREATE TABLE IF NOT EXISTS `insight-bolivia.comercio_exterior.fact_comercio_exterior`"
        assert expected in content

    def test_partitioning_and_clustering(self, content: str) -> None:
        assert "PARTITION BY DATE_TRUNC(fecha, MONTH)" in content
        assert "CLUSTER BY codigo_nandina, pais_iso" in content

    def test_keys_and_metrics(self, content: str) -> None:
        expected_elements = [
            "id_transaccion INT64 NOT NULL",
            "fecha DATE NOT NULL",
            "codigo_nandina STRING NOT NULL",
            "pais_iso STRING NOT NULL",
            "id_departamento INT64",
            "id_via_transporte INT64",
            "id_aduana INT64",
            "tipo_operacion STRING NOT NULL",
            "valor_fob_usd NUMERIC",
            "valor_cif_usd NUMERIC",
            "valor_fob_bob NUMERIC",
            "peso_neto_kg NUMERIC",
            "peso_bruto_kg NUMERIC",
            "contenido_fino NUMERIC",
            "anio INT64 NOT NULL",
            "mes INT64 NOT NULL",
            "trimestre INT64 NOT NULL",
        ]
        for element in expected_elements:
            assert element in content, f"Elemento '{element}' no encontrado en fact_comercio_exterior."
