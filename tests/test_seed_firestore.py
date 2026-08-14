"""Pruebas unitarias para la carga de datos semilla a Google Cloud Firestore.

Valida:
1. Existencia, sintaxis y conformidad del archivo `firestore/seeds/seed_catalog.json`.
2. Función de carga y validación de esquemas `load_seed_catalog`.
3. Inicialización del cliente de Firestore `get_firestore_client`.
4. Ingesta idempotente con `merge=True` en `seed_dwh_catalog`.
5. Ejecución del CLI `main()` y manejo de errores.
"""

from __future__ import annotations

import json
import runpy
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from src import seed_firestore
from src.firestore_models import CatalogView, DwhCatalog
from src.seed_firestore import (
    COLLECTION_NAME,
    DEFAULT_SEED_FILE,
    get_firestore_client,
    load_seed_catalog,
    main,
    seed_dwh_catalog,
)


# ==============================================================================
# 1. Pruebas del Archivo Semilla (seed_catalog.json)
# ==============================================================================
class TestSeedCatalogJsonFile:
    """Verifica la integridad del archivo seed_catalog.json."""

    @pytest.fixture
    def seed_file_path(self) -> Path:
        """Retorna la ruta al archivo seed_catalog.json."""
        project_root = Path(__file__).resolve().parent.parent
        return project_root / "firestore" / "seeds" / "seed_catalog.json"

    def test_seed_file_exists(self, seed_file_path: Path) -> None:
        """Verifica que el archivo exista en la ruta esperada."""
        assert seed_file_path.is_file(), f"No se encontró el archivo {seed_file_path}"
        assert DEFAULT_SEED_FILE.resolve() == seed_file_path.resolve()

    def test_seed_file_is_valid_json(self, seed_file_path: Path) -> None:
        """Verifica que el contenido sea JSON sintácticamente válido."""
        content = seed_file_path.read_text(encoding="utf-8")
        data = json.loads(content)
        assert isinstance(data, list), "El archivo semilla debe ser una lista JSON."
        assert len(data) >= 1, "Debe contener al menos un Data Warehouse registrado."

    def test_seed_file_contains_comercio_exterior(self, seed_file_path: Path) -> None:
        """Verifica que el Data Warehouse de Comercio Exterior esté correctamente configurado."""
        data = json.loads(seed_file_path.read_text(encoding="utf-8"))
        comercio = next((dwh for dwh in data if dwh.get("code") == "comercio_exterior"), None)
        assert comercio is not None, "Falta el Data Warehouse 'comercio_exterior'."
        assert comercio["id"] == "comercio_exterior"
        assert comercio["name"] == "Comercio Exterior de Bolivia"
        assert comercio["bq_dataset"] == "comercio_exterior"
        assert comercio["bq_project"] == "insight-bolivia"
        assert comercio["status"] == "active"
        assert comercio["data_source"] == "INE - Instituto Nacional de Estadística"
        assert comercio["update_frequency"] == "mensual"
        assert comercio["last_data_refresh"] is None
        assert comercio["record_count"] == 0

    def test_seed_file_contains_3_analytics_views(self, seed_file_path: Path) -> None:
        """Verifica que las 3 vistas analíticas de BigQuery estén registradas."""
        data = json.loads(seed_file_path.read_text(encoding="utf-8"))
        comercio = next(dwh for dwh in data if dwh.get("code") == "comercio_exterior")
        views = comercio.get("views", [])
        assert len(views) == 3, f"Se esperaban 3 vistas analíticas, se encontraron {len(views)}."

        expected_views = {
            "vw_balanza_comercial_mensual": {
                "display_name": "Balanza Comercial Mensual",
                "chart_type": "line",
                "sort_order": 1,
            },
            "vw_top_productos_exportados": {
                "display_name": "Top 10 Productos Exportados",
                "chart_type": "bar",
                "sort_order": 2,
            },
            "vw_socios_comerciales": {
                "display_name": "Principales Socios Comerciales",
                "chart_type": "choropleth",
                "sort_order": 3,
            },
        }

        for view in views:
            v_name = view["view_name"]
            assert v_name in expected_views, f"Vista inesperada: {v_name}"
            exp = expected_views[v_name]
            assert view["display_name"] == exp["display_name"]
            assert view["chart_type"] == exp["chart_type"]
            assert view["sort_order"] == exp["sort_order"]
            assert view["is_public"] is True

    def test_seed_file_validates_against_pydantic_model(self, seed_file_path: Path) -> None:
        """Verifica que todos los elementos cumplan el modelo DwhCatalog."""
        data = json.loads(seed_file_path.read_text(encoding="utf-8"))
        for item in data:
            catalog = DwhCatalog.model_validate(item)
            assert isinstance(catalog, DwhCatalog)
            assert catalog.code == "comercio_exterior"
            assert len(catalog.views) == 3


# ==============================================================================
# 2. Pruebas de la Función load_seed_catalog
# ==============================================================================
class TestLoadSeedCatalog:
    """Pruebas para la función load_seed_catalog."""

    def test_load_default_seed_catalog(self) -> None:
        """Carga exitosa del archivo por defecto."""
        items = load_seed_catalog()
        assert isinstance(items, list)
        assert len(items) >= 1
        assert isinstance(items[0], DwhCatalog)
        assert items[0].code == "comercio_exterior"

    def test_load_custom_valid_file(self, tmp_path: Path) -> None:
        """Carga exitosa desde un archivo personalizado válido."""
        custom_data = [
            {
                "code": "benchmark_regional",
                "name": "Benchmark Regional",
                "description": "Indicadores económicos regionales.",
                "bq_dataset": "benchmark_regional",
                "data_source": "Banco Mundial",
                "views": [
                    {
                        "view_name": "vw_comparativa_pib",
                        "display_name": "Comparativa PIB",
                        "bq_view_path": "benchmark_regional.vw_comparativa_pib",
                    }
                ],
            }
        ]
        test_file = tmp_path / "custom_seed.json"
        test_file.write_text(json.dumps(custom_data), encoding="utf-8")

        items = load_seed_catalog(test_file)
        assert len(items) == 1
        assert items[0].code == "benchmark_regional"
        assert len(items[0].views) == 1
        assert items[0].views[0].view_name == "vw_comparativa_pib"

    def test_load_non_existent_file_raises_file_not_found(self, tmp_path: Path) -> None:
        """Lanza FileNotFoundError si el archivo no existe."""
        non_existent = tmp_path / "does_not_exist.json"
        with pytest.raises(FileNotFoundError, match="No se encontró el archivo de datos semilla"):
            load_seed_catalog(non_existent)

    def test_load_invalid_json_syntax_raises_value_error(self, tmp_path: Path) -> None:
        """Lanza ValueError si el archivo tiene errores de sintaxis JSON."""
        bad_json_file = tmp_path / "bad_syntax.json"
        bad_json_file.write_text("{ unclosed invalid json", encoding="utf-8")
        with pytest.raises(ValueError, match="Error de sintaxis JSON"):
            load_seed_catalog(bad_json_file)

    def test_load_non_list_root_raises_value_error(self, tmp_path: Path) -> None:
        """Lanza ValueError si la raíz del JSON es un diccionario en lugar de lista."""
        dict_json_file = tmp_path / "dict_root.json"
        dict_json_file.write_text('{"code": "comercio_exterior"}', encoding="utf-8")
        with pytest.raises(ValueError, match="debe contener una lista de Data Warehouses"):
            load_seed_catalog(dict_json_file)

    def test_load_invalid_item_type_raises_value_error(self, tmp_path: Path) -> None:
        """Lanza ValueError si un elemento de la lista no es un diccionario."""
        invalid_item_file = tmp_path / "invalid_item.json"
        invalid_item_file.write_text('["not_a_dict_item"]', encoding="utf-8")
        with pytest.raises(ValueError, match="no es un objeto JSON"):
            load_seed_catalog(invalid_item_file)

    def test_load_invalid_schema_raises_validation_error(self, tmp_path: Path) -> None:
        """Lanza ValidationError si faltan campos obligatorios del modelo."""
        incomplete_item_file = tmp_path / "incomplete.json"
        incomplete_item_file.write_text('[{"code": "incomplete_dwh"}]', encoding="utf-8")
        with pytest.raises(ValidationError):
            load_seed_catalog(incomplete_item_file)


# ==============================================================================
# 3. Pruebas de Inicialización del Cliente Firestore (get_firestore_client)
# ==============================================================================
class TestGetFirestoreClient:
    """Pruebas para get_firestore_client."""

    @patch("src.seed_firestore.firestore.Client")
    def test_get_firestore_client_default_env(self, mock_client_cls: MagicMock) -> None:
        """Verifica la creación del cliente con valores por defecto."""
        with patch.dict("os.environ", {}, clear=True):
            client = get_firestore_client()
            assert client is not None
            mock_client_cls.assert_called_once_with(database="(default)")

    @patch("src.seed_firestore.firestore.Client")
    def test_get_firestore_client_with_custom_env(self, mock_client_cls: MagicMock) -> None:
        """Verifica la lectura de variables de entorno FIRESTORE_DATABASE y GOOGLE_CLOUD_PROJECT."""
        env_vars = {
            "FIRESTORE_DATABASE": "insight-db",
            "GOOGLE_CLOUD_PROJECT": "insight-bolivia",
        }
        with patch.dict("os.environ", env_vars, clear=True):
            client = get_firestore_client()
            assert client is not None
            mock_client_cls.assert_called_once_with(database="insight-db", project="insight-bolivia")

    @patch("src.seed_firestore.firestore.Client")
    def test_get_firestore_client_with_explicit_args(self, mock_client_cls: MagicMock) -> None:
        """Verifica la precedencia de argumentos explícitos."""
        env_vars = {
            "FIRESTORE_DATABASE": "env-db",
            "GOOGLE_CLOUD_PROJECT": "env-proj",
        }
        with patch.dict("os.environ", env_vars, clear=True):
            client = get_firestore_client(database="explicit-db", project="explicit-proj")
            assert client is not None
            mock_client_cls.assert_called_once_with(database="explicit-db", project="explicit-proj")


# ==============================================================================
# 4. Pruebas de Ingesta Idempotente (seed_dwh_catalog)
# ==============================================================================
class TestSeedDwhCatalog:
    """Pruebas para la función principal seed_dwh_catalog."""

    @pytest.fixture
    def sample_catalog_item(self) -> DwhCatalog:
        """Retorna un objeto DwhCatalog de prueba."""
        return DwhCatalog(
            id="comercio_exterior",
            code="comercio_exterior",
            name="Comercio Exterior de Bolivia",
            description="Datos del INE.",
            bq_dataset="comercio_exterior",
            bq_project="insight-bolivia",
            data_source="INE",
            views=[
                CatalogView(
                    view_name="vw_balanza_comercial_mensual",
                    display_name="Balanza Comercial Mensual",
                    bq_view_path="comercio_exterior.vw_balanza_comercial_mensual",
                )
            ],
        )

    def test_seed_dwh_catalog_with_mock_client(self, sample_catalog_item: DwhCatalog) -> None:
        """Valida que la ingesta llame a collection('dwh_catalog').document(...).set(..., merge=True)."""
        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_document = MagicMock()

        mock_client.collection.return_value = mock_collection
        mock_collection.document.return_value = mock_document

        result = seed_dwh_catalog(client=mock_client, catalog_items=[sample_catalog_item])

        assert result == ["comercio_exterior"]
        mock_client.collection.assert_called_once_with(COLLECTION_NAME)
        mock_collection.document.assert_called_once_with("comercio_exterior")
        mock_document.set.assert_called_once()

        # Verificar que se utilizó merge=True
        call_kwargs = mock_document.set.call_args.kwargs
        assert call_kwargs.get("merge") is True

    def test_seed_dwh_catalog_idempotency(self, sample_catalog_item: DwhCatalog) -> None:
        """Valida que ejecutar la ingesta múltiples veces no genere duplicados y sea consistente."""
        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_document = MagicMock()

        mock_client.collection.return_value = mock_collection
        mock_collection.document.return_value = mock_document

        # Primera ejecución
        result1 = seed_dwh_catalog(client=mock_client, catalog_items=[sample_catalog_item])
        # Segunda ejecución
        result2 = seed_dwh_catalog(client=mock_client, catalog_items=[sample_catalog_item])

        assert result1 == result2 == ["comercio_exterior"]
        assert mock_document.set.call_count == 2
        for call in mock_document.set.call_args_list:
            assert call.kwargs.get("merge") is True

    @patch("src.seed_firestore.get_firestore_client")
    def test_seed_dwh_catalog_auto_inits_client_when_none(
        self,
        mock_get_client: MagicMock,
        sample_catalog_item: DwhCatalog,
    ) -> None:
        """Valida que inicialice el cliente automáticamente si no se provee."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_collection = MagicMock()
        mock_document = MagicMock()
        mock_client.collection.return_value = mock_collection
        mock_collection.document.return_value = mock_document

        result = seed_dwh_catalog(client=None, catalog_items=[sample_catalog_item], database="test-db")

        assert result == ["comercio_exterior"]
        mock_get_client.assert_called_once_with(database="test-db", project=None)

    def test_seed_dwh_catalog_dry_run_mode(self, sample_catalog_item: DwhCatalog) -> None:
        """Valida que en modo dry_run no se interactúe con Firestore."""
        mock_client = MagicMock()

        result = seed_dwh_catalog(client=mock_client, catalog_items=[sample_catalog_item], dry_run=True)

        assert result == ["comercio_exterior"]
        mock_client.collection.assert_not_called()

    def test_seed_dwh_catalog_uses_default_file_when_no_items_provided(self) -> None:
        """Valida que lea el archivo por defecto si no se pasan catalog_items."""
        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_document = MagicMock()
        mock_client.collection.return_value = mock_collection
        mock_collection.document.return_value = mock_document

        result = seed_dwh_catalog(client=mock_client, catalog_items=None)

        assert "comercio_exterior" in result
        mock_client.collection.assert_called_once_with(COLLECTION_NAME)


# ==============================================================================
# 5. Pruebas del Punto de Entrada CLI (main)
# ==============================================================================
class TestSeedFirestoreCli:
    """Pruebas para el CLI main()."""

    def test_cli_main_dry_run_success(self) -> None:
        """Valida ejecución exitosa de CLI en modo --dry-run."""
        exit_code = main(["--dry-run"])
        assert exit_code == 0

    @patch("src.seed_firestore.seed_dwh_catalog")
    def test_cli_main_with_all_flags(self, mock_seed: MagicMock) -> None:
        """Valida el paso correcto de flags CLI a seed_dwh_catalog."""
        mock_seed.return_value = ["comercio_exterior"]

        exit_code = main(["-f", "custom.json", "-d", "custom-db", "-p", "custom-proj", "--dry-run", "-v"])

        assert exit_code == 0
        mock_seed.assert_called_once_with(
            file_path="custom.json",
            database="custom-db",
            project="custom-proj",
            dry_run=True,
        )

    @patch("src.seed_firestore.seed_dwh_catalog")
    def test_cli_main_exception_returns_error_code(self, mock_seed: MagicMock) -> None:
        """Valida que ante una excepción no controlada el CLI retorne código 1."""
        mock_seed.side_effect = RuntimeError("Firestore connection refused")

        exit_code = main([])
        assert exit_code == 1

    def test_seed_firestore_module_execution(self) -> None:
        """Valida la ejecución del script como módulo principal con __main__."""
        file_path = str(Path(seed_firestore.__file__).resolve())
        with patch("sys.argv", ["seed_firestore.py", "--dry-run"]):
            with pytest.raises(SystemExit) as exc_info:
                runpy.run_path(file_path, run_name="__main__")
            assert exc_info.value.code == 0
