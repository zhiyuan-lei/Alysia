from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from alysia.core.config import AlysiaConfig
from alysia.core.run import RunManager, RunState
from alysia.production.metrics import ExecutionMetricsStore
from alysia.production.planner import ProductionPlanner
from alysia.production.quality import ProductionQualityGate
from alysia.production.registry import ProviderCapabilityRegistry, SystemDoctorSnapshot
from alysia.schemas import (
    CostValue,
    ExecutionMetrics,
    ProductionPlan,
    ProductionProfile,
    ProductionReport,
)


class ProductionPolicyError(RuntimeError):
    pass


class ProductionService:
    def __init__(
        self,
        config: AlysiaConfig,
        *,
        registry: ProviderCapabilityRegistry | None = None,
        snapshot: SystemDoctorSnapshot | None = None,
    ) -> None:
        self.config = config
        self.manager = RunManager(config.runtime.runs_dir)
        self.snapshot = snapshot or SystemDoctorSnapshot.capture()
        self.registry = registry or ProviderCapabilityRegistry.default(config, self.snapshot)

    def profile(self, quality_target: str | None = None) -> ProductionProfile:
        source = self.config.production
        return ProductionProfile(
            name=f"alysia-{quality_target or source.quality_target}",
            quality_target=quality_target or source.quality_target,
            max_local_vram_mb=source.max_local_vram_mb,
            max_cloud_cost=source.max_cloud_cost,
            max_wall_time_sec=source.max_wall_time_sec,
            prefer_local=source.prefer_local,
            allow_cloud=source.allow_cloud,
            allow_fallback=source.allow_fallback,
            sequential_gpu_required=source.sequential_gpu_required,
            offline_mode=source.offline_mode,
            reproducibility_priority=source.reproducibility_priority,
            provider_allowlist=source.provider_allowlist,
            provider_denylist=source.provider_denylist,
            max_retries_per_stage=source.max_retries_per_stage,
            research_cache_ttl_hours=source.research_cache_ttl_hours,
        )

    def plan(
        self,
        run_id: str,
        *,
        requested_operation: str = "full",
        quality_target: str | None = None,
        select: bool = True,
    ) -> ProductionPlan:
        state = self.manager.load(run_id)
        profile = self.profile(quality_target)
        planner = ProductionPlanner(
            self.registry,
            self._effective_optimization(profile.quality_target),
            snapshot=self.snapshot,
            historical_metrics=self._historical_metrics(),
        )
        plan = planner.generate(run_id=run_id, profile=profile, requested_operation=requested_operation)
        quality_path = f"production/plans/{profile.quality_target}.json"
        self.manager.write_json(run_id, quality_path, plan.model_dump(mode="json"))
        if select:
            self.manager.write_json(run_id, "production/production_plan.json", plan.model_dump(mode="json"))
            state.artifacts["production_plan"] = "production/production_plan.json"
            state.artifacts[f"production_plan_{profile.quality_target}"] = quality_path
            state.config_snapshot["production"] = self.config.production.model_dump(mode="json")
            state.config_snapshot["optimization"] = self.config.optimization.model_dump(mode="json")
            self.manager.save(state)
        return plan

    def ensure_plan(
        self,
        state: RunState,
        *,
        requested_operation: str,
        quality_target: str | None = None,
    ) -> ProductionPlan:
        current = self._load_selected(state.run_id)
        if current is None or current.requested_operation not in {requested_operation, "full"}:
            current = self.plan(
                state.run_id,
                requested_operation=requested_operation,
                quality_target=quality_target,
                select=True,
            )
        self.assert_allowed(state.run_id, current)
        return current

    def approve_policy(self, run_id: str, *, approved_by: str) -> dict[str, Any]:
        if approved_by.strip().lower() in {"", "automation", "agent", "alysia", "system"}:
            raise ValueError("Production policy confirmation 必须由明确的人类审核者完成")
        plan = self.load_plan(run_id)
        if not plan.requires_human_confirmation:
            raise ValueError("当前 ProductionPlan 不需要额外人工确认")
        record = {
            "run_id": run_id,
            "plan_id": plan.plan_id,
            "approved_by": approved_by.strip(),
            "approved_at": datetime.now().astimezone().isoformat(),
            "accepted_blockers": plan.policy_blockers,
        }
        self.manager.write_json(run_id, "production/policy_approval.json", record)
        return record

    def assert_allowed(self, run_id: str, plan: ProductionPlan) -> None:
        if not plan.policy_blockers:
            return
        approval_path = self.manager.run_dir(run_id) / "production" / "policy_approval.json"
        if plan.requires_human_confirmation and approval_path.is_file():
            approval = json.loads(approval_path.read_text(encoding="utf-8"))
            if approval.get("plan_id") == plan.plan_id and approval.get("approved_by"):
                non_confirmable = [item for item in plan.policy_blockers if "人工确认" not in item]
                if not non_confirmable:
                    return
        raise ProductionPolicyError("ProductionPlan 被策略阻止：" + "; ".join(plan.policy_blockers))

    def load_plan(self, run_id: str, quality_target: str | None = None) -> ProductionPlan:
        relative = (
            f"production/plans/{quality_target}.json" if quality_target else "production/production_plan.json"
        )
        path = self.manager.run_dir(run_id) / relative
        if not path.is_file():
            raise FileNotFoundError(f"run 尚无 ProductionPlan：{relative}")
        return ProductionPlan.model_validate_json(path.read_text(encoding="utf-8"))

    def status(self, run_id: str) -> dict[str, Any]:
        plan = self.load_plan(run_id)
        metrics = self.metrics_store(run_id, plan.plan_id).load()
        gate_path = self.manager.run_dir(run_id) / "production" / "quality_gate_report.json"
        return {
            "run_id": run_id,
            "plan_id": plan.plan_id,
            "quality_target": plan.profile.quality_target,
            "providers": plan.selected_provider_per_stage,
            "policy_blockers": plan.policy_blockers,
            "requires_human_confirmation": plan.requires_human_confirmation,
            "completed_metric_records": len(metrics.stages),
            "fallbacks": len(metrics.fallbacks),
            "quality_gate": json.loads(gate_path.read_text(encoding="utf-8")) if gate_path.is_file() else None,
        }

    def quality_gate(self, run_id: str) -> Any:
        return ProductionQualityGate(self.manager).evaluate(run_id, self.load_plan(run_id))

    def report(self, run_id: str) -> ProductionReport:
        plan = self.load_plan(run_id)
        metrics = self.metrics_store(run_id, plan.plan_id).load()
        elapsed: dict[str, float | None] = {stage: None for stage in plan.execution_order}
        cache_hits: list[str] = []
        for item in metrics.stages:
            elapsed[item.stage_id] = (elapsed.get(item.stage_id) or 0) + item.elapsed_sec
            if item.cache_hit and item.stage_id not in cache_hits:
                cache_hits.append(item.stage_id)
        successful = [item for item in metrics.stages if item.success and not item.cache_hit]
        bottlenecks = []
        if successful:
            slowest = max(successful, key=lambda item: item.elapsed_sec)
            bottlenecks.append(f"当前最慢 stage：{slowest.stage_id} ({slowest.elapsed_sec:.3f}s)")
        suggestions = []
        failure_counts: dict[str, int] = {}
        for item in metrics.stages:
            if not item.success:
                failure_counts[item.provider] = failure_counts.get(item.provider, 0) + 1
        for provider, count in sorted(failure_counts.items()):
            suggestions.append(f"{provider} 失败 {count} 次；仅建议下调本次 ranking，不自动修改全局配置")
        gate_path = self.manager.run_dir(run_id) / "production" / "quality_gate_report.json"
        gate = None
        if gate_path.is_file():
            from alysia.schemas import ProductionQualityGateReport

            gate = ProductionQualityGateReport.model_validate_json(gate_path.read_text(encoding="utf-8"))
        unknown_cost = CostValue(status="unknown", details="未获得可验证 provider usage/price 来源")
        report = ProductionReport(
            run_id=run_id,
            selected_plan=plan,
            elapsed_time_per_stage=elapsed,
            fallbacks=metrics.fallbacks,
            cache_hits=cache_hits,
            cost={stage: unknown_cost for stage in plan.execution_order},
            qa_outcome=gate,
            bottlenecks=bottlenecks,
            optimization_suggestions=suggestions,
            generated_at=datetime.now().astimezone(),
            metadata={
                "gpu_name": self.snapshot.gpu_name,
                "gpu_total_vram_mb": self.snapshot.gpu_total_vram_mb,
                "cost_policy": "known | estimated_with_source | unknown",
            },
        )
        self.manager.write_json(run_id, "production/production_report.json", report.model_dump(mode="json"))
        return report

    def metrics_store(self, run_id: str, plan_id: str | None = None) -> ExecutionMetricsStore:
        if plan_id is None:
            plan_id = self.load_plan(run_id).plan_id
        return ExecutionMetricsStore(self.manager.run_dir(run_id), run_id=run_id, plan_id=plan_id)

    def _load_selected(self, run_id: str) -> ProductionPlan | None:
        try:
            return self.load_plan(run_id)
        except FileNotFoundError:
            return None

    def _historical_metrics(self) -> dict[str, dict[str, float]]:
        counts: dict[str, dict[str, int]] = {}
        for path in self.manager.runs_dir.glob("*/production/execution_metrics.json"):
            try:
                metrics = ExecutionMetrics.model_validate_json(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            for item in metrics.stages:
                entry = counts.setdefault(item.provider, {"total": 0, "failed": 0})
                entry["total"] += 1
                entry["failed"] += int(not item.success)
        return {
            provider: {
                "failure_rate": value["failed"] / value["total"],
                "sample_count": float(value["total"]),
            }
            for provider, value in counts.items()
            if value["total"]
        }

    def _effective_optimization(self, quality_target: str) -> Any:
        optimization = self.config.optimization.model_copy(deep=True)
        if quality_target != "standard":
            return optimization
        standard = optimization.routing.setdefault("standard", {})
        configured = {
            "research": f"research.{self.config.research.provider}",
            "script": f"llm.{self.config.llm.provider}",
            "storyboard": f"llm.{self.config.llm.provider}",
            "tts": f"tts.{self.config.tts.provider}",
            "subtitle_alignment": (
                f"asr.{self.config.asr.provider}" if self.config.asr.enabled else "subtitle.deterministic"
            ),
            "render": f"render.{self.config.video.renderer}",
            "cover": "cover.template",
        }
        for task, provider_id in configured.items():
            standard.setdefault(task, [provider_id])
        return optimization
