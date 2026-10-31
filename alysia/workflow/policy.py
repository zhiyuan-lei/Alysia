from __future__ import annotations

from alysia.schemas import WorkflowPlan, WorkflowTask

from .contracts import RegistryView


class CompositionPolicy:
    def __init__(self, *, max_skill_hops: int = 12, allow_unapproved_skills: bool = False) -> None:
        self.max_skill_hops = max_skill_hops
        self.allow_unapproved_skills = allow_unapproved_skills

    def check(self, task: WorkflowTask, plan: WorkflowPlan, registry: RegistryView) -> list[str]:
        errors: list[str] = []
        selected = {step.implementation_id for step in plan.steps}
        skill_hops = sum(step.skill_id is not None for step in plan.steps)
        if skill_hops > self.max_skill_hops:
            errors.append(f"skill hops {skill_hops} 超过上限 {self.max_skill_hops}")
        for step in plan.steps:
            try:
                contract = registry.get(
                    step.implementation_id,
                    source_type="skill" if step.skill_id else "capability",
                )
            except KeyError as exc:
                errors.append(str(exc))
                continue
            if step.skill_id and contract.status != "active" and not self.allow_unapproved_skills:
                errors.append(f"Skill 未处于 active/registered：{step.skill_id} ({contract.status})")
            if "no_mock_in_production" in contract.policy_restrictions and task.execution_mode == "production":
                if any("mock" in item.lower() for item in task.constraints):
                    errors.append(f"production 不允许 mock skill artifact：{step.implementation_id}")
            if contract.execution_layer != step.execution_layer:
                errors.append(
                    f"{step.step_id} execution layer 不匹配：plan={step.execution_layer}, registry={contract.execution_layer}"
                )
            missing_prerequisites = set(contract.prerequisites) - selected
            if missing_prerequisites:
                errors.append(f"{step.step_id} 缺少 capability prerequisites：{sorted(missing_prerequisites)}")
            peak = contract.resource_requirements.get("peak_vram_mb")
            if isinstance(peak, (int, float)) and peak > task.budget_policy.max_local_vram_mb:
                errors.append(f"{step.step_id} 资源预算越界：peak_vram_mb={peak}")
            if (
                contract.resource_requirements.get("gpu_heavy")
                and not isinstance(peak, (int, float))
                and task.execution_mode == "production"
                and not task.budget_policy.allow_unknown_resources
            ):
                errors.append(f"{step.step_id} production 资源预算未知")
            for fallback_id in step.fallback:
                try:
                    fallback = registry.get(fallback_id)
                except KeyError:
                    errors.append(f"fallback 不存在：{fallback_id}")
                    continue
                if fallback.source_type == "skill" and fallback.status != "active":
                    errors.append(f"fallback skill 未获批准/未 active：{fallback_id}")
                if fallback.execution_layer != step.execution_layer:
                    errors.append(f"fallback layer 不兼容：{fallback_id}")
                if not set(step.inputs).issubset(fallback.accepted_inputs) or not set(step.outputs).issubset(fallback.produced_outputs):
                    errors.append(f"fallback contract 不兼容：{fallback_id}")
        required_gates = set(task.approval_policy.required_gates)
        if any("publish" in step.implementation_id for step in plan.steps):
            required_gates.add("human_publish_approval")
        if not required_gates.issubset(set(plan.approval_points)):
            errors.append(f"缺少 approval points：{sorted(required_gates - set(plan.approval_points))}")
        return errors
