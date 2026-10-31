import sys

from typer.testing import CliRunner

from alysia.cli import _run, app

runner = CliRunner()


def test_help_is_available() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "doctor" in result.stdout


def test_doctor_runs_without_changing_environment() -> None:
    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert "Python" in result.stdout
    assert "FFmpeg" in result.stdout
    assert "NVIDIA GPU" in result.stdout


def test_command_probe_can_preserve_multiline_output() -> None:
    ok, output = _run(
        sys.executable,
        "-c",
        "print('NAME ID SIZE'); print('qwen3.5:4b abc 3.4GB')",
        first_line_only=False,
    )

    assert ok
    assert "qwen3.5:4b" in output
