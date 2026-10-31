from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from alysia.core.config import AlysiaConfig
from alysia.schemas import CandidatePlan, Prediction, SimulationScenario, WorldStateSnapshot
from alysia.workflow import WorkflowService


def _simulated(metric: str, value: float | str | bool, assumption: str, *, confidence: str = "low", unit: str | None = None, caveats: list[str] | None = None) -> Prediction:
    return Prediction(
        metric=metric, estimate_type="simulated", point_estimate=value, unit=unit,
        confidence=confidence, assumptions=[assumption], caveats=caveats or [],
    )


def _unknown(metric: str, caveat: str, *, evidence: list[str] | None = None, unit: str | None = None) -> Prediction:
    return Prediction(
        metric=metric, estimate_type="unknown", confidence="low", unit=unit,
        evidence_refs=evidence or [], caveats=[caveat],
    )


def _derived(metric: str, value: float | str | bool, assumption: str, evidence: list[str], *, confidence: str = "medium", unit: str | None = None) -> Prediction:
    return Prediction(
        metric=metric, estimate_type="derived", point_estimate=value, unit=unit,
        confidence=confidence, evidence_refs=evidence, assumptions=[assumption],
    )


class ProductionSimulationEngine:
    def __init__(self, project_root: Path = Path(".")) -> None:
        self.project_root = project_root.resolve()

    def evaluate(self, scenario: SimulationScenario, candidate: CandidatePlan, snapshot: WorldStateSnapshot) -> tuple[list[Prediction], list[str], list[str]]:
        changed = candidate.changed_variables
        h3_clips = int(changed.get("h3_clip_count", 0) or 0)
        h3_seconds = float(changed.get("total_h3_seconds", 0) or 0)
        provider = next((item for item in snapshot.provider_health if item.get("provider_id") == "visual.comfyui-h3"), {})
        predictions: list[Prediction] = [
            _derived(
                "total_h3_seconds", h3_seconds,
                "候选计划中的 total_h3_seconds 是计划参数，不是实测生成结果",
                [f"scenario:{scenario.scenario_id}", f"candidate:{candidate.candidate_id}"],
                confidence="high", unit="sec",
            )
        ]
        failure_paths: list[str] = []
        notes: list[str] = []
        real_samples = self._latency_samples(h3_required=h3_clips > 0)
        if real_samples:
            low, high = min(real_samples), max(real_samples)
            predictions.append(Prediction(
                metric="production_latency_sec", estimate_type="derived",
                range=(low, high), unit="sec", confidence="low",
                evidence_refs=["runs/*/production/execution_metrics.json"],
                assumptions=["历史 stage 样本与当前候选具有可比性"],
                caveats=["区间是历史观察范围，不是 SLA"],
            ))
        else:
            predictions.append(_unknown(
                "production_latency_sec",
                "没有与该候选可比的真实 execution metrics；不使用宣传数字或 mock runtime",
                unit="sec",
            ))
        if h3_clips:
            available = provider.get("health_status") == "healthy"
            if not available:
                failure_paths.append("H3/ComfyUI provider unavailable，视觉生成步骤会在执行前被 ProductionPlanner 阻断")
            predictions.extend([
                _simulated(
                    "expected_quality_score", min(0.8, 0.62 + 0.035 * h3_clips),
                    "少量合格动态镜头可能提升视觉丰富度；未做真实 preview",
                    caveats=["VisualQA 失败会抵消提升"],
                ),
                _simulated(
                    "reliability_score", 0.25 if not available else max(0.35, 0.75 - 0.06 * h3_clips),
                    "provider health 与串行 GPU 任务数用于相对可靠性比较",
                    confidence="medium",
                ),
                _simulated(
                    "latency_score", max(0.1, 0.65 - 0.08 * h3_clips),
                    "H3 clip 数仅用于相对时延排序，不表示真实秒数",
                ),
                _simulated(
                    "resource_efficiency_score", max(0.1, 0.55 - 0.06 * h3_clips),
                    "8GB VRAM + 24GB RAM 下 GPU-heavy clips 必须串行，且峰值资源仍 unknown",
                ),
            ])
            if provider.get("estimated_vram_mb") is None:
                notes.append("H3 peak VRAM unknown；禁止把模型规格推算成实测峰值")
        else:
            predictions.extend([
                _simulated("expected_quality_score", 0.58, "Remotion-only 使用现有程序化视觉质量基线"),
                _derived("reliability_score", 0.9, "不依赖当前 unavailable H3 provider", ["provider:visual.comfyui-h3"], confidence="medium"),
                _simulated("latency_score", 0.9, "无 H3 GPU-heavy clip，仅用于候选间相对排序", confidence="medium"),
                _simulated("resource_efficiency_score", 0.95, "Remotion/FFmpeg 不需要 H3 权重常驻", confidence="medium"),
            ])
        predictions.append(_unknown(
            "monetary_cost", "本地能耗/电费没有可验证计量；沿用 alpha11 unknown policy", unit="currency",
        ))
        return predictions, failure_paths, notes

    def _latency_samples(self, *, h3_required: bool) -> list[float]:
        samples: list[float] = []
        for path in self.project_root.glob("runs/*/production/execution_metrics.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            for stage in payload.get("stages", []):
                provider = str(stage.get("provider_id", ""))
                source = str(stage.get("source", payload.get("source", ""))).lower()
                if source not in {"real", "production", "observed"}:
                    continue
                if h3_required != ("h3" in provider or "comfyui" in provider):
                    continue
                value = stage.get("elapsed_sec")
                if isinstance(value, (int, float)) and value >= 0:
                    samples.append(float(value))
        return samples


class ContentStructureSimulationEngine:
    def evaluate(self, scenario: SimulationScenario, candidate: CandidatePlan, snapshot: WorldStateSnapshot) -> tuple[list[Prediction], list[str]]:
        changed = candidate.changed_variables
        predictions: list[Prediction] = []
        notes: list[str] = []
        for key, unit in (("hook_seconds", "sec"), ("video_duration_sec", "sec"), ("subtitle_chars_per_sec", "chars/sec")):
            if key in changed:
                predictions.append(_derived(
                    key, float(changed[key]), f"{key} 来自候选计划参数",
                    [f"scenario:{scenario.scenario_id}", f"candidate:{candidate.candidate_id}"],
                    confidence="high", unit=unit,
                ))
        real_history = [
            item for item in snapshot.recent_content_metrics_summaries
            if str(item.get("source", "")).lower() not in {"mock", "testing"}
        ]
        if "hook_seconds" in changed:
            if len(real_history) < 3:
                predictions.append(_unknown(
                    "relative_platform_outcome",
                    "真实历史样本不足 3 条；不能从 testing/mock episode 推断 hook 对平台结果的影响",
                    evidence=snapshot.source_refs.get("recent_content_metrics", []),
                ))
                predictions.append(_simulated(
                    "experiment_value_score", 0.75,
                    "hook_seconds 是单一可控变量，适合在审批后设计真实对照实验",
                    confidence="low",
                    caveats=["该值表示实验设计价值，不是平台结果预测"],
                ))
                notes.append("hook comparison 只保留实验价值，不预测精确播放或留存")
            else:
                predictions.append(_simulated(
                    "experiment_value_score", 0.75,
                    "单变量 hook 变化适合形成受控实验；平台结果仍需真实 run 验证",
                    confidence="medium",
                ))
        else:
            predictions.append(_simulated(
                "experiment_value_score", min(0.8, 0.35 + 0.08 * len(changed)),
                "changed variables 数量用于粗略实验价值排序",
            ))
        predictions.append(_simulated(
            "novelty_score", min(0.9, 0.45 + 0.08 * len(changed)),
            "仅根据方案变量差异估计，不代表观众感知的新颖度",
        ))
        return predictions, notes


class RiskSimulationEngine:
    def evaluate(self, scenario: SimulationScenario, candidate: CandidatePlan, snapshot: WorldStateSnapshot) -> tuple[list[Prediction], list[str]]:
        changed = candidate.changed_variables
        risks: list[str] = []
        risk = 0.15
        if int(changed.get("h3_clip_count", 0) or 0):
            h3 = next((item for item in snapshot.provider_health if item.get("provider_id") == "visual.comfyui-h3"), {})
            if h3.get("health_status") != "healthy":
                risk += 0.45
                risks.append("provider availability risk: visual.comfyui-h3 unavailable")
            if h3.get("estimated_vram_mb") is None:
                risk += 0.15
                risks.append("resource/OOM risk: H3 peak VRAM unknown")
        if candidate.expected_approvals:
            risk += min(0.15, 0.04 * len(candidate.expected_approvals))
            risks.append("approval burden: " + ", ".join(candidate.expected_approvals))
        if changed.get("real_publish"):
            risks.append("real publish requires human gate")
        duplicate = changed.get("duplicate_similarity")
        if isinstance(duplicate, (int, float)) and duplicate >= 0.72:
            risk += 0.2
            risks.append("duplicate/topic fatigue risk")
        risk = min(1.0, risk)
        return [
            _simulated("risk_score", risk, "规则化 provider/resource/approval/topic 风险合成；不是事故概率", confidence="medium"),
            _simulated("approval_burden_score", max(0.0, 1.0 - 0.2 * len(candidate.expected_approvals)), "审批点数量用于相对负担排序", confidence="medium"),
        ], risks


class WorkflowSimulationEngine:
    def __init__(self, config: AlysiaConfig) -> None:
        self.service = WorkflowService(config)

    def evaluate(self, candidate: CandidatePlan) -> tuple[list[Prediction], dict[str, Any], list[str]]:
        recipe_id = candidate.changed_variables.get("workflow_recipe_id")
        if not recipe_id:
            return [], {"applicable": False, "real_steps_executed": False}, []
        notes: list[str] = []
        try:
            recipe = self.service.recipes.get(str(recipe_id))
        except KeyError:
            return [
                _simulated("reliability_score", 0.1, "引用的 recipe 不存在，dry-run 判定不可执行", confidence="high")
            ], {"applicable": True, "recipe_id": recipe_id, "valid": False, "real_steps_executed": False}, ["workflow recipe 不存在"]
        valid = recipe.status == "validated"
        invalid_requirements: list[str] = []
        for requirement in recipe.required_capabilities:
            implementation = requirement.split("@", 1)[0]
            source_type = "skill" if "@skill:" in requirement else "capability"
            try:
                self.service.registry.get(implementation, source_type=source_type)
            except KeyError:
                invalid_requirements.append(requirement)
        valid = valid and not invalid_requirements
        if recipe.status != "validated":
            notes.append(f"recipe status={recipe.status}，不可作为 validated recipe 使用")
        if invalid_requirements:
            notes.append(f"registry 版本/状态不可用：{invalid_requirements}")
        quality = str(candidate.changed_variables.get("quality_profile", "standard"))
        return [
            _derived("workflow_valid", valid, "只做 recipe/registry/contract snapshot dry-run，不执行 step", [f"recipe:{recipe.recipe_id}"], confidence="high"),
            _simulated("expected_quality_score", 0.52 if quality == "draft" else 0.72, "quality profile 仅用于相对比较；最终质量仍由真实 QA 决定"),
            _simulated("reliability_score", recipe.confidence if valid else 0.1, "validated recipe confidence 用于 dry-run 相对可靠性", confidence="medium"),
            _simulated("latency_score", 0.85 if quality == "draft" else 0.62, "draft/standard profile 的相对时延假设，不是实测 runtime"),
        ], {
            "applicable": True, "recipe_id": recipe.recipe_id, "recipe_status": recipe.status,
            "valid": valid, "step_count": len(recipe.steps_template),
            "quality_gates": recipe.quality_gates, "real_steps_executed": False,
            "invalid_requirements": invalid_requirements,
        }, notes


class PlatformOutcomeEstimator:
    def evaluate(self, candidate: CandidatePlan, snapshot: WorldStateSnapshot) -> list[Prediction]:
        real = [
            item for item in snapshot.recent_content_metrics_summaries
            if str(item.get("source", "")).lower() not in {"mock", "testing"}
        ]
        if len(real) < 3:
            return [_unknown(
                "platform_outcome_relative",
                "真实可比内容数据不足；不预测精确播放量、粉丝数、收益或留存",
                evidence=snapshot.source_refs.get("recent_content_metrics", []),
            )]
        return [Prediction(
            metric="platform_outcome_relative", estimate_type="simulated",
            point_estimate="wide_interval_only", confidence="low",
            evidence_refs=snapshot.source_refs.get("recent_content_metrics", []),
            assumptions=["最近真实内容与候选主题/结构可比"],
            caveats=["仅允许相对比较；不输出精确播放量或粉丝数"],
        )]
