from __future__ import annotations

from alysia.core.config import OptimizationConfig
from alysia.production.registry import ProviderCapabilityRegistry
from alysia.schemas import ProductionConstraints, ProviderCapability

_DEFAULT_ROUTING: dict[str, dict[str, list[str]]] = {
    "draft": {
        "research": ["research.mock", "research.manual", "research.web"],
        "script": ["llm.mock", "llm.ollama", "llm.cloud"],
        "storyboard": ["llm.mock", "llm.ollama", "llm.cloud"],
        "visual_generation": ["visual.mock", "visual.comfyui-h3"],
        "tts": ["tts.mock", "tts.sapi", "tts.cosyvoice"],
        "subtitle_alignment": ["subtitle.deterministic", "asr.mock", "asr.faster-whisper"],
        "render": ["render.mock", "render.remotion"],
        "cover": ["cover.template"],
    },
    "standard": {
        "research": ["research.web", "research.manual", "research.mock"],
        "script": ["llm.ollama", "llm.cloud", "llm.mock"],
        "storyboard": ["llm.ollama", "llm.cloud", "llm.mock"],
        "visual_generation": ["visual.comfyui-h3", "visual.mock"],
        "tts": ["tts.sapi", "tts.cosyvoice", "tts.mock"],
        "subtitle_alignment": ["asr.faster-whisper", "subtitle.deterministic", "asr.mock"],
        "render": ["render.remotion", "render.mock"],
        "cover": ["cover.template"],
    },
    "high": {
        "research": ["research.web", "research.manual", "research.mock"],
        "script": ["llm.cloud", "llm.ollama", "llm.mock"],
        "storyboard": ["llm.cloud", "llm.ollama", "llm.mock"],
        "visual_generation": ["visual.comfyui-h3", "visual.mock"],
        "tts": ["tts.cosyvoice", "tts.sapi", "tts.mock"],
        "subtitle_alignment": ["asr.faster-whisper", "subtitle.deterministic", "asr.mock"],
        "render": ["render.remotion", "render.mock"],
        "cover": ["cover.template"],
    },
}


class ProviderRouter:
    def __init__(self, registry: ProviderCapabilityRegistry, optimization: OptimizationConfig) -> None:
        self.registry = registry
        self.optimization = optimization

    def rank(
        self,
        task_type: str,
        constraints: ProductionConstraints,
    ) -> tuple[list[ProviderCapability], list[str]]:
        warnings: list[str] = []
        candidates = []
        for capability in self.registry.for_task(task_type):
            reason = self._exclusion_reason(capability, constraints)
            if reason:
                warnings.append(f"排除 {capability.provider_id}：{reason}")
                continue
            candidates.append(capability)
        preferences = self._preferences(constraints.quality_target, task_type)
        preference_index = {provider_id: index for index, provider_id in enumerate(preferences)}
        candidates.sort(
            key=lambda item: (
                preference_index.get(item.provider_id, len(preference_index) + 1),
                -self.score(item, constraints),
                item.provider_id,
            )
        )
        return candidates, warnings

    def score(self, capability: ProviderCapability, constraints: ProductionConstraints) -> float:
        quality = {"low": 0.25, "medium": 0.65, "high": 1.0, "unknown": 0.4}[capability.expected_quality_class]
        reliability = {"healthy": 1.0, "degraded": 0.55, "unknown": 0.35, "unavailable": 0.0}[
            capability.health_status
        ]
        latency = {"low": 1.0, "medium": 0.65, "high": 0.3, "unknown": 0.4}[
            capability.expected_latency_class
        ]
        cost = {"free": 1.0, "low": 0.75, "medium": 0.5, "high": 0.2, "unknown": 0.35}[
            capability.monetary_cost_class
        ]
        local = 1.0 if capability.local_or_cloud in {"local", "mock"} else 0.0
        weights = self.optimization.weights
        return round(
            quality * weights.quality
            + reliability * weights.reliability
            + latency * weights.latency
            + cost * weights.cost
            + local * weights.local_preference,
            6,
        )

    def _preferences(self, quality: str, task_type: str) -> list[str]:
        configured = self.optimization.routing.get(quality, {}).get(task_type)
        return list(configured or _DEFAULT_ROUTING.get(quality, {}).get(task_type, []))

    @staticmethod
    def _exclusion_reason(capability: ProviderCapability, constraints: ProductionConstraints) -> str | None:
        if capability.health_status == "unavailable":
            return capability.health_details or "health_status=unavailable"
        if constraints.provider_allowlist and capability.provider_id not in constraints.provider_allowlist:
            return "不在 provider_allowlist"
        if capability.provider_id in constraints.provider_denylist:
            return "命中 provider_denylist"
        if constraints.offline_mode and (capability.requires_network or capability.local_or_cloud == "cloud"):
            return "offline_mode 禁止网络/cloud provider"
        if not constraints.allow_cloud and capability.local_or_cloud == "cloud":
            return "allow_cloud=false"
        if capability.requires_credentials and capability.health_status != "healthy":
            return "缺少已验证凭证或 provider 未就绪"
        budget = min(constraints.max_local_vram_mb, 6144)
        if capability.local_or_cloud == "local" and capability.gpu_heavy and capability.estimated_vram_mb is None:
            return "GPU 任务峰值显存未知，无法验证 6144 MiB 预算"
        if (
            capability.estimated_vram_mb is not None
            and capability.estimated_vram_mb > budget
        ):
            return (
                f"estimated_vram_mb={capability.estimated_vram_mb} "
                f"超过预算 {budget}"
            )
        return None
