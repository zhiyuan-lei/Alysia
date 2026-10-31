from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from alysia.schemas import SupervisorTraceEvent


_SENSITIVE_KEY = re.compile(r"(?:token|secret|password|cookie|authorization|api[_-]?key)", re.I)


class SupervisorTraceStore:
    def __init__(self, root: Path) -> None:
        self.path = root.resolve() / "supervisor_trace.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, event: SupervisorTraceEvent) -> None:
        payload = _redact(event.model_dump(mode="json"))
        with self.path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")

    def records(self) -> list[dict[str, Any]]:
        if not self.path.is_file():
            return []
        return [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): "[REDACTED]" if _SENSITIVE_KEY.search(str(key)) else _redact(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value

