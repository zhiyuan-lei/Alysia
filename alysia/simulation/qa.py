from __future__ import annotations

from datetime import datetime

from alysia.core.config import SimulationConfig
from alysia.schemas import SimulationDecision, SimulationQAReport, SimulationResults, SimulationScenario


class SimulationQA:
    def __init__(self, config: SimulationConfig) -> None:
        self.config = config

    def run(self, scenario: SimulationScenario, results: SimulationResults, decision: SimulationDecision | None = None) -> SimulationQAReport:
        errors: list[str] = []
        warnings: list[str] = []
        count_ok = 2 <= len(results.candidates) <= self.config.max_candidates
        if not count_ok:
            errors.append("candidate 数量必须在 2..max_candidates 范围")
        all_marked = all(
            prediction.estimate_type in {"known", "derived", "simulated", "unknown"}
            for candidate in results.candidates for prediction in candidate.predictions
        )
        uncertainty_ok = all(
            prediction.confidence and (
                prediction.estimate_type not in {"derived", "simulated"} or prediction.assumptions
            )
            for candidate in results.candidates for prediction in candidate.predictions
        )
        unknown_ok = all(
            prediction.estimate_type != "unknown"
            or (prediction.point_estimate is None and prediction.range is None)
            for candidate in results.candidates for prediction in candidate.predictions
        )
        approvals_ok = all(
            set(scenario.approval_policy.required_gates) <= set(candidate.approval_gates_preserved)
            for candidate in results.candidates
        )
        isolation_ok = not results.real_metrics_written and not results.real_providers_called
        if not all_marked:
            errors.append("存在未标记的 simulated data")
        if not uncertainty_ok:
            errors.append("derived/simulated prediction 缺少 uncertainty/assumption")
        if not unknown_ok:
            errors.append("unknown 被强行估算")
        if not approvals_ok:
            errors.append("simulation 丢失 required approval gate")
        if not isolation_ok:
            errors.append("dry-run 调用了真实 provider 或写入真实 metrics")
        if decision and decision.mode == "recommendation_only" and decision.dispatch_allowed:
            errors.append("recommendation_only 不得允许 dispatch")
        if any(not item.predictions for item in results.candidates):
            warnings.append("部分 candidate 没有 evaluator prediction")
        checks = {
            "candidate_limit": count_ok,
            "simulated_values_marked": all_marked,
            "uncertainty_required": uncertainty_ok,
            "unknown_not_fabricated": unknown_ok,
            "approval_gate_preserved": approvals_ok,
            "simulation_reality_isolation": isolation_ok,
            "finite_depth": self.config.max_depth <= 2,
        }
        return SimulationQAReport(
            scenario_id=scenario.scenario_id, passed=not errors,
            errors=errors, warnings=warnings, checks=checks,
            checked_at=datetime.now().astimezone(),
        )

