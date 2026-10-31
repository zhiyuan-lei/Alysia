from __future__ import annotations

from datetime import datetime
from pathlib import Path

from alysia.schemas import WorkflowPlan, WorkflowQAReport, WorkflowState, WorkflowTask, WorkflowValidationReport

from .contracts import RegistryView


class WorkflowQA:
    def run(
        self,
        task: WorkflowTask,
        plan: WorkflowPlan,
        state: WorkflowState,
        validation: WorkflowValidationReport,
        registry: RegistryView,
        *,
        max_repair_rounds: int,
    ) -> WorkflowQAReport:
        errors = list(validation.errors)
        checks = {
            "registry_status": True, "contracts": validation.passed, "cycle_free": True,
            "artifacts_present": True, "approval_preserved": True, "budget_preserved": True,
            "mock_not_in_production": True, "repair_limit": True, "recipe_provenance": True,
        }
        if state.status in {"failed", "blocked", "blocked_waiting_capability"}:
            errors.append(f"workflow terminal state 未成功：{state.status}")
        if any("资源预算" in item for item in validation.errors):
            checks["budget_preserved"] = False
        for step in plan.steps:
            contract = registry.get(step.implementation_id, source_type="skill" if step.skill_id else "capability")
            if step.skill_id and contract.status != "active":
                checks["registry_status"] = False
                errors.append(f"不可执行 skill：{step.skill_id} ({contract.status})")
        if self._cycle(plan):
            checks["cycle_free"] = False; errors.append("workflow 存在 cycle")
        if state.status == "completed":
            missing = [name for name in plan.expected_artifacts if name not in state.artifacts or not Path(state.artifacts[name]).is_file()]
            if missing:
                checks["artifacts_present"] = False; errors.append(f"缺少 artifacts：{missing}")
        if any("publish" in step.implementation_id for step in plan.steps) and "human_publish_approval" not in plan.approval_points:
            checks["approval_preserved"] = False; errors.append("publish approval gate 被遗漏")
        if task.execution_mode == "production" and task.approval_policy.allow_mock_artifacts:
            checks["mock_not_in_production"] = False; errors.append("production 不能允许 mock artifacts")
        if state.repair_rounds > max_repair_rounds:
            checks["repair_limit"] = False; errors.append("repair loop 超过配置上限")
        if plan.recipe_id and (not plan.recipe_evidence_runs or not plan.recipe_adjustments):
            checks["recipe_provenance"] = False; errors.append("recipe provenance 缺失")
        return WorkflowQAReport(
            workflow_id=plan.workflow_id, passed=not errors and all(checks.values()),
            errors=list(dict.fromkeys(errors)), warnings=list(validation.warnings), checks=checks,
            checked_at=datetime.now().astimezone(),
        )

    @staticmethod
    def _cycle(plan: WorkflowPlan) -> bool:
        graph = {step.step_id: set(step.depends_on) for step in plan.steps}
        done: set[str] = set()
        while graph:
            ready = {key for key, deps in graph.items() if deps <= done}
            if not ready:
                return True
            done |= ready
            for key in ready:
                graph.pop(key)
        return False
