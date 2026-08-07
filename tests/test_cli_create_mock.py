import re

from typer.testing import CliRunner

from alysia.cli import app
from tests.helpers import write_config


def test_cli_create_status_and_resume_with_mock(tmp_path) -> None:
    config_path = tmp_path / "config.yaml"
    write_config(config_path, tmp_path / "runs")
    runner = CliRunner()
    environment = {"ALYSIA_CONFIG_FILE": str(config_path)}

    created = runner.invoke(
        app,
        ["create", "为什么AI Agent还不是AGI？", "--provider", "mock"],
        env=environment,
    )

    assert created.exit_code == 0, created.stdout
    match = re.search(r"run_id:\s*(\S+)", created.stdout)
    assert match is not None
    run_id = match.group(1)
    status = runner.invoke(app, ["status", run_id], env=environment)
    resumed = runner.invoke(app, ["resume", run_id], env=environment)
    assert status.exit_code == 0
    assert '"text_pipeline_completed": true' in status.stdout
    assert resumed.exit_code == 0
    assert "resume: completed" in resumed.stdout
