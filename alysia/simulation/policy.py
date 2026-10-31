from __future__ import annotations

from datetime import datetime

from alysia.core.config import SimulationConfig
from alysia.schemas import CounterfactualComparison, SimulationDecision, SimulationScenario, SimulationResults


class SimulationDecisionPolicy:
    def __init__(self, config: SimulationConfig) -> None:
        self.config = config

    def decide(self, scenario: SimulationScenario, results: SimulationResults, comparison: CounterfactualComparison) -> SimulationDecision:
        selected = comparison.recommendation if comparison.recommendation != "no_recommendation" else None
        selected_result = next((item for item in results.candidates if item.candidate_id == selected), None)
        risk = None
        if selected_result:
            prediction = next((item for item in selected_result.predictions if item.metric == "risk_score"), None)
            if prediction and isinstance(prediction.point_estimate, (int, float)):
                risk = float(prediction.point_estimate)
        approvals = list(dict.fromkeys([
            *scenario.approval_policy.required_gates,
            *(selected_result.approval_gates_preserved if selected_result else []),
        ]))
        high_impact = any([
            scenario.approval_policy.real_publish,
            scenario.approval_policy.identity_change,
            scenario.approval_policy.major_replan,
            bool(approvals),
        ])
        low_risk = risk is not None and risk <= 0.25
        can_auto = all([
            self.config.auto_select_low_risk_only,
            scenario.approval_policy.allow_auto_select,
            low_risk,
            not high_impact,
            selected is not None,
        ])
        reasons = [
            "simulation 只提供决策辅助；真实执行仍由现有 Supervisor/Studio/Production 分层负责",
        ]
        if high_impact:
            reasons.append("涉及审批、发布、身份或重大 replan，必须 recommendation_only")
        if risk is None:
            reasons.append("risk unknown，默认 conservative")
        return SimulationDecision(
            scenario_id=scenario.scenario_id,
            mode="auto_select" if can_auto else "recommendation_only",
            selected_candidate_id=selected, recommendation=comparison.recommendation,
            required_approvals=approvals, dispatch_allowed=can_auto,
            reasons=reasons, decided_at=datetime.now().astimezone(),
        )

