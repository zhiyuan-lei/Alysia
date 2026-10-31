from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from alysia.core.config import OptimizationConfig
from alysia.production.registry import ProviderCapabilityRegistry, SystemDoctorSnapshot
from alysia.production.router import ProviderRouter
from alysia.schemas import (
    PlanAlternative,
    ProductionPlan,
    ProductionProfile,
    ProductionStagePlan,
    ProviderCapability,
)

_STAGES: list[tuple[str, str]] = [
    ("research", "research"),
    ("script", "script"),
    ("storyboard", "storyboard"),
    ("visual_generation", "visual_generation"),
    ("text_qa", "text_qa"),
    ("tts", "tts"),
    ("subtitle_alignment", "subtitle_alignment"),
    ("audio_qa", "audio_qa"),
    ("render", "render"),
    ("video_qa", "video_qa"),
    ("cover", "cover"),
    ("metadata", "metadata"),
    ("publish_qa", "publish_qa"),
]
_OPERATIONS: dict[str, set[str]] = {
    "text": {"research", "script", "storyboard", "text_qa"},
    "audio": {"tts", "subtitle_alignment", "audio_qa"},
    "video": {"visual_generation", "render", "video_qa"},
    "package": {"cover", "metadata", "publish_qa"},
    "full": {stage for stage, _ in _STAGES},
}


class ProductionPlanner:
    def __init__(
        self,
        registry: ProviderCapabilityRegistry,
        optimization: OptimizationConfig,
        *,
        snapshot: SystemDoctorSnapshot | None = None,
        historical_metrics: dict[str, dict[str, float]] | None = None,
        approved_skills: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        self.registry = registry
        self.router = ProviderRouter(registry, optimization)
        self.snapshot = snapshot or SystemDoctorSnapshot()
        self.historical_metrics = historical_metrics or {}
        self.approved_skills = approved_skills or {}

    def generate(
        self,
        *,
        run_id: str,
        profile: ProductionProfile,
        requested_operation: str = "full",
    ) -> ProductionPlan:
        if requested_operation not in _OPERATIONS:
            raise ValueError(f"不支持的 requested_operation：{requested_operation}")
        selected_stages = [item for item in _STAGES if item[0] in _OPERATIONS[requested_operation]]
        stages: list[ProductionStagePlan] = []
        warnings: list[str] = []
        reasons: list[str] = []
        blockers: list[str] = []
        candidate_map: dict[str, list[ProviderCapability]] = {}
        for skill_id in profile.required_skills:
            record = self.approved_skills.get(skill_id)
            if not record or record.get("status") != "active":
                blockers.append(f"required skill 未批准或不可用：{skill_id}")

        for stage_id, task_type in selected_stages:
            candidates, excluded = self.router.rank(task_type, profile)
            warnings.extend(excluded)
            candidates = self._apply_history(candidates)
            if not candidates:
                blockers.append(f"{stage_id} 没有满足约束的 provider")
                continue
            candidate_map[stage_id] = candidates
            selected = candidates[0]
            fallbacks = [item.provider_id for item in candidates[1:]] if profile.allow_fallback else []
            stage_warnings: list[str] = []
            if selected.estimated_vram_mb is None and selected.gpu_heavy:
                stage_warnings.append("GPU provider 显存需求未知；执行前后只做真实可用探测，不推测峰值")
            if selected.local_or_cloud == "mock" and profile.quality_target != "draft":
                stage_warnings.append("非 draft 计划使用 mock provider，只适合测试或明确 testing run")
            stages.append(
                ProductionStagePlan(
                    stage_id=stage_id,
                    task_type=task_type,
                    selected_provider=selected.provider_id,
                    fallback_chain=fallbacks,
                    gpu_heavy=selected.gpu_heavy,
                    expected_vram_mb=selected.estimated_vram_mb,
                    reasons=self._selection_reasons(selected, profile),
                    warnings=stage_warnings,
                )
            )
            warnings.extend(f"{stage_id}: {item}" for item in stage_warnings)

        if profile.sequential_gpu_required:
            reasons.append("所有 GPU-heavy stage 按 execution_order 串行执行，并在阶段间卸载 provider")
        if self.snapshot.gpu_total_vram_mb is not None:
            reasons.append(
                f"系统探测 GPU 总显存 {self.snapshot.gpu_total_vram_mb} MiB；计划预算固定为 "
                f"{profile.max_local_vram_mb} MiB"
            )

        selected_map = {stage.stage_id: stage.selected_provider for stage in stages}
        for stage in stages:
            capability = self.registry.get(stage.selected_provider)
            if capability.local_or_cloud == "cloud" and profile.max_cloud_cost is not None:
                blockers.append(
                    f"{stage.stage_id} 选择 cloud provider，但成本未知且 max_cloud_cost="
                    f"{profile.max_cloud_cost}；必须人工确认"
                )

        alternatives = self._alternatives(candidate_map, profile)
        stable_payload = {
            "run_id": run_id,
            "operation": requested_operation,
            "profile": profile.model_dump(mode="json"),
            "providers": selected_map,
            "registry": self.registry.digest(),
        }
        digest = hashlib.sha256(
            json.dumps(stable_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        resource_notes = [
            "计划不包含多 GPU 或 GPU-heavy stage 并发。",
            "estimated_vram_mb 为 null 时保持 unknown，不用模型大小或历史宣传数字替代实测。",
        ]
        for skill_id in profile.required_skills:
            requirements = profile.skill_resource_requirements.get(
                skill_id, self.approved_skills.get(skill_id, {}).get("resource_requirements", {})
            )
            resource_notes.append(f"skill {skill_id} resource requirements={requirements}")
        cost_notes = [
            "本地计算只记录 runtime；energy/electricity cost 保持 unknown。",
            "Cloud 成本只有 provider 返回可验证 usage/price 来源时才估算。",
        ]
        tradeoffs = self._tradeoffs(profile, stages)
        return ProductionPlan(
            plan_id=f"prod_{digest[:16]}",
            run_id=run_id,
            requested_operation=requested_operation,
            profile=profile,
            stages=stages,
            selected_provider_per_stage=selected_map,
            execution_order=[stage.stage_id for stage in stages],
            fallback_chain={stage.stage_id: stage.fallback_chain for stage in stages},
            expected_resource_notes=resource_notes,
            expected_cost_notes=cost_notes,
            quality_tradeoffs=tradeoffs,
            reasons=reasons,
            warnings=sorted(set(warnings)),
            alternatives=alternatives,
            policy_blockers=sorted(set(blockers)),
            requires_human_confirmation=any("人工确认" in blocker for blocker in blockers),
            registry_digest=self.registry.digest(),
            created_at=datetime.now().astimezone(),
        )

    def _apply_history(self, candidates: list[ProviderCapability]) -> list[ProviderCapability]:
        return sorted(
            candidates,
            key=lambda item: (
                (
                    self.historical_metrics.get(item.provider_id, {}).get("failure_rate", 0.0) >= 0.5
                    and self.historical_metrics.get(item.provider_id, {}).get("sample_count", 0.0) >= 3
                ),
                candidates.index(item),
            ),
        )

    def _selection_reasons(self, selected: ProviderCapability, profile: ProductionProfile) -> list[str]:
        reasons = [
            f"匹配 task type；health={selected.health_status}",
            f"quality={selected.expected_quality_class}, latency={selected.expected_latency_class}",
        ]
        if profile.prefer_local and selected.local_or_cloud in {"local", "mock"}:
            reasons.append("符合 prefer_local")
        if selected.estimated_vram_mb is not None:
            reasons.append(
                f"estimated_vram_mb={selected.estimated_vram_mb} 未超过预算 {profile.max_local_vram_mb}"
            )
        return reasons

    def _alternatives(
        self,
        candidate_map: dict[str, list[ProviderCapability]],
        profile: ProductionProfile,
    ) -> list[PlanAlternative]:
        selectors = {
            "balanced": lambda items: items[0],
            "local_first": lambda items: next(
                (item for item in items if item.local_or_cloud in {"local", "mock"}), items[0]
            ),
            "quality_first": lambda items: max(
                items,
                key=lambda item: ({"unknown": 0, "low": 1, "medium": 2, "high": 3}[item.expected_quality_class], -items.index(item)),
            ),
        }
        alternatives: list[PlanAlternative] = []
        seen: set[tuple[tuple[str, str], ...]] = set()
        for name, selector in selectors.items():
            provider_map = {stage: selector(items).provider_id for stage, items in candidate_map.items()}
            signature = tuple(sorted(provider_map.items()))
            if signature in seen:
                continue
            seen.add(signature)
            score = sum(
                self.router.score(self.registry.get(provider_id), profile)
                for provider_id in provider_map.values()
            ) / max(1, len(provider_map))
            alternatives.append(
                PlanAlternative(
                    name=name,
                    provider_by_stage=provider_map,
                    score=round(score, 6),
                    reasons=[f"基于 {name} 可解释选择器生成"],
                    tradeoffs=["排序依据来自声明能力和历史可靠性；不是实测 benchmark"],
                )
            )
        return sorted(alternatives, key=lambda item: (-item.score, item.name))

    @staticmethod
    def _tradeoffs(profile: ProductionProfile, stages: list[ProductionStagePlan]) -> list[str]:
        notes = [f"quality_target={profile.quality_target} 影响 provider 优先级与 QA 容忍度"]
        if any(stage.selected_provider.endswith(".mock") or ".mock" in stage.selected_provider for stage in stages):
            notes.append("Mock provider 提升可复现性与速度，但不代表正式内容质量")
        if profile.quality_target == "high":
            notes.append("high 允许更严格检查，但最大 retry/repair budget 仍受配置限制")
        return notes
