from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel

from alysia.core.run import RunManager
from alysia.core.io import atomic_write_text, load_json_with_recovery
from alysia.studio.protocol import (
    AgentDecision,
    AgentHandoff,
    AgentResult,
    ArtifactRef,
    RevisionRequest,
    StudioQAReport,
    StudioState,
    StudioTraceEvent,
)

ModelT = TypeVar("ModelT", bound=BaseModel)
_SENSITIVE_KEY = re.compile(r"(?:token|secret|password|cookie|authorization|api[_-]?key)", re.I)


class StudioTraceStore:
    def __init__(self, manager: RunManager, run_id: str) -> None:
        self.manager = manager
        self.run_id = run_id
        self.root = manager.run_dir(run_id) / "studio"
        self.context_dir = self.root / "context_snapshots"
        self.root.mkdir(parents=True, exist_ok=True)
        self.context_dir.mkdir(parents=True, exist_ok=True)

    def save_state(self, state: StudioState) -> Path:
        return self._write_json("studio_state.json", state.model_dump(mode="json"))

    def load_state(self) -> StudioState | None:
        path = self.root / "studio_state.json"
        return load_json_with_recovery(path, validator=StudioState.model_validate, backup_count=2) if path.is_file() else None

    def append_trace(self, event: StudioTraceEvent) -> None:
        path = self.root / "studio_trace.jsonl"
        payload = json.dumps(_redact(event.model_dump(mode="json")), ensure_ascii=False, default=str)
        with path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(payload + "\n")

    def save_handoff(self, handoff: AgentHandoff) -> None:
        self._upsert("handoffs.json", handoff, "handoff_id")

    def handoffs(self) -> list[AgentHandoff]:
        return self._load_list("handoffs.json", AgentHandoff)

    def save_result(self, result: AgentResult) -> None:
        self._upsert("agent_results.json", result, "task_id")
        decisions = self.decisions()
        by_id = {item.decision_id: item for item in decisions}
        by_id.update({item.decision_id: item for item in result.decisions})
        self._write_json("decisions.json", [item.model_dump(mode="json") for item in by_id.values()])

    def results(self) -> list[AgentResult]:
        return self._load_list("agent_results.json", AgentResult)

    def decisions(self) -> list[AgentDecision]:
        return self._load_list("decisions.json", AgentDecision)

    def save_artifact(self, artifact: ArtifactRef) -> None:
        self._upsert("artifacts.json", artifact, "artifact_id")

    def artifacts(self) -> list[ArtifactRef]:
        return self._load_list("artifacts.json", ArtifactRef)

    def save_revision(self, request: RevisionRequest) -> None:
        self._upsert("revision_requests.json", request, "request_id")

    def revisions(self) -> list[RevisionRequest]:
        return self._load_list("revision_requests.json", RevisionRequest)

    def save_context_snapshot(self, payload: BaseModel, version: int) -> Path:
        path = self.context_dir / f"context.v{version:04d}.json"
        encoded = json.dumps(_redact(payload.model_dump(mode="json")), ensure_ascii=False, indent=2, default=str) + "\n"
        self._atomic_write(path, encoded)
        return path

    def latest_context_version(self) -> int:
        versions = []
        for path in self.context_dir.glob("context.v*.json"):
            try:
                versions.append(int(path.stem.split("v")[-1]))
            except ValueError:
                continue
        return max(versions, default=0)

    def save_qa(self, report: StudioQAReport) -> Path:
        return self._write_json("studio_qa_report.json", report.model_dump(mode="json"))

    def trace_records(self) -> list[dict[str, Any]]:
        path = self.root / "studio_trace.jsonl"
        if not path.is_file():
            return []
        records = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                records.append(json.loads(line))
        return records

    def _upsert(self, filename: str, value: BaseModel, key: str) -> None:
        path = self.root / filename
        payload = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else []
        dumped = value.model_dump(mode="json")
        for index, item in enumerate(payload):
            if item.get(key) == dumped.get(key):
                payload[index] = dumped
                break
        else:
            payload.append(dumped)
        self._write_json(filename, payload)

    def _load_list(self, filename: str, model: type[ModelT]) -> list[ModelT]:
        path = self.root / filename
        if not path.is_file():
            return []
        return [model.model_validate(item) for item in json.loads(path.read_text(encoding="utf-8"))]

    def _write_json(self, filename: str, payload: Any) -> Path:
        path = self.root / filename
        encoded = json.dumps(_redact(payload), ensure_ascii=False, indent=2, default=str) + "\n"
        self._atomic_write(path, encoded, backup_count=2 if filename == "studio_state.json" else 0)
        return path

    @staticmethod
    def _atomic_write(path: Path, content: str, *, backup_count: int = 0) -> None:
        atomic_write_text(path, content, backup_count=backup_count)


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): "[REDACTED]" if _SENSITIVE_KEY.search(str(key)) else _redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value
