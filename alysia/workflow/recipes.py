from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

from alysia.capabilities.store import atomic_json, load_models
from alysia.schemas import (
    WorkflowEvaluationReport,
    WorkflowPlan,
    WorkflowRecipe,
    WorkflowRecipeStep,
    WorkflowStep,
    WorkflowTask,
)

from .contracts import RegistryView


class WorkflowRecipeStore:
    def __init__(self, root: Path, *, validation_successes: int = 3) -> None:
        self.root = root.resolve()
        self.validation_successes = validation_successes

    def list(self) -> list[WorkflowRecipe]:
        return load_models(self.root, WorkflowRecipe)

    def get(self, recipe_id: str) -> WorkflowRecipe:
        path = self.root / f"{recipe_id}.json"
        if not path.is_file():
            raise KeyError(f"WorkflowRecipe 不存在：{recipe_id}")
        return WorkflowRecipe.model_validate_json(path.read_text(encoding="utf-8"))

    def record(
        self,
        task: WorkflowTask,
        plan: WorkflowPlan,
        evaluation: WorkflowEvaluationReport,
    ) -> WorkflowRecipe:
        pattern = self.task_pattern(task)
        signature = {
            "pattern": pattern,
            "steps": [(step.capability_id, step.skill_id, step.inputs, step.outputs) for step in plan.steps],
        }
        digest = hashlib.sha256(json.dumps(signature, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]
        recipe_id = f"recipe_{digest}"
        now = datetime.now().astimezone()
        try:
            recipe = self.get(recipe_id)
        except KeyError:
            recipe = WorkflowRecipe(
                recipe_id=recipe_id, name=f"{task.objective[:60]} workflow", task_pattern=pattern,
                required_capabilities=[
                    f"{step.skill_id}@{plan.registry_versions.get(step.skill_id, 'unknown')}" if step.skill_id
                    else f"{step.capability_id}@{plan.registry_versions.get(step.capability_id or '', 'unknown')}"
                    for step in plan.steps
                ],
                steps_template=[WorkflowRecipeStep(
                    step_id=step.step_id, capability_id=step.capability_id, skill_id=step.skill_id,
                    owner_agent=step.owner_agent, inputs=step.inputs, outputs=step.outputs,
                    depends_on=step.depends_on, fallback=step.fallback, execution_layer=step.execution_layer,
                ) for step in plan.steps],
                constraints=task.constraints, quality_gates=plan.quality_gates,
                created_at=now, updated_at=now,
            )
        if plan.run_id not in recipe.evidence_runs:
            recipe.evidence_runs.append(plan.run_id)
            if evaluation.task_success:
                recipe.success_count += 1
            else:
                recipe.failure_count += 1
        total = recipe.success_count + recipe.failure_count
        recipe.confidence = round((recipe.success_count + 1) / (total + 2), 4)
        recipe.status = "validated" if recipe.success_count >= self.validation_successes else "candidate"
        if recipe.failure_count > recipe.success_count:
            recipe.status = "deprecated"
        recipe.updated_at = now
        atomic_json(self.root / f"{recipe.recipe_id}.json", recipe.model_dump(mode="json"))
        return recipe

    def retrieve(self, task: WorkflowTask, registry: RegistryView) -> WorkflowRecipe | None:
        pattern = self.task_pattern(task)
        candidates = [item for item in self.list() if item.status == "validated" and self._versions_valid(item, registry)]
        if not candidates:
            return None
        desired = set(pattern["desired_outputs"])
        keywords = set(pattern["keywords"])
        scored = []
        for item in candidates:
            outputs = set(item.task_pattern.get("desired_outputs", []))
            other_keywords = set(item.task_pattern.get("keywords", []))
            output_score = len(desired & outputs) / max(1, len(desired | outputs))
            keyword_score = len(keywords & other_keywords) / max(1, len(keywords | other_keywords))
            scored.append((0.8 * output_score + 0.2 * keyword_score, item.confidence, item))
        best = max(scored, key=lambda value: (value[0], value[1]))
        return best[2] if best[0] >= 0.6 else None

    def clone(self, task: WorkflowTask, recipe: WorkflowRecipe, registry: RegistryView, *, run_id: str) -> WorkflowPlan:
        now = datetime.now().astimezone()
        digest = hashlib.sha256(f"{task.task_id}:{now.isoformat()}:recipe".encode()).hexdigest()[:12]
        return WorkflowPlan(
            workflow_id=f"wf_{digest}", run_id=run_id, task_id=task.task_id,
            steps=[WorkflowStep(
                step_id=step.step_id, capability_id=step.capability_id, skill_id=step.skill_id,
                owner_agent=step.owner_agent, inputs=step.inputs, outputs=step.outputs,
                depends_on=step.depends_on, fallback=step.fallback,
                retry_policy={"max_retries": 1}, validation=[f"produces:{item}" for item in step.outputs],
                execution_layer=step.execution_layer,
            ) for step in recipe.steps_template],
            dependencies=[(dep, step.step_id) for step in recipe.steps_template for dep in step.depends_on],
            selected_capabilities=[step.skill_id or step.capability_id or "" for step in recipe.steps_template],
            fallback_steps=[item for step in recipe.steps_template for item in step.fallback],
            expected_artifacts=sorted({item for step in recipe.steps_template for item in step.outputs}),
            approval_points=list(task.approval_policy.required_gates), quality_gates=recipe.quality_gates,
            recipe_id=recipe.recipe_id, recipe_evidence_runs=recipe.evidence_runs,
            recipe_adjustments=["cloned for current task_id", "current budget/approval policy revalidated"],
            registry_versions=registry.versions(), created_at=now,
        )

    @staticmethod
    def task_pattern(task: WorkflowTask) -> dict:
        stop = {"the", "and", "for", "with", "一个", "进行", "已有"}
        keywords = [item for item in re.findall(r"[a-zA-Z0-9_]+|[\u4e00-\u9fff]{2,}", task.objective.lower()) if item not in stop]
        return {
            "keywords": sorted(set(keywords)), "inputs": sorted(task.inputs),
            "desired_outputs": sorted(task.desired_outputs), "quality_target": task.quality_target,
        }

    @staticmethod
    def _versions_valid(recipe: WorkflowRecipe, registry: RegistryView) -> bool:
        versions = registry.versions()
        for required in recipe.required_capabilities:
            implementation, _, version = required.partition("@")
            if versions.get(implementation) != version:
                return False
        return True
