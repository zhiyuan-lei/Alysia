from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from alysia.creator import (
    ClaimClassification,
    CreatorClaimTrace,
    CreatorJobService,
    CreatorJobStore,
    CreatorQAGate,
    DuplicateCheckReport,
    ResearchEvidenceStatus,
)
from tests.test_alpha22_creator import passed_qa, publication_receipt, ready_job


@pytest.mark.parametrize(
    ("stage", "failure", "recovery"),
    [
        ("visual", "ComfyUI unavailable", "resume_from_visual_checkpoint"),
        ("visual", "H3 invocation failed", "retry_h3_with_approved_budget"),
    ],
)
def test_f1_f2_production_failure_preserves_creator_job(
    tmp_path: Path, stage: str, failure: str, recovery: str,
) -> None:
    store = CreatorJobStore(tmp_path / "creator_jobs")
    service = CreatorJobService(store)
    job = service.create(topic="故障恢复", topic_source="manual", topic_score=75)
    original_id = job.job_id
    original_topic = job.topic
    updated = service.record_recovery_event(
        job.job_id, stage=stage, failure=failure, recovery_result=recovery, terminal=False,
    )
    reloaded = CreatorJobStore(tmp_path / "creator_jobs").load(job.job_id)
    assert updated.status == "DRAFT"
    assert reloaded.job_id == original_id
    assert reloaded.topic == original_topic
    assert reloaded.failure_count == 1
    assert reloaded.recovery_events[-1].recovery_result == recovery


def test_f3_bilibili_failure_never_marks_published(tmp_path: Path) -> None:
    job = ready_job(tmp_path)
    service = CreatorJobService(CreatorJobStore(tmp_path / "creator_jobs"))
    failed = service.record_publish_failure(
        job.job_id, error="network unavailable", terminal=False,
    )
    assert failed.status == "PUBLISH_READY"
    assert failed.publish_status == "FAILED"
    assert failed.platform_content_id is None
    assert failed.published_at is None


def test_f4_restart_after_network_failure_is_idempotent(tmp_path: Path) -> None:
    job = ready_job(tmp_path)
    first_process = CreatorJobService(CreatorJobStore(tmp_path / "creator_jobs"))
    first_process.record_publish_failure(job.job_id, error="connection reset", terminal=False)
    receipt = publication_receipt(tmp_path)
    first = first_process.record_publication(job.job_id, receipt)
    restarted = CreatorJobService(CreatorJobStore(tmp_path / "creator_jobs"))
    second = restarted.record_publication(job.job_id, receipt)
    assert first.platform_content_id == second.platform_content_id
    assert len(second.publish_attempts) == len(first.publish_attempts)


def test_f5_process_exit_resumes_same_creator_job(tmp_path: Path) -> None:
    first_store = CreatorJobStore(tmp_path / "creator_jobs")
    service = CreatorJobService(first_store)
    job = service.create(topic="进程退出恢复", topic_source="manual", topic_score=70)
    job.qa_report = passed_qa()
    first_store.save(job)
    service.submit_for_review(job.job_id)

    resumed = CreatorJobStore(tmp_path / "creator_jobs").load(job.job_id)
    assert resumed.job_id == job.job_id
    assert resumed.status == "REVIEW"
    assert resumed.current_revision == 1


def test_f6_rejected_approval_cannot_publish(tmp_path: Path) -> None:
    store = CreatorJobStore(tmp_path / "creator_jobs")
    service = CreatorJobService(store)
    job = service.create(topic="拒绝门禁", topic_source="manual", topic_score=70)
    job.qa_report = passed_qa()
    store.save(job)
    service.submit_for_review(job.job_id)
    rejected = service.reject(job.job_id, reason="事实证据不足", rejected_by="human:reviewer")
    assert rejected.status == "BLOCKED"
    with pytest.raises(ValueError, match="APPROVED"):
        service.mark_publish_ready(job.job_id, package_path=tmp_path / "package.json")


def test_f7_stale_research_cannot_become_undeclared_fact() -> None:
    report = CreatorQAGate().evaluate(
        claims=[
            CreatorClaimTrace(
                claim="已经过期的价格",
                classification=ClaimClassification.VERIFIED_FACT,
                confidence=0.8,
                source_refs=["old-source"],
                presented_as_fact=True,
                stale=True,
            )
        ],
        research_status=ResearchEvidenceStatus.SUFFICIENT,
        video_passed=True,
        copy_passed=True,
        safety_passed=True,
        duplicate_report=DuplicateCheckReport(passed=True),
        evidence_refs=["grounding.json"],
    )
    assert not report.passed
    assert "claim[0]:stale_verified_fact" in report.errors

