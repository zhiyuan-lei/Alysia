from __future__ import annotations

from datetime import datetime
from contextlib import contextmanager
from pathlib import Path
from collections.abc import Iterator
from uuid import uuid4

from alysia.core.io import atomic_write_json
from alysia.schemas.reliability import LongRunningTaskRecord


class LongRunningTaskMonitor:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def start(
        self,
        task_type: str,
        *,
        expected_timeout: float,
        run_id: str | None = None,
        pid: int | None = None,
        job_id: str | None = None,
    ) -> LongRunningTaskRecord:
        now = datetime.now().astimezone()
        record = LongRunningTaskRecord(
            task_id=f"task_{uuid4().hex[:16]}", task_type=task_type, run_id=run_id,
            started_at=now, last_heartbeat=now, expected_timeout=expected_timeout,
            pid=pid, job_id=job_id,
        )
        self._save(record)
        return record

    @contextmanager
    def track(
        self,
        task_type: str,
        *,
        expected_timeout: float,
        run_id: str | None = None,
        pid: int | None = None,
        job_id: str | None = None,
    ) -> Iterator[LongRunningTaskRecord]:
        record = self.start(
            task_type, expected_timeout=expected_timeout, run_id=run_id, pid=pid, job_id=job_id,
        )
        try:
            yield record
        except Exception as exc:
            self.finish(record.task_id, status="failed", error=str(exc))
            raise
        else:
            self.finish(record.task_id, status="completed")

    def heartbeat(self, task_id: str, **details: object) -> LongRunningTaskRecord:
        record = self.load(task_id)
        if record.status != "running":
            return record
        record.last_heartbeat = datetime.now().astimezone()
        record.details.update(details)
        self._save(record)
        return record

    def finish(self, task_id: str, *, status: str = "completed", **details: object) -> LongRunningTaskRecord:
        record = self.load(task_id)
        record.last_heartbeat = datetime.now().astimezone()
        record.status = status
        record.details.update(details)
        self._save(record)
        return record

    def timed_out(self, task_id: str, *, now: datetime | None = None) -> bool:
        record = self.load(task_id)
        current = now or datetime.now().astimezone()
        elapsed = (current - record.last_heartbeat).total_seconds()
        if record.status == "running" and elapsed > record.expected_timeout:
            record.status = "timed_out"
            record.details["heartbeat_age_sec"] = elapsed
            self._save(record)
            return True
        return False

    def load(self, task_id: str) -> LongRunningTaskRecord:
        if not task_id or Path(task_id).name != task_id:
            raise ValueError("task_id 格式无效")
        path = self.root / f"{task_id}.json"
        if not path.is_file():
            raise FileNotFoundError(path)
        return LongRunningTaskRecord.model_validate_json(path.read_text(encoding="utf-8"))

    def list(self) -> list[LongRunningTaskRecord]:
        output: list[LongRunningTaskRecord] = []
        for path in sorted(self.root.glob("task_*.json")):
            try:
                output.append(LongRunningTaskRecord.model_validate_json(path.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                continue
        return output

    def _save(self, record: LongRunningTaskRecord) -> Path:
        return atomic_write_json(
            self.root / f"{record.task_id}.json", record.model_dump(mode="json"), backup_count=2,
        )
