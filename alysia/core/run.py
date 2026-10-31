from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from alysia.core.state import Stage
from alysia.core.io import StateRecoveryError, atomic_write_json, atomic_write_text, load_json_with_recovery


def utc_now() -> datetime:
    return datetime.now().astimezone()


class RunState(BaseModel):
    run_id: str
    topic: str
    created_at: datetime
    updated_at: datetime
    current_stage: Stage = Stage.CREATED
    completed_stages: list[Stage] = Field(default_factory=list)
    failed_stage: Stage | None = None
    error_message: str | None = None
    artifacts: dict[str, str] = Field(default_factory=dict)
    config_snapshot: dict[str, Any] = Field(default_factory=dict)
    pipeline_phase: str = "text"
    milestone: str | None = None
    text_pipeline_completed: bool = False
    audio_pipeline_completed: bool = False
    video_pipeline_completed: bool = False
    package_pipeline_completed: bool = False
    review_ready: bool = False
    analytics_imported: bool = False
    analysis_completed: bool = False
    learning_completed: bool = False
    strategy_ready: bool = False
    publish_job_id: str | None = None
    external_id: str | None = None
    feedback_imported: bool = False
    planning_provenance: dict[str, Any] | None = None
    creator_job_id: str | None = None

    def start_stage(self, stage: Stage) -> None:
        self.current_stage = stage
        self.failed_stage = None
        self.error_message = None
        self.updated_at = utc_now()

    def complete_stage(self, stage: Stage) -> None:
        if stage not in self.completed_stages:
            self.completed_stages.append(stage)
        self.current_stage = stage
        self.updated_at = utc_now()

    def fail_stage(self, stage: Stage, error: Exception) -> None:
        self.current_stage = Stage.FAILED
        self.failed_stage = stage
        self.error_message = str(error)
        self.updated_at = utc_now()


class RunManager:
    def __init__(self, runs_dir: Path) -> None:
        self.runs_dir = runs_dir.resolve()
        self.runs_dir.mkdir(parents=True, exist_ok=True)

    def create(
        self,
        topic: str,
        config_snapshot: dict[str, Any],
        *,
        planning_provenance: dict[str, Any] | None = None,
    ) -> RunState:
        now = utc_now()
        run_id = f"{now:%Y%m%d_%H%M%S}_{uuid4().hex[:8]}"
        state = RunState(
            run_id=run_id,
            topic=topic,
            created_at=now,
            updated_at=now,
            artifacts={"input": "input.json", "run_state": "run_state.json"},
            config_snapshot=config_snapshot,
            planning_provenance=planning_provenance,
        )
        run_dir = self.run_dir(run_id)
        (run_dir / "logs").mkdir(parents=True, exist_ok=False)
        self.write_json(
            run_id,
            "input.json",
            {
                "run_id": run_id,
                "topic": topic,
                "created_at": now,
                "config": config_snapshot,
                "planning_provenance": planning_provenance,
            },
        )
        self.save(state)
        self.append_event(run_id, "run_created", stage=Stage.CREATED)
        return state

    def run_dir(self, run_id: str) -> Path:
        if not run_id or Path(run_id).name != run_id:
            raise ValueError("run_id 格式无效")
        return self.runs_dir / run_id

    def load(self, run_id: str) -> RunState:
        state_path = self.run_dir(run_id) / "run_state.json"
        if not state_path.is_file():
            raise FileNotFoundError(f"找不到 run：{run_id}")
        try:
            return load_json_with_recovery(
                state_path,
                validator=RunState.model_validate,
                backup_count=2,
                on_recovery=lambda backup: self._record_state_recovery(run_id, backup),
            )
        except StateRecoveryError as exc:
            self._record_state_blocked(run_id, exc)
            self.append_event(run_id, "state_corrupt_human_intervention_required", stage=Stage.FAILED)
            raise

    def save(self, state: RunState) -> None:
        state.updated_at = utc_now()
        self.write_json(state.run_id, "run_state.json", state.model_dump(mode="json"))

    def write_json(self, run_id: str, filename: str, payload: Any) -> Path:
        path = self.run_dir(run_id) / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        backup_count = 2 if filename in {"run_state.json", "workflow_state.json"} else 0
        atomic_write_json(path, payload, backup_count=backup_count)
        return path

    def read_json(self, run_id: str, filename: str) -> Any:
        path = self.run_dir(run_id) / filename
        return json.loads(path.read_text(encoding="utf-8"))

    def write_text(self, run_id: str, filename: str, content: str) -> Path:
        path = self.run_dir(run_id) / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(path, content.rstrip() + "\n")
        return path

    def artifact_exists(self, state: RunState, key: str) -> bool:
        from alysia.reliability.artifacts import ArtifactIntegrityChecker

        relative = state.artifacts.get(key)
        if not relative:
            return False
        result = ArtifactIntegrityChecker().check(
            self.run_dir(state.run_id) / relative,
            producer=key,
        )
        return result.validity == "valid"

    def append_event(self, run_id: str, event: str, *, stage: Stage) -> None:
        path = self.run_dir(run_id) / "logs" / "events.jsonl"
        import json

        record = json.dumps(
            {"at": utc_now().isoformat(), "event": event, "stage": stage.value},
            ensure_ascii=False,
        )
        with path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(record + "\n")

    def _record_state_recovery(self, run_id: str, backup: Path) -> None:
        from uuid import uuid4

        from alysia.reliability.failures import FailureStore
        from alysia.schemas.reliability import FailureCategory, FailureRecord

        record = FailureRecord(
            failure_id=f"failure_{uuid4().hex[:16]}", run_id=run_id, stage="run_state",
            category=FailureCategory.STATE_CORRUPT,
            message=f"run_state.json 损坏，已从 {backup.name} 恢复",
            evidence_refs=[str(backup)], occurred_at=utc_now(), recoverable=True, retryable=False,
            suggested_action="已恢复最近有效状态副本并记录事件", status="recovered",
        )
        FailureStore(self.run_dir(run_id) / "reliability" / "failures").save(record)
        self.append_event(run_id, f"state_restored_from:{backup.name}", stage=Stage.FAILED)

    def _record_state_blocked(self, run_id: str, error: StateRecoveryError) -> None:
        from uuid import uuid4

        from alysia.reliability.failures import FailureStore
        from alysia.schemas.reliability import FailureCategory, FailureRecord

        record = FailureRecord(
            failure_id=f"failure_{uuid4().hex[:16]}", run_id=run_id, stage="run_state",
            category=FailureCategory.STATE_CORRUPT, message=str(error),
            evidence_refs=[str(error.path)], occurred_at=utc_now(), recoverable=True, retryable=False,
            suggested_action="没有有效 backup；需要人工确认状态", status="escalated",
        )
        FailureStore(self.run_dir(run_id) / "reliability" / "failures").save(record)
