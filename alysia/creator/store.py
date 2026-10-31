from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Mapping

from alysia.core.io import atomic_write_json, load_json_with_recovery
from alysia.creator.models import CreatorJob
from alysia.creator.models import ApprovalStatus, PublishStatus


APPROVAL_SENSITIVE_FIELDS = {
    "script",
    "title_candidates",
    "selected_title",
    "description",
    "tags",
    "video_path",
    "thumbnail_path",
    "research_sources",
    "claims",
    "uncertainties",
    "creator_plan",
    "visual_plan",
    "audio_plan",
}


class CreatorJobStore:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.jobs_dir = self.root / "jobs"
        self.jobs_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _safe_id(job_id: str) -> str:
        if not job_id or Path(job_id).name != job_id or not job_id.startswith("creator_"):
            raise ValueError("invalid CreatorJob job_id")
        return job_id

    def job_dir(self, job_id: str) -> Path:
        return self.jobs_dir / self._safe_id(job_id)

    def path_for(self, job_id: str) -> Path:
        return self.job_dir(job_id) / "creator_job.json"

    def revision_path(self, job_id: str, revision: int) -> Path:
        if revision < 1:
            raise ValueError("revision must be >= 1")
        return self.job_dir(job_id) / "revisions" / f"revision_{revision:04d}.json"

    def save(self, job: CreatorJob) -> Path:
        validated = CreatorJob.model_validate(job.model_dump())
        path = self.path_for(validated.job_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        return atomic_write_json(path, validated.model_dump(mode="json"), backup_count=2)

    def create(self, job: CreatorJob) -> Path:
        path = self.path_for(job.job_id)
        if path.exists():
            raise FileExistsError(f"CreatorJob already exists: {job.job_id}")
        return self.save(job)

    def update(
        self,
        job_id: str,
        changes: Mapping[str, object],
        *,
        reason: str,
        updated_by: str,
    ) -> CreatorJob:
        if not reason.strip():
            raise ValueError("revision reason is required")
        if not updated_by.strip():
            raise ValueError("revision actor is required")
        reserved = {"job_id", "created_at", "updated_at", "current_revision", "revisions"}
        invalid = reserved.intersection(changes)
        unknown = set(changes).difference(CreatorJob.model_fields)
        if invalid:
            raise ValueError("cannot update reserved fields: " + ", ".join(sorted(invalid)))
        if unknown:
            raise ValueError("unknown CreatorJob fields: " + ", ".join(sorted(unknown)))

        current = self.load(job_id)
        now = datetime.now().astimezone()
        snapshot_path = self.revision_path(job_id, current.current_revision)
        payload = current.model_dump()
        payload.update(changes)
        payload["current_revision"] = current.current_revision + 1
        payload["updated_at"] = now
        if (
            current.approval_status == ApprovalStatus.APPROVED
            and APPROVAL_SENSITIVE_FIELDS.intersection(changes)
        ):
            payload.update(
                status="DRAFT",
                approval_status=ApprovalStatus.DRAFT,
                approved_by=None,
                approved_at=None,
                approval_ref=None,
                package_hash=None,
                package_path=None,
                publish_status=PublishStatus.NOT_READY,
            )
        payload["revisions"] = [
            *current.revisions,
            {
                "revision": current.current_revision,
                "reason": reason,
                "requested_by": updated_by,
                "requested_at": now,
                "snapshot_path": snapshot_path,
                "status": "COMPLETED",
            },
        ]
        updated = CreatorJob.model_validate(payload)
        self.save_revision(current)
        self.save(updated)
        return updated

    def save_revision(self, job: CreatorJob) -> Path:
        job = CreatorJob.model_validate(job.model_dump())
        path = self.revision_path(job.job_id, job.current_revision)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            existing = CreatorJob.model_validate(json.loads(path.read_text(encoding="utf-8")))
            if existing.model_dump(mode="json") != job.model_dump(mode="json"):
                raise FileExistsError(f"revision snapshot already exists: {path}")
            return path
        return atomic_write_json(path, job.model_dump(mode="json"))

    def load(self, job_id: str) -> CreatorJob:
        path = self.path_for(job_id)
        if not path.is_file():
            raise FileNotFoundError(f"CreatorJob not found: {job_id}")
        return load_json_with_recovery(path, validator=CreatorJob.model_validate, backup_count=2)

    def list(self) -> list[CreatorJob]:
        jobs: list[CreatorJob] = []
        for path in sorted(self.jobs_dir.glob("creator_*/creator_job.json")):
            try:
                jobs.append(CreatorJob.model_validate(json.loads(path.read_text(encoding="utf-8"))))
            except (OSError, ValueError):
                continue
        return jobs

    def find_by_run_id(self, run_id: str) -> CreatorJob | None:
        return next((job for job in self.list() if job.run_id == run_id), None)
