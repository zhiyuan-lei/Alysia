from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path

from alysia.core.io import atomic_write_json
from alysia.creator.models import (
    ApprovalStatus,
    BilibiliPublicationReceipt,
    ContentObservation,
    CreatorJob,
    CreatorReflection,
    PublishAttempt,
    PublishStatus,
    RecoveryEvent,
    RevisionRecord,
)
from alysia.creator.store import CreatorJobStore


class CreatorJobService:
    def __init__(self, store: CreatorJobStore) -> None:
        self.store = store

    @staticmethod
    def _now() -> datetime:
        return datetime.now().astimezone()

    def create(
        self,
        *,
        topic: str,
        topic_source: str,
        topic_score: float,
        testing: bool = False,
        dry_run: bool = False,
    ) -> CreatorJob:
        now = self._now()
        job = CreatorJob.new(
            created_at=now,
            updated_at=now,
            topic=topic,
            topic_source=topic_source,
            topic_score=topic_score,
            testing=testing,
            dry_run=dry_run,
        )
        self.store.save(job)
        return job

    def attach_run(self, job_id: str, run_id: str) -> CreatorJob:
        job = self.store.load(job_id)
        if job.run_id and job.run_id != run_id:
            raise ValueError("CreatorJob already bound to a different run")
        job.run_id = run_id
        return self._save(job)

    def submit_for_review(self, job_id: str) -> CreatorJob:
        job = self.store.load(job_id)
        if job.status != "DRAFT":
            raise ValueError("only DRAFT CreatorJob can enter REVIEW")
        if not job.qa_report or not job.qa_report.passed:
            raise ValueError("CreatorJob requires passing QA before REVIEW")
        job.status = "REVIEW"
        job.approval_status = ApprovalStatus.REVIEW
        return self._save(job)

    def approve(
        self,
        job_id: str,
        *,
        approved_by: str,
        package_hash: str,
        approval_ref: str | None = None,
    ) -> CreatorJob:
        job = self.store.load(job_id)
        if job.status != "REVIEW":
            raise ValueError("only REVIEW CreatorJob can become APPROVED")
        if not approved_by.startswith("human:"):
            raise ValueError("APPROVED requires a human actor")
        if len(package_hash) != 64:
            raise ValueError("package_hash must be SHA-256")
        if not job.qa_report or not job.qa_report.passed:
            raise ValueError("APPROVED requires passing CreatorQA")
        job.status = "APPROVED"
        job.approval_status = ApprovalStatus.APPROVED
        job.approved_by = approved_by
        job.approved_at = self._now()
        job.package_hash = package_hash
        job.approval_ref = approval_ref
        return self._save(job)

    def reject(self, job_id: str, *, reason: str, rejected_by: str) -> CreatorJob:
        job = self.store.load(job_id)
        if job.status != "REVIEW":
            raise ValueError("only REVIEW CreatorJob can be REJECTED")
        if not rejected_by.startswith("human:"):
            raise ValueError("REJECTED requires a human actor")
        snapshot = self.store.save_revision(job)
        job.revisions.append(
            RevisionRecord(
                revision=job.current_revision,
                reason=reason,
                requested_by=rejected_by,
                requested_at=self._now(),
                snapshot_path=snapshot,
            )
        )
        job.status = "BLOCKED"
        job.approval_status = ApprovalStatus.REJECTED
        job.publish_status = PublishStatus.NOT_READY
        return self._save(job)

    def request_revision(self, job_id: str, *, reason: str, requested_by: str) -> CreatorJob:
        job = self.store.load(job_id)
        if job.status != "REVIEW":
            raise ValueError("only REVIEW CreatorJob can receive REQUEST_REVISION")
        if not requested_by.startswith("human:"):
            raise ValueError("REQUEST_REVISION requires a human actor")
        snapshot = self.store.save_revision(job)
        job.revisions.append(
            RevisionRecord(
                revision=job.current_revision,
                reason=reason,
                requested_by=requested_by,
                requested_at=self._now(),
                snapshot_path=snapshot,
            )
        )
        job.current_revision += 1
        job.status = "DRAFT"
        job.approval_status = ApprovalStatus.REVISION_REQUIRED
        job.approved_by = None
        job.approved_at = None
        job.approval_ref = None
        job.package_hash = None
        job.package_path = None
        job.publish_status = PublishStatus.NOT_READY
        return self._save(job)

    def mark_publish_ready(self, job_id: str, *, package_path: Path) -> CreatorJob:
        job = self.store.load(job_id)
        if job.status != "APPROVED" or job.approval_status != "APPROVED":
            raise ValueError("CreatorJob must be APPROVED before PUBLISH_READY")
        if not job.qa_report or not job.qa_report.passed:
            raise ValueError("PUBLISH_READY requires passing CreatorQA")
        if not job.video_path or not job.video_path.is_file():
            raise ValueError("PUBLISH_READY requires an existing video")
        if not job.thumbnail_path or not job.thumbnail_path.is_file():
            raise ValueError("PUBLISH_READY requires an existing thumbnail")
        if not job.package_hash:
            raise ValueError("PUBLISH_READY requires package_hash")
        manifest = {
            "job_id": job.job_id,
            "revision": job.current_revision,
            "platform": "bilibili",
            "title": job.selected_title,
            "description": job.description,
            "tags": job.tags,
            "video_path": str(job.video_path),
            "thumbnail_path": str(job.thumbnail_path),
            "package_hash": job.package_hash,
            "prepared_at": self._now().isoformat(),
            "action": "human_upload_required",
        }
        atomic_write_json(package_path, manifest)
        job.package_path = package_path.resolve()
        job.status = "PUBLISH_READY"
        job.publish_status = PublishStatus.PUBLISH_READY
        job.publish_attempts.append(
            PublishAttempt(
                attempt=len(job.publish_attempts) + 1,
                attempted_at=self._now(),
                status="PREPARED",
                idempotency_key=self._idempotency_key(job),
            )
        )
        return self._save(job)

    def record_publication(
        self,
        job_id: str,
        receipt: BilibiliPublicationReceipt,
    ) -> CreatorJob:
        job = self.store.load(job_id)
        if job.status == "PUBLISHED":
            if (
                job.platform_content_id == receipt.content_id
                and job.publication_url == receipt.publication_url
                and job.publication_evidence_path == receipt.evidence_path.resolve()
            ):
                return job
            raise ValueError("CreatorJob already PUBLISHED with a different receipt")
        if job.status != "PUBLISH_READY":
            raise ValueError("CreatorJob must be PUBLISH_READY before publication")
        if job.testing or job.dry_run:
            raise ValueError("testing/dry-run jobs are not eligible for real publication")
        if not receipt.evidence_path.is_file() or receipt.evidence_path.stat().st_size == 0:
            raise ValueError("real publication receipt evidence is missing")
        job.status = "PUBLISHED"
        job.publish_status = PublishStatus.PUBLISHED
        job.platform_content_id = receipt.content_id
        job.publication_url = receipt.publication_url
        job.published_at = receipt.published_at
        job.publication_evidence_path = receipt.evidence_path.resolve()
        job.evidence_paths.append(receipt.evidence_path.resolve())
        job.publish_attempts.append(
            PublishAttempt(
                attempt=len(job.publish_attempts) + 1,
                attempted_at=receipt.recorded_at,
                status="PUBLISHED",
                idempotency_key=self._idempotency_key(job),
            )
        )
        return self._save(job)

    def record_publish_failure(
        self,
        job_id: str,
        *,
        error: str,
        terminal: bool,
        retry_after: datetime | None = None,
    ) -> CreatorJob:
        job = self.store.load(job_id)
        if job.status not in {"PUBLISH_READY", "FAILED"}:
            raise ValueError("publish failure can only be recorded for PUBLISH_READY/FAILED")
        job.failure_count += 1
        job.publish_status = PublishStatus.FAILED
        job.status = "FAILED" if terminal else "PUBLISH_READY"
        job.publish_attempts.append(
            PublishAttempt(
                attempt=len(job.publish_attempts) + 1,
                attempted_at=self._now(),
                status="MANUAL_INTERVENTION" if terminal else "FAILED",
                error=error,
                retry_after=retry_after,
                terminal=terminal,
                idempotency_key=self._idempotency_key(job),
            )
        )
        return self._save(job)

    def record_recovery_event(
        self,
        job_id: str,
        *,
        stage: str,
        failure: str,
        recovery_result: str,
        terminal: bool,
    ) -> CreatorJob:
        job = self.store.load(job_id)
        job.failure_count += 1
        job.recovery_result = recovery_result
        job.recovery_events.append(
            RecoveryEvent(
                stage=stage,
                failure=failure,
                recoverable=not terminal,
                recovery_result=recovery_result,
                occurred_at=self._now(),
                terminal=terminal,
            )
        )
        if terminal:
            job.status = "FAILED"
        return self._save(job)

    def add_observation(self, job_id: str, observation: ContentObservation) -> CreatorJob:
        job = self.store.load(job_id)
        if job.status != "PUBLISHED" or observation.content_id != job.platform_content_id:
            raise ValueError("observation must belong to a PUBLISHED CreatorJob")
        if not observation.evidence_path.is_file() or observation.evidence_path.stat().st_size == 0:
            raise ValueError("real observation evidence is missing")
        key = (observation.observed_at.isoformat(), observation.source)
        if any((item.observed_at.isoformat(), item.source) == key for item in job.metrics):
            return job
        job.metrics.append(observation)
        job.metrics.sort(key=lambda item: item.observed_at)
        return self._save(job)

    def set_reflection(self, job_id: str, reflection: CreatorReflection) -> CreatorJob:
        job = self.store.load(job_id)
        if job.status != "PUBLISHED":
            raise ValueError("reflection requires a PUBLISHED CreatorJob")
        job.reflection = reflection
        return self._save(job)

    def _save(self, job: CreatorJob) -> CreatorJob:
        job.updated_at = self._now()
        self.store.save(job)
        return job

    @staticmethod
    def _idempotency_key(job: CreatorJob) -> str:
        value = f"{job.job_id}|{job.current_revision}|{job.package_hash}|bilibili"
        return hashlib.sha256(value.encode("utf-8")).hexdigest()
