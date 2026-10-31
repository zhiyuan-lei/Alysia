from __future__ import annotations

from alysia.schemas import CandidatePlan, SimulationScenario


class CounterfactualCandidateGenerator:
    def __init__(self, max_candidates: int = 5) -> None:
        self.max_candidates = max_candidates

    def generate(self, scenario: SimulationScenario) -> list[CandidatePlan]:
        actions = scenario.candidate_actions
        if len(actions) < 2:
            raise ValueError("Counterfactual simulation 至少需要 2 个 candidate actions")
        if len(actions) > self.max_candidates:
            raise ValueError(f"candidate 数量超过 max_candidates={self.max_candidates}")
        candidates: list[CandidatePlan] = []
        for index, action in enumerate(actions, 1):
            changed = dict(action.get("changed_variables", {}))
            prohibited = {"bypass_approval", "publish_without_approval", "identity_change_without_approval"}
            if any(bool(changed.get(key)) for key in prohibited):
                continue
            candidates.append(CandidatePlan(
                candidate_id=str(action.get("candidate_id") or f"candidate_{index}"),
                actions=list(action.get("actions", [])), changed_variables=changed,
                held_constant={**scenario.fixed_variables, **dict(action.get("held_constant", {}))},
                required_capabilities=list(action.get("required_capabilities", [])),
                expected_approvals=list(dict.fromkeys([
                    *scenario.approval_policy.required_gates,
                    *action.get("expected_approvals", []),
                ])),
                rationale=str(action.get("rationale") or "由 scenario candidate_actions 明确提供"),
            ))
        if len(candidates) < 2:
            raise ValueError("policy 过滤后不足 2 个有效候选")
        return candidates
