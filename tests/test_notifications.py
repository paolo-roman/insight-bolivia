"""Pruebas unitarias para el módulo de notificaciones y alertas src.notifications.

Verifica:
- Mapeo de códigos de color por estado.
- Construcción estructurada de Discord Embeds (título, descripción, campos, URLs, commits, errores).
- Truncamiento defensivo de mensajes de error largos.
- Envío HTTP exitoso y manejo de respuestas HTTP 2xx, 4xx, 5xx y fallos de conexión.
- Omisión defensiva y segura cuando no hay webhook configurado.
- Recopilación automática de metadatos de entorno de GitHub Actions.
- Parser de argumentos e interfaz CLI (send-github-alert, send-alert).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest
import requests

from src.notifications import (
    COLOR_FAILURE,
    COLOR_INFO,
    COLOR_SUCCESS,
    COLOR_WARNING,
    build_arg_parser,
    build_discord_payload,
    get_status_color,
    main,
    send_discord_alert,
    send_github_actions_alert,
)

if TYPE_CHECKING:
    from pytest import MonkeyPatch


class TestGetStatusColor:
    """Valida la resolución de códigos de color según el estado."""

    @pytest.mark.parametrize(
        ("status", "expected"),
        [
            ("success", COLOR_SUCCESS),
            ("ok", COLOR_SUCCESS),
            ("exitoso", COLOR_SUCCESS),
            ("exito", COLOR_SUCCESS),
            ("SUCCESS", COLOR_SUCCESS),
            ("warning", COLOR_WARNING),
            ("advertencia", COLOR_WARNING),
            ("skipped", COLOR_WARNING),
            ("omitido", COLOR_WARNING),
            ("failure", COLOR_FAILURE),
            ("error", COLOR_FAILURE),
            ("failed", COLOR_FAILURE),
            ("fallido", COLOR_FAILURE),
            ("fallo", COLOR_FAILURE),
            ("FAILURE", COLOR_FAILURE),
            ("info", COLOR_INFO),
            ("custom_status", COLOR_INFO),
            ("", COLOR_INFO),
        ],
    )
    def test_status_color_mapping(self, status: str, expected: int) -> None:
        assert get_status_color(status) == expected


class TestBuildDiscordPayload:
    """Valida la construcción de payloads JSON para Discord Webhooks."""

    def test_minimal_payload(self) -> None:
        payload = build_discord_payload(
            title="Alerta de Prueba",
            description="Descripción básica",
            status="failure",
        )
        assert payload["username"] == "InsightBolivia ETL Monitor"
        assert len(payload["embeds"]) == 1
        embed = payload["embeds"][0]
        assert embed["title"] == "Alerta de Prueba"
        assert embed["description"] == "Descripción básica"
        assert embed["color"] == COLOR_FAILURE
        assert "timestamp" in embed
        assert "InsightBolivia" in embed["footer"]["text"]

    def test_custom_color_override(self) -> None:
        payload = build_discord_payload(
            title="Test",
            description="Desc",
            custom_color=0x123456,
        )
        assert payload["embeds"][0]["color"] == 0x123456

    def test_full_metadata_fields(self) -> None:
        payload = build_discord_payload(
            title="Fallo Crítico",
            description="Error en pipeline",
            status="error",
            workflow="ETL - Ingestión",
            repository="insightbolivia/insight-bolivia",
            run_url="https://github.com/insightbolivia/insight-bolivia/actions/runs/123",
            commit_sha="a1b2c3d4e5f6",
            error_details="ZeroDivisionError: division by zero",
            fields=[{"name": "Extra", "value": "Val", "inline": True}],
        )
        embed = payload["embeds"][0]
        fields = {f["name"]: f["value"] for f in embed["fields"]}

        assert "📋 Workflow" in fields
        assert "`ETL - Ingestión`" in fields["📋 Workflow"]
        assert "📦 Repositorio" in fields
        assert "`insightbolivia/insight-bolivia`" in fields["📦 Repositorio"]
        assert "🔗 Run en GitHub" in fields
        assert "[Ver Ejecución]" in fields["🔗 Run en GitHub"]
        assert "🔖 Commit" in fields
        assert "`a1b2c3d`" in fields["🔖 Commit"]
        assert "💥 Detalles del Error" in fields
        assert "ZeroDivisionError" in fields["💥 Detalles del Error"]
        assert "Extra" in fields

    def test_error_details_truncation(self) -> None:
        long_error = "X" * 1500
        payload = build_discord_payload(
            title="Error",
            description="Desc",
            error_details=long_error,
        )
        embed = payload["embeds"][0]
        error_field = next(f for f in embed["fields"] if f["name"] == "💥 Detalles del Error")
        # Deve estar contenido dentro de ```...``` y truncado a 1000 + "..."
        assert len(error_field["value"]) <= 1010
        assert "..." in error_field["value"]


class TestSendDiscordAlert:
    """Valida el envío HTTP de alertas a Discord."""

    def test_returns_false_when_no_webhook_url(self, monkeypatch: MonkeyPatch) -> None:
        monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
        with patch("src.notifications.get_settings", side_effect=Exception("No settings")):
            result = send_discord_alert(webhook_url=None, title="Test", description="Desc")
            assert result is False

    def test_successful_send_with_explicit_url(self) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 204
        mock_response.raise_for_status.return_value = None

        with patch("requests.post", return_value=mock_response) as mock_post:
            result = send_discord_alert(
                webhook_url="https://discord.com/api/webhooks/123/abc",
                title="Prueba",
                description="Mensaje exitoso",
                status="success",
            )
            assert result is True
            mock_post.assert_called_once()
            args, kwargs = mock_post.call_args
            assert args[0] == "https://discord.com/api/webhooks/123/abc"
            assert kwargs["json"]["embeds"][0]["color"] == COLOR_SUCCESS

    def test_uses_env_variable_webhook_url(self, monkeypatch: MonkeyPatch) -> None:
        monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/env_url")
        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch("requests.post", return_value=mock_response) as mock_post:
            result = send_discord_alert(title="Alerta Env", description="Desc")
            assert result is True
            assert mock_post.call_args[0][0] == "https://discord.com/api/webhooks/env_url"

    def test_uses_settings_fallback_webhook_url(self, monkeypatch: MonkeyPatch) -> None:
        monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
        mock_settings = MagicMock()
        mock_settings.notifications.discord_webhook_url = "https://discord.com/api/webhooks/settings_url"

        mock_response = MagicMock()
        mock_response.status_code = 200

        with (
            patch("src.notifications.get_settings", return_value=mock_settings),
            patch("requests.post", return_value=mock_response) as mock_post,
        ):
            result = send_discord_alert(title="Alerta Settings", description="Desc")
            assert result is True
            assert mock_post.call_args[0][0] == "https://discord.com/api/webhooks/settings_url"

    def test_handles_http_error_gracefully_when_raise_false(self, caplog: pytest.LogCaptureFixture) -> None:
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = requests.HTTPError("404 Not Found")

        with (
            patch("requests.post", return_value=mock_response),
            caplog.at_level(logging.ERROR),
        ):
            result = send_discord_alert(
                webhook_url="https://discord.com/api/webhooks/invalid",
                title="Error Test",
                raise_on_error=False,
            )
            assert result is False
            assert "Error al enviar alerta a Discord Webhook" in caplog.text

    def test_raises_http_error_when_raise_true(self) -> None:
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = requests.HTTPError("500 Server Error")

        with (
            patch("requests.post", return_value=mock_response),
            pytest.raises(requests.HTTPError),
        ):
            send_discord_alert(
                webhook_url="https://discord.com/api/webhooks/invalid",
                title="Error Test",
                raise_on_error=True,
            )

    def test_uses_custom_session(self) -> None:
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 204
        mock_session.post.return_value = mock_response

        result = send_discord_alert(
            webhook_url="https://discord.com/api/webhooks/custom",
            title="Custom Session",
            session=mock_session,
        )
        assert result is True
        mock_session.post.assert_called_once()


class TestSendGithubActionsAlert:
    """Valida la recolección de metadatos de GitHub Actions y envío de alertas."""

    def test_collects_github_env_vars_and_sends(self, monkeypatch: MonkeyPatch) -> None:
        monkeypatch.setenv("GITHUB_REPOSITORY", "testorg/testrepo")
        monkeypatch.setenv("GITHUB_RUN_ID", "998877")
        monkeypatch.setenv("GITHUB_SERVER_URL", "https://github.com")
        monkeypatch.setenv("GITHUB_WORKFLOW", "ETL Daily")
        monkeypatch.setenv("GITHUB_JOB", "run-pipeline")
        monkeypatch.setenv("GITHUB_EVENT_NAME", "schedule")
        monkeypatch.setenv("GITHUB_SHA", "1234567890abcdef")
        monkeypatch.setenv("GITHUB_REF_NAME", "feature/test")

        with patch("src.notifications.send_discord_alert", return_value=True) as mock_send:
            result = send_github_actions_alert(
                status="failure",
                error_message="Dataset not found",
                webhook_url="https://discord.com/api/webhooks/mock",
            )
            assert result is True
            mock_send.assert_called_once()
            kwargs = mock_send.call_args[1]
            payload = kwargs["payload"]
            embed = payload["embeds"][0]
            assert "Fallo en Workflow: ETL Daily" in embed["title"]
            assert "run-pipeline" in embed["description"]

            fields = {f["name"]: f["value"] for f in embed["fields"]}
            assert fields["⚡ Disparador"] == "`schedule`"
            assert fields["🌿 Rama / Ref"] == "`feature/test`"
            assert "https://github.com/testorg/testrepo/actions/runs/998877" in fields["🔗 Run en GitHub"]

    def test_github_actions_alert_success_status(self, monkeypatch: MonkeyPatch) -> None:
        monkeypatch.delenv("GITHUB_RUN_ID", raising=False)
        monkeypatch.setenv("GITHUB_WORKFLOW", "CI Tests")

        with patch("src.notifications.send_discord_alert", return_value=True) as mock_send:
            result = send_github_actions_alert(status="success")
            assert result is True
            payload = mock_send.call_args[1]["payload"]
            embed = payload["embeds"][0]
            assert "Éxito en Workflow: CI Tests" in embed["title"]
            assert "concluido exitosamente" in embed["description"]


class TestNotificationsCLI:
    """Valida la interfaz de línea de comandos del módulo de notificaciones."""

    def test_parser_structure(self) -> None:
        parser = build_arg_parser()
        assert "send-github-alert" in parser.format_help()
        assert "send-alert" in parser.format_help()

    def test_cli_send_github_alert_command(self) -> None:
        with patch("src.notifications.send_github_actions_alert", return_value=True) as mock_gh_alert:
            exit_code = main(
                [
                    "send-github-alert",
                    "--status",
                    "failure",
                    "--error",
                    "Error de test",
                    "--webhook-url",
                    "https://discord.com/api/webhooks/cli_test",
                ]
            )
            assert exit_code == 0
            mock_gh_alert.assert_called_once_with(
                status="failure",
                error_message="Error de test",
                webhook_url="https://discord.com/api/webhooks/cli_test",
            )

    def test_cli_send_alert_command(self) -> None:
        with patch("src.notifications.send_discord_alert", return_value=True) as mock_send:
            exit_code = main(
                [
                    "send-alert",
                    "--title",
                    "Título CLI",
                    "--message",
                    "Cuerpo del mensaje",
                    "--status",
                    "info",
                    "--webhook-url",
                    "https://discord.com/api/webhooks/cli_alert",
                ]
            )
            assert exit_code == 0
            mock_send.assert_called_once_with(
                webhook_url="https://discord.com/api/webhooks/cli_alert",
                title="Título CLI",
                description="Cuerpo del mensaje",
                status="info",
            )

    def test_cli_no_args_prints_help(self) -> None:
        with patch("argparse.ArgumentParser.print_help") as mock_help:
            exit_code = main([])
            assert exit_code == 0
            mock_help.assert_called_once()

    def test_notifications_module_execution(self) -> None:
        """Valida la ejecución del módulo con __name__ == '__main__'."""
        import runpy
        from pathlib import Path

        import src.notifications as notif_mod

        file_path = str(Path(notif_mod.__file__).resolve())
        with (
            patch("sys.argv", ["notifications", "send-alert", "-m", "Test Runpy"]),
            patch("src.notifications.send_discord_alert", return_value=True),
            pytest.raises(SystemExit) as exc_info,
        ):
            runpy.run_path(file_path, run_name="__main__")
        assert exc_info.value.code == 0
