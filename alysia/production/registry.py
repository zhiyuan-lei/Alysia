from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import subprocess
from pathlib import Path

from pydantic import BaseModel, Field

from alysia.core.config import AlysiaConfig
from alysia.providers.tts import SapiTTSProvider
from alysia.schemas import ProviderCapability
from alysia.workers.media import find_media_executable


class SystemDoctorSnapshot(BaseModel):
    components: dict[str, bool | None] = Field(default_factory=dict)
    details: dict[str, str] = Field(default_factory=dict)
    gpu_name: str | None = None
    gpu_total_vram_mb: int | None = Field(default=None, ge=0)
    gpu_used_vram_mb: int | None = Field(default=None, ge=0)

    @classmethod
    def capture(cls) -> "SystemDoctorSnapshot":
        components: dict[str, bool | None] = {
            "ollama": shutil.which("ollama") is not None,
            "npm": shutil.which("npm") is not None,
            "ffmpeg": find_media_executable("ffmpeg") is not None,
            "sapi": SapiTTSProvider.is_available(),
            "cosyvoice": importlib.util.find_spec("cosyvoice") is not None,
            "faster_whisper": importlib.util.find_spec("faster_whisper") is not None,
            "comfyui_dir": bool(False),
        }
        details: dict[str, str] = {}
        gpu_name = None
        total = None
        used = None
        executable = shutil.which("nvidia-smi")
        if executable:
            try:
                result = subprocess.run(
                    [
                        executable,
                        "--query-gpu=name,memory.total,memory.used",
                        "--format=csv,noheader,nounits",
                    ],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=5,
                    check=False,
                )
                if result.returncode == 0 and result.stdout.strip():
                    name, total_text, used_text = [item.strip() for item in result.stdout.splitlines()[0].split(",")]
                    gpu_name = name
                    total = int(total_text)
                    used = int(used_text)
                    components["nvidia_smi"] = True
                else:
                    components["nvidia_smi"] = False
                    details["nvidia_smi"] = (result.stderr or result.stdout).strip()[-500:]
            except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
                components["nvidia_smi"] = False
                details["nvidia_smi"] = str(exc)
        else:
            components["nvidia_smi"] = False
        return cls(
            components=components,
            details=details,
            gpu_name=gpu_name,
            gpu_total_vram_mb=total,
            gpu_used_vram_mb=used,
        )


class ProviderCapabilityRegistry:
    def __init__(self, capabilities: list[ProviderCapability] | None = None) -> None:
        self._capabilities: dict[str, ProviderCapability] = {}
        for capability in capabilities or []:
            self.register(capability)

    def register(self, capability: ProviderCapability) -> None:
        if capability.provider_id in self._capabilities:
            raise ValueError(f"重复 provider_id：{capability.provider_id}")
        self._capabilities[capability.provider_id] = capability

    def get(self, provider_id: str) -> ProviderCapability:
        try:
            return self._capabilities[provider_id]
        except KeyError as exc:
            raise KeyError(f"Provider registry 中不存在：{provider_id}") from exc

    def list(self) -> list[ProviderCapability]:
        return [self._capabilities[key] for key in sorted(self._capabilities)]

    def for_task(self, task_type: str) -> list[ProviderCapability]:
        return [item for item in self.list() if task_type in item.task_types]

    def digest(self) -> str:
        payload = [item.model_dump(mode="json") for item in self.list()]
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    @classmethod
    def default(cls, config: AlysiaConfig, snapshot: SystemDoctorSnapshot | None = None) -> "ProviderCapabilityRegistry":
        snapshot = snapshot or SystemDoctorSnapshot.capture()
        component = snapshot.components

        def health(name: str, *, unavailable_when_false: bool = True) -> str:
            value = component.get(name)
            if value is True:
                return "healthy"
            if value is False and unavailable_when_false:
                return "unavailable"
            return "unknown"

        remotion_ready = bool(component.get("npm")) and (
            config.render.remotion_dir / "node_modules" / "remotion"
        ).is_dir()
        cosy_ready = bool(component.get("cosyvoice")) and bool(
            config.tts.model_dir and Path(config.tts.model_dir).is_dir()
        )
        comfy_dir_ready = bool(
            config.visual_generation.h3.comfyui_dir
            and Path(config.visual_generation.h3.comfyui_dir).is_dir()
        )
        h3_model_ready = bool(
            config.visual_generation.h3.model_path
            and Path(config.visual_generation.h3.model_path).exists()
        )
        capabilities = [
            ProviderCapability(
                provider_id="llm.mock",
                task_types=["schema_formatting", "metadata", "routing", "script", "storyboard"],
                local_or_cloud="mock",
                estimated_vram_mb=0,
                supports_unload=False,
                expected_latency_class="low",
                expected_quality_class="low",
                monetary_cost_class="free",
                health_status="healthy",
            ),
            ProviderCapability(
                provider_id="llm.ollama",
                task_types=["schema_formatting", "metadata", "routing", "script", "storyboard"],
                local_or_cloud="local",
                estimated_vram_mb=None,
                supports_unload=True,
                expected_latency_class="medium",
                expected_quality_class="medium",
                monetary_cost_class="unknown",
                health_status=health("ollama"),
                gpu_heavy=True,
                version=config.llm.model,
            ),
            ProviderCapability(
                provider_id="llm.cloud",
                task_types=["script", "storyboard"],
                local_or_cloud="cloud",
                expected_latency_class="medium",
                expected_quality_class="high",
                monetary_cost_class="unknown",
                requires_network=True,
                requires_credentials=True,
                health_status="unavailable",
                health_details="CloudLLMProvider 当前是显式占位实现",
            ),
            ProviderCapability(
                provider_id="research.mock",
                task_types=["research"],
                local_or_cloud="mock",
                estimated_vram_mb=0,
                expected_latency_class="low",
                expected_quality_class="low",
                monetary_cost_class="free",
                health_status="healthy",
            ),
            ProviderCapability(
                provider_id="research.web",
                task_types=["research"],
                local_or_cloud="cloud",
                expected_latency_class="medium",
                expected_quality_class="unknown",
                monetary_cost_class="unknown",
                requires_network=True,
                health_status="unavailable",
                health_details="WebResearchProvider 当前是显式占位实现",
            ),
            ProviderCapability(
                provider_id="research.manual",
                task_types=["research"],
                local_or_cloud="local",
                estimated_vram_mb=0,
                expected_latency_class="low",
                expected_quality_class="unknown",
                monetary_cost_class="free",
                health_status=(
                    "healthy"
                    if config.research.manual_source_file is not None and config.research.manual_source_file.is_file()
                    else "unavailable"
                ),
                health_details="显式手工 ResearchResult 文件；事实质量仍由 alpha17 Knowledge QA 决定",
            ),
            ProviderCapability(
                provider_id="tts.mock",
                task_types=["tts"],
                local_or_cloud="mock",
                estimated_vram_mb=0,
                expected_latency_class="low",
                expected_quality_class="low",
                monetary_cost_class="free",
                health_status="healthy",
            ),
            ProviderCapability(
                provider_id="tts.sapi",
                task_types=["tts"],
                local_or_cloud="local",
                estimated_vram_mb=0,
                expected_latency_class="low",
                expected_quality_class="medium",
                monetary_cost_class="unknown",
                health_status=health("sapi"),
            ),
            ProviderCapability(
                provider_id="tts.cosyvoice",
                task_types=["tts"],
                local_or_cloud="local",
                estimated_vram_mb=None,
                supports_unload=True,
                expected_latency_class="high",
                expected_quality_class="high",
                monetary_cost_class="unknown",
                health_status="healthy" if cosy_ready else "unavailable",
                gpu_heavy=True,
                health_details=None if cosy_ready else "缺少 cosyvoice 包或已配置本地模型目录",
            ),
            ProviderCapability(
                provider_id="subtitle.deterministic",
                task_types=["subtitle_alignment"],
                local_or_cloud="local",
                estimated_vram_mb=0,
                expected_latency_class="low",
                expected_quality_class="medium",
                monetary_cost_class="unknown",
                health_status="healthy",
            ),
            ProviderCapability(
                provider_id="asr.mock",
                task_types=["subtitle_alignment"],
                local_or_cloud="mock",
                estimated_vram_mb=0,
                expected_latency_class="low",
                expected_quality_class="low",
                monetary_cost_class="free",
                health_status="healthy",
            ),
            ProviderCapability(
                provider_id="asr.faster-whisper",
                task_types=["subtitle_alignment"],
                local_or_cloud="local",
                estimated_vram_mb=None,
                supports_unload=True,
                expected_latency_class="medium",
                expected_quality_class="high",
                monetary_cost_class="unknown",
                health_status="unknown" if component.get("faster_whisper") else "unavailable",
                gpu_heavy=config.asr.device == "cuda",
                version=config.asr.model,
            ),
            ProviderCapability(
                provider_id="render.mock",
                task_types=["render"],
                local_or_cloud="mock",
                estimated_vram_mb=0,
                expected_latency_class="low",
                expected_quality_class="low",
                monetary_cost_class="free",
                health_status=health("ffmpeg"),
            ),
            ProviderCapability(
                provider_id="render.remotion",
                task_types=["render"],
                local_or_cloud="local",
                estimated_vram_mb=0,
                expected_latency_class="medium",
                expected_quality_class="high",
                monetary_cost_class="unknown",
                health_status="healthy" if remotion_ready else "unavailable",
            ),
            ProviderCapability(
                provider_id="visual.mock",
                task_types=["visual_generation"],
                local_or_cloud="mock",
                estimated_vram_mb=0,
                expected_latency_class="low",
                expected_quality_class="low",
                monetary_cost_class="free",
                health_status="healthy",
                health_details="仅用于离线测试；mock artifact 不得进入 production review",
            ),
            ProviderCapability(
                provider_id="visual.comfyui-h3",
                task_types=["visual_generation"],
                local_or_cloud="local",
                estimated_vram_mb=config.visual_generation.h3.measured_peak_vram_mb,
                supports_unload=True,
                expected_latency_class="high",
                expected_quality_class="high",
                monetary_cost_class="unknown",
                health_status="healthy" if comfy_dir_ready and h3_model_ready else "unavailable",
                health_details=(
                    f"本机 smoke={config.visual_generation.h3.measurement_profile}; "
                    f"peak_vram_mb={config.visual_generation.h3.measured_peak_vram_mb}; "
                    f"peak_ram_mb={config.visual_generation.h3.measured_peak_ram_mb}; "
                    f"wall_time_sec={config.visual_generation.h3.measured_wall_time_sec}"
                    if comfy_dir_ready and h3_model_ready
                    else "缺少已配置的 ComfyUI 目录或 H3 model_path"
                ),
                gpu_heavy=True,
                version="runtime-1",
            ),
            ProviderCapability(
                provider_id="cover.template",
                task_types=["cover"],
                local_or_cloud="local",
                estimated_vram_mb=0,
                expected_latency_class="low",
                expected_quality_class="medium",
                monetary_cost_class="unknown",
                health_status="healthy",
            ),
        ]
        deterministic_tasks = ["text_qa", "audio_qa", "video_qa", "metadata", "publish_qa"]
        for task in deterministic_tasks:
            capabilities.append(
                ProviderCapability(
                    provider_id=f"deterministic.{task}",
                    task_types=[task],
                    local_or_cloud="local",
                    estimated_vram_mb=0,
                    expected_latency_class="low",
                    expected_quality_class="medium",
                    monetary_cost_class="unknown",
                    health_status="healthy",
                )
            )
        return cls(capabilities)
