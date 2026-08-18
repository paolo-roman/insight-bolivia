"""Módulo de alertas y notificaciones vía Webhook para InsightBolivia.

Gestiona el envío de notificaciones y alertas operacionales estructuradas (Discord Webhooks)
ante fallos o eventos críticos en la orquestación del pipeline ETL en GitHub Actions y localmente.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import UTC, datetime
from typing import Any

import requests

from src.config import get_settings

logger = logging.getLogger("insight_bolivia.notifications")

# Paleta de colores estándar para Discord Embeds
COLOR_SUCCESS = 0x2ECC71  # Verde
COLOR_FAILURE = 0xE74C3C  # Rojo
COLOR_WARNING = 0xF39C12  # Naranja / Amarillo
COLOR_INFO = 0x3498DB  # Azul


def get_status_color(status: str) -> int:
    """Retorna el código de color hexadecimal según el estado del pipeline."""
    normalized = status.strip().lower()
    if normalized in {"success", "ok", "exitoso", "exito"}:
        return COLOR_SUCCESS
    if normalized in {"warning", "advertencia", "skipped", "omitido"}:
        return COLOR_WARNING
    if normalized in {"failure", "error", "failed", "fallido", "fallo"}:
        return COLOR_FAILURE
    return COLOR_INFO


def build_discord_payload(
    title: str,
    description: str,
    status: str = "failure",
    fields: list[dict[str, Any]] | None = None,
    run_url: str | None = None,
    commit_sha: str | None = None,
    repository: str | None = None,
    workflow: str | None = None,
    error_details: str | None = None,
    custom_color: int | None = None,
) -> dict[str, Any]:
    """Construye un payload JSON estructurado con Discord Embeds.

    Args:
        title: Título principal del mensaje de alerta.
        description: Descripción general o resumen del suceso.
        status: Estado de la ejecución ('failure', 'success', 'warning', 'info').
        fields: Lista opcional de campos adicionales con formato [{'name': ..., 'value': ..., 'inline': bool}].
        run_url: URL directa al log de ejecución en GitHub Actions.
        commit_sha: Hash SHA del commit actual.
        repository: Nombre del repositorio de GitHub (ej: 'org/repo').
        workflow: Nombre del workflow ejecutado.
        error_details: Detalles técnicos adicionales del error.
        custom_color: Código de color hexadecimal opcional para sobreescribir el automático.

    Returns:
        Diccionario con el payload listo para enviar al webhook de Discord.
    """
    color = custom_color if custom_color is not None else get_status_color(status)
    embed_fields: list[dict[str, Any]] = []

    if workflow:
        embed_fields.append({"name": "📋 Workflow", "value": f"`{workflow}`", "inline": True})
    if repository:
        embed_fields.append({"name": "📦 Repositorio", "value": f"`{repository}`", "inline": True})
    if run_url:
        embed_fields.append({"name": "🔗 Run en GitHub", "value": f"[Ver Ejecución]({run_url})", "inline": True})
    if commit_sha:
        short_sha = commit_sha[:7] if len(commit_sha) >= 7 else commit_sha
        embed_fields.append({"name": "🔖 Commit", "value": f"`{short_sha}`", "inline": True})

    if error_details:
        # Limitar longitud para no exceder los límites de campos en Discord (1024 caracteres)
        truncated_error = error_details[:1000] + ("..." if len(error_details) > 1000 else "")
        embed_fields.append(
            {
                "name": "💥 Detalles del Error",
                "value": f"```{truncated_error}```",
                "inline": False,
            }
        )

    if fields:
        embed_fields.extend(fields)

    embed = {
        "title": title,
        "description": description,
        "color": color,
        "fields": embed_fields,
        "footer": {
            "text": "InsightBolivia • Observabilidad y Alertas ETL",
        },
        "timestamp": datetime.now(UTC).isoformat(),
    }

    return {
        "username": "InsightBolivia ETL Monitor",
        "embeds": [embed],
    }


def send_discord_alert(
    webhook_url: str | None = None,
    title: str | None = None,
    description: str | None = None,
    status: str = "failure",
    fields: list[dict[str, Any]] | None = None,
    payload: dict[str, Any] | None = None,
    raise_on_error: bool = False,
    timeout: int = 10,
    session: requests.Session | None = None,
) -> bool:
    """Envía una alerta estructurada a un canal de Discord vía Webhook.

    Args:
        webhook_url: URL del Webhook de Discord. Si es None, busca en .env o config.
        title: Título de la alerta si no se provee payload preconstruido.
        description: Descripción de la alerta.
        status: Estado ('failure', 'success', 'warning', 'info').
        fields: Campos adicionales para el embed.
        payload: Payload JSON preconstruido. Si se omite, se construye automáticamente.
        raise_on_error: Si es True, propaga excepciones HTTP; si es False, las registra en logs.
        timeout: Tiempo máximo de espera en segundos para la petición HTTP.
        session: Instancia opcional de requests.Session para reutilización de conexiones.

    Returns:
        True si el webhook fue entregado exitosamente (HTTP 2xx), False en caso contrario.
    """
    resolved_url = webhook_url
    if not resolved_url:
        resolved_url = os.getenv("DISCORD_WEBHOOK_URL")
    if not resolved_url:
        try:
            settings = get_settings(load_env=True)
            resolved_url = settings.notifications.discord_webhook_url
        except Exception:
            resolved_url = None

    if not resolved_url or not resolved_url.strip():
        logger.warning("No se configuró DISCORD_WEBHOOK_URL. Omitiendo envío de alerta.")
        return False

    final_payload = payload
    if final_payload is None:
        default_title = (
            "🚨 Alerta: Fallo en Pipeline ETL Comercio Exterior"
            if status.lower() in {"failure", "error", "failed"}
            else "ℹ️ Notificación: Evento en Pipeline ETL"
        )
        final_title = title or default_title
        final_description = description or "Se ha registrado un evento operacional en el pipeline ETL."
        final_payload = build_discord_payload(
            title=final_title,
            description=final_description,
            status=status,
            fields=fields,
        )

    http_client = session or requests
    try:
        response = http_client.post(resolved_url.strip(), json=final_payload, timeout=timeout)
        response.raise_for_status()
        logger.info("Alerta de Discord entregada exitosamente (HTTP %s).", response.status_code)
        return True
    except requests.RequestException as exc:
        logger.error("Error al enviar alerta a Discord Webhook: %s", exc)
        if raise_on_error:
            raise
        return False


def send_github_actions_alert(
    status: str = "failure",
    error_message: str | None = None,
    webhook_url: str | None = None,
    raise_on_error: bool = False,
    timeout: int = 10,
    session: requests.Session | None = None,
) -> bool:
    """Recopila metadatos del entorno de GitHub Actions y despacha la alerta de Discord."""
    repository = os.getenv("GITHUB_REPOSITORY", "insightbolivia/insight-bolivia")
    run_id = os.getenv("GITHUB_RUN_ID")
    server_url = os.getenv("GITHUB_SERVER_URL", "https://github.com")
    workflow = os.getenv("GITHUB_WORKFLOW", "ETL - Ingestión Diaria de Comercio Exterior")
    job_name = os.getenv("GITHUB_JOB", "run-etl")
    event_name = os.getenv("GITHUB_EVENT_NAME", "schedule")
    commit_sha = os.getenv("GITHUB_SHA", "")
    ref_name = os.getenv("GITHUB_REF_NAME", "main")

    run_url = f"{server_url}/{repository}/actions/runs/{run_id}" if run_id else None

    is_failure = status.lower() in {"failure", "error", "failed"}
    title = (
        f"🚨 Fallo en Workflow: {workflow}"
        if is_failure
        else f"✅ Éxito en Workflow: {workflow}"
    )

    description = (
        f"La ejecución del job `{job_name}` ha **fallado** en el entorno automatizado de GitHub Actions."
        if is_failure
        else f"La ejecución del job `{job_name}` ha **concluido exitosamente** en GitHub Actions."
    )

    extra_fields = [
        {"name": "⚡ Disparador", "value": f"`{event_name}`", "inline": True},
        {"name": "🌿 Rama / Ref", "value": f"`{ref_name}`", "inline": True},
    ]

    payload = build_discord_payload(
        title=title,
        description=description,
        status=status,
        fields=extra_fields,
        run_url=run_url,
        commit_sha=commit_sha,
        repository=repository,
        workflow=workflow,
        error_details=error_message,
    )

    return send_discord_alert(
        webhook_url=webhook_url,
        payload=payload,
        status=status,
        raise_on_error=raise_on_error,
        timeout=timeout,
        session=session,
    )


def build_arg_parser() -> argparse.ArgumentParser:
    """Construye el parser de argumentos para la CLI de notificaciones."""
    parser = argparse.ArgumentParser(
        prog="uv run python -m src.notifications",
        description="Gestor de alertas y notificaciones Webhook para InsightBolivia.",
    )
    subparsers = parser.add_subparsers(dest="command", help="Comando a ejecutar")

    # Subcomando: send-github-alert
    gh_parser = subparsers.add_parser(
        "send-github-alert",
        help="Envía una alerta recopilando automáticamente variables de GitHub Actions.",
    )
    gh_parser.add_argument(
        "--status",
        type=str,
        default="failure",
        choices=["failure", "success", "warning", "info"],
        help="Estado de la ejecución (por defecto: 'failure').",
    )
    gh_parser.add_argument(
        "--error",
        "-e",
        type=str,
        default=None,
        help="Mensaje o detalle de error opcional.",
    )
    gh_parser.add_argument(
        "--webhook-url",
        type=str,
        default=None,
        help="URL opcional de Discord Webhook para sobreescribir la configuración.",
    )

    # Subcomando: send-alert
    alert_parser = subparsers.add_parser(
        "send-alert",
        help="Envía una alerta genérica con título y mensaje personalizados.",
    )
    alert_parser.add_argument(
        "--title",
        "-t",
        type=str,
        default="Notificación InsightBolivia",
        help="Título de la alerta.",
    )
    alert_parser.add_argument(
        "--message",
        "-m",
        type=str,
        required=True,
        help="Descripción o cuerpo del mensaje.",
    )
    alert_parser.add_argument(
        "--status",
        type=str,
        default="info",
        choices=["failure", "success", "warning", "info"],
        help="Nivel de severidad o estado (por defecto: 'info').",
    )
    alert_parser.add_argument(
        "--webhook-url",
        type=str,
        default=None,
        help="URL opcional de Discord Webhook.",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    """Punto de entrada CLI para ejecución manual o desde GitHub Actions."""
    parser = build_arg_parser()
    options = parser.parse_args(argv)

    if options.command == "send-github-alert":
        success = send_github_actions_alert(
            status=options.status,
            error_message=options.error,
            webhook_url=options.webhook_url,
        )
        return 0 if (success or not options.webhook_url and not os.getenv("DISCORD_WEBHOOK_URL")) else 0

    if options.command == "send-alert":
        success = send_discord_alert(
            webhook_url=options.webhook_url,
            title=options.title,
            description=options.message,
            status=options.status,
        )
        return 0 if (success or not options.webhook_url and not os.getenv("DISCORD_WEBHOOK_URL")) else 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
