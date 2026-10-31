from __future__ import annotations

import hashlib
from datetime import datetime

from alysia.schemas import CandidateCapability, WorkflowPlan, WorkflowStep, WorkflowTask

from .contracts import RegistryView


class WorkflowPlanner:
    def __init__(self, *, max_steps: int = 20) -> None:
        self.max_steps = max_steps

    def plan(
        self,
        task: WorkflowTask,
        candidates: list[CandidateCapability],
        registry: RegistryView,
        *,
        run_id: str | None = None,
    ) -> WorkflowPlan:
        now = datetime.now().astimezone()
        digest = hashlib.sha256(f"{task.task_id}:{now.isoformat()}".encode()).hexdigest()[:12]
        workflow_id = f"wf_{digest}"
        run_id = run_id or workflow_id
        eligible = [item for item in candidates if item.eligible]
        producers: dict[str, list[CandidateCapability]] = {}
        for item in eligible:
            for output in item.produced_outputs:
                producers.setdefault(output, []).append(item)
        for values in producers.values():
            values.sort(key=lambda item: (item.source_type == "skill", item.match_score, item.confidence), reverse=True)

        initial = set(task.inputs)
        selected: dict[str, CandidateCapability] = {}
        artifact_owner: dict[str, str] = {}
        gaps: list[str] = []
        visiting: set[str] = set()

        def resolve(artifact: str) -> bool:
            if artifact in initial or artifact in artifact_owner:
                return True
            if artifact in visiting:
                return False
            visiting.add(artifact)
            for candidate in producers.get(artifact, []):
                snapshot_selected = dict(selected)
                snapshot_owner = dict(artifact_owner)
                if all(resolve(required) for required in candidate.accepted_inputs):
                    step_id = selected.get(candidate.candidate_id)
                    if step_id is None:
                        selected[candidate.candidate_id] = candidate
                    for output in candidate.produced_outputs:
                        artifact_owner[output] = candidate.candidate_id
                    visiting.remove(artifact)
                    return True
                selected.clear(); selected.update(snapshot_selected)
                artifact_owner.clear(); artifact_owner.update(snapshot_owner)
            visiting.remove(artifact)
            return False

        for output in task.desired_outputs:
            if not resolve(output) and output not in gaps:
                gaps.append(output)

        steps: list[WorkflowStep] = []
        id_by_impl = {impl: f"step_{index:02d}_{impl}" for index, impl in enumerate(selected, 1)}
        for impl, candidate in selected.items():
            dependencies = sorted({
                id_by_impl[artifact_owner[item]]
                for item in candidate.accepted_inputs
                if item in artifact_owner and artifact_owner[item] != impl
            })
            steps.append(WorkflowStep(
                step_id=id_by_impl[impl],
                capability_id=impl if candidate.source_type == "capability" else None,
                skill_id=impl if candidate.source_type == "skill" else None,
                owner_agent=candidate.owner_agent, inputs=candidate.accepted_inputs,
                outputs=candidate.produced_outputs, depends_on=dependencies,
                retry_policy={"max_retries": 1},
                fallback=[], validation=[f"produces:{item}" for item in candidate.produced_outputs],
                execution_layer=candidate.execution_layer,
            ))
        steps = self._topological(steps)
        if len(steps) > self.max_steps:
            gaps.append(f"workflow steps {len(steps)} 超过 max_steps={self.max_steps}")
            steps = []

        approval_points = list(dict.fromkeys(task.approval_policy.required_gates))
        for step in steps:
            contract = registry.get(step.implementation_id, source_type="skill" if step.skill_id else "capability")
            approval_points.extend(
                item for item in contract.policy_restrictions
                if item in {"human_publish_approval", "identity_approval", "budget_approval"}
            )
        status = "blocked_waiting_capability" if gaps else "planned"
        return WorkflowPlan(
            workflow_id=workflow_id, run_id=run_id, task_id=task.task_id, status=status,
            steps=steps, dependencies=[(dep, step.step_id) for step in steps for dep in step.depends_on],
            selected_capabilities=[step.implementation_id for step in steps],
            fallback_steps=[item for step in steps for item in step.fallback],
            expected_artifacts=sorted({item for step in steps for item in step.outputs}),
            approval_points=list(dict.fromkeys(approval_points)),
            quality_gates=["workflow_validation", *[item for item in task.success_criteria if item.startswith("qa:")]],
            resource_notes=[item for candidate in selected.values() for item in candidate.resource_notes],
            unresolved_gaps=gaps, registry_versions=registry.versions(), created_at=now,
        )

    @staticmethod
    def _topological(steps: list[WorkflowStep]) -> list[WorkflowStep]:
        remaining = {step.step_id: step for step in steps}
        ordered: list[WorkflowStep] = []
        completed: set[str] = set()
        while remaining:
            ready = [step for step in remaining.values() if set(step.depends_on) <= completed]
            if not ready:
                return steps
            for step in sorted(ready, key=lambda item: item.step_id):
                ordered.append(step)
                completed.add(step.step_id)
                remaining.pop(step.step_id)
        return ordered
