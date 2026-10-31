from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from alysia.core.io import atomic_write_json, load_json_with_recovery
from alysia.schemas.reliability import CheckpointRecord

from .artifacts import ArtifactIntegrityChecker


class CheckpointManager:
    def __init__(self, root: Path, *, integrity: ArtifactIntegrityChecker | None = None) -> None:
        self.root = root.resolve()
        self.records_dir = self.root / "records"
        self.snapshots_dir = self.root / "snapshots"
        self.records_dir.mkdir(parents=True, exist_ok=True)
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)
        self.integrity = integrity or ArtifactIntegrityChecker(compute_hash=True)

    def create(
        self,
        *,
        run_id: str,
        stage: str,
        status: str,
        state_payload: dict[str, Any],
        artifact_paths: list[Path] | None = None,
        workflow_id: str | None = None,
        producer: str = "checkpoint_manager",
    ) -> CheckpointRecord:
        now = datetime.now().astimezone()
        checkpoint_id = f"checkpoint_{now:%Y%m%dT%H%M%S%f}_{uuid4().hex[:8]}"
        snapshot = self.snapshots_dir / f"{checkpoint_id}.json"
        atomic_write_json(snapshot, state_payload, backup_count=0)
        artifacts = [self.integrity.check(path, producer=producer) for path in (artifact_paths or [])]
        record = CheckpointRecord(
            checkpoint_id=checkpoint_id,
            run_id=run_id,
            workflow_id=workflow_id,
            stage=stage,
            status=status,
            state_snapshot=snapshot,
            artifacts=artifacts,
            created_at=now,
            valid=all(item.validity == "valid" for item in artifacts),
        )
        atomic_write_json(
            self.records_dir / f"{checkpoint_id}.json", record.model_dump(mode="json"), backup_count=2,
        )
        return record

    def validate(self, checkpoint_id: str) -> CheckpointRecord:
        record = self._load(checkpoint_id)
        snapshot = self.integrity.check(record.state_snapshot, producer="checkpoint_manager")
        artifacts = [self.integrity.check(item.path, producer=item.producer) for item in record.artifacts]
        record.artifacts = artifacts
        record.valid = snapshot.validity == "valid" and all(item.validity == "valid" for item in artifacts)
        record.invalid_reason = None if record.valid else "; ".join(
            [*snapshot.errors, *[error for item in artifacts for error in item.errors]]
        )
        atomic_write_json(
            self.records_dir / f"{checkpoint_id}.json", record.model_dump(mode="json"), backup_count=2,
        )
        return record

    def restore(self, checkpoint_id: str | None = None, *, stage: str | None = None) -> tuple[CheckpointRecord, dict[str, Any]]:
        candidates = [self._load(checkpoint_id)] if checkpoint_id else list(reversed(self.list(stage=stage)))
        for record in candidates:
            validated = self.validate(record.checkpoint_id)
            if not validated.valid or validated.status not in {"started", "succeeded", "failed"}:
                continue
            payload = load_json_with_recovery(validated.state_snapshot, backup_count=0)
            return validated, payload
        raise RuntimeError("没有可恢复的有效 checkpoint")

    def invalidate(self, checkpoint_id: str, reason: str) -> CheckpointRecord:
        record = self._load(checkpoint_id)
        record.status = "invalidated"
        record.valid = False
        record.invalid_reason = reason
        atomic_write_json(
            self.records_dir / f"{checkpoint_id}.json", record.model_dump(mode="json"), backup_count=2,
        )
        return record

    def list(self, *, stage: str | None = None) -> list[CheckpointRecord]:
        records: list[CheckpointRecord] = []
        for path in sorted(self.records_dir.glob("checkpoint_*.json")):
            try:
                item = CheckpointRecord.model_validate_json(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if stage is None or item.stage == stage:
                records.append(item)
        return records

    def _load(self, checkpoint_id: str | None) -> CheckpointRecord:
        if not checkpoint_id or Path(checkpoint_id).name != checkpoint_id:
            raise ValueError("checkpoint_id 格式无效")
        path = self.records_dir / f"{checkpoint_id}.json"
        if not path.is_file():
            raise FileNotFoundError(path)
        return CheckpointRecord.model_validate_json(path.read_text(encoding="utf-8"))

