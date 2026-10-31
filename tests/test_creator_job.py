from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from alysia.creator import ApprovalStatus, CreatorJob, CreatorJobStore, CreatorQAReport, PublishStatus


def make_job() -> CreatorJob:
    now = datetime.now().astimezone()
    return CreatorJob.new(
        created_at=now,
        updated_at=now,
        topic="Alpha22 CreatorJob",
        topic_source="human",
        topic_score=100,
    )


def passing_qa() -> CreatorQAReport:
    return CreatorQAReport(
        passed=True,
        content_passed=True,
        video_passed=True,
        copy_passed=True,
        safety_passed=True,
        duplicate_passed=True,
        checked_at=datetime.now().astimezone(),
    )


def test_create_serialize_deserialize_and_load(tmp_path: Path) -> None:
    store = CreatorJobStore(tmp_path / "creator_jobs")
    job = make_job()

    path = store.create(job)
    serialized = job.model_dump_json()

    assert path.is_file()
    assert CreatorJob.model_validate_json(serialized) == job
    assert store.load(job.job_id) == job
    with pytest.raises(FileExistsError, match="already exists"):
        store.create(job)


def test_missing_job_id_is_rejected() -> None:
    payload = make_job().model_dump()
    payload.pop("job_id")

    with pytest.raises(ValidationError, match="job_id"):
        CreatorJob.model_validate(payload)


def test_approval_transition_requires_review_and_human_actor() -> None:
    job = make_job()

    with pytest.raises(ValueError, match="invalid approval transition"):
        job.transition_approval(ApprovalStatus.APPROVED, approved_by="human:owner")

    review = job.transition_approval(ApprovalStatus.REVIEW)
    with pytest.raises(ValueError, match="human actor"):
        review.transition_approval(ApprovalStatus.APPROVED, approved_by="agent:creator")

    approved = review.transition_approval(ApprovalStatus.APPROVED, approved_by="human:owner")
    assert approved.approval_status == ApprovalStatus.APPROVED
    assert approved.approved_by == "human:owner"


def test_unapproved_job_cannot_enter_publish_ready() -> None:
    with pytest.raises(ValueError, match="APPROVED before PUBLISH_READY"):
        make_job().transition_publish(PublishStatus.PUBLISH_READY)


def test_published_job_requires_platform_content_id(tmp_path: Path) -> None:
    evidence = tmp_path / "receipt.json"
    evidence.write_text("{}", encoding="utf-8")
    job = (
        make_job()
        .transition_approval(ApprovalStatus.REVIEW)
        .transition_approval(ApprovalStatus.APPROVED, approved_by="human:owner")
    )
    payload = job.model_dump()
    payload.update(
        status="PUBLISHED",
        publish_status=PublishStatus.PUBLISHED,
        qa_report=passing_qa(),
        platform_content_id=None,
        published_at=datetime.now().astimezone(),
        publication_evidence_path=evidence,
    )

    with pytest.raises(ValidationError, match="platform receipt"):
        CreatorJob.model_validate(payload)


def test_update_preserves_previous_revision(tmp_path: Path) -> None:
    store = CreatorJobStore(tmp_path / "creator_jobs")
    job = make_job()
    store.create(job)

    updated = store.update(
        job.job_id,
        {"selected_title": "CreatorJob v2"},
        reason="select title",
        updated_by="human:owner",
    )

    snapshot_path = store.revision_path(job.job_id, 1)
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    assert updated.current_revision == 2
    assert updated.selected_title == "CreatorJob v2"
    assert updated.updated_at >= job.updated_at
    assert updated.revisions[-1].revision == 1
    assert updated.revisions[-1].snapshot_path == snapshot_path
    assert snapshot["current_revision"] == 1
    assert snapshot["selected_title"] == ""

