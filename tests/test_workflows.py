"""Pruebas unitarias para los flujos de trabajo (Workflows) de GitHub Actions.

Valida la sintaxis YAML, configuración de triggers (cron/dispatch), inyección segura
de credenciales y variables de entorno, comandos de ejecución con uv y pasos de observabilidad.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

WORKFLOWS_DIR = Path(__file__).resolve().parent.parent / ".github" / "workflows"
ETL_WORKFLOW_FILE = WORKFLOWS_DIR / "etl_comercio_exterior.yml"
TESTS_WORKFLOW_FILE = WORKFLOWS_DIR / "tests.yml"


def _load_yaml(file_path: Path) -> dict[str, Any]:
    """Carga y parsea un archivo YAML de workflow."""
    assert file_path.exists(), f"El archivo {file_path} no existe."
    with file_path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    assert isinstance(data, dict), f"El archivo {file_path} no es un documento YAML válido."
    return data


def _get_on_block(data: dict[str, Any]) -> dict[str, Any]:
    """Extrae el bloque 'on' o True del documento YAML parseado."""
    raw_dict: dict[Any, Any] = data
    on_val = raw_dict.get("on", raw_dict.get(True))
    assert isinstance(on_val, dict), "El bloque 'on' debe ser un diccionario."
    return on_val


class TestWorkflowsSyntaxAndIntegrity:
    """Valida la sintaxis y existencia de todos los workflows de GitHub Actions."""

    @pytest.mark.parametrize("file_path", [ETL_WORKFLOW_FILE, TESTS_WORKFLOW_FILE])
    def test_workflow_exists_and_is_valid_yaml(self, file_path: Path) -> None:
        """Verifica que los archivos de workflow existan y contengan YAML parseable."""
        data = _load_yaml(file_path)
        assert "name" in data
        on_block = _get_on_block(data)
        assert len(on_block) > 0
        assert "jobs" in data


class TestEtlComercioExteriorWorkflow:
    """Pruebas exhaustivas para el workflow de orquestación ETL de comercio exterior."""

    @pytest.fixture(scope="module")
    def etl_data(self) -> dict[str, Any]:
        """Fixture que carga los datos parseados de etl_comercio_exterior.yml."""
        return _load_yaml(ETL_WORKFLOW_FILE)

    def test_cron_schedule_configuration(self, etl_data: dict[str, Any]) -> None:
        """Valida que el cron esté configurado para las 06:00 UTC diariamente."""
        on_block = _get_on_block(etl_data)
        assert "schedule" in on_block, "El trigger 'schedule' no está configurado."

        schedules = on_block["schedule"]
        assert isinstance(schedules, list) and len(schedules) > 0
        cron_expr = schedules[0].get("cron")
        assert cron_expr == "0 6 * * *", f"Expresión cron esperada '0 6 * * *', obtenido: {cron_expr}"

    def test_workflow_dispatch_inputs(self, etl_data: dict[str, Any]) -> None:
        """Valida que workflow_dispatch incluya inputs paramétricos configurados correctamente."""
        on_block = _get_on_block(etl_data)
        assert "workflow_dispatch" in on_block, "El trigger 'workflow_dispatch' no está configurado."

        dispatch = on_block["workflow_dispatch"]
        assert isinstance(dispatch, dict), "El trigger 'workflow_dispatch' debe ser un diccionario."
        inputs = dispatch.get("inputs", {})
        assert "operation" in inputs
        assert inputs["operation"].get("type") == "choice"
        assert "force_reprocess" in inputs
        assert inputs["force_reprocess"].get("type") == "boolean"
        assert "dry_run" in inputs
        assert inputs["dry_run"].get("type") == "boolean"
        assert "date_range" in inputs
        assert "skip_extract" in inputs

    def test_concurrency_group_settings(self, etl_data: dict[str, Any]) -> None:
        """Valida el grupo de concurrencia y política anti-cancelación simultánea."""
        assert "concurrency" in etl_data
        concurrency = etl_data["concurrency"]
        assert "group" in concurrency
        assert concurrency.get("cancel-in-progress") is False

    def test_job_structure_and_runner(self, etl_data: dict[str, Any]) -> None:
        """Valida la definición de los jobs y el runner de ejecución."""
        jobs = etl_data.get("jobs", {})
        assert "run-etl" in jobs
        etl_job = jobs["run-etl"]
        assert etl_job.get("runs-on") == "ubuntu-latest"
        assert "steps" in etl_job
        assert isinstance(etl_job["steps"], list)

    def test_gcp_authentication_step(self, etl_data: dict[str, Any]) -> None:
        """Valida el paso de autenticación oficial con Google Cloud."""
        steps = etl_data["jobs"]["run-etl"]["steps"]
        auth_steps = [s for s in steps if s.get("uses", "").startswith("google-github-actions/auth")]
        assert len(auth_steps) == 1, "Debe existir un paso de autenticación con google-github-actions/auth."

        auth_step = auth_steps[0]
        with_block = auth_step.get("with", {})
        assert "credentials_json" in with_block
        assert "secrets.GCP_SA_KEY" in with_block["credentials_json"]

    def test_uv_and_python_setup_steps(self, etl_data: dict[str, Any]) -> None:
        """Valida los pasos de instalación de uv, Python y sincronización de dependencias."""
        steps = etl_data["jobs"]["run-etl"]["steps"]

        uv_steps = [s for s in steps if s.get("uses", "").startswith("astral-sh/setup-uv")]
        assert len(uv_steps) == 1, "Debe existir un paso con astral-sh/setup-uv."
        assert uv_steps[0].get("with", {}).get("enable-cache") is True

        python_steps = [s for s in steps if "uv python install" in s.get("run", "")]
        assert len(python_steps) == 1, "Debe existir un paso ejecutando 'uv python install'."

        sync_steps = [s for s in steps if "uv sync" in s.get("run", "")]
        assert len(sync_steps) == 1, "Debe existir un paso ejecutando 'uv sync'."

    def test_etl_execution_step_and_env_vars(self, etl_data: dict[str, Any]) -> None:
        """Valida el comando de ejecución del pipeline y las variables de entorno inyectadas."""
        steps = etl_data["jobs"]["run-etl"]["steps"]
        etl_step = next(
            (s for s in steps if "uv run python -m src.main" in s.get("run", "")),
            None,
        )
        assert etl_step is not None, "Debe existir un paso que invoque 'uv run python -m src.main'."

        env = etl_step.get("env", {})
        assert "BQ_PROJECT_ID" in env
        assert "GCP_PROJECT_ID" in env
        assert "FIRESTORE_DATABASE" in env
        assert "LOG_LEVEL" in env
        assert "LOG_FORMAT" in env

    def test_artifact_upload_step(self, etl_data: dict[str, Any]) -> None:
        """Valida que se guarden artefactos de diagnóstico y reportes de calidad."""
        steps = etl_data["jobs"]["run-etl"]["steps"]
        upload_steps = [s for s in steps if s.get("uses", "").startswith("actions/upload-artifact")]
        assert len(upload_steps) == 1, "Debe existir un paso de subida de artefactos."

        upload_step = upload_steps[0]
        assert upload_step.get("if") in {"always()", "failure()", "failure() || always()"}
        with_block = upload_step.get("with", {})
        assert "gx/uncommitted/data_docs/" in with_block.get("path", "")

    def test_permissions_configuration(self, etl_data: dict[str, Any]) -> None:
        """Valida que el workflow configure permisos de escritura para actualizar last_run.txt."""
        assert "permissions" in etl_data, "El bloque 'permissions' no está configurado en el workflow."
        permissions = etl_data["permissions"]
        assert isinstance(permissions, dict)
        assert permissions.get("contents") == "write", "Se requiere permiso 'contents: write' para commits automáticos."

    def test_discord_failure_notification_step(self, etl_data: dict[str, Any]) -> None:
        """Valida el paso de envío de alerta a Discord Webhook ante fallos."""
        steps = etl_data["jobs"]["run-etl"]["steps"]
        webhook_steps = [
            s
            for s in steps
            if "src.notifications" in s.get("run", "") or "DISCORD_WEBHOOK_URL" in str(s.get("env", {}))
        ]
        assert len(webhook_steps) == 1, "Debe existir exactamente un paso de alerta por webhook."

        webhook_step = webhook_steps[0]
        assert webhook_step.get("if") == "failure()", "El paso de alerta debe ejecutarse con 'if: failure()'."
        assert "DISCORD_WEBHOOK_URL" in webhook_step.get("env", {})
        assert "secrets.DISCORD_WEBHOOK_URL" in webhook_step["env"]["DISCORD_WEBHOOK_URL"]
        assert "send-github-alert" in webhook_step.get("run", "")

    def test_anti_cron_deactivation_step(self, etl_data: dict[str, Any]) -> None:
        """Valida el paso de actualización y commit de last_run.txt para persistencia de cron."""
        steps = etl_data["jobs"]["run-etl"]["steps"]
        anti_cron_steps = [s for s in steps if "last_run.txt" in s.get("run", "")]
        assert len(anti_cron_steps) == 1, "Debe existir un paso que actualice 'last_run.txt'."

        anti_cron_step = anti_cron_steps[0]
        assert anti_cron_step.get("if") == "success()", "El paso debe ejecutarse solo ante éxito ('if: success()')."
        run_cmd = anti_cron_step.get("run", "")
        assert "last_run.txt" in run_cmd
        assert "github-actions[bot]" in run_cmd
        assert "[skip ci]" in run_cmd
        assert "git push" in run_cmd

    def test_no_hardcoded_secrets(self, etl_data: dict[str, Any]) -> None:
        """Verifica que no existan credenciales en texto plano en el archivo de workflow."""
        raw_text = ETL_WORKFLOW_FILE.read_text(encoding="utf-8")
        forbidden_patterns = [
            "AIza",
            "-----BEGIN PRIVATE KEY-----",
            "client_secret",
            "private_key_id",
        ]
        for pattern in forbidden_patterns:
            assert pattern not in raw_text, f"Se detectó un posible secreto hardcodeado: '{pattern}'"
