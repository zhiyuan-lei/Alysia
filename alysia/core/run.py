from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from alysia.core.state import Stage


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

    def create(self, topic: str, config_snapshot: dict[str, Any]) -> RunState:
        now = utc_now()
        run_id = f"{now:%Y%m%d_%H%M%S}_{uuid4().hex[:8]}"
        state = RunState(
            run_id=run_id,
            topic=topic,
            created_at=now,
            updated_at=now,
            artifacts={"input": "input.json", "run_state": "run_state.json"},
            config_snapshot=config_snapshot,
        )
        run_dir = self.run_dir(run_id)
        (run_dir / "logs").mkdir(parents=True, exist_ok=False)
        self.write_json(
            run_id,
            "input.json",
            {"run_id": run_id, "topic": topic, "created_at": now, "config": config_snapshot},
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
        return RunState.model_validate_json(state_path.read_text(encoding="utf-8"))

    def save(self, state: RunState) -> None:
        state.updated_at = utc_now()
        self.write_json(state.run_id, "run_state.json", state.model_dump(mode="json"))

    def write_json(self, run_id: str, filename: str, payload: Any) -> Path:
        path = self.run_dir(run_id) / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        encoded = json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n"
        self._atomic_write(path, encoded)
        return path

    def read_json(self, run_id: str, filename: str) -> Any:
        path = self.run_dir(run_id) / filename
        return json.loads(path.read_text(encoding="utf-8"))

    def write_text(self, run_id: str, filename: str, content: str) -> Path:
        path = self.run_dir(run_id) / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        self._atomic_write(path, content.rstrip() + "\n")
        return path

    def artifact_exists(self, state: RunState, key: str) -> bool:
        relative = state.artifacts.get(key)
        return bool(relative and (self.run_dir(state.run_id) / relative).is_file())

    def append_event(self, run_id: str, event: str, *, stage: Stage) -> None:
        path = self.run_dir(run_id) / "logs" / "events.jsonl"
        record = json.dumps(
            {"at": utc_now().isoformat(), "event": event, "stage": stage.value},
            ensure_ascii=False,
        )
        with path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(record + "\n")

    @staticmethod
    def _atomic_write(path: Path, content: str) -> None:
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(content, encoding="utf-8", newline="\n")
        temporary.replace(path)
