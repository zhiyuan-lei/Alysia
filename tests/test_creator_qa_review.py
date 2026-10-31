from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from PIL import Image

from alysia.creator import (
    ApprovalStatus,
    ArtifactStatus,
    ClaimClassification,
    ContentQAChecker,
    CreatorClaimTrace,
    CreatorJob,
    CreatorJobStore,
    CreatorPlanBuilder,
    CreatorProductionIntegrator,
    CreatorQAConfig,
    CreatorQAService,
    CreatorScriptSection,
    EvidenceStatus,
    HumanReviewService,
    ProductionArtifactRegistry,
    ProductionPlanner,
    ProductionPlanStore,
    ProductionStatus,
    ProductionTask,
    ProductionTaskStatus,
    ProductionTaskType,
    PublishStatus,
    QAOverallResult,
    QAReviewStore,
    QAStatus,
    ResearchSourceTrace,
    ReviewAction,
)
from alysia.security.audit import AuditLog


def media_probe(path: Path) -> dict[str, object]:
    assert path.is_file()
    return {
        "streams": [
            {"codec_type": "video", "width": 1920, "height": 1080, "duration": "10.0"},
            {"codec_type": "audio", "duration": "10.0"},
        ],
        "format": {"duration": "10.0"},
    }


def make_job(*, uncertain: bool = False) -> CreatorJob:
    now = datetime.now().astimezone()
    claims = [
        CreatorClaimTrace(
            claim_id="claim_grounded",
            claim="The source documents recoverable production.",
            classification=ClaimClassification.VERIFIED_FACT,
            confidence=0.8,
            source_refs=["source_grounded"],
            evidence_status=EvidenceStatus.SUPPORTED,
        )
    ]
    if uncertain:
        claims.append(
            CreatorClaimTrace(
                claim_id="claim_uncertain",
                claim="The performance change remains disputed.",
                classification=ClaimClassification.UNKNOWN,
                confidence=0.3,
                source_refs=["source_grounded"],
                evidence_status=EvidenceStatus.CONFLICTING,
            )
        )
    return CreatorJob.new(
        created_at=now,
        updated_at=now,
        topic="Recoverable production",
        topic_source="research",
        topic_score=85,
        research_sources=[
            ResearchSourceTrace(
                source_id="source_grounded",
                source="https://example.com/source",
                retrieved_at=now,
                claim="Grounded evidence",
                confidence=0.9,
                source_type="web",
            )
        ],
        claims=claims,
        uncertainties=["scope uncertainty"] if uncertain else [],
    )


def make_plan(job: CreatorJob):
    return CreatorPlanBuilder().create(
        job,
        hook="Start with a production failure.",
        core_message="Recoverable production protects creator work.",
        target_audience="AI creators",
        sections=[
            CreatorScriptSection(
                section_id="grounded",
                purpose="Explain recoverable production",
                text="The source documents recoverable production.",
                factual=True,
                claim_refs=["claim_grounded"],
            )
        ],
        visual_direction="Technical diagrams",
        visual_scenes=[{"scene_id": "scene_1"}],
        voice_direction="Calm",
        audio_direction="Clear voice",
        thumbnail_concept="TEST review gate",
        title_candidates=["Recoverable production"],
        preferred_title="Recoverable production",
        description_draft="Recoverable production test description.",
        tags=["production", "recoverable"],
    )


class ReviewFixture:
    def __init__(self, tmp_path: Path, *, uncertain: bool = False) -> None:
        self.jobs = CreatorJobStore(tmp_path / "creator_jobs")
        self.job = make_job(uncertain=uncertain)
        self.jobs.create(self.job)
        self.creator_plan = make_plan(self.job)
        self.production_plan = ProductionPlanner().build(
            self.creator_plan,
            [
                ProductionTask(
                    task_id="video",
                    task_type=ProductionTaskType.VIDEO,
                    status=ProductionTaskStatus.SUCCEEDED,
                ),
                ProductionTask(
                    task_id="thumbnail",
                    task_type=ProductionTaskType.THUMBNAIL,
                    status=ProductionTaskStatus.SUCCEEDED,
                ),
            ],
        )
        self.production_plan.status = ProductionStatus.SUCCEEDED
        self.artifacts = ProductionArtifactRegistry(tmp_path / "production_artifacts", probe_media=False)
        video = self.artifacts.task_dir(self.job.job_id, "video") / "video.mp4"
        thumbnail = self.artifacts.task_dir(self.job.job_id, "thumbnail") / "thumbnail.png"
        video.write_bytes(b"TEST-video-content")
        Image.new("RGB", (4, 4), "white").save(thumbnail)
        self.video_manifest = self.artifacts.register(
            job_id=self.job.job_id,
            task_id="video",
            artifact_type="VIDEO",
            path=video,
        )
        self.thumbnail_manifest = self.artifacts.register(
            job_id=self.job.job_id,
            task_id="thumbnail",
            artifact_type="THUMBNAIL",
            path=thumbnail,
        )
        self.production_plan.task("video").output_refs = [self.video_manifest.artifact_id]
        self.production_plan.task("thumbnail").output_refs = [self.thumbnail_manifest.artifact_id]
        ProductionPlanStore(tmp_path / "production_plans").save(self.production_plan)
        self.job = CreatorProductionIntegrator(self.jobs).apply(
            self.job.job_id,
            creator_plan=self.creator_plan,
            production_plan=self.production_plan,
            artifacts=[self.video_manifest, self.thumbnail_manifest],
        )
        self.review_store = QAReviewStore(tmp_path / "qa_review")
        self.audit = AuditLog(tmp_path / "audit" / "creator_review.jsonl")
        self.qa = CreatorQAService(
            jobs=self.jobs,
            production_artifacts=self.artifacts,
            store=self.review_store,
            audit=self.audit,
            media_probe=media_probe,
        )
        self.reviews = HumanReviewService(jobs=self.jobs, store=self.review_store, audit=self.audit)

    def run_qa(self):
        return self.qa.run(self.job.job_id, self.creator_plan, self.production_plan)

    def approve(self):
        report = self.run_qa()
        decision = self.reviews.submit(
            job_id=self.job.job_id,
            qa_id=report.qa_id,
            action=ReviewAction.APPROVE,
            reason="Human reviewed all QA evidence.",
            reviewer="human:reviewer",
            job_revision=report.job_revision,
        )
        return report, decision


def test_valid_production_passes_qa_persists_and_does_not_auto_approve(tmp_path: Path) -> None:
    fixture = ReviewFixture(tmp_path)

    report = fixture.run_qa()
    job = fixture.jobs.load(fixture.job.job_id)

    assert report.overall_result == QAOverallResult.PASS
    assert report.review_eligible
    assert report.job_revision == fixture.job.current_revision
    assert fixture.review_store.load_qa(job.job_id, report.qa_id) == report
    assert fixture.qa.load_report(job.job_id, report.qa_id).status == QAStatus.COMPLETED
    assert fixture.review_store.qa_history(job.job_id) == [report]
    assert job.approval_status == ApprovalStatus.REVIEW
    assert job.publish_status == PublishStatus.NOT_READY
    assert [event.action for event in fixture.audit.list()] == ["QA_STARTED", "QA_COMPLETED"]


@pytest.mark.parametrize(
    ("change", "expected_code"),
    [
        ({"video_path": None}, "MISSING_VIDEO"),
        ({"thumbnail_path": None}, "MISSING_THUMBNAIL"),
        ({"script": ""}, "EMPTY_SCRIPT"),
    ],
)
def test_missing_required_qa_inputs_fail(
    tmp_path: Path,
    change: dict[str, object],
    expected_code: str,
) -> None:
    fixture = ReviewFixture(tmp_path)
    fixture.jobs.update(
        fixture.job.job_id,
        change,
        reason="negative QA fixture",
        updated_by="system:test",
    )

    report = fixture.run_qa()

    assert report.overall_result == QAOverallResult.FAIL
    assert expected_code in {item.code for item in report.blocking_issues}
    assert fixture.jobs.load(fixture.job.job_id).approval_status == ApprovalStatus.DRAFT


def test_invalid_artifact_fails_qa(tmp_path: Path) -> None:
    fixture = ReviewFixture(tmp_path)
    fixture.video_manifest.path.write_bytes(b"changed-after-manifest")

    report = fixture.run_qa()

    assert report.overall_result == QAOverallResult.FAIL
    assert "INVALID_ARTIFACT" in {item.code for item in report.blocking_issues}


def test_grounding_trace_loss_and_uncertainty_misrepresentation_fail(tmp_path: Path) -> None:
    fixture = ReviewFixture(tmp_path, uncertain=True)
    fixture.creator_plan = fixture.creator_plan.model_copy(update={"uncertainty_refs": []})
    fixture.jobs.update(
        fixture.job.job_id,
        {"claims": []},
        reason="remove grounding trace",
        updated_by="system:test",
    )

    report = fixture.run_qa()
    codes = {item.code for item in report.blocking_issues}

    assert "UNKNOWN_CLAIM_REF" in codes
    assert "UNCERTAINTY_TRACE_LOST" in codes


def test_uncertain_claim_cannot_be_presented_as_fact(tmp_path: Path) -> None:
    fixture = ReviewFixture(tmp_path, uncertain=True)
    fixture.creator_plan.script_sections.append(
        CreatorScriptSection(
            section_id="uncertain",
            purpose="Bad certainty fixture",
            text="The performance definitely changed.",
            factual=True,
            claim_refs=["claim_uncertain"],
        )
    )
    fixture.creator_plan.script += "\n\nThe performance definitely changed."
    fixture.jobs.update(
        fixture.job.job_id,
        {"script": fixture.creator_plan.script},
        reason="bad certainty fixture",
        updated_by="system:test",
    )

    report = fixture.run_qa()
    codes = {item.code for item in report.blocking_issues}

    assert "UNCERTAIN_CLAIM_AS_FACT" in codes
    assert "NON_FACTUAL_CLAIM_AS_FACT" in codes


def test_metadata_mismatch_is_explainable_warning(tmp_path: Path) -> None:
    fixture = ReviewFixture(tmp_path)
    fixture.jobs.update(
        fixture.job.job_id,
        {"selected_title": "Banana astronomy"},
        reason="metadata mismatch fixture",
        updated_by="system:test",
    )

    report = fixture.run_qa()

    assert report.overall_result == QAOverallResult.PASS_WITH_WARNINGS
    assert "TITLE_BODY_MISMATCH" in {item.code for item in report.warnings}


@pytest.mark.parametrize(
    ("description", "expected_code"),
    [
        ("authorization: Bearer super-secret-token", "SECRET_LEAKAGE"),
        ("Internal preview: http://127.0.0.1:8188/history", "PRIVATE_NETWORK_REFERENCE"),
    ],
)
def test_safety_qa_blocks_secret_or_private_network_leakage(
    tmp_path: Path,
    description: str,
    expected_code: str,
) -> None:
    fixture = ReviewFixture(tmp_path)
    fixture.jobs.update(
        fixture.job.job_id,
        {"description": description},
        reason="safety fixture",
        updated_by="system:test",
    )

    report = fixture.run_qa()

    assert report.overall_result == QAOverallResult.FAIL
    issue_by_code = {item.code: item for item in report.blocking_issues}
    assert issue_by_code[expected_code].severity.value == "CRITICAL"


def test_content_checker_detects_duplicate_and_direct_contradiction() -> None:
    job = make_job()
    plan = make_plan(job)
    plan.script_sections = [
        CreatorScriptSection(section_id="a", purpose="A", text="系统是安全的"),
        CreatorScriptSection(section_id="b", purpose="B", text="系统不是安全的"),
        CreatorScriptSection(section_id="c", purpose="C", text="系统是安全的"),
    ]

    codes = {item.code for item in ContentQAChecker().check(job, plan)}

    assert "DUPLICATE_SECTIONS" in codes
    assert "INTERNAL_CONTRADICTION" in codes


def test_av_duration_delta_is_configurable(tmp_path: Path) -> None:
    fixture = ReviewFixture(tmp_path)

    def mismatched_probe(path: Path) -> dict[str, object]:
        payload = media_probe(path)
        payload["streams"][1]["duration"] = "7.0"
        return payload

    fixture.qa = CreatorQAService(
        jobs=fixture.jobs,
        production_artifacts=fixture.artifacts,
        store=fixture.review_store,
        audit=fixture.audit,
        config=CreatorQAConfig(max_av_duration_delta=0.5, av_delta_blocking_threshold=2.0),
        media_probe=mismatched_probe,
    )

    report = fixture.run_qa()

    assert report.overall_result == QAOverallResult.FAIL
    assert "AV_DURATION_MISMATCH" in {item.code for item in report.blocking_issues}


def test_fail_qa_forbids_approve(tmp_path: Path) -> None:
    fixture = ReviewFixture(tmp_path)
    fixture.jobs.update(
        fixture.job.job_id,
        {"video_path": None},
        reason="fail QA fixture",
        updated_by="system:test",
    )
    report = fixture.run_qa()

    with pytest.raises(PermissionError, match="cannot be approved"):
        fixture.reviews.submit(
            job_id=fixture.job.job_id,
            qa_id=report.qa_id,
            action=ReviewAction.APPROVE,
            reason="Should not pass.",
            reviewer="human:reviewer",
            job_revision=report.job_revision,
        )


def test_explicit_approve_is_persisted_and_publish_ready_is_separate(tmp_path: Path) -> None:
    fixture = ReviewFixture(tmp_path)

    report, decision = fixture.approve()
    approved = fixture.jobs.load(fixture.job.job_id)

    assert approved.approval_status == ApprovalStatus.APPROVED
    assert approved.approval_ref == decision.review_id
    assert approved.publish_status == PublishStatus.NOT_READY
    assert decision.reason == "Human reviewed all QA evidence."
    assert decision.reviewer == "human:reviewer"
    assert fixture.review_store.load_review(approved.job_id, decision.review_id) == decision
    ready = fixture.reviews.enter_publish_ready(
        job_id=approved.job_id,
        qa_id=report.qa_id,
        review_id=decision.review_id,
    )
    assert ready.publish_status == PublishStatus.PUBLISH_READY
    assert [event.action for event in fixture.audit.list()][-2:] == ["REVIEW_APPROVED", "PUBLISH_READY_ENTERED"]


def test_repeated_identical_review_is_idempotent(tmp_path: Path) -> None:
    fixture = ReviewFixture(tmp_path)
    report = fixture.run_qa()
    kwargs = dict(
        job_id=fixture.job.job_id,
        qa_id=report.qa_id,
        action=ReviewAction.APPROVE,
        reason="Approved once.",
        reviewer="human:reviewer",
        job_revision=report.job_revision,
    )

    first = fixture.reviews.submit(**kwargs)
    second = fixture.reviews.submit(**kwargs)

    assert first == second
    assert fixture.review_store.review_history(fixture.job.job_id) == [first]


def test_reject_persists_reason_and_cannot_enter_publish_ready(tmp_path: Path) -> None:
    fixture = ReviewFixture(tmp_path)
    report = fixture.run_qa()
    decision = fixture.reviews.submit(
        job_id=fixture.job.job_id,
        qa_id=report.qa_id,
        action=ReviewAction.REJECT,
        reason="Claims need stronger evidence.",
        reviewer="human:editor",
        job_revision=report.job_revision,
    )

    job = fixture.jobs.load(fixture.job.job_id)
    assert job.approval_status == ApprovalStatus.REJECTED
    assert decision.reason == "Claims need stronger evidence."
    assert job.publish_status == PublishStatus.NOT_READY
    with pytest.raises((PermissionError, ValueError)):
        fixture.reviews.enter_publish_ready(job_id=job.job_id, qa_id=report.qa_id, review_id=decision.review_id)


def test_request_revision_preserves_snapshot_and_invalidates_old_qa(tmp_path: Path) -> None:
    fixture = ReviewFixture(tmp_path)
    report = fixture.run_qa()
    previous_revision = report.job_revision
    decision = fixture.reviews.submit(
        job_id=fixture.job.job_id,
        qa_id=report.qa_id,
        action=ReviewAction.REQUEST_REVISION,
        reason="Clarify the opening.",
        reviewer="human:editor",
        job_revision=previous_revision,
        requested_changes=["Rewrite hook", "Retain claim citations"],
    )

    job = fixture.jobs.load(fixture.job.job_id)
    assert job.current_revision == previous_revision + 1
    assert job.approval_status == ApprovalStatus.REVISION_REQUIRED
    assert job.publish_status == PublishStatus.NOT_READY
    assert fixture.jobs.revision_path(job.job_id, previous_revision).is_file()
    assert decision.requested_changes == ["Rewrite hook", "Retain claim citations"]
    with pytest.raises((PermissionError, ValueError)):
        fixture.reviews.enter_publish_ready(job_id=job.job_id, qa_id=report.qa_id, review_id=decision.review_id)


@pytest.mark.parametrize(
    "changes",
    [
        {"selected_title": "Changed approved title"},
        {"script": "Changed approved script."},
        {"video_path": None},
    ],
)
def test_approved_content_change_invalidates_approval_and_old_evidence(
    tmp_path: Path,
    changes: dict[str, object],
) -> None:
    fixture = ReviewFixture(tmp_path)
    report, decision = fixture.approve()

    updated = fixture.reviews.update_content(
        fixture.job.job_id,
        changes,
        reason="Approved content changed.",
        actor="human:editor",
    )

    assert updated.approval_status == ApprovalStatus.DRAFT
    assert updated.publish_status == PublishStatus.NOT_READY
    assert updated.current_revision == report.job_revision + 1
    assert "APPROVAL_INVALIDATED" in [event.action for event in fixture.audit.list()]
    with pytest.raises(ValueError, match="stale QA"):
        fixture.reviews.enter_publish_ready(
            job_id=updated.job_id,
            qa_id=report.qa_id,
            review_id=decision.review_id,
        )


def test_stale_qa_cannot_approve_new_revision(tmp_path: Path) -> None:
    fixture = ReviewFixture(tmp_path)
    report = fixture.run_qa()
    fixture.jobs.update(
        fixture.job.job_id,
        {"description": "A revised description."},
        reason="revision after QA",
        updated_by="human:editor",
    )

    assert fixture.qa.load_report(fixture.job.job_id, report.qa_id).status == QAStatus.STALE

    with pytest.raises(ValueError, match="stale review or QA"):
        fixture.reviews.submit(
            job_id=fixture.job.job_id,
            qa_id=report.qa_id,
            action=ReviewAction.APPROVE,
            reason="Old QA should not apply.",
            reviewer="human:reviewer",
            job_revision=report.job_revision,
        )


def test_anonymous_or_automatic_reviewer_is_forbidden(tmp_path: Path) -> None:
    fixture = ReviewFixture(tmp_path)
    report = fixture.run_qa()

    with pytest.raises(PermissionError, match="human identity"):
        fixture.reviews.submit(
            job_id=fixture.job.job_id,
            qa_id=report.qa_id,
            action=ReviewAction.APPROVE,
            reason="Automated approval is forbidden.",
            reviewer="system",
            job_revision=report.job_revision,
        )
