from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from alysia.capabilities.store import atomic_json
from alysia.core.io import atomic_write_json, load_json_with_recovery
from alysia.schemas import (
    StepExecutionResult,
    WorkflowEvaluationReport,
    WorkflowPlan,
    WorkflowQAReport,
    WorkflowState,
    WorkflowStepState,
    WorkflowTask,
    WorkflowValidationReport,
)


class WorkflowStore:
    def __init__(self, runs_dir: Path, task_dir: Path = Path("workspace/workflows/tasks")) -> None:
        self.runs_dir = runs_dir.resolve()
        self.task_dir = task_dir.resolve()

    def save_task(self, task: WorkflowTask) -> Path:
        return atomic_json(self.task_dir / f"{task.task_id}.json", task.model_dump(mode="json"))

    def load_task(self, task_id_or_path: str | Path) -> WorkflowTask:
        path = Path(task_id_or_path)
        if not path.is_file():
            path = self.task_dir / f"{task_id_or_path}.json"
        if not path.is_file():
            raise FileNotFoundError(f"WorkflowTask 不存在：{task_id_or_path}")
        return WorkflowTask.model_validate_json(path.read_text(encoding="utf-8"))

    def workflow_dir(self, plan: WorkflowPlan) -> Path:
        return self.runs_dir / plan.run_id / "workflow"

    def save_plan(self, plan: WorkflowPlan) -> Path:
        return atomic_json(self.workflow_dir(plan) / "workflow_plan.json", plan.model_dump(mode="json"))

    def load_plan(self, workflow_id: str) -> WorkflowPlan:
        path = self._find(workflow_id, "workflow_plan.json")
        return WorkflowPlan.model_validate_json(path.read_text(encoding="utf-8"))

    def initialize_state(self, plan: WorkflowPlan) -> WorkflowState:
        now = datetime.now().astimezone()
        state = WorkflowState(
            workflow_id=plan.workflow_id, run_id=plan.run_id, status=plan.status,
            steps={step.step_id: WorkflowStepState(step_id=step.step_id) for step in plan.steps},
            created_at=now, updated_at=now,
        )
        self.save_state(plan, state)
        return state

    def save_state(self, plan: WorkflowPlan, state: WorkflowState) -> Path:
        state.updated_at = datetime.now().astimezone()
        return atomic_write_json(
            self.workflow_dir(plan) / "workflow_state.json", state.model_dump(mode="json"), backup_count=2,
        )

    def load_state(self, plan: WorkflowPlan) -> WorkflowState:
        path = self.workflow_dir(plan) / "workflow_state.json"
        return load_json_with_recovery(path, validator=WorkflowState.model_validate, backup_count=2)

    def append_result(self, plan: WorkflowPlan, result: StepExecutionResult) -> None:
        self._append_jsonl(self.workflow_dir(plan) / "step_results.jsonl", result.model_dump(mode="json"))

    def append_trace(self, plan: WorkflowPlan, event: dict[str, Any]) -> None:
        payload = {"created_at": datetime.now().astimezone().isoformat(), **event}
        self._append_jsonl(self.workflow_dir(plan) / "workflow_trace.jsonl", payload)

    def save_validation(self, plan: WorkflowPlan, report: WorkflowValidationReport) -> Path:
        return atomic_json(self.workflow_dir(plan) / "workflow_validation_report.json", report.model_dump(mode="json"))

    def save_evaluation(self, plan: WorkflowPlan, report: WorkflowEvaluationReport) -> Path:
        return atomic_json(self.workflow_dir(plan) / "workflow_evaluation_report.json", report.model_dump(mode="json"))

    def load_evaluation(self, plan: WorkflowPlan) -> WorkflowEvaluationReport:
        path = self.workflow_dir(plan) / "workflow_evaluation_report.json"
        return WorkflowEvaluationReport.model_validate_json(path.read_text(encoding="utf-8"))

    def save_qa(self, plan: WorkflowPlan, report: WorkflowQAReport) -> Path:
        return atomic_json(self.workflow_dir(plan) / "workflow_qa_report.json", report.model_dump(mode="json"))

    def materialize_inputs(self, plan: WorkflowPlan, task: WorkflowTask) -> dict[str, str]:
        result: dict[str, str] = {}
        for name in task.inputs:
            path = self.workflow_dir(plan) / "inputs" / f"{name}.json"
            if not path.exists():
                atomic_json(path, {"artifact": name, "task_id": task.task_id, "context_refs": task.context_refs})
            result[name] = str(path)
        return result

    def artifact_path(self, plan: WorkflowPlan, step_id: str, artifact: str) -> Path:
        return self.workflow_dir(plan) / "artifacts" / step_id / f"{artifact}.json"

    def _find(self, workflow_id: str, filename: str) -> Path:
        for path in self.runs_dir.glob(f"*/workflow/{filename}"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if payload.get("workflow_id") == workflow_id:
                return path
        raise FileNotFoundError(f"Workflow 不存在：{workflow_id}")

    @staticmethod
    def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str) + "\n")
