from __future__ import annotations

from datetime import datetime

from alysia.schemas import WorkflowPlan, WorkflowTask, WorkflowValidationReport

from .contracts import RegistryView
from .policy import CompositionPolicy


class WorkflowValidator:
    def __init__(self, policy: CompositionPolicy, *, max_steps: int = 20) -> None:
        self.policy = policy
        self.max_steps = max_steps

    def validate(self, task: WorkflowTask, plan: WorkflowPlan, registry: RegistryView) -> WorkflowValidationReport:
        errors: list[str] = []
        warnings: list[str] = []
        if plan.unresolved_gaps:
            errors.append(f"存在 unresolved capability gaps：{plan.unresolved_gaps}")
        if len(plan.steps) > self.max_steps:
            errors.append(f"steps 超过 max_steps={self.max_steps}")
        step_ids = [step.step_id for step in plan.steps]
        if len(step_ids) != len(set(step_ids)):
            errors.append("step_id 重复")
        if self._has_cycle(plan):
            errors.append("workflow dependency graph 存在循环")
        available = set(task.inputs)
        for step in self._ordered(plan):
            try:
                contract = registry.get(step.implementation_id, source_type="skill" if step.skill_id else "capability")
            except KeyError as exc:
                errors.append(str(exc)); continue
            missing = set(step.inputs) - available
            if missing:
                errors.append(f"{step.step_id} 缺少输入 contract：{sorted(missing)}")
            if not set(step.inputs).issubset(set(contract.accepted_inputs)):
                errors.append(f"{step.step_id} 输入与 registry contract 不兼容")
            if not set(step.outputs).issubset(set(contract.produced_outputs)):
                errors.append(f"{step.step_id} 输出与 registry contract 不兼容")
            available.update(step.outputs)
        missing_outputs = set(task.desired_outputs) - available
        if missing_outputs:
            errors.append(f"计划无法产生 desired outputs：{sorted(missing_outputs)}")
        errors.extend(self.policy.check(task, plan, registry))
        if task.execution_mode == "production" and any("mock" in item.lower() for item in plan.selected_capabilities):
            errors.append("production workflow 包含 mock/testing capability")
        return WorkflowValidationReport(
            workflow_id=plan.workflow_id, passed=not errors, errors=list(dict.fromkeys(errors)),
            warnings=warnings, checked_steps=len(plan.steps), checked_at=datetime.now().astimezone(),
        )

    @staticmethod
    def _has_cycle(plan: WorkflowPlan) -> bool:
        deps = {step.step_id: set(step.depends_on) for step in plan.steps}
        completed: set[str] = set()
        while deps:
            ready = {step_id for step_id, requirements in deps.items() if requirements <= completed}
            if not ready:
                return True
            completed.update(ready)
            for step_id in ready:
                deps.pop(step_id)
        return False

    @staticmethod
    def _ordered(plan: WorkflowPlan):
        by_id = {step.step_id: step for step in plan.steps}
        return [by_id[step.step_id] for step in plan.steps if step.step_id in by_id]
