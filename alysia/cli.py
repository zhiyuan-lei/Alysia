from __future__ import annotations

import asyncio
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from alysia.core.config import AlysiaConfig, load_config
from alysia.core.orchestrator import AlysiaOrchestrator
from alysia.core.run import RunManager

app = typer.Typer(
    name="alysia",
    help="Alysia 自主创作者系统命令行工具。",
    no_args_is_help=True,
)
console = Console()


class ProviderName(str, Enum):
    MOCK = "mock"
    OLLAMA = "ollama"


@dataclass(frozen=True)
class DoctorCheck:
    name: str
    available: bool
    details: str


@app.callback()
def main() -> None:
    """Alysia 命令入口。"""


def _run(executable: str, *arguments: str) -> tuple[bool, str]:
    path = shutil.which(executable)
    if path is None:
        return False, "未找到"

    try:
        result = subprocess.run(
            [path, *arguments],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=8,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"调用失败：{exc}"

    output = (result.stdout or result.stderr).strip()
    first_line = output.splitlines()[0] if output else f"退出码 {result.returncode}"
    return result.returncode == 0, first_line


def collect_doctor_checks() -> list[DoctorCheck]:
    checks = [
        DoctorCheck("Python", True, f"{sys.version.split()[0]} ({sys.executable})"),
    ]

    pip_ok, pip_version = _run(sys.executable, "-m", "pip", "--version")
    checks.append(DoctorCheck("pip", pip_ok, pip_version))

    for name, command, arguments in (
        ("uv", "uv", ("--version",)),
        ("Git", "git", ("--version",)),
        ("Node.js", "node", ("--version",)),
        ("npm", "npm", ("--version",)),
        ("FFmpeg", "ffmpeg", ("-version",)),
    ):
        ok, details = _run(command, *arguments)
        checks.append(DoctorCheck(name, ok, details))

    ollama_ok, ollama_version = _run("ollama", "--version")
    checks.append(DoctorCheck("Ollama", ollama_ok, ollama_version))
    if ollama_ok:
        models_ok, models = _run("ollama", "list")
        has_qwen = models_ok and "qwen3.5:4b" in models.lower()
        details = "qwen3.5:4b 已安装" if has_qwen else "qwen3.5:4b 未安装"
        checks.append(DoctorCheck("Ollama 模型", has_qwen, details))
    else:
        checks.append(DoctorCheck("Ollama 模型", False, "跳过：Ollama 不可用"))

    gpu_ok, gpu_details = _run(
        "nvidia-smi",
        "--query-gpu=name,driver_version,memory.total",
        "--format=csv,noheader",
    )
    if gpu_ok:
        smi_ok, smi_output = _run("nvidia-smi")
        cuda_match = re.search(r"CUDA Version:\s*([0-9.]+)", smi_output) if smi_ok else None
        if cuda_match:
            gpu_details = f"{gpu_details}; 驱动支持 CUDA {cuda_match.group(1)}"
    checks.append(DoctorCheck("NVIDIA GPU", gpu_ok, gpu_details))

    nvcc_ok, nvcc_details = _run("nvcc", "--version")
    checks.append(DoctorCheck("CUDA Toolkit (nvcc)", nvcc_ok, nvcc_details))
    return checks


def _config_with_provider(provider: ProviderName | None) -> AlysiaConfig:
    config = load_config()
    if provider is not None:
        config.llm.provider = provider.value
        if provider is ProviderName.MOCK:
            config.research.provider = "mock"
    return config


@app.command()
def create(
    topic: str = typer.Argument(..., help="中文视频主题。"),
    provider: ProviderName | None = typer.Option(None, "--provider", help="覆盖配置中的 LLM provider。"),
) -> None:
    """从 Topic 创建调研、脚本、分镜与文本 QA。"""
    try:
        orchestrator = AlysiaOrchestrator(_config_with_provider(provider))
        state = asyncio.run(orchestrator.create(topic))
    except Exception as exc:
        console.print(f"[red]创建失败：{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print(f"run_id: {state.run_id}")
    console.print(f"milestone: {state.milestone}")
    console.print(f"path: {orchestrator.manager.run_dir(state.run_id)}")


@app.command()
def status(run_id: str = typer.Argument(..., help="任务 run_id。")) -> None:
    """查看持久化任务状态。"""
    try:
        config = load_config()
        state = RunManager(config.runtime.runs_dir).load(run_id)
    except Exception as exc:
        console.print(f"[red]读取状态失败：{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print_json(data=state.model_dump(mode="json"), ensure_ascii=False)


@app.command()
def resume(
    run_id: str = typer.Argument(..., help="任务 run_id。"),
    provider: ProviderName | None = typer.Option(None, "--provider", help="覆盖原任务的 LLM provider。"),
    force: bool = typer.Option(False, "--force", help="重新执行已完成的文本阶段。"),
) -> None:
    """从持久化状态恢复任务，默认跳过已有有效产物的阶段。"""
    try:
        base_config = load_config()
        existing = RunManager(base_config.runtime.runs_dir).load(run_id)
        config = AlysiaConfig.model_validate(existing.config_snapshot)
        if provider is not None:
            config.llm.provider = provider.value
            if provider is ProviderName.MOCK:
                config.research.provider = "mock"
        orchestrator = AlysiaOrchestrator(config)
        state = asyncio.run(orchestrator.resume(run_id, force=force))
    except Exception as exc:
        console.print(f"[red]恢复失败：{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print(f"run_id: {state.run_id}")
    console.print(f"milestone: {state.milestone}")
    console.print("resume: completed")


@app.command("runs")
def list_runs() -> None:
    """列出本地任务。"""
    config = load_config()
    manager = RunManager(config.runtime.runs_dir)
    directories = sorted((path for path in manager.runs_dir.iterdir() if path.is_dir()), reverse=True)
    for directory in directories:
        if (directory / "run_state.json").is_file():
            console.print(directory.name)


@app.command()
def doctor() -> None:
    """检测 Alysia 所需的本机工具链，不修改系统。"""
    table = Table(title="Alysia 环境诊断")
    table.add_column("组件", style="cyan", no_wrap=True)
    table.add_column("状态", no_wrap=True)
    table.add_column("详情")

    checks = collect_doctor_checks()
    for check in checks:
        status = "[green]可用[/green]" if check.available else "[yellow]缺失/未就绪[/yellow]"
        table.add_row(check.name, status, check.details)

    console.print(table)
    missing = sum(not check.available for check in checks)
    console.print(f"诊断完成：{len(checks) - missing} 项可用，{missing} 项缺失或未就绪。")


if __name__ == "__main__":
    app()
