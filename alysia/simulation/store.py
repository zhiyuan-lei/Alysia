from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel

from alysia.capabilities.store import atomic_json

T = TypeVar("T", bound=BaseModel)
_SAFE_ID = re.compile(r"^[A-Za-z0-9_-]+$")


class SimulationStore:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def scenario_dir(self, scenario_id: str) -> Path:
        if not _SAFE_ID.fullmatch(scenario_id):
            raise ValueError("scenario_id 只能包含字母、数字、下划线和连字符")
        path = (self.root / scenario_id).resolve()
        if path.parent != self.root:
            raise ValueError("simulation path 越界")
        return path

    def save(self, scenario_id: str, filename: str, payload: BaseModel | dict[str, Any] | list[Any]) -> Path:
        if Path(filename).name != filename or not filename.endswith((".json", ".jsonl")):
            raise ValueError("simulation artifact filename 非法")
        data = payload.model_dump(mode="json") if isinstance(payload, BaseModel) else payload
        return atomic_json(self.scenario_dir(scenario_id) / filename, data)

    def load(self, scenario_id: str, filename: str, model: type[T]) -> T:
        path = self.scenario_dir(scenario_id) / filename
        if not path.is_file():
            raise FileNotFoundError(f"Simulation artifact 不存在：{scenario_id}/{filename}")
        return model.model_validate_json(path.read_text(encoding="utf-8"))

    def load_json(self, scenario_id: str, filename: str) -> Any:
        path = self.scenario_dir(scenario_id) / filename
        if not path.is_file():
            raise FileNotFoundError(f"Simulation artifact 不存在：{scenario_id}/{filename}")
        return json.loads(path.read_text(encoding="utf-8"))

    def append_trace(self, scenario_id: str, event_id: str, payload: dict[str, Any]) -> None:
        path = self.scenario_dir(scenario_id) / "trace.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        existing_ids: set[str] = set()
        if path.is_file():
            for line in path.read_text(encoding="utf-8").splitlines():
                try:
                    existing_ids.add(str(json.loads(line).get("event_id")))
                except ValueError:
                    continue
        if event_id in existing_ids:
            return
        with path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps({"event_id": event_id, **payload}, ensure_ascii=False, sort_keys=True, default=str) + "\n")

    def history(self) -> list[dict[str, Any]]:
        if not self.root.is_dir():
            return []
        rows: list[dict[str, Any]] = []
        for directory in sorted(path for path in self.root.iterdir() if path.is_dir()):
            scenario = directory / "scenario.json"
            if not scenario.is_file():
                continue
            payload = json.loads(scenario.read_text(encoding="utf-8"))
            rows.append({
                "scenario_id": payload.get("scenario_id"),
                "objective": payload.get("objective"),
                "created_at": payload.get("created_at"),
                "has_results": (directory / "simulation_results.json").is_file(),
                "has_decision": (directory / "decision.json").is_file(),
            })
        return rows

