from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from alysia.schemas import WorkflowEvaluationReport, WorkflowPlan, WorkflowState, WorkflowTask

from .store import WorkflowStore


class WorkflowEvaluator:
    def evaluate(
        self,
        task: WorkflowTask,
        plan: WorkflowPlan,
        state: WorkflowState,
        store: WorkflowStore,
    ) -> WorkflowEvaluationReport:
        results = self._results(store.workflow_dir(plan) / "step_results.jsonl")
        step_rates: dict[str, float] = {}
        retries: dict[str, int] = {}
        fallbacks: list[str] = []
        resources: dict[str, object] = {}
        qa: dict[str, object] = {}
        for step in plan.steps:
            attempts = [item for item in results if item.get("step_id") == step.step_id]
            successes = sum(item.get("status") == "completed" for item in attempts)
            step_rates[step.step_id] = successes / max(1, len(attempts))
            retries[step.step_id] = max(0, len(attempts) - 1)
            for item in attempts:
                if item.get("fallback_used"):
                    fallbacks.append(str(item.get("implementation_id")))
                resources.update(item.get("resource_observations") or {})
                qa.update(item.get("qa_outcomes") or {})
        unmet = [criterion for criterion in task.success_criteria if not self._criterion_met(criterion, state, qa)]
        elapsed = sum(float(item.get("elapsed_sec", 0) or 0) for item in results)
        reliability = sum(step_rates.values()) / max(1, len(step_rates))
        criteria_score = (len(task.success_criteria) - len(unmet)) / len(task.success_criteria)
        success = state.status == "completed" and not unmet
        score = round(0.6 * criteria_score + 0.4 * reliability, 4)
        return WorkflowEvaluationReport(
            workflow_id=plan.workflow_id, run_id=plan.run_id, task_success=success,
            step_success_rates=step_rates, elapsed_time_sec=elapsed,
            fallbacks=list(dict.fromkeys(fallbacks)), retries=retries,
            resource_observations=resources, qa_outcomes=qa, unmet_criteria=unmet,
            overall_score=score, reliability=round(reliability, 4),
            recommendation="reuse" if success and score >= 0.8 else "revise" if score >= 0.5 else "do_not_reuse",
            created_at=datetime.now().astimezone(),
        )

    @staticmethod
    def _criterion_met(criterion: str, state: WorkflowState, qa: dict[str, object]) -> bool:
        if criterion == "status:completed":
            return state.status == "completed"
        if criterion.startswith("artifact:"):
            name = criterion.split(":", 1)[1]
            return name in state.artifacts and Path(state.artifacts[name]).is_file()
        if criterion.startswith("qa:"):
            name = criterion.split(":", 1)[1]
            return qa.get(name) is True or name in state.artifacts
        return False

    @staticmethod
    def _results(path: Path) -> list[dict]:
        if not path.is_file():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
