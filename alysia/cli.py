from __future__ import annotations

import asyncio
import importlib.util
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path

import typer
import yaml
from rich.console import Console
from rich.table import Table

from alysia.core.config import AlysiaConfig, load_config
from alysia.capabilities import CapabilityService
from alysia.core.orchestrator import AlysiaOrchestrator
from alysia.core.run import RunManager
from alysia.learning import LearningPipeline
from alysia.local_creator import LocalCreationSpec, LocalCreatorService
from alysia.knowledge import (
    KnowledgeService,
    demo_a_supersession,
    demo_b_conflict,
    demo_c_stale_block,
    demo_d_h3_observation,
    demo_grounding_run,
)
from alysia.identity import IdentityService
from alysia.learning.memory import MemoryStore
from alysia.operations import ChannelStore, ExperimentManager, OperationsService
from alysia.feedback import FeedbackService
from alysia.social.cli import app as social_app
from alysia.planning import CreatorLoop, PlanStore
from alysia.publishing import PublishingService
from alysia.production import ProductionService
from alysia.studio.director import StudioDirector
from alysia.studio.registry import AgentRegistry
from alysia.supervisor import AutonomousSupervisor, SupervisorStore
from alysia.supervisor.demo import exercise_demo
from alysia.visual import VisualGenerationService
from alysia.workflow import WorkflowService
from alysia.simulation import SimulationService
from alysia.evaluation import EvaluationGate, EvaluationService
from alysia.reliability.service import ReliabilityService
from alysia.security import SecurityService
from alysia.workflow.demo import (
    capability_gap_demo,
    failure_repair_resume_demo,
    recipe_learning_demo,
    visual_enhancement_demo,
)
from alysia.planning.trend_workspace import TrendWorkspace
from alysia.providers.cover import MockCoverGenerator, TemplateCoverGenerator
from alysia.providers.tts import SapiTTSProvider
from alysia.workers.media import find_media_executable
from alysia.schemas import ExperimentMetric, Script

app = typer.Typer(
    name="alysia",
    help="Alysia 自主创作者系统命令行工具。",
    no_args_is_help=True,
)
analytics_app = typer.Typer(help="离线导入与检查视频表现指标。", no_args_is_help=True)
memory_app = typer.Typer(help="查看可审计的长期记忆。", no_args_is_help=True)
trends_app = typer.Typer(help="生成或导入可追溯趋势快照。", no_args_is_help=True)
plan_app = typer.Typer(help="创建、查看与人工审批内容计划。", no_args_is_help=True)
creator_loop_app = typer.Typer(help="运行可恢复的自主创作者计划循环。", no_args_is_help=True)
publish_app = typer.Typer(help="人工审批、验证并提交 PublishJob。", no_args_is_help=True)
feedback_app = typer.Typer(help="导入发布后反馈并回流 Analytics。", no_args_is_help=True)
operations_app = typer.Typer(help="查看按频道隔离的长期运营状态。", no_args_is_help=True)
experiment_app = typer.Typer(help="创建并人工审批可审计内容实验。", no_args_is_help=True)
identity_app = typer.Typer(help="查看、审计与版本化管理 AI 创作者身份。", no_args_is_help=True)
style_app = typer.Typer(help="只读检查内容与品牌风格的一致性。", no_args_is_help=True)
production_app = typer.Typer(help="规划、审计并报告资源受限的内容生产。", no_args_is_help=True)
studio_app = typer.Typer(help="运行与审计串行 Multi-Agent Creator Studio。", no_args_is_help=True)
supervisor_app = typer.Typer(help="管理长期 Goal、Plan、Project 与单次 Supervisor tick。", no_args_is_help=True)
visual_app = typer.Typer(help="规划、生成并检查本地混合视觉资产。", no_args_is_help=True)
local_create_app = typer.Typer(help="用自写提示词和 ComfyUI 工作流制作本地视频、配音与剪辑。", no_args_is_help=True)
capability_app = typer.Typer(help="查看能力清单并执行证据驱动的自评。", no_args_is_help=True)
gaps_app = typer.Typer(help="查看有证据的能力缺口。", no_args_is_help=True)
skill_app = typer.Typer(help="管理受控 Skill 提案、评测、审批和回滚。", no_args_is_help=True)
workflow_app = typer.Typer(help="规划、验证、运行并复用受控 Capability Workflow。", no_args_is_help=True)
simulate_app = typer.Typer(help="在隔离 dry-run 中比较反事实方案；结果不是现实事实。", no_args_is_help=True)
knowledge_app = typer.Typer(help="审计、查询并维护证据化知识库。", no_args_is_help=True)
research_app = typer.Typer(help="创建有限轮次、受证据策略约束的研究任务。", no_args_is_help=True)
grounding_app = typer.Typer(help="检查 run 脚本的事实引用与新鲜度。", no_args_is_help=True)
eval_app = typer.Typer(help="运行版本化 benchmark、baseline、regression comparison 与 promotion gate。", no_args_is_help=True)
reliability_app = typer.Typer(help="查看故障、恢复决策、checkpoint 与资源守卫状态。", no_args_is_help=True)
security_app = typer.Typer(help="检查权限、审批、审计、凭证引用与敏感信息泄漏。", no_args_is_help=True)
control_app = typer.Typer(help="启动本地 Alysia Control Center。", no_args_is_help=True)
app.add_typer(analytics_app, name="analytics")
app.add_typer(memory_app, name="memory")
app.add_typer(trends_app, name="trends")
app.add_typer(plan_app, name="plan")
app.add_typer(creator_loop_app, name="creator-loop")
app.add_typer(publish_app, name="publish")
app.add_typer(feedback_app, name="feedback")
app.add_typer(social_app, name="social")
app.add_typer(operations_app, name="operations")
app.add_typer(experiment_app, name="experiment")
app.add_typer(identity_app, name="identity")
app.add_typer(style_app, name="style")
app.add_typer(production_app, name="production")
app.add_typer(studio_app, name="studio")
app.add_typer(supervisor_app, name="supervisor")
app.add_typer(visual_app, name="visual")
app.add_typer(local_create_app, name="local-create")
app.add_typer(capability_app, name="capability")
app.add_typer(gaps_app, name="gaps")
app.add_typer(skill_app, name="skill")
app.add_typer(workflow_app, name="workflow")
app.add_typer(simulate_app, name="simulate")
app.add_typer(knowledge_app, name="knowledge")
app.add_typer(research_app, name="research")
app.add_typer(grounding_app, name="grounding")
app.add_typer(eval_app, name="eval")
app.add_typer(reliability_app, name="reliability")
app.add_typer(security_app, name="security")
app.add_typer(control_app, name="control")
console = Console()


class ProviderName(str, Enum):
    MOCK = "mock"
    OLLAMA = "ollama"


class TTSProviderName(str, Enum):
    MOCK = "mock"
    SAPI = "sapi"
    COSYVOICE = "cosyvoice"


class ASRProviderName(str, Enum):
    NONE = "none"
    FASTER_WHISPER = "faster-whisper"


class VideoRendererName(str, Enum):
    MOCK = "mock"
    REMOTION = "remotion"


class CoverGeneratorName(str, Enum):
    MOCK = "mock"
    TEMPLATE = "template"


class PublishingProviderName(str, Enum):
    MOCK = "mock"
    BILIBILI = "bilibili"


class FeedbackProviderName(str, Enum):
    MANUAL = "manual"
    MOCK = "mock"
    BILIBILI = "bilibili"


class ProductionQualityName(str, Enum):
    DRAFT = "draft"
    STANDARD = "standard"
    HIGH = "high"


class VisualProviderName(str, Enum):
    MOCK = "mock"
    COMFYUI_H3 = "comfyui-h3"


@dataclass(frozen=True)
class DoctorCheck:
    name: str
    available: bool
    details: str


@app.callback()
def main() -> None:
    """Alysia 命令入口。"""


def _run(
    executable: str,
    *arguments: str,
    first_line_only: bool = True,
) -> tuple[bool, str]:
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
    if not output:
        output = f"退出码 {result.returncode}"
    details = output.splitlines()[0] if first_line_only else output
    return result.returncode == 0, details


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
    ):
        ok, details = _run(command, *arguments)
        checks.append(DoctorCheck(name, ok, details))

    for name, executable in (("FFmpeg", "ffmpeg"), ("FFprobe", "ffprobe")):
        path = find_media_executable(executable)
        if path is None:
            checks.append(DoctorCheck(name, False, "未找到"))
        else:
            ok, details = _run(str(path), "-version")
            checks.append(DoctorCheck(name, ok, f"{details} ({path})"))

    ollama_ok, ollama_version = _run("ollama", "--version")
    checks.append(DoctorCheck("Ollama", ollama_ok, ollama_version))
    if ollama_ok:
        models_ok, models = _run("ollama", "list", first_line_only=False)
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

    hardware = load_config().hardware_profile
    checks.append(
        DoctorCheck(
            "Alysia 硬件预算",
            True,
            f"{hardware.gpu}; VRAM={hardware.vram_mb} MB; RAM={hardware.ram_gb} GB; "
            f"sequential_gpu_required={hardware.sequential_gpu_required}",
        )
    )

    nvcc_ok, nvcc_details = _run("nvcc", "--version")
    checks.append(DoctorCheck("CUDA Toolkit (nvcc)", nvcc_ok, nvcc_details))
    checks.append(
        DoctorCheck(
            "Windows SAPI TTS",
            SapiTTSProvider.is_available(),
            "可用（使用本机已安装语音）" if SapiTTSProvider.is_available() else "不可用",
        )
    )
    checks.append(
        DoctorCheck(
            "CosyVoice Python",
            importlib.util.find_spec("cosyvoice") is not None,
            "已安装" if importlib.util.find_spec("cosyvoice") is not None else "未安装（可选）",
        )
    )
    checks.append(
        DoctorCheck(
            "faster-whisper",
            importlib.util.find_spec("faster_whisper") is not None,
            "已安装" if importlib.util.find_spec("faster_whisper") is not None else "未安装（可选）",
        )
    )
    return checks


def _config_with_provider(provider: ProviderName | None) -> AlysiaConfig:
    config = load_config()
    if provider is not None:
        config.llm.provider = provider.value
        if provider is ProviderName.MOCK:
            config.research.provider = "mock"
    return config


def _config_for_run(
    run_id: str,
    *,
    llm_provider: ProviderName | None = None,
    tts_provider: TTSProviderName | None = None,
    asr_provider: ASRProviderName | None = None,
    video_renderer: VideoRendererName | None = None,
) -> AlysiaConfig:
    base_config = load_config()
    existing = RunManager(base_config.runtime.runs_dir).load(run_id)
    config = AlysiaConfig.model_validate(existing.config_snapshot)
    if llm_provider is not None:
        config.llm.provider = llm_provider.value
        if llm_provider is ProviderName.MOCK:
            config.research.provider = "mock"
    if tts_provider is not None:
        config.tts.provider = tts_provider.value
    if asr_provider is not None:
        config.asr.enabled = asr_provider is not ASRProviderName.NONE
        if config.asr.enabled:
            config.asr.provider = "faster-whisper"
    if video_renderer is not None:
        config.video.renderer = video_renderer.value
    return config


def _learning_pipeline() -> LearningPipeline:
    config = load_config()
    manager = RunManager(config.runtime.runs_dir)
    return LearningPipeline(manager, config.learning.memory_dir)


def _creator_loop(channel_id: str | None = None) -> CreatorLoop:
    return CreatorLoop(load_config(), channel_id=channel_id)


def _publishing_service() -> PublishingService:
    return PublishingService(load_config())


def _feedback_service() -> FeedbackService:
    return FeedbackService(load_config())


def _operations_service() -> OperationsService:
    return OperationsService(load_config())


def _experiment_manager() -> ExperimentManager:
    config = load_config()
    return ExperimentManager(
        ChannelStore(config.learning.memory_dir),
        MemoryStore(config.learning.memory_dir),
        minimum_group_size=config.operations.minimum_experiment_group_size,
    )


def _identity_service() -> IdentityService:
    return IdentityService(load_config())


def _production_service(run_id: str | None = None) -> ProductionService:
    config = load_config()
    if run_id is not None:
        state = RunManager(config.runtime.runs_dir).load(run_id)
        config = AlysiaConfig.model_validate(state.config_snapshot)
    return ProductionService(config)


def _knowledge_service(config: AlysiaConfig | None = None) -> KnowledgeService:
    return KnowledgeService(config or load_config())


def _knowledge_demo_service() -> KnowledgeService:
    return KnowledgeService(load_config(), root=Path("workspace/knowledge_demos/alpha17"))


def _security_service() -> SecurityService:
    return SecurityService(load_config())


def _studio_director(run_id: str) -> StudioDirector:
    return StudioDirector(_config_for_run(run_id))


def _supervisor() -> AutonomousSupervisor:
    return AutonomousSupervisor(load_config())


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
    tts_provider: TTSProviderName | None = typer.Option(None, "--tts-provider", help="覆盖 TTS provider。"),
    asr_provider: ASRProviderName | None = typer.Option(None, "--asr-provider", help="可选 ASR 校准。"),
    renderer: VideoRendererName | None = typer.Option(None, "--renderer", help="覆盖视频 renderer。"),
    force: bool = typer.Option(False, "--force", help="重新执行当前可恢复阶段。"),
) -> None:
    """恢复任务；每次推进一个里程碑，默认跳过已有有效产物。"""
    try:
        config = _config_for_run(
            run_id,
            llm_provider=provider,
            tts_provider=tts_provider,
            asr_provider=asr_provider,
            video_renderer=renderer,
        )
        orchestrator = AlysiaOrchestrator(config)
        state = asyncio.run(orchestrator.resume(run_id, force=force))
    except Exception as exc:
        console.print(f"[red]恢复失败：{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print(f"run_id: {state.run_id}")
    console.print(f"milestone: {state.milestone}")
    console.print("resume: completed")


@app.command()
def render(
    run_id: str = typer.Argument(..., help="已有 audio_ready 任务 run_id。"),
    renderer: VideoRendererName | None = typer.Option(None, "--renderer", help="mock 或 remotion。"),
    force: bool = typer.Option(False, "--force", help="重新生成视频与视频 QA。"),
) -> None:
    """将 Storyboard、旁白和字幕渲染为 final.mp4。"""
    try:
        config = _config_for_run(run_id, video_renderer=renderer)
        orchestrator = AlysiaOrchestrator(config)
        state = asyncio.run(orchestrator.render(run_id, force=force))
    except Exception as exc:
        console.print(f"[red]视频渲染失败：{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print(f"run_id: {state.run_id}")
    console.print(f"milestone: {state.milestone}")
    console.print(f"final.mp4: {orchestrator.manager.run_dir(run_id) / state.artifacts['final_video']}")


@app.command("package")
def package_run(
    run_id: str = typer.Argument(..., help="已有 video_ready 任务 run_id。"),
    generator: CoverGeneratorName = typer.Option(
        CoverGeneratorName.TEMPLATE,
        "--generator",
        help="封面生成器：mock 或 template。",
    ),
    force: bool = typer.Option(False, "--force", help="重新生成投稿包。"),
) -> None:
    """生成封面、标题、简介、标签和可追溯投稿元数据。"""
    try:
        config = _config_for_run(run_id)
        cover_generator = (
            MockCoverGenerator(config.publish.cover, config.visual_identity.template_version)
            if generator is CoverGeneratorName.MOCK
            else TemplateCoverGenerator(config.publish.cover, config.visual_identity.template_version)
        )
        orchestrator = AlysiaOrchestrator(config, cover_generator=cover_generator)
        state = asyncio.run(orchestrator.package(run_id, force=force))
    except Exception as exc:
        console.print(f"[red]投稿包生成失败：{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print(f"run_id: {state.run_id}")
    console.print(f"milestone: {state.milestone}")
    console.print(f"publish package: {orchestrator.manager.run_dir(run_id) / state.artifacts['publish_package']}")


@app.command("publish-check")
def publish_check(
    run_id: str = typer.Argument(..., help="已有 package_ready 任务 run_id。"),
    force: bool = typer.Option(False, "--force", help="重新执行发布前 QA。"),
) -> None:
    """检查视频、标题、简介、标签和封面，进入人工审核门。"""
    try:
        config = _config_for_run(run_id)
        orchestrator = AlysiaOrchestrator(config)
        state = asyncio.run(orchestrator.publish_check(run_id, force=force))
    except Exception as exc:
        console.print(f"[red]发布前检查失败：{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print(f"run_id: {state.run_id}")
    console.print(f"milestone: {state.milestone}")
    console.print(f"QA: {orchestrator.manager.run_dir(run_id) / state.artifacts['publish_qa_report']}")


@app.command()
def voice(
    run_id: str = typer.Argument(..., help="已有 text_ready 任务 run_id。"),
    tts_provider: TTSProviderName | None = typer.Option(None, "--tts-provider", help="覆盖 TTS provider。"),
    force: bool = typer.Option(False, "--force", help="重新生成 scene 音频。"),
) -> None:
    """只推进 Voice 阶段并生成 narration 与 manifest。"""
    try:
        config = _config_for_run(run_id, tts_provider=tts_provider)
        orchestrator = AlysiaOrchestrator(config)
        state = asyncio.run(orchestrator.voice(run_id, force=force))
    except Exception as exc:
        console.print(f"[red]旁白生成失败：{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print(f"run_id: {state.run_id}")
    console.print(f"milestone: {state.milestone}")


@app.command()
def subtitle(
    run_id: str = typer.Argument(..., help="已有 voice_ready 任务 run_id。"),
    asr_provider: ASRProviderName | None = typer.Option(None, "--asr-provider", help="可选 ASR 校准。"),
    force: bool = typer.Option(False, "--force", help="重新生成字幕与音频 QA。"),
) -> None:
    """从 audio manifest 生成字幕、QA，并推进到 audio_ready。"""
    try:
        config = _config_for_run(run_id, asr_provider=asr_provider)
        orchestrator = AlysiaOrchestrator(config)
        state = asyncio.run(orchestrator.subtitle(run_id, force=force))
    except Exception as exc:
        console.print(f"[red]字幕生成失败：{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print(f"run_id: {state.run_id}")
    console.print(f"milestone: {state.milestone}")


@app.command("audio-status")
def audio_status(run_id: str = typer.Argument(..., help="任务 run_id。")) -> None:
    """查看音频里程碑和关键产物状态。"""
    try:
        config = load_config()
        manager = RunManager(config.runtime.runs_dir)
        state = manager.load(run_id)
        payload = {
            "run_id": run_id,
            "pipeline_phase": state.pipeline_phase,
            "milestone": state.milestone,
            "audio_pipeline_completed": state.audio_pipeline_completed,
            "artifacts": {
                key: manager.artifact_exists(state, key)
                for key in ("audio_manifest", "narration", "subtitles_json", "subtitles_srt", "audio_qa_report")
            },
        }
    except Exception as exc:
        console.print(f"[red]读取音频状态失败：{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print_json(data=payload, ensure_ascii=False)


@app.command("runs")
def list_runs() -> None:
    """列出本地任务。"""
    config = load_config()
    manager = RunManager(config.runtime.runs_dir)
    directories = sorted((path for path in manager.runs_dir.iterdir() if path.is_dir()), reverse=True)
    for directory in directories:
        if (directory / "run_state.json").is_file():
            console.print(directory.name)


@publish_app.command("review")
def publish_review(run_id: str = typer.Argument(..., help="已有 REVIEW_READY 内容 run_id。")) -> None:
    """展示视频、封面、文案、QA 与风险，不执行投稿。"""
    try:
        payload = _publishing_service().review(run_id)
    except Exception as exc:
        console.print(f"[red]发布审核读取失败：{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print_json(data=payload, ensure_ascii=False)


@publish_app.command("approve")
def publish_approve(run_id: str = typer.Argument(..., help="已有 REVIEW_READY 内容 run_id。")) -> None:
    """显式记录人工批准，并接受当前审核页列出的 warning。"""
    try:
        job = _publishing_service().approve(run_id)
    except Exception as exc:
        console.print(f"[red]发布批准失败：{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print(f"job_id: {job.job_id}")
    console.print(f"status: {job.status}")
    console.print(f"package_hash: {job.package_hash}")


@publish_app.command("validate")
def publish_validate(run_id: str = typer.Argument(..., help="待验证 run_id。")) -> None:
    """验证 QA、文件、mock 边界、warning 接受情况与 ApprovalRecord。"""
    try:
        report = _publishing_service().validate(run_id)
    except Exception as exc:
        console.print(f"[red]发布验证失败：{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print_json(data=report.model_dump(mode="json"), ensure_ascii=False)
    if not report.passed:
        raise typer.Exit(code=1)


@publish_app.command("submit")
def publish_submit(
    run_id: str = typer.Argument(..., help="已批准且验证通过的 run_id。"),
    provider: PublishingProviderName = typer.Option(..., "--provider", help="mock 或 bilibili。"),
) -> None:
    """提交 PublishJob；Bilibili 仅使用已核验的官方授权能力。"""
    try:
        job = _publishing_service().submit(run_id, provider=provider.value)
    except Exception as exc:
        console.print(f"[red]发布提交失败：{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print(f"job_id: {job.job_id}")
    console.print(f"status: {job.status}")
    console.print(f"external_id: {job.external_id}")


@publish_app.command("status")
def publish_status(job_id: str = typer.Argument(..., help="PublishJob job_id。")) -> None:
    """查看可恢复 PublishJob 状态。"""
    try:
        job = _publishing_service().status(job_id)
    except Exception as exc:
        console.print(f"[red]读取 PublishJob 失败：{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print_json(data=job.model_dump(mode="json"), ensure_ascii=False)


@feedback_app.command("import")
def feedback_import(
    run_id: str = typer.Argument(..., help="已提交的 run_id。"),
    provider: FeedbackProviderName | None = typer.Option(None, "--provider", help="manual、mock 或 bilibili。"),
    file: Path | None = typer.Option(None, "--file", dir_okay=False, readable=True, help="manual JSON/CSV。"),
) -> None:
    """导入只读反馈，映射到现有 Analytics；不会自动回复。"""
    try:
        state = _feedback_service().import_feedback(
            run_id,
            provider=provider.value if provider else None,
            source=file,
        )
    except Exception as exc:
        console.print(f"[red]反馈导入失败：{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print(f"run_id: {state.run_id}")
    console.print(f"milestone: {state.milestone}")
    console.print(f"external_id: {state.external_id}")


@analytics_app.command("template")
def analytics_template(run_id: str = typer.Argument(..., help="已有 review_ready 任务 run_id。")) -> None:
    """生成不含假造数据的手工指标模板。"""
    try:
        path = _learning_pipeline().write_template(run_id)
    except Exception as exc:
        console.print(f"[red]模板生成失败：{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print(f"metrics template: {path}")


@analytics_app.command("import")
def analytics_import(
    run_id: str = typer.Argument(..., help="已有 review_ready 任务 run_id。"),
    file: Path = typer.Option(..., "--file", exists=True, dir_okay=False, readable=True, help="JSON 或 CSV 指标文件。"),
) -> None:
    """离线导入一条视频的手工或 mock 指标。"""
    try:
        pipeline = _learning_pipeline()
        state = pipeline.import_metrics(run_id, file)
    except Exception as exc:
        console.print(f"[red]Analytics 导入失败：{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print(f"run_id: {state.run_id}")
    console.print(f"milestone: {state.milestone}")


@app.command("analyze")
def analyze_run(run_id: str = typer.Argument(..., help="已导入 Analytics 的 run_id。")) -> None:
    """生成区分事实、推断和缺失数据的表现分析。"""
    try:
        pipeline = _learning_pipeline()
        state = pipeline.analyze(run_id)
    except Exception as exc:
        console.print(f"[red]分析失败：{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print(f"run_id: {state.run_id}")
    console.print(f"milestone: {state.milestone}")


@app.command("learn")
def learn_run(run_id: str = typer.Argument(..., help="已完成分析的 run_id。")) -> None:
    """沉淀 episode 与有证据边界的 tentative lessons。"""
    try:
        pipeline = _learning_pipeline()
        state = pipeline.learn(run_id)
    except Exception as exc:
        console.print(f"[red]学习失败：{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print(f"run_id: {state.run_id}")
    console.print(f"milestone: {state.milestone}")


@app.command("strategy")
def strategy_run(run_id: str = typer.Argument(..., help="已更新 Memory 的 run_id。")) -> None:
    """输出可验证策略与下一内容实验，不修改全局配置。"""
    try:
        pipeline = _learning_pipeline()
        state = pipeline.strategy(run_id)
    except Exception as exc:
        console.print(f"[red]策略生成失败：{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print(f"run_id: {state.run_id}")
    console.print(f"milestone: {state.milestone}")


@memory_app.command("list")
def memory_list() -> None:
    """列出长期 lesson。"""
    config = load_config()
    lessons = MemoryStore(config.learning.memory_dir).list_lessons()
    console.print_json(data=[lesson.model_dump(mode="json") for lesson in lessons], ensure_ascii=False)


@memory_app.command("show")
def memory_show(lesson_id: str = typer.Argument(..., help="lesson id。")) -> None:
    """查看一条 lesson 的证据与状态。"""
    try:
        config = load_config()
        lesson = MemoryStore(config.learning.memory_dir).show_lesson(lesson_id)
    except Exception as exc:
        console.print(f"[red]读取 lesson 失败：{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print_json(data=lesson.model_dump(mode="json"), ensure_ascii=False)


@trends_app.command("template")
def trends_template() -> None:
    """生成缺失字段保持 null 的手工趋势模板。"""
    config = load_config()
    path = TrendWorkspace(config.trends.workspace_dir).write_template()
    console.print(f"trend template: {path}")


@trends_app.command("import")
def trends_import(
    file: Path = typer.Option(..., "--file", exists=True, dir_okay=False, readable=True, help="JSON 或 CSV 趋势文件。"),
) -> None:
    """导入并规范化手工趋势；不会登录平台或猜测热度。"""
    try:
        config = load_config()
        path = TrendWorkspace(config.trends.workspace_dir).import_file(
            file,
            max_items=config.trends.max_items,
            freshness_days=config.trends.freshness_days,
        )
    except Exception as exc:
        console.print(f"[red]趋势导入失败：{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print(f"trend snapshot: {path}")


@plan_app.command("create")
def plan_create(channel_id: str | None = typer.Option(None, "--channel")) -> None:
    """立即创建一个新计划；默认仍等待人工审批。"""
    try:
        plan = _creator_loop(channel_id).create_plan()
    except Exception as exc:
        console.print(f"[red]计划创建失败：{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print(f"plan_id: {plan.plan_id}")
    console.print(f"status: {plan.status}")
    console.print(f"testing: {str(plan.testing).lower()}")


@plan_app.command("show")
def plan_show(plan_id: str = typer.Argument(..., help="内容计划 plan_id。")) -> None:
    """查看计划、槽位状态与关联 run。"""
    try:
        config = load_config()
        plan = PlanStore(config.planning.plans_dir).load_plan(plan_id)
    except Exception as exc:
        console.print(f"[red]读取计划失败：{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print_json(data=plan.model_dump(mode="json"), ensure_ascii=False)


@plan_app.command("approve")
def plan_approve(
    plan_id: str = typer.Argument(..., help="内容计划 plan_id。"),
    slot_id: str = typer.Argument(..., help="待批准 slot_id。"),
    channel_id: str | None = typer.Option(None, "--channel"),
) -> None:
    """人工批准一个槽位，并创建带完整规划来源的新 content run。"""
    try:
        plan, run = _creator_loop(channel_id).approve(plan_id, slot_id)
    except Exception as exc:
        console.print(f"[red]批准失败：{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print(f"plan_id: {plan.plan_id}")
    console.print(f"slot_id: {slot_id}")
    console.print(f"run_id: {run.run_id}")
    console.print("research_handoff: required")


@plan_app.command("reject")
def plan_reject(
    plan_id: str = typer.Argument(..., help="内容计划 plan_id。"),
    slot_id: str = typer.Argument(..., help="待拒绝 slot_id。"),
    channel_id: str | None = typer.Option(None, "--channel"),
) -> None:
    """人工拒绝一个槽位；不会创建 content run。"""
    try:
        plan = _creator_loop(channel_id).reject(plan_id, slot_id)
    except Exception as exc:
        console.print(f"[red]拒绝失败：{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print(f"plan_id: {plan.plan_id}")
    console.print(f"slot_id: {slot_id}")
    console.print("status: skipped")


@creator_loop_app.command("tick")
def creator_loop_tick(channel_id: str | None = typer.Option(None, "--channel")) -> None:
    """执行一次计划 tick；调度开关关闭时也允许显式调用。"""
    try:
        plan = _creator_loop(channel_id).tick()
    except Exception as exc:
        console.print(f"[red]Creator Loop tick 失败：{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print(f"plan_id: {plan.plan_id}")
    console.print(f"status: {plan.status}")
    console.print(f"testing: {str(plan.testing).lower()}")


@creator_loop_app.command("plan")
def creator_loop_plan(channel_id: str | None = typer.Option(None, "--channel")) -> None:
    """强制生成一个新计划，不复用当前调度窗口内计划。"""
    try:
        plan = _creator_loop(channel_id).tick(force=True)
    except Exception as exc:
        console.print(f"[red]Creator Loop plan 失败：{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print(f"plan_id: {plan.plan_id}")
    console.print(f"status: {plan.status}")


@creator_loop_app.command("run")
def creator_loop_run(
    plan_id: str = typer.Argument(..., help="已审批内容计划 plan_id。"),
    slot_id: str = typer.Argument(..., help="已审批 slot_id。"),
    channel_id: str | None = typer.Option(None, "--channel"),
) -> None:
    """显式启动 approved slot 的现有文本创作管线；不会投稿。"""
    try:
        plan, state = asyncio.run(_creator_loop(channel_id).start(plan_id, slot_id))
    except Exception as exc:
        console.print(f"[red]Creator Loop run 失败：{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print(f"plan_id: {plan.plan_id}")
    console.print(f"slot_id: {slot_id}")
    console.print(f"run_id: {state.run_id}")
    console.print(f"milestone: {state.milestone}")


@creator_loop_app.command("status")
def creator_loop_status(channel_id: str | None = typer.Option(None, "--channel")) -> None:
    """查看 Creator Loop 持久化状态。"""
    state = _creator_loop(channel_id).status()
    console.print_json(data=state.model_dump(mode="json"), ensure_ascii=False)


@operations_app.command("refresh")
def operations_refresh(
    channel_id: str | None = typer.Option(None, "--channel", help="频道标识；默认使用配置值。"),
) -> None:
    """从已有 Analytics/Memory 证据刷新频道运营快照。"""
    try:
        dashboard = _operations_service().refresh(channel_id)
    except Exception as exc:
        console.print(f"[red]运营快照刷新失败：{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print_json(data=dashboard.model_dump(mode="json"), ensure_ascii=False)


@operations_app.command("dashboard")
def operations_dashboard(
    channel_id: str | None = typer.Option(None, "--channel", help="频道标识；默认使用配置值。"),
) -> None:
    """输出幂等、可审计的频道 Dashboard JSON。"""
    config = load_config()
    selected = channel_id or config.operations.default_channel_id
    store = ChannelStore(config.learning.memory_dir)
    dashboard = store.load_dashboard(selected) or OperationsService(config).refresh(selected)
    console.print_json(data=dashboard.model_dump(mode="json"), ensure_ascii=False)


@experiment_app.command("create")
def experiment_create(
    hypothesis: str = typer.Argument(..., help="待验证假设。"),
    variable_changed: str = typer.Option(..., "--variable", help="唯一主动改变的变量。"),
    success_metric: str = typer.Option(..., "--metric", help="成功指标字段。"),
    controls: str = typer.Option(..., "--controls", help="逗号分隔的控制变量。"),
    channel_id: str | None = typer.Option(None, "--channel", help="频道标识。"),
    minimum_change: float = typer.Option(0.0, "--minimum-change", min=0.0),
) -> None:
    """创建 draft 实验；不会自动批准或启动。"""
    config = load_config()
    experiment = _experiment_manager().create(
        channel_id or config.operations.default_channel_id,
        hypothesis=hypothesis,
        variable_changed=variable_changed,
        control_variables=[item.strip() for item in controls.split(",") if item.strip()],
        success_metrics=[ExperimentMetric(metric=success_metric, minimum_relative_change=minimum_change)],
    )
    console.print_json(data=experiment.model_dump(mode="json"), ensure_ascii=False)


@experiment_app.command("approve")
def experiment_approve(
    experiment_id: str = typer.Argument(...),
    approved_by: str = typer.Option(..., "--approved-by", help="人工审核者标识。"),
    channel_id: str | None = typer.Option(None, "--channel"),
) -> None:
    """显式记录人工实验审批。"""
    config = load_config()
    experiment = _experiment_manager().approve(
        channel_id or config.operations.default_channel_id,
        experiment_id,
        approved_by=approved_by,
    )
    console.print_json(data=experiment.model_dump(mode="json"), ensure_ascii=False)


@experiment_app.command("assign")
def experiment_assign(
    experiment_id: str = typer.Argument(...),
    run_id: str = typer.Argument(...),
    group: str = typer.Option(..., "--group", help="control 或 treatment。"),
    source: str = typer.Option("manual", "--source", help="manual/platform/mock/testing。"),
    channel_id: str | None = typer.Option(None, "--channel"),
) -> None:
    """将已有 run 幂等分配到人工批准的实验组。"""
    config = load_config()
    experiment = _experiment_manager().assign(
        channel_id or config.operations.default_channel_id,
        experiment_id,
        run_id=run_id,
        experiment_group=group,
        source=source,
    )
    console.print_json(data=experiment.model_dump(mode="json"), ensure_ascii=False)


@experiment_app.command("evaluate")
def experiment_evaluate(
    experiment_id: str = typer.Argument(...),
    channel_id: str | None = typer.Option(None, "--channel"),
) -> None:
    """使用已有 Analytics 评估实验；不会自动改动创作配置。"""
    config = load_config()
    selected = channel_id or config.operations.default_channel_id
    service = OperationsService(config)
    experiment = _experiment_manager().evaluate(
        selected,
        experiment_id,
        service.collect_snapshots(selected),
    )
    console.print_json(data=experiment.model_dump(mode="json"), ensure_ascii=False)


@identity_app.command("show")
def identity_show() -> None:
    """显示当前 Creator Identity，并生成安全的 Identity Card。"""
    try:
        identity = _identity_service().ensure()
    except Exception as exc:
        console.print(f"[red]读取身份失败：{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print(yaml.safe_dump(identity.model_dump(mode="json"), allow_unicode=True, sort_keys=False).rstrip())


@identity_app.command("history")
def identity_history() -> None:
    """列出不可覆盖的 Creator Identity 历史版本。"""
    try:
        service = _identity_service()
        service.ensure()
        history = service.store.list_history()
    except Exception as exc:
        console.print(f"[red]读取身份历史失败：{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print_json(
        data=[
            {
                "version": item.version,
                "creator_name": item.creator_name,
                "mission_statement": item.mission_statement,
                "updated_at": item.updated_at.isoformat(),
            }
            for item in history
        ],
        ensure_ascii=False,
    )


@identity_app.command("check")
def identity_check(run_id: str = typer.Argument(..., help="待检查的内容 run_id。")) -> None:
    """检查 run 的身份边界，并保存可调试 Prompt Context。"""
    try:
        report = _identity_service().check_run(run_id)
    except Exception as exc:
        console.print(f"[red]身份检查失败：{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print_json(data=report.model_dump(mode="json"), ensure_ascii=False)


@identity_app.command("propose")
def identity_propose(
    field: str = typer.Option("content_philosophy", "--field", help="待修改的顶层身份字段。"),
    value: str | None = typer.Option(None, "--value", help="候选值；省略时生成保守的默认候选。"),
    reason: str = typer.Option("alpha10 身份审计候选；尚未应用。", "--reason"),
    evidence: str = typer.Option("manual:alpha10_identity_review", "--evidence"),
) -> None:
    """创建待人工批准的身份变更提案，不修改当前身份。"""
    try:
        service = _identity_service()
        current = service.ensure()
        candidate = value or (
            f"{current.content_philosophy}；证据不足时明确说明未知与限制"
            if field == "content_philosophy"
            else str(current.model_dump(mode="json").get(field, "待人工定义"))
        )
        proposal = service.evolution().propose(
            proposed_change={field: candidate},
            reason=reason,
            evidence=[item.strip() for item in evidence.split(",") if item.strip()],
            expected_effect="提高创作者身份与内容表达的一致性",
            risk="未经跨视频验证的变更可能缩窄表达空间",
        )
    except Exception as exc:
        console.print(f"[red]身份提案创建失败：{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print_json(data=proposal.model_dump(mode="json"), ensure_ascii=False)


@identity_app.command("approve")
def identity_approve(
    proposal_id: str = typer.Argument(..., help="待批准 proposal id。"),
    approved_by: str = typer.Option(..., "--approved-by", help="明确的人工审核者标识。"),
) -> None:
    """显式人工批准提案并创建新身份版本。"""
    try:
        identity = _identity_service().evolution().approve(proposal_id, approved_by=approved_by)
    except Exception as exc:
        console.print(f"[red]身份提案批准失败：{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print_json(data=identity.model_dump(mode="json"), ensure_ascii=False)


@style_app.command("check")
def style_check(run_id: str = typer.Argument(..., help="待检查的完整内容 run_id。")) -> None:
    """生成幂等 StyleConsistencyReport；只建议，不自动修改。"""
    try:
        report = _identity_service().style_check(run_id)
    except Exception as exc:
        console.print(f"[red]Style QA 失败：{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print_json(data=report.model_dump(mode="json"), ensure_ascii=False)


@production_app.command("plan")
def production_plan(
    run_id: str = typer.Argument(..., help="已有内容 run_id。"),
    quality: ProductionQualityName | None = typer.Option(None, "--quality"),
    operation: str = typer.Option("full", "--operation", help="text|audio|video|package|full"),
) -> None:
    """生成并选择可解释 ProductionPlan，同时保留同 profile 的历史计划文件。"""
    try:
        plan = _production_service(run_id).plan(
            run_id,
            requested_operation=operation,
            quality_target=quality.value if quality else None,
            select=True,
        )
    except Exception as exc:
        console.print(f"[red]Production plan 失败：{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print_json(data=plan.model_dump(mode="json"), ensure_ascii=False)


@production_app.command("status")
def production_status(run_id: str = typer.Argument(..., help="已有 ProductionPlan 的 run_id。")) -> None:
    """查看所选计划、执行记录、fallback 与质量闸门状态。"""
    try:
        status_payload = _production_service(run_id).status(run_id)
    except Exception as exc:
        console.print(f"[red]Production status 失败：{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print_json(data=status_payload, ensure_ascii=False)


@production_app.command("report")
def production_report(run_id: str = typer.Argument(..., help="已有 ProductionPlan 的 run_id。")) -> None:
    """运行 ProductionQualityGate 并生成可审计生产报告。"""
    try:
        service = _production_service(run_id)
        service.quality_gate(run_id)
        report = service.report(run_id)
    except Exception as exc:
        console.print(f"[red]Production report 失败：{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print_json(data=report.model_dump(mode="json"), ensure_ascii=False)


@production_app.command("approve-policy")
def production_approve_policy(
    run_id: str = typer.Argument(..., help="被 cloud cost 等策略阻止的 run_id。"),
    approved_by: str = typer.Option(..., "--approved-by", help="明确的人类审核者标识。"),
) -> None:
    """确认当前计划的可确认策略风险；不改变全局预算或发布审批。"""
    try:
        record = _production_service(run_id).approve_policy(run_id, approved_by=approved_by)
    except Exception as exc:
        console.print(f"[red]Production policy approval 失败：{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print_json(data=record, ensure_ascii=False)


@studio_app.command("agents")
def studio_agents() -> None:
    """列出角色职责、允许 provider 与产物边界。"""
    console.print_json(
        data=[item.model_dump(mode="json") for item in AgentRegistry().list()],
        ensure_ascii=False,
    )


@studio_app.command("status")
def studio_status(run_id: str = typer.Argument(..., help="已有内容 run_id。")) -> None:
    """查看 Studio 状态、handoff/result/trace 数量和 Studio QA。"""
    try:
        payload = _studio_director(run_id).status(run_id)
    except Exception as exc:
        console.print(f"[red]Studio status 失败：{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print_json(data=payload, ensure_ascii=False)


@studio_app.command("trace")
def studio_trace(run_id: str = typer.Argument(..., help="已有内容 run_id。")) -> None:
    """输出已脱敏的 Studio trace JSONL 记录。"""
    try:
        payload = _studio_director(run_id).trace(run_id)
    except Exception as exc:
        console.print(f"[red]Studio trace 失败：{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print_json(data=payload, ensure_ascii=False)


@studio_app.command("run")
def studio_run(run_id: str = typer.Argument(..., help="已有内容 run_id。")) -> None:
    """由唯一 StudioDirector 串行推进现有流水线；不会绕过审批。"""
    try:
        state = asyncio.run(_studio_director(run_id).run(run_id))
    except Exception as exc:
        console.print(f"[red]Studio run 失败：{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print_json(data=state.model_dump(mode="json"), ensure_ascii=False)


@studio_app.command("resume")
def studio_resume(run_id: str = typer.Argument(..., help="已有 Studio run_id。")) -> None:
    """幂等恢复 Studio；从现有 artifact/handoff 状态继续。"""
    try:
        state = asyncio.run(_studio_director(run_id).resume(run_id))
    except Exception as exc:
        console.print(f"[red]Studio resume 失败：{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print_json(data=state.model_dump(mode="json"), ensure_ascii=False)


@supervisor_app.command("tick")
def supervisor_tick() -> None:
    """执行一次有动作/派发上限的长期 Supervisor tick。"""
    try:
        state = asyncio.run(_supervisor().tick())
    except Exception as exc:
        console.print(f"[red]Supervisor tick 失败：{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print_json(data=state.model_dump(mode="json"), ensure_ascii=False)


@supervisor_app.command("status")
def supervisor_status() -> None:
    """查看长期 Supervisor 的当前状态与产物计数。"""
    try:
        payload = _supervisor().status()
    except Exception as exc:
        console.print(f"[red]Supervisor status 失败：{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print_json(data=payload, ensure_ascii=False)


@supervisor_app.command("goals")
def supervisor_goals() -> None:
    """列出显式、可暂停/可取消的长期目标。"""
    try:
        service = _supervisor()
        payload = [item.model_dump(mode="json") for item in service.store.list_goals()]
    except Exception as exc:
        console.print(f"[red]读取 Supervisor goals 失败：{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print_json(data=payload, ensure_ascii=False)


@supervisor_app.command("plan")
def supervisor_plan(goal_id: str = typer.Argument(..., help="长期 goal_id。")) -> None:
    """显示 goal 最新的版本化 LongHorizonPlan。"""
    try:
        plan = _supervisor().store.latest_plan_for_goal(goal_id)
    except Exception as exc:
        console.print(f"[red]读取 Supervisor plan 失败：{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print_json(data=plan.model_dump(mode="json"), ensure_ascii=False)


@supervisor_app.command("review")
def supervisor_review(goal_id: str = typer.Argument(..., help="长期 goal_id。")) -> None:
    """生成阶段复盘；重大 replan 只形成待批 proposal。"""
    try:
        review = _supervisor().review(goal_id)
    except Exception as exc:
        console.print(f"[red]Supervisor review 失败：{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print_json(data=review.model_dump(mode="json"), ensure_ascii=False)


@supervisor_app.command("blockers")
def supervisor_blockers(goal_id: str | None = typer.Argument(None, help="可选 goal_id。")) -> None:
    """解释 goal、run、审批和前后依赖阻塞。"""
    try:
        payload = _supervisor().blockers(goal_id)
    except Exception as exc:
        console.print(f"[red]Supervisor blockers 失败：{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print_json(data=payload, ensure_ascii=False)


@supervisor_app.command("goal-status")
def supervisor_goal_status(
    goal_id: str = typer.Argument(..., help="长期 goal_id。"),
    status: str = typer.Argument(..., help="draft|active|paused|completed|cancelled|blocked。"),
) -> None:
    """显式暂停、恢复、完成、取消或阻塞长期目标。"""
    try:
        goal = _supervisor().set_goal_status(goal_id, status)
    except Exception as exc:
        console.print(f"[red]修改 goal status 失败：{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print_json(data=goal.model_dump(mode="json"), ensure_ascii=False)


@supervisor_app.command("approve-run")
def supervisor_approve_run(
    planned_run_id: str = typer.Argument(..., help="待批准 planned_run_id。"),
    approved_by: str = typer.Option(..., "--approved-by", help="人工审核者标识。"),
) -> None:
    """显式批准单条长期计划内容；Supervisor 不能自行调用此命令。"""
    try:
        run = _supervisor().approve_planned_run(planned_run_id, approved_by=approved_by)
    except Exception as exc:
        console.print(f"[red]planned run 批准失败：{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print_json(data=run.model_dump(mode="json"), ensure_ascii=False)


@supervisor_app.command("replan")
def supervisor_replan(
    goal_id: str = typer.Argument(..., help="长期 goal_id。"),
    reason: str = typer.Option(..., "--reason", help="发生变化及原因。"),
) -> None:
    """只创建待人工批准的新版本提案，不覆盖当前计划。"""
    try:
        proposal = _supervisor().propose_replan(
            goal_id,
            what_changed=[reason],
            why=[reason],
            impact=["等待人工评估后才可能应用"],
            risks=["重规划可能改变排期和资源分配"],
        )
    except Exception as exc:
        console.print(f"[red]ReplanProposal 创建失败：{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print_json(data=proposal.model_dump(mode="json"), ensure_ascii=False)


@supervisor_app.command("qa")
def supervisor_qa() -> None:
    """检查可测量性、预算、循环依赖、审批和计划边界。"""
    try:
        report = _supervisor().qa()
    except Exception as exc:
        console.print(f"[red]Supervisor QA 失败：{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print_json(data=report.model_dump(mode="json"), ensure_ascii=False)
    if not report.passed:
        raise typer.Exit(code=1)


@supervisor_app.command("demo")
def supervisor_demo() -> None:
    """运行完全离线的四期系列、blocker、预算暂停、review 与 replan demo。"""
    try:
        payload = asyncio.run(exercise_demo(load_config()))
    except Exception as exc:
        console.print(f"[red]Supervisor demo 失败：{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print_json(data=payload, ensure_ascii=False)


@visual_app.command("doctor")
def visual_doctor() -> None:
    """只读检查 ComfyUI/H3、本机显存与 workflow 配置。"""
    console.print_json(data=VisualGenerationService(load_config()).doctor(), ensure_ascii=False)


@local_create_app.command("run")
def local_create_run(spec_file: Path = typer.Argument(..., help="UTF-8 JSON 创作规格文件。")) -> None:
    """提交并同步执行真实本地生成；不发布。"""
    try:
        spec = LocalCreationSpec.model_validate_json(spec_file.read_text(encoding="utf-8"))
        service = LocalCreatorService(load_config())
        job = service.submit(spec)
        console.print(f"run_id: {job['run_id']}")
        result = service.run(job["run_id"])
    except Exception as exc:
        console.print(f"[red]本地创作失败：{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print_json(data=result, ensure_ascii=False)
    if result["status"] != "COMPLETE":
        raise typer.Exit(code=1)


@local_create_app.command("resume")
def local_create_resume(run_id: str = typer.Argument(..., help="此前 local-create run_id。")) -> None:
    """跳过哈希有效的片段与语音，从失败阶段继续。"""
    result = LocalCreatorService(load_config()).run(run_id)
    console.print_json(data=result, ensure_ascii=False)
    if result["status"] != "COMPLETE":
        raise typer.Exit(code=1)


@local_create_app.command("status")
def local_create_status(run_id: str = typer.Argument(..., help="local-create run_id。")) -> None:
    console.print_json(data=LocalCreatorService(load_config()).status(run_id), ensure_ascii=False)


@local_create_app.command("list")
def local_create_list() -> None:
    console.print_json(data=LocalCreatorService(load_config()).list(), ensure_ascii=False)


@visual_app.command("h3-setup-status")
def visual_h3_setup_status() -> None:
    """检查真实 ComfyUI、H3 权重、API workflow 与当前资源预算。"""
    console.print_json(data=VisualGenerationService(load_config()).h3_setup_status(), ensure_ascii=False)


@visual_app.command("h3-smoke-test")
def visual_h3_smoke_test() -> None:
    """显式运行一次真实、低分辨率、串行的本地 H3 T2V 集成测试。"""
    try:
        payload = VisualGenerationService(load_config()).h3_smoke_test()
    except Exception as exc:
        console.print(f"[red]H3 smoke test 失败：{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print_json(data=payload, ensure_ascii=False)


@visual_app.command("dynamic-wallpaper")
def visual_dynamic_wallpaper(
    image: Path = typer.Option(..., "--image", help="单张本地参考图片。"),
    prompt: str | None = typer.Option(None, "--prompt", help="动作提示词。"),
    prompt_file: Path | None = typer.Option(None, "--prompt-file", help="UTF-8 动作提示词文件。"),
    output_dir: Path | None = typer.Option(None, "--output-dir", help="运行记录和 MP4 的输出目录。"),
) -> None:
    """动态壁纸制作：分阶段 H3 单图生成 720p 视频，仅供人工审看。"""
    if (prompt is None) == (prompt_file is None):
        raise typer.BadParameter("必须且只能提供 --prompt 或 --prompt-file")
    try:
        text = prompt if prompt is not None else prompt_file.read_text(encoding="utf-8")
        result = VisualGenerationService(load_config()).dynamic_wallpaper(
            image, text, output_dir=output_dir,
        )
    except Exception as exc:
        console.print(f"[red]动态壁纸制作失败：{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print_json(data=result, ensure_ascii=False)


@visual_app.command("dynamic-wallpaper-resume")
def visual_dynamic_wallpaper_resume(
    run_dir: Path = typer.Argument(..., help="此前动态壁纸运行记录目录。"),
) -> None:
    """从已完成的 H3 阶段后继续，不重复生成有效中间产物。"""
    try:
        result = VisualGenerationService(load_config()).resume_dynamic_wallpaper(run_dir)
    except Exception as exc:
        console.print(f"[red]动态壁纸恢复失败：{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print_json(data=result, ensure_ascii=False)


@visual_app.command("plan")
def visual_plan(run_id: str = typer.Argument(..., help="已有 storyboard 的 run_id。")) -> None:
    """按镜头类型、质量目标与 H3 预算生成混合视觉计划。"""
    try:
        plan = VisualGenerationService(load_config()).plan(run_id)
    except Exception as exc:
        console.print(f"[red]Visual plan 失败：{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print_json(data=plan.model_dump(mode="json"), ensure_ascii=False)


@visual_app.command("generate")
def visual_generate(
    run_id: str = typer.Argument(..., help="已有 visual plan 的 run_id。"),
    provider: VisualProviderName | None = typer.Option(None, "--provider"),
    force: bool = typer.Option(False, "--force", help="忽略已有 manifest 并重跑。"),
) -> None:
    """串行生成 H3 路由镜头；mock 产物永远不可提升到 production review。"""
    try:
        manifest = VisualGenerationService(load_config()).generate(
            run_id, provider=provider.value if provider else None, force=force
        )
    except Exception as exc:
        console.print(f"[red]Visual generate 失败：{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print_json(data=manifest.model_dump(mode="json"), ensure_ascii=False)


@visual_app.command("status")
def visual_status(run_id: str = typer.Argument(..., help="visual run_id。")) -> None:
    """显示可恢复本地视觉队列、plan 和 review gate 状态。"""
    try:
        payload = VisualGenerationService(load_config()).status(run_id)
    except Exception as exc:
        console.print(f"[red]Visual status 失败：{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print_json(data=payload, ensure_ascii=False)


@capability_app.command("list")
def capability_list() -> None:
    """列出现有 agents/workers/providers/skills 对应的初始能力清单。"""
    service = CapabilityService(load_config())
    console.print_json(data=[item.model_dump(mode="json") for item in service.list_capabilities()], ensure_ascii=False)


@capability_app.command("evaluate")
def capability_evaluate() -> None:
    """基于 QA、trace、metrics 与人工证据进行自评并保存 gap。"""
    try:
        report = CapabilityService(load_config()).evaluate()
    except Exception as exc:
        console.print(f"[red]Capability evaluate 失败：{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print_json(data=report.model_dump(mode="json"), ensure_ascii=False)


@gaps_app.command("list")
def gaps_list() -> None:
    service = CapabilityService(load_config())
    console.print_json(data=[item.model_dump(mode="json") for item in service.list_gaps()], ensure_ascii=False)


@skill_app.command("propose")
def skill_propose(gap_id: str = typer.Argument(..., help="有证据的 gap_id。")) -> None:
    try:
        proposal = CapabilityService(load_config()).skills.propose(gap_id)
    except Exception as exc:
        console.print(f"[red]Skill propose 失败：{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print_json(data=proposal.model_dump(mode="json"), ensure_ascii=False)


@skill_app.command("test")
def skill_test(skill_id: str = typer.Argument(..., help="待评测 skill_id。")) -> None:
    """在逻辑 sandbox 中运行声明式五类评测；不执行外部未知代码。"""
    try:
        report = CapabilityService(load_config()).skills.test(skill_id)
    except Exception as exc:
        console.print(f"[red]Skill test 失败：{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print_json(data=report.model_dump(mode="json"), ensure_ascii=False)


@skill_app.command("review")
def skill_review(
    skill_id: str = typer.Argument(...),
    reviewer: str = typer.Option("human:cli-reviewer", "--reviewer"),
    notes: str = typer.Option("", "--notes"),
) -> None:
    try:
        record = CapabilityService(load_config()).skills.review(skill_id, reviewer=reviewer, notes=notes)
    except Exception as exc:
        console.print(f"[red]Skill review 失败：{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print_json(data=record.model_dump(mode="json"), ensure_ascii=False)


@skill_app.command("approve")
def skill_approve(
    skill_id: str = typer.Argument(...),
    approved_by: str = typer.Option(..., "--approved-by", help="必须为 human:<name>。"),
    evaluation_id: str = typer.Option(..., "--evaluation-id", help="必须通过 Alpha18 EvaluationGate 的 candidate evaluation。"),
    baseline_id: str = typer.Option(..., "--baseline-id", help="用于比较的已保存 baseline。"),
) -> None:
    try:
        gate = EvaluationService(load_config()).gate(evaluation_id, baseline_id=baseline_id)
        EvaluationGate.require_promotion_allowed(gate)
        record = CapabilityService(load_config()).skills.approve(skill_id, approved_by=approved_by)
    except Exception as exc:
        console.print(f"[red]Skill approve 失败：{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print_json(
        data={"skill": record.model_dump(mode="json"), "evaluation_gate": gate.model_dump(mode="json")},
        ensure_ascii=False,
    )


@skill_app.command("disable")
def skill_disable(skill_id: str = typer.Argument(...)) -> None:
    try:
        record = CapabilityService(load_config()).skills.disable(skill_id)
    except Exception as exc:
        console.print(f"[red]Skill disable 失败：{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print_json(data=record.model_dump(mode="json"), ensure_ascii=False)


@skill_app.command("rollback")
def skill_rollback(skill_id: str = typer.Argument(...), target_version: int = typer.Argument(..., min=1)) -> None:
    try:
        record = CapabilityService(load_config()).skills.rollback(skill_id, target_version)
    except Exception as exc:
        console.print(f"[red]Skill rollback 失败：{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print_json(data=record.model_dump(mode="json"), ensure_ascii=False)


@workflow_app.command("plan")
def workflow_plan(
    task: str = typer.Option(..., "--task", help="WorkflowTask JSON 文件路径或已保存 task_id。"),
) -> None:
    try:
        service = WorkflowService(load_config())
        model = service.store.load_task(task)
        plan = service.plan(model)
    except Exception as exc:
        console.print(f"[red]Workflow plan 失败：{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print_json(data=plan.model_dump(mode="json"), ensure_ascii=False)


@simulate_app.command("create")
def simulate_create(
    task: str = typer.Option(..., "--task", help="SimulationScenario 或 WorkflowTask JSON 文件/ID。"),
) -> None:
    try:
        scenario = SimulationService(load_config()).create_from_task(task)
    except Exception as exc:
        console.print(f"[red]Simulation create 失败：{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print_json(data=scenario.model_dump(mode="json"), ensure_ascii=False)


@simulate_app.command("run")
def simulate_run(scenario_id: str = typer.Argument(...)) -> None:
    try:
        results = SimulationService(load_config()).run(scenario_id)
    except Exception as exc:
        console.print(f"[red]Simulation run 失败：{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print_json(data=results.model_dump(mode="json"), ensure_ascii=False)


@simulate_app.command("compare")
def simulate_compare(scenario_id: str = typer.Argument(...)) -> None:
    try:
        comparison, decision = SimulationService(load_config()).compare(scenario_id)
    except Exception as exc:
        console.print(f"[red]Simulation compare 失败：{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print_json(data={
        "comparison": comparison.model_dump(mode="json"),
        "decision": decision.model_dump(mode="json"),
    }, ensure_ascii=False)


@simulate_app.command("show")
def simulate_show(scenario_id: str = typer.Argument(...)) -> None:
    try:
        payload = SimulationService(load_config()).show(scenario_id)
    except Exception as exc:
        console.print(f"[red]Simulation show 失败：{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print_json(data=payload, ensure_ascii=False)


@simulate_app.command("calibrate")
def simulate_calibrate(
    scenario_id: str = typer.Argument(...),
    actual: Path = typer.Option(..., "--actual", exists=True, dir_okay=False),
) -> None:
    try:
        record = SimulationService(load_config()).calibrate(scenario_id, actual)
    except Exception as exc:
        console.print(f"[red]Simulation calibrate 失败：{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print_json(data=record.model_dump(mode="json"), ensure_ascii=False)


@simulate_app.command("history")
def simulate_history() -> None:
    console.print_json(data=SimulationService(load_config()).history(), ensure_ascii=False)


@workflow_app.command("validate")
def workflow_validate(workflow_id: str = typer.Argument(...)) -> None:
    try:
        report = WorkflowService(load_config()).validate(workflow_id)
    except Exception as exc:
        console.print(f"[red]Workflow validate 失败：{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print_json(data=report.model_dump(mode="json"), ensure_ascii=False)
    if not report.passed:
        raise typer.Exit(code=1)


@workflow_app.command("run")
def workflow_run(workflow_id: str = typer.Argument(...)) -> None:
    try:
        state = WorkflowService(load_config()).run(workflow_id)
    except Exception as exc:
        console.print(f"[red]Workflow run 失败：{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print_json(data=state.model_dump(mode="json"), ensure_ascii=False)


@workflow_app.command("resume")
def workflow_resume(workflow_id: str = typer.Argument(...)) -> None:
    try:
        state = WorkflowService(load_config()).resume(workflow_id)
    except Exception as exc:
        console.print(f"[red]Workflow resume 失败：{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print_json(data=state.model_dump(mode="json"), ensure_ascii=False)


@workflow_app.command("status")
def workflow_status(workflow_id: str = typer.Argument(...)) -> None:
    try:
        payload = WorkflowService(load_config()).status(workflow_id)
    except Exception as exc:
        console.print(f"[red]Workflow status 失败：{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print_json(data=payload, ensure_ascii=False)


@workflow_app.command("report")
def workflow_report(workflow_id: str = typer.Argument(...)) -> None:
    try:
        payload = WorkflowService(load_config()).report(workflow_id)
    except Exception as exc:
        console.print(f"[red]Workflow report 失败：{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print_json(data=payload, ensure_ascii=False)


@workflow_app.command("qa")
def workflow_qa(workflow_id: str = typer.Argument(...)) -> None:
    try:
        report = WorkflowService(load_config()).qa(workflow_id)
    except Exception as exc:
        console.print(f"[red]Workflow QA 失败：{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print_json(data=report.model_dump(mode="json"), ensure_ascii=False)
    if not report.passed:
        raise typer.Exit(code=1)


@workflow_app.command("recipes")
def workflow_recipes() -> None:
    recipes = WorkflowService(load_config()).recipes.list()
    console.print_json(data=[item.model_dump(mode="json") for item in recipes], ensure_ascii=False)


@workflow_app.command("recipe-show")
def workflow_recipe_show(recipe_id: str = typer.Argument(...)) -> None:
    try:
        recipe = WorkflowService(load_config()).recipes.get(recipe_id)
    except Exception as exc:
        console.print(f"[red]Workflow recipe-show 失败：{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print_json(data=recipe.model_dump(mode="json"), ensure_ascii=False)


@workflow_app.command("demo-a")
def workflow_demo_a() -> None:
    console.print_json(data=visual_enhancement_demo(load_config()), ensure_ascii=False)


@workflow_app.command("demo-repair")
def workflow_demo_repair() -> None:
    console.print_json(data=failure_repair_resume_demo(load_config()), ensure_ascii=False)


@workflow_app.command("demo-b")
def workflow_demo_b() -> None:
    console.print_json(data=capability_gap_demo(load_config()), ensure_ascii=False)


@workflow_app.command("demo-c")
def workflow_demo_c() -> None:
    console.print_json(data=recipe_learning_demo(load_config()), ensure_ascii=False)


@knowledge_app.command("status")
def knowledge_status() -> None:
    console.print_json(data=_knowledge_service().store.status(), ensure_ascii=False)


@knowledge_app.command("claims")
def knowledge_claims(topic: str | None = typer.Option(None, "--topic")) -> None:
    claims = _knowledge_service().store.list_claims(topic)
    console.print_json(data=[item.model_dump(mode="json") for item in claims], ensure_ascii=False)


@knowledge_app.command("sources")
def knowledge_sources(claim_id: str = typer.Option(..., "--claim")) -> None:
    service = _knowledge_service()
    try:
        claim = service.store.get_claim(claim_id)
        sources = [service.store.get_source(item) for item in claim.evidence_refs]
    except Exception as exc:
        console.print(f"[red]Knowledge sources 失败：{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print_json(data=[item.model_dump(mode="json") for item in sources], ensure_ascii=False)


@knowledge_app.command("conflicts")
def knowledge_conflicts() -> None:
    items = _knowledge_service().store.list_conflicts(open_only=False)
    console.print_json(data=[item.model_dump(mode="json") for item in items], ensure_ascii=False)


@knowledge_app.command("stale")
def knowledge_stale() -> None:
    service = _knowledge_service()
    items = [
        service.freshness.assess(claim)
        for claim in service.store.active_claims()
        if service.freshness.assess(claim).state in {"aging", "stale", "reverify_required"}
    ]
    console.print_json(data=[item.model_dump(mode="json") for item in items], ensure_ascii=False)


@knowledge_app.command("verify")
def knowledge_verify(claim_id: str = typer.Argument(...)) -> None:
    service = _knowledge_service()
    try:
        result = service.verifier.verify_existing(claim_id)
        if result.status in {"verified", "provisional"}:
            claim = service.store.get_claim(claim_id)
            claim.status = result.status
            claim.confidence = result.confidence
            claim.last_verified_at = datetime.now().astimezone()
            claim.updated_at = claim.last_verified_at
            service.store.add_claim(claim)
    except Exception as exc:
        console.print(f"[red]Knowledge verify 失败：{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print_json(data=result.model_dump(mode="json"), ensure_ascii=False)


@knowledge_app.command("tick")
def knowledge_tick() -> None:
    service = _knowledge_service()
    if not service.config.knowledge.maintenance_tick_enabled:
        console.print_json(data={"enabled": False, "reason": "knowledge.maintenance_tick_enabled=false"}, ensure_ascii=False)
        return
    report = service.maintenance.tick()
    console.print_json(data=report.model_dump(mode="json"), ensure_ascii=False)


@knowledge_app.command("qa")
def knowledge_qa() -> None:
    report = _knowledge_service().qa.run()
    console.print_json(data=report.model_dump(mode="json"), ensure_ascii=False)
    if not report.passed:
        raise typer.Exit(code=1)


@knowledge_app.command("demo-a")
def knowledge_demo_a() -> None:
    console.print_json(
        data=demo_a_supersession(
            _knowledge_demo_service(),
            run_root=Path("workspace/knowledge_demos/alpha17/runs"),
        ),
        ensure_ascii=False,
    )


@knowledge_app.command("demo-b")
def knowledge_demo_b() -> None:
    console.print_json(data=demo_b_conflict(_knowledge_demo_service()), ensure_ascii=False)


@knowledge_app.command("demo-c")
def knowledge_demo_c() -> None:
    console.print_json(data=demo_c_stale_block(_knowledge_demo_service()), ensure_ascii=False)


@knowledge_app.command("demo-d")
def knowledge_demo_d() -> None:
    console.print_json(data=demo_d_h3_observation(_knowledge_service()), ensure_ascii=False)


@knowledge_app.command("demo-grounding")
def knowledge_demo_grounding() -> None:
    console.print_json(data=demo_grounding_run(_knowledge_service()), ensure_ascii=False)


@research_app.command("task")
def research_task(
    question: str = typer.Argument(...),
    quality: str = typer.Option("medium", "--quality"),
    freshness_days: int | None = typer.Option(None, "--freshness-days", min=1),
) -> None:
    try:
        task = _knowledge_service().research_tasks.create(
            question,
            required_evidence_quality=quality,
            freshness_requirement_days=freshness_days,
        )
    except Exception as exc:
        console.print(f"[red]Research task 失败：{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print_json(data=task.model_dump(mode="json"), ensure_ascii=False)


@grounding_app.command("check")
def grounding_check(run_id: str = typer.Argument(...)) -> None:
    try:
        config = _config_for_run(run_id)
        manager = RunManager(config.runtime.runs_dir)
        state = manager.load(run_id)
        script = Script.model_validate(manager.read_json(run_id, state.artifacts["script"]))
        service = _knowledge_service(config)
        report = service.grounding.check(script, run_id=run_id)
        service.grounding.save(report, manager.run_dir(run_id))
        qa = service.qa.run(grounding=report)
        manager.write_json(run_id, "knowledge/knowledge_qa_report.json", qa.model_dump(mode="json"))
    except Exception as exc:
        console.print(f"[red]Grounding check 失败：{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print_json(data={"grounding": report.model_dump(mode="json"), "knowledge_qa": qa.model_dump(mode="json")}, ensure_ascii=False)
    if not report.passed or not qa.passed:
        raise typer.Exit(code=1)


@eval_app.command("list")
def eval_list(include_integration: bool = typer.Option(True, "--include-integration/--offline-only")) -> None:
    service = EvaluationService(load_config())
    console.print_json(
        data={
            "registry_version": service.registry.version,
            "categories": service.registry.categories,
            "cases": service.list_cases(include_integration=include_integration),
        },
        ensure_ascii=False,
    )


@eval_app.command("run")
def eval_run(
    label: str = typer.Option("candidate", "--label"),
    integration: bool = typer.Option(False, "--integration"),
    regression_injection: str | None = typer.Option(None, "--inject-regression"),
) -> None:
    if regression_injection not in {None, "subtitle_timing"}:
        console.print("[red]仅支持隔离的测试注入：subtitle_timing[/red]")
        raise typer.Exit(code=2)
    run = EvaluationService(load_config()).run(
        label=label,
        integration=integration,
        regression_injection=regression_injection,
    )
    console.print_json(data=run.model_dump(mode="json"), ensure_ascii=False)
    if run.status != "completed":
        raise typer.Exit(code=2)


@eval_app.command("baseline-create")
def eval_baseline_create(
    label: str = typer.Option("alpha17-baseline", "--label"),
    version: str = typer.Option("alpha17", "--version"),
) -> None:
    baseline = EvaluationService(load_config()).create_baseline(label=label, version=version)
    console.print_json(data=baseline.model_dump(mode="json"), ensure_ascii=False)


@eval_app.command("compare")
def eval_compare(baseline_id: str = typer.Argument(...), evaluation_id: str = typer.Argument(...)) -> None:
    comparison = EvaluationService(load_config()).compare(baseline_id, evaluation_id)
    console.print_json(data=comparison.model_dump(mode="json"), ensure_ascii=False)


@eval_app.command("report")
def eval_report(evaluation_id: str = typer.Argument(...)) -> None:
    console.print_json(data=EvaluationService(load_config()).report(evaluation_id), ensure_ascii=False)


@eval_app.command("gate")
def eval_gate(
    evaluation_id: str = typer.Argument(...),
    baseline_id: str | None = typer.Option(None, "--baseline-id"),
) -> None:
    gate = EvaluationService(load_config()).gate(evaluation_id, baseline_id=baseline_id)
    console.print_json(data=gate.model_dump(mode="json"), ensure_ascii=False)
    if gate.status == "BLOCKED":
        raise typer.Exit(code=2)


@reliability_app.command("status")
def reliability_status(run_id: str | None = typer.Argument(None)) -> None:
    console.print_json(data=ReliabilityService(load_config()).status(run_id), ensure_ascii=False)


@reliability_app.command("failures")
def reliability_failures(run_id: str = typer.Argument(...)) -> None:
    service = ReliabilityService(load_config())
    console.print_json(
        data=[item.model_dump(mode="json") for item in service.failures(run_id).list(run_id=run_id)],
        ensure_ascii=False,
    )


@reliability_app.command("demo")
def reliability_demo(evidence_dir: Path | None = typer.Option(None, "--evidence-dir")) -> None:
    """运行 Alpha19 四个确定性故障恢复 demo；不会加载真实 H3 大模型。"""
    from alysia.reliability.demos import run_reliability_demos

    result = run_reliability_demos(load_config(), evidence_dir)
    console.print_json(data=result, ensure_ascii=False)
    if result["status"] != "PASS":
        raise typer.Exit(code=2)


@security_app.command("status")
def security_status() -> None:
    console.print_json(data=_security_service().status().model_dump(mode="json"), ensure_ascii=False)


@security_app.command("permissions")
def security_permissions() -> None:
    console.print_json(data=_security_service().permissions(), ensure_ascii=False)


@security_app.command("audit")
def security_audit(run_id: str | None = typer.Option(None, "--run-id")) -> None:
    events = _security_service().audit.list(run_id=run_id)
    console.print_json(data=[item.model_dump(mode="json") for item in events], ensure_ascii=False)


@security_app.command("scan")
def security_scan(path_or_run: str = typer.Argument(...)) -> None:
    config = load_config()
    candidate = Path(path_or_run)
    if not candidate.exists():
        candidate = config.runtime.runs_dir / path_or_run
    if not candidate.exists():
        console.print(f"[red]安全扫描目标不存在：{path_or_run}[/red]")
        raise typer.Exit(code=1)
    report = SecurityService(config).scanner.scan(candidate)
    console.print_json(data=report.model_dump(mode="json"), ensure_ascii=False)


@security_app.command("approvals")
def security_approvals(subject: str | None = typer.Argument(None)) -> None:
    config = load_config()
    rows: list[dict[str, object]] = []
    for path in sorted(config.runtime.runs_dir.glob("*/publish/approval_record.json")):
        try:
            from alysia.schemas import ApprovalRecord
            record = ApprovalRecord.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if subject and subject not in {record.run_id, record.subject_id, record.approval_id}:
            continue
        rows.append({
            "approval_id": record.approval_id, "action_type": record.action_type,
            "subject_id": record.subject_id, "approved_by": record.approved_by,
            "approved_at": record.approved_at.isoformat(),
            "expires_at": record.expires_at.isoformat() if record.expires_at else None,
            "scope": record.scope, "consumed_at": record.consumed_at.isoformat() if record.consumed_at else None,
            "consumed_by": record.consumed_by,
        })
    console.print_json(data=rows, ensure_ascii=False)


@security_app.command("demo")
def security_demo(evidence_dir: Path | None = typer.Option(None, "--evidence-dir")) -> None:
    from alysia.security.demos import run_security_demos

    result = run_security_demos(load_config(), evidence_dir)
    console.print_json(data=result, ensure_ascii=False)
    if result["status"] != "PASS":
        raise typer.Exit(code=2)


@app.command("diagnose")
def reliability_diagnose(run_id: str = typer.Argument(...)) -> None:
    console.print_json(data=ReliabilityService(load_config()).diagnose(run_id), ensure_ascii=False)


@app.command("checkpoints")
def reliability_checkpoints(run_id: str = typer.Argument(...)) -> None:
    service = ReliabilityService(load_config())
    console.print_json(
        data=[item.model_dump(mode="json") for item in service.checkpoints(run_id).list()],
        ensure_ascii=False,
    )


@app.command("recover")
def reliability_recover(run_id: str = typer.Argument(...), failure_id: str | None = typer.Option(None, "--failure-id")) -> None:
    config = load_config()
    service = ReliabilityService(config)
    decision = service.prepare_recovery(run_id, failure_id)
    result: dict[str, object] = {"decision": decision.model_dump(mode="json"), "resume_executed": False}
    if decision.action in {
        "retry_same_step",
        "retry_with_backoff",
        "use_approved_fallback",
        "invalidate_artifact_and_rebuild_stage",
        "rollback_to_artifact_owner",
    }:
        state = asyncio.run(AlysiaOrchestrator(config).resume(run_id))
        result["resume_executed"] = True
        result["state"] = state.model_dump(mode="json")
    elif decision.action in {"pause_waiting_resource", "escalate_human", "terminal_fail"}:
        result["note"] = "安全策略要求暂停/人工介入；CLI 未越权继续。"
    console.print_json(data=result, ensure_ascii=False)


@control_app.command("start")
def control_start(
    port: int = typer.Option(8765, "--port", min=1024, max=65535),
    open_browser: bool = typer.Option(False, "--open-browser"),
) -> None:
    """在 127.0.0.1 启动本地 Control Center。"""
    from alysia.control.server import start_control_center

    console.print(f"Alysia Control Center: http://127.0.0.1:{port}")
    console.print("Local-only adapter；不会监听 0.0.0.0。")
    start_control_center(port=port, open_browser=open_browser)


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
