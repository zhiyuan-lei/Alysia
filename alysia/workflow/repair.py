from __future__ import annotations

import hashlib
from datetime import datetime

from alysia.schemas import RepairPlan, WorkflowPlan, WorkflowState, WorkflowStep

from .contracts import RegistryView


class WorkflowRepairPlanner:
    def __init__(self, *, max_repair_rounds: int = 2) -> None:
        self.max_repair_rounds = max_repair_rounds

    def propose(
        self,
        plan: WorkflowPlan,
        state: WorkflowState,
        step: WorkflowStep,
        error: str,
        registry: RegistryView,
    ) -> RepairPlan:
        digest = hashlib.sha256(f"{plan.workflow_id}:{step.step_id}:{state.repair_rounds}:{error}".encode()).hexdigest()[:12]
        base = dict(
            repair_id=f"repair_{digest}", workflow_id=plan.workflow_id,
            failed_step_id=step.step_id, created_at=datetime.now().astimezone(),
        )
        if state.repair_rounds >= self.max_repair_rounds:
            return RepairPlan(**base, action="escalate_to_human", reason="达到 max repair rounds", approval_required=True)
        step_state = state.steps[step.step_id]
        max_retries = int(step.retry_policy.get("max_retries", 0))
        if step_state.attempts <= max_retries:
            return RepairPlan(**base, action="retry_same_step", selected_implementation=step.implementation_id, reason=error)
        for fallback in step.fallback:
            try:
                contract = registry.get(fallback)
            except KeyError:
                continue
            if contract.source_type == "skill" and contract.status != "active":
                continue
            if (
                contract.execution_layer == step.execution_layer
                and set(step.inputs).issubset(contract.accepted_inputs)
                and set(step.outputs).issubset(contract.produced_outputs)
            ):
                return RepairPlan(
                    **base, action="use_approved_fallback", selected_implementation=fallback,
                    reason=f"主能力失败：{error}",
                )
        if step.optional:
            return RepairPlan(**base, action="skip_optional_step", reason=error)
        if "missing" in error.lower() or "不存在" in error:
            return RepairPlan(**base, action="create_capability_gap_proposal", reason=error, approval_required=True)
        return RepairPlan(**base, action="return_to_artifact_owner", reason=error, approval_required=True)
