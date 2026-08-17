"""Módulo de extracción y web scraping resiliente para Comercio Exterior del INE Bolivia.

Proporciona funciones para conectarse dinámicamente al portal del INE,
descargar de forma idempotente bases de datos de Comercio Exterior
(Exportaciones e Importaciones), calcular hashes criptográficos SHA-256
en streaming y orquestar la ingesta de nuevos archivos.
"""

from __future__ import annotations

import hashlib
import logging
import re
import tempfile
import urllib.parse
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constantes del Portal INE y Configuración
# ---------------------------------------------------------------------------
INE_EXPORTACIONES_URL = (
    "https://www.ine.gob.bo/index.php/estadisticas-economicas/comercio-exterior/bases-de-datos-exportaciones/"
)
INE_IMPORTACIONES_URL = (
    "https://www.ine.gob.bo/index.php/estadisticas-economicas/comercio-exterior/importaciones-bases-de-datos/"
)

_DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

_SUPPORTED_EXTENSIONS = {".xlsx", ".xls", ".csv"}
_FILE_EXTENSIONS_PATTERN = re.compile(r"\.(xlsx|xls|csv|dbf|zip|rar)($|\?)", re.IGNORECASE)
_YEAR_PATTERN = re.compile(r"(19\d{2}|20\d{2})")


# ---------------------------------------------------------------------------
# Estructuras de Datos (Dataclasses)
# ---------------------------------------------------------------------------
@dataclass
class ScrapedResource:
    """Recurso de datos identificado en el portal del INE.

    Attributes:
        title: Título o texto descriptivo del enlace en la página.
        url: URL absoluta de descarga del archivo.
        operation_type: Tipo de operación ('exportaciones' o 'importaciones').
        is_dictionary: Indica si el recurso corresponde a un diccionario de variables.
        year: Año / gestión estimada del archivo (si se detecta).
    """

    title: str
    url: str
    operation_type: str
    is_dictionary: bool = False
    year: int | None = None


@dataclass
class ExtractionMetadata:
    """Metadatos resultantes de la extracción y descarga de un recurso.

    Attributes:
        resource: Recurso scrapeado de origen.
        file_path: Ruta local final del archivo descargado (None si no se descargó).
        filename: Nombre de archivo asignado o recibido.
        hash_sha256: Hash SHA-256 del contenido del archivo.
        file_size_bytes: Tamaño del archivo en bytes.
        status: Estado del proceso ('DOWNLOADED', 'SKIPPED_EXISTING', 'FAILED').
        error_message: Mensaje descriptivo en caso de error.
        downloaded_at: Marca temporal ISO 8601 en UTC del momento de la descarga.
    """

    resource: ScrapedResource
    file_path: Path | None = None
    filename: str = ""
    hash_sha256: str = ""
    file_size_bytes: int = 0
    status: str = "DOWNLOADED"
    error_message: str | None = None
    downloaded_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


@dataclass
class ExtractionSummary:
    """Resumen consolidado de una sesión de extracción ETL.

    Attributes:
        total_scraped: Cantidad total de recursos detectados en el scraping.
        downloaded: Lista de recursos descargados exitosamente.
        skipped: Lista de recursos omitidos por ya existir previamente (idempotencia).
        failed: Lista de recursos cuya descarga o procesamiento falló.
    """

    total_scraped: int = 0
    downloaded: list[ExtractionMetadata] = field(default_factory=list)
    skipped: list[ExtractionMetadata] = field(default_factory=list)
    failed: list[ExtractionMetadata] = field(default_factory=list)

    @property
    def total_downloaded(self) -> int:
        """Número de archivos descargados con éxito."""
        return len(self.downloaded)

    @property
    def total_skipped(self) -> int:
        """Número de archivos omitidos por idempotencia."""
        return len(self.skipped)

    @property
    def total_failed(self) -> int:
        """Número de archivos fallidos."""
        return len(self.failed)


# ---------------------------------------------------------------------------
# Clientes HTTP y Hashing
# ---------------------------------------------------------------------------
def create_resilient_session(
    user_agent: str | None = None,
    *,
    max_retries: int = 3,
    backoff_factor: float = 1.0,
) -> requests.Session:
    """Crea una sesión HTTP configurada con reintentos exponenciales y User-Agent real.

    Parameters
    ----------
    user_agent:
        Cabecera User-Agent a utilizar. Si es None, usa el valor por defecto.
    max_retries:
        Número máximo de reintentos ante fallos transitorios.
    backoff_factor:
        Factor multiplicador para el retroceso exponencial entre reintentos.

    Returns
    -------
    requests.Session
        Sesión HTTP configurada con adaptadores de reintento.
    """
    session = requests.Session()
    session.headers.update({"User-Agent": user_agent or _DEFAULT_USER_AGENT})

    retry_strategy = Retry(
        total=max_retries,
        backoff_factor=backoff_factor,
        status_forcelist=[429, 500, 502, 503, 504],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def compute_sha256(filepath: str | Path, *, chunk_size: int = 65536) -> str:
    """Calcula el hash criptográfico SHA-256 de un archivo en streaming.

    Parameters
    ----------
    filepath:
        Ruta al archivo en disco.
    chunk_size:
        Tamaño de bloque en bytes para lectura por fragmentos (por defecto 64 KB).

    Returns
    -------
    str
        Hash SHA-256 en formato hexadecimal en minúsculas.
    """
    path = Path(filepath)
    if not path.is_file():
        msg = f"El archivo no existe o no es un archivo válido: {path}"
        raise FileNotFoundError(msg)

    sha256_hash = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(chunk_size):
            sha256_hash.update(chunk)
    return sha256_hash.hexdigest()


# ---------------------------------------------------------------------------
# Scraping y Detección de Recursos
# ---------------------------------------------------------------------------
def scrape_ine_resources(
    page_url: str,
    *,
    operation_type: str = "exportaciones",
    session: requests.Session | None = None,
    timeout: int = 30,
    exclude_dictionaries: bool = True,
) -> list[ScrapedResource]:
    """Escanea una página web del INE y extrae los enlaces a bases de datos.

    Parameters
    ----------
    page_url:
        URL de la sección de comercio exterior a escanear.
    operation_type:
        Tipo de operación ('exportaciones' o 'importaciones').
    session:
        Sesión de requests a reutilizar. Si es None, se crea una sesión resiliente.
    timeout:
        Timeout en segundos para la petición HTTP.
    exclude_dictionaries:
        Si es True, excluye enlaces de diccionarios de variables.

    Returns
    -------
    list[ScrapedResource]
        Lista de recursos identificados en el portal.
    """
    sess = session or create_resilient_session()
    try:
        response = sess.get(page_url, timeout=timeout)
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.error("Error al obtener la página de recursos de %s: %s", page_url, exc)
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    resources: list[ScrapedResource] = []
    seen_urls: set[str] = set()

    for anchor in soup.find_all("a"):
        href = anchor.get("href")
        if not href or not isinstance(href, str):
            continue

        raw_href = href.strip()
        is_cloud_link = "nube.ine.gob.bo" in raw_href
        is_file_link = bool(_FILE_EXTENSIONS_PATTERN.search(raw_href))

        if not (is_cloud_link or is_file_link):
            continue

        full_url = urllib.parse.urljoin(page_url, raw_href)
        if full_url in seen_urls:
            continue
        seen_urls.add(full_url)

        title = anchor.get_text(strip=True) or Path(urllib.parse.urlparse(full_url).path).name
        is_dict = "DICCIONARIO" in title.upper() or "DICCIONARIO" in full_url.upper()

        if exclude_dictionaries and is_dict:
            continue

        # Intentar extraer el año/gestión
        year_match = _YEAR_PATTERN.search(title) or _YEAR_PATTERN.search(full_url)
        year = int(year_match.group(1)) if year_match else None

        resources.append(
            ScrapedResource(
                title=title,
                url=full_url,
                operation_type=operation_type,
                is_dictionary=is_dict,
                year=year,
            )
        )

    return resources


def _extract_filename_from_response(response: requests.Response, resource: ScrapedResource) -> str:
    """Extrae o infiere el nombre del archivo a partir de los headers o del recurso."""
    cd_header = response.headers.get("Content-Disposition", "")
    if cd_header:
        # Formato standard: attachment; filename="nombre.xlsx" o filename=nombre.xlsx
        match = re.search(r'filename\*?=(?:UTF-8\'\')?["\']?([^";\n]+)["\']?', cd_header, re.IGNORECASE)
        if match:
            raw_name = match.group(1).strip()
            decoded = urllib.parse.unquote(raw_name)
            if decoded:
                return decoded

    # Alternativa: derivar de la URL o del título del recurso
    url_path = urllib.parse.urlparse(resource.url).path
    candidate_name = Path(url_path).name
    if candidate_name and "." in candidate_name and candidate_name.lower() != "download":
        return candidate_name

    # Generar a partir del título
    clean_title = re.sub(r'[\\/*?:"<>|]', "_", resource.title).strip()
    if not clean_title.lower().endswith((".xlsx", ".xls", ".csv", ".dbf")):
        clean_title = f"{clean_title}.xlsx"
    return clean_title


# ---------------------------------------------------------------------------
# Descarga e Idempotencia
# ---------------------------------------------------------------------------
def download_resource(
    resource: ScrapedResource,
    output_dir: str | Path,
    *,
    known_hashes: set[str] | None = None,
    session: requests.Session | None = None,
    timeout: int = 30,
    chunk_size: int = 65536,
) -> ExtractionMetadata:
    """Descarga un recurso del portal del INE con verificación de idempotencia vía SHA-256."""
    dest_dir = Path(output_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)

    sess = session or create_resilient_session()
    hashes_set = known_hashes or set()

    temp_file_path: Path | None = None
    try:
        with sess.get(resource.url, stream=True, timeout=timeout) as response:
            response.raise_for_status()

            filename = _extract_filename_from_response(response, resource)

            # Escribir temporalmente mientras calculamos SHA-256
            with tempfile.NamedTemporaryFile(delete=False, dir=dest_dir) as tmp_file:
                temp_file_path = Path(tmp_file.name)
                sha256_hasher = hashlib.sha256()
                total_bytes = 0

                for chunk in response.iter_content(chunk_size=chunk_size):
                    if chunk:
                        tmp_file.write(chunk)
                        sha256_hasher.update(chunk)
                        total_bytes += len(chunk)

            computed_hash = sha256_hasher.hexdigest()

            # Verificar si ya fue procesado / conocido
            if computed_hash in hashes_set:
                if temp_file_path.exists():
                    temp_file_path.unlink()
                logger.info(
                    "Recurso '%s' (hash: %s) ya existe en registros conocidos. Omitiendo.",
                    filename,
                    computed_hash,
                )
                return ExtractionMetadata(
                    resource=resource,
                    file_path=None,
                    filename=filename,
                    hash_sha256=computed_hash,
                    file_size_bytes=total_bytes,
                    status="SKIPPED_EXISTING",
                )

            # Mover archivo temporal al nombre final
            final_path = dest_dir / filename
            if final_path.exists():
                final_path.unlink()
            temp_file_path.replace(final_path)

            logger.info("Recurso '%s' descargado exitosamente (%d bytes).", filename, total_bytes)
            return ExtractionMetadata(
                resource=resource,
                file_path=final_path,
                filename=filename,
                hash_sha256=computed_hash,
                file_size_bytes=total_bytes,
                status="DOWNLOADED",
            )

    except Exception as exc:
        if temp_file_path and temp_file_path.exists():
            temp_file_path.unlink()
        logger.error("Error al descargar recurso '%s' desde %s: %s", resource.title, resource.url, exc)
        return ExtractionMetadata(
            resource=resource,
            file_path=None,
            filename=resource.title,
            hash_sha256="",
            file_size_bytes=0,
            status="FAILED",
            error_message=str(exc),
        )


def _collect_existing_disk_hashes(directory: Path) -> set[str]:
    """Calcula los hashes SHA-256 de los archivos existentes en un directorio."""
    hashes: set[str] = set()
    if directory.is_dir():
        for file in directory.glob("*"):
            if file.is_file() and file.suffix.lower() in _SUPPORTED_EXTENSIONS:
                try:
                    hashes.add(compute_sha256(file))
                except Exception as exc:
                    logger.warning("No se pudo calcular hash para archivo existente %s: %s", file, exc)
    return hashes


def extract_comercio_exterior(
    sources: dict[str, str] | None = None,
    *,
    output_base_dir: str | Path | None = None,
    known_hashes: set[str] | list[str] | None = None,
    exclude_dictionaries: bool = True,
    session: requests.Session | None = None,
    timeout: int = 30,
) -> ExtractionSummary:
    """Orquesta la extracción completa de nuevas bases de datos de Comercio Exterior del INE."""
    resolved_sources = sources or {
        "exportaciones": INE_EXPORTACIONES_URL,
        "importaciones": INE_IMPORTACIONES_URL,
    }

    base_dir = Path(output_base_dir) if output_base_dir else Path("data/raw/comercio exterior")
    sess = session or create_resilient_session()

    current_known_hashes: set[str] = set(known_hashes) if known_hashes else set()

    summary = ExtractionSummary()

    for op_type, url in resolved_sources.items():
        op_dir = base_dir / op_type
        op_dir.mkdir(parents=True, exist_ok=True)

        # Si no se proveyeron hashes conocidos iniciales, indexar los de disco local
        if known_hashes is None:
            current_known_hashes.update(_collect_existing_disk_hashes(op_dir))

        scraped = scrape_ine_resources(
            url,
            operation_type=op_type,
            session=sess,
            timeout=timeout,
            exclude_dictionaries=exclude_dictionaries,
        )
        summary.total_scraped += len(scraped)

        for resource in scraped:
            result = download_resource(
                resource,
                output_dir=op_dir,
                known_hashes=current_known_hashes,
                session=sess,
                timeout=timeout,
            )

            if result.status == "DOWNLOADED":
                summary.downloaded.append(result)
                if result.hash_sha256:
                    current_known_hashes.add(result.hash_sha256)
            elif result.status == "SKIPPED_EXISTING":
                summary.skipped.append(result)
            else:
                summary.failed.append(result)

    return summary
