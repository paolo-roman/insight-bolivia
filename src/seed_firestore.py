"""Módulo de inicialización y carga de datos semilla a Google Cloud Firestore.

Puebla la colección operacional `dwh_catalog` con los metadatos de los Data Warehouses
y vistas analíticas predefinidas en BigQuery de forma estrictamente idempotente
utilizando `set(..., merge=True)`.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from google.cloud import firestore

from src.firestore_models import DwhCatalog

if TYPE_CHECKING:
    from collections.abc import Sequence

# Configuración de logging estándar
logger = logging.getLogger("insight_bolivia.seed_firestore")

# Rutas y constantes predeterminadas
DEFAULT_SEED_FILE = Path(__file__).resolve().parent.parent / "firestore" / "seeds" / "seed_catalog.json"
COLLECTION_NAME = "dwh_catalog"


def load_seed_catalog(file_path: Path | str | None = None) -> list[DwhCatalog]:
    """Carga y valida el archivo JSON de datos semilla del catálogo.

    Parameters
    ----------
    file_path:
        Ruta al archivo JSON. Si no se especifica, usa ``DEFAULT_SEED_FILE``.

    Returns
    -------
    list[DwhCatalog]
        Lista de instancias de ``DwhCatalog`` validadas con Pydantic.

    Raises
    ------
    FileNotFoundError
        Si el archivo de datos semilla no existe.
    ValueError
        Si el archivo no contiene una lista JSON o si falla la validación de esquemas.
    """
    path = Path(file_path) if file_path is not None else DEFAULT_SEED_FILE

    if not path.is_file():
        raise FileNotFoundError(f"No se encontró el archivo de datos semilla en: '{path}'")

    try:
        raw_text = path.read_text(encoding="utf-8")
        data = json.loads(raw_text)
    except json.JSONDecodeError as err:
        raise ValueError(f"Error de sintaxis JSON en el archivo semilla '{path}': {err}") from err

    if not isinstance(data, list):
        raise ValueError(
            f"El archivo semilla '{path}' debe contener una lista de Data Warehouses, "
            f"se obtuvo un tipo '{type(data).__name__}'."
        )

    catalog_items: list[DwhCatalog] = []
    for idx, item_data in enumerate(data):
        if not isinstance(item_data, dict):
            raise ValueError(f"El elemento en el índice {idx} del archivo semilla no es un objeto JSON.")
        model = DwhCatalog.model_validate(item_data)
        catalog_items.append(model)

    return catalog_items


def get_firestore_client(
    database: str | None = None,
    project: str | None = None,
) -> firestore.Client:
    """Inicializa y retorna una instancia del cliente de Google Cloud Firestore.

    Parameters
    ----------
    database:
        Nombre de la base de datos de Firestore. Si es None, busca en ``FIRESTORE_DATABASE``
        o usa ``(default)``.
    project:
        ID del proyecto de GCP. Si es None, busca en ``GOOGLE_CLOUD_PROJECT``,
        ``GCP_PROJECT_ID`` o credenciales implícitas de ADC.

    Returns
    -------
    firestore.Client
        Cliente autenticado de Google Cloud Firestore.
    """
    resolved_db = database or os.getenv("FIRESTORE_DATABASE") or "(default)"
    resolved_project = project or os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GCP_PROJECT_ID")

    client_kwargs: dict[str, str] = {"database": resolved_db}
    if resolved_project:
        client_kwargs["project"] = resolved_project

    return firestore.Client(**client_kwargs)


def seed_dwh_catalog(
    client: firestore.Client | None = None,
    catalog_items: list[DwhCatalog] | None = None,
    file_path: Path | str | None = None,
    database: str | None = None,
    project: str | None = None,
    dry_run: bool = False,
) -> list[str]:
    """Carga de forma idempotente los Data Warehouses semilla a la colección `dwh_catalog`.

    Parameters
    ----------
    client:
        Cliente de Firestore. Si no se provee y ``dry_run`` es False, se inicializa automáticamente.
    catalog_items:
        Lista pre-cargada de objetos ``DwhCatalog``. Si no se provee, se cargan desde ``file_path``.
    file_path:
        Ruta personalizada al archivo de semillas si ``catalog_items`` es None.
    database:
        Nombre de la base de datos Firestore si se inicializa el cliente automáticamente.
    project:
        ID del proyecto GCP si se inicializa el cliente automáticamente.
    dry_run:
        Si es True, realiza la validación de los datos sin persistir en Firestore.

    Returns
    -------
    list[str]
        Lista de IDs de documentos creados o actualizados.
    """
    items = catalog_items if catalog_items is not None else load_seed_catalog(file_path=file_path)
    seeded_doc_ids: list[str] = []

    if dry_run:
        for item in items:
            doc_id = item.id or item.code
            logger.info("[DRY-RUN] Validado DWH '%s' (%s) con %d vistas.", item.name, doc_id, len(item.views))
            seeded_doc_ids.append(doc_id)
        logger.info("[DRY-RUN] Validación completada. %d catálogo(s) listos para ingesta.", len(seeded_doc_ids))
        return seeded_doc_ids

    db_client = client if client is not None else get_firestore_client(database=database, project=project)

    collection_ref = db_client.collection(COLLECTION_NAME)

    for item in items:
        doc_id = item.id or item.code
        payload = item.to_firestore_dict(exclude_none=False)

        # Ingesta idempotente: set con merge=True previene sobreescrituras destructivas
        doc_ref = collection_ref.document(doc_id)
        doc_ref.set(payload, merge=True)

        logger.info(
            "Cargado DWH '%s' [ID: %s] con %d vistas en colección '%s'.",
            item.name,
            doc_id,
            len(item.views),
            COLLECTION_NAME,
        )
        seeded_doc_ids.append(doc_id)

    logger.info("Ingesta de semillas completada exitosamente. Total documentos: %d.", len(seeded_doc_ids))
    return seeded_doc_ids


def main(argv: Sequence[str] | None = None) -> int:
    """Punto de entrada de línea de comandos (CLI) para inicializar datos semilla."""
    parser = argparse.ArgumentParser(
        description="Script de carga e inicialización de datos semilla en Google Cloud Firestore."
    )
    parser.add_argument(
        "-f",
        "--file",
        type=str,
        default=None,
        help="Ruta al archivo JSON de semillas (por defecto: firestore/seeds/seed_catalog.json).",
    )
    parser.add_argument(
        "-d",
        "--database",
        type=str,
        default=None,
        help="Nombre de la base de datos Firestore (por defecto: variable FIRESTORE_DATABASE o '(default)').",
    )
    parser.add_argument(
        "-p",
        "--project",
        type=str,
        default=None,
        help="ID del proyecto GCP (por defecto: GOOGLE_CLOUD_PROJECT o ADC).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Ejecuta en modo simulación: valida los datos sin escribir en Firestore.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Habilita nivel de log detallado (DEBUG).",
    )

    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    try:
        seeded = seed_dwh_catalog(
            file_path=args.file,
            database=args.database,
            project=args.project,
            dry_run=args.dry_run,
        )
        logger.info("Proceso finalizado con éxito. Documentos procesados: %s", seeded)
        return 0
    except Exception as err:
        logger.error("Error durante la carga de datos semilla en Firestore: %s", err, exc_info=args.verbose)
        return 1


if __name__ == "__main__":
    sys.exit(main())
