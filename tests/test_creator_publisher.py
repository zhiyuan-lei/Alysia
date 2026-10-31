from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest
from PIL import Image

from alysia.creator import (
    AuthenticationRequired,
    AuthenticationState,
    ApprovalStatus,
    ClaimClassification,
    CopyrightType,
    CreatorClaimTrace,
    CreatorJob,
    CreatorJobStore,
    CreatorPlanBuilder,
    CreatorProductionIntegrator,
    CreatorQAService,
    CreatorScriptSection,
    DuplicatePublishBlocked,
    EvidenceStatus,
    HumanPublishConfirmationRequired,
    HumanReviewService,
    LivePublishingDisabled,
    ProductionArtifactRegistry,
    ProductionPlanner,
    ProductionStatus,
    ProductionTask,
    ProductionTaskStatus,
    ProductionTaskType,
    PublishLockBusy,
    PublishMode,
    PublishRecord,
    PublishRecordStatus,
    PublishRequest,
    PublishStatus,
    PublisherStore,
    PublishTransportError,
    PublishValidationError,
    QAReviewStore,
    RemotePublishState,
    ResearchSourceTrace,
    ReviewAction,
    SessionLease,
    TransportPublishResult,
    UploadReceipt,
)
from alysia.security.audit import AuditLog


def fake_media_probe(path: Path) -> dict[str, object]:
    assert path.is_file()
    return {
        "streams": [
            {"codec_type": "video", "width": 1920, "height": 1080, "duration": "10.0"},
            {"codec_type": "audio", "duration": "10.0"},
        ],
        "format": {"duration": "10.0"},
    }


class FakeSessionProvider:
    def __init__(
        self,
        state: AuthenticationState = AuthenticationState.READY,
        *,
        acquired_state: AuthenticationState | None = None,
    ) -> None:
        self.state = state
        self.acquired_state = acquired_state or state
        self.secret_handle = {"cookie": "cookie-super-secret", "token": "token-super-secret"}

    def auth_state(self, platform: str) -> AuthenticationState:
        assert platform == "bilibili"
        return self.state

    def acquire(self, platform: str) -> SessionLease:
        assert platform == "bilibili"
        handle = self.secret_handle if self.acquired_state == AuthenticationState.READY else None
        return SessionLease(self.acquired_state, handle)


class FakeTransport:
    def __init__(self) -> None:
        self.upload_calls = 0
        self.submit_calls = 0
        self.reconcile_calls = 0
        self.pre_submit_failures = 0
        self.submit_error: PublishTransportError | None = None
        self.submit_result = TransportPublishResult(
            remote_state=RemotePublishState.PUBLISHED,
            platform_content_id="TEST_ONLY_BV0000000001",
            platform_url_ref="TEST_ONLY://bilibili/video/BV0000000001",
            test_only=True,
        )
        self.reconcile_result = self.submit_result

    def upload(self, package, *, session_handle: object, idempotency_key: str) -> UploadReceipt:
        del package
        assert session_handle
        assert idempotency_key.startswith("publish_key_")
        self.upload_calls += 1
        if self.upload_calls <= self.pre_submit_failures:
            raise PublishTransportError(
                "transient before submission",
                code="TRANSIENT_UPLOAD",
                retryable=True,
                submission_started=False,
            )
        return UploadReceipt(upload_ref="TEST_ONLY_UPLOAD", test_only=True)

    def submit(self, upload_ref: str, package, *, session_handle: object, idempotency_key: str):
        del package
        assert upload_ref == "TEST_ONLY_UPLOAD"
        assert session_handle
        assert idempotency_key.startswith("publish_key_")
        self.submit_calls += 1
        if self.submit_error:
            raise self.submit_error
        return self.submit_result

    def status(self, platform_content_id: str, *, session_handle: object):
        del platform_content_id, session_handle
        return self.submit_result

    def cancel(self, upload_ref: str, *, session_handle: object) -> bool:
        del upload_ref, session_handle
        return True

    def reconcile(self, *, idempotency_key: str, session_handle: object):
        assert idempotency_key.startswith("publish_key_")
        assert session_handle
        self.reconcile_calls += 1
        return self.reconcile_result


class PublisherFixture:
    def __init__(
        self,
        tmp_path: Path,
        *,
        mode: PublishMode = PublishMode.PREPARE_ONLY,
        live_enabled: bool = False,
        session: FakeSessionProvider | None = None,
        transport: FakeTransport | None = None,
    ) -> None:
        self.root = tmp_path
        self.jobs = CreatorJobStore(tmp_path / "creator_jobs")
        now = datetime.now().astimezone()
        job = CreatorJob.new(
            created_at=now,
            updated_at=now,
            topic="Safe Bilibili publishing",
            topic_source="fixture",
            topic_score=90,
            research_sources=[
                ResearchSourceTrace(
                    source_id="source_publish",
                    source="https://example.com/publish",
                    retrieved_at=now,
                    claim="Publishing requires explicit safety gates.",
                    confidence=0.9,
                    source_type="web",
                )
            ],
            claims=[
                CreatorClaimTrace(
                    claim_id="claim_publish",
                    claim="Publishing requires explicit safety gates.",
                    classification=ClaimClassification.VERIFIED_FACT,
                    confidence=0.9,
                    source_refs=["source_publish"],
                    evidence_status=EvidenceStatus.SUPPORTED,
                )
            ],
        )
        self.jobs.create(job)
        self.plan = CreatorPlanBuilder().create(
            job,
            hook="Start at the publish boundary.",
            core_message="Safe publishing needs a human gate.",
            target_audience="AI creators",
            sections=[
                CreatorScriptSection(
                    section_id="publish",
                    purpose="Explain publish safety",
                    text="Publishing requires explicit safety gates.",
                    factual=True,
                    claim_refs=["claim_publish"],
                )
            ],
            visual_direction="Safety workflow",
            visual_scenes=[{"scene_id": "scene_publish"}],
            voice_direction="Calm",
            audio_direction="Clear",
            thumbnail_concept="TEST_ONLY publish gate",
            title_candidates=["Safe publishing"],
            preferred_title="Safe publishing",
            description_draft="A TEST_ONLY package for the safe publishing gate.",
            tags=["safety", "publishing"],
        )
        self.production = ProductionPlanner().build(
            self.plan,
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
        self.production.status = ProductionStatus.SUCCEEDED
        self.artifacts = ProductionArtifactRegistry(tmp_path / "artifacts", probe_media=False)
        video_path = self.artifacts.task_dir(job.job_id, "video") / "video.mp4"
        thumbnail_path = self.artifacts.task_dir(job.job_id, "thumbnail") / "thumbnail.png"
        video_path.write_bytes(b"TEST-video-content")
        Image.new("RGB", (4, 4), "white").save(thumbnail_path)
        self.video = self.artifacts.register(
            job_id=job.job_id,
            task_id="video",
            artifact_type="VIDEO",
            path=video_path,
            metadata={"test_only": True},
        )
        self.thumbnail = self.artifacts.register(
            job_id=job.job_id,
            task_id="thumbnail",
            artifact_type="THUMBNAIL",
            path=thumbnail_path,
            metadata={"test_only": True},
        )
        self.production.task("video").output_refs = [self.video.artifact_id]
        self.production.task("thumbnail").output_refs = [self.thumbnail.artifact_id]
        CreatorProductionIntegrator(self.jobs).apply(
            job.job_id,
            creator_plan=self.plan,
            production_plan=self.production,
            artifacts=[self.video, self.thumbnail],
        )
        self.qa_reviews = QAReviewStore(tmp_path / "qa_review")
        self.audit = AuditLog(tmp_path / "audit" / "publisher.jsonl")
        qa_service = CreatorQAService(
            jobs=self.jobs,
            production_artifacts=self.artifacts,
            store=self.qa_reviews,
            audit=self.audit,
            media_probe=fake_media_probe,
        )
        self.report = qa_service.run(job.job_id, self.plan, self.production)
        reviews = HumanReviewService(jobs=self.jobs, store=self.qa_reviews, audit=self.audit)
        self.review = reviews.submit(
            job_id=job.job_id,
            qa_id=self.report.qa_id,
            action=ReviewAction.APPROVE,
            reason="Human reviewed the TEST_ONLY publish fixture.",
            reviewer="human:reviewer",
            job_revision=self.report.job_revision,
        )
        self.job = reviews.enter_publish_ready(
            job_id=job.job_id,
            qa_id=self.report.qa_id,
            review_id=self.review.review_id,
        )
        self.publisher_store = PublisherStore(tmp_path / "publisher")
        self.session = session or FakeSessionProvider()
        self.transport = transport or FakeTransport()
        self.publisher = __import__("alysia.creator", fromlist=["BilibiliPublisher"]).BilibiliPublisher(
            mode=mode,
            jobs=self.jobs,
            qa_reviews=self.qa_reviews,
            artifacts=self.artifacts,
            store=self.publisher_store,
            audit=self.audit,
            session_provider=self.session,
            transport=self.transport,
            live_enabled=live_enabled,
        )
        self.request = PublishRequest(
            request_id="request_test_only_001",
            job_id=self.job.job_id,
            job_revision=self.job.current_revision,
            review_id=self.review.review_id,
            qa_id=self.report.qa_id,
            platform="bilibili",
            video_artifact_id=self.video.artifact_id,
            thumbnail_artifact_id=self.thumbnail.artifact_id,
            title=self.job.selected_title,
            description=self.job.description,
            tags=self.job.tags,
            category="TEST_ONLY_CATEGORY",
            copyright_type=CopyrightType.ORIGINAL,
            mode=mode,
            metadata={"test_only": True},
        )

    def prepare(self):
        return self.publisher.prepare(self.request)

    def confirm(self, actor: str = "human:publisher"):
        return self.publisher.confirm(
            self.request.request_id,
            actor=actor,
            job_revision=self.request.job_revision,
            metadata={"test_only": True},
        )


def test_prepare_only_smoke_builds_secret_free_package_without_submission(tmp_path: Path) -> None:
    fixture = PublisherFixture(tmp_path)
    package = fixture.prepare()

    assert package.validation.valid
    assert package.mode == PublishMode.PREPARE_ONLY
    assert package.job_revision == fixture.job.current_revision
    assert package.video_artifact_hash == fixture.video.hash
    assert package.thumbnail_artifact_hash == fixture.thumbnail.hash
    assert package.platform_payload.thumbnail_artifact_id == fixture.thumbnail.artifact_id
    persisted_request = fixture.publisher_store.load_request(fixture.request.request_id)
    assert persisted_request.video_artifact_hash == fixture.video.hash
    assert persisted_request.thumbnail_artifact_hash == fixture.thumbnail.hash
    assert fixture.transport.upload_calls == fixture.transport.submit_calls == 0
    assert fixture.publisher.status("publish_" + package.package_id.removeprefix("publish_package_"))


def test_validate_only_never_creates_package_or_calls_transport(tmp_path: Path) -> None:
    fixture = PublisherFixture(tmp_path, mode=PublishMode.VALIDATE_ONLY)

    report = fixture.publisher.prepare(fixture.request)

    assert report.valid
    assert report.artifact_hashes == {
        "video": fixture.video.hash,
        "thumbnail": fixture.thumbnail.hash,
    }
    assert fixture.publisher_store.records() == []
    assert not list((tmp_path / "publisher" / "packages").glob("*.json"))
    assert fixture.transport.upload_calls == fixture.transport.submit_calls == 0


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        ("unapproved", "HUMAN_APPROVAL_REQUIRED"),
        ("not_ready", "JOB_NOT_PUBLISH_READY"),
        ("stale_qa", "STALE_QA"),
        ("stale_review", "STALE_OR_NON_APPROVAL_REVIEW"),
        ("stale_revision", "STALE_JOB_REVISION"),
        ("video_hash", "VIDEO_ARTIFACT_INVALID_OR_CHANGED"),
        ("thumbnail_hash", "THUMBNAIL_ARTIFACT_INVALID_OR_CHANGED"),
        ("invalid_artifact", "VIDEO_ARTIFACT_NOT_FOUND"),
        ("missing_metadata", "TITLE_REQUIRED"),
    ],
)
def test_publish_gate_rejects_invalid_state(tmp_path: Path, mutation: str, expected: str) -> None:
    fixture = PublisherFixture(tmp_path)
    request = fixture.request
    if mutation == "unapproved":
        fixture.job.approval_status = ApprovalStatus.DRAFT
        fixture.job.approved_by = None
        fixture.job.approved_at = None
        fixture.job.status = "DRAFT"
        fixture.job.publish_status = PublishStatus.NOT_READY
        fixture.jobs.save(fixture.job)
    elif mutation == "not_ready":
        fixture.job.status = "APPROVED"
        fixture.job.publish_status = PublishStatus.NOT_READY
        fixture.jobs.save(fixture.job)
    elif mutation == "stale_qa":
        report = fixture.report.model_copy(update={"job_revision": fixture.report.job_revision + 1})
        fixture.qa_reviews.save_qa(report)
    elif mutation == "stale_review":
        review = fixture.review.model_copy(update={"job_revision": fixture.review.job_revision + 1})
        path = tmp_path / "qa_review" / "reviews" / fixture.job.job_id / f"{review.review_id}.json"
        path.write_text(review.model_dump_json(), encoding="utf-8")
    elif mutation == "stale_revision":
        request = request.model_copy(update={"job_revision": request.job_revision + 1})
    elif mutation == "video_hash":
        fixture.video.path.write_bytes(b"changed-video")
    elif mutation == "thumbnail_hash":
        fixture.thumbnail.path.write_bytes(b"changed-thumbnail")
    elif mutation == "invalid_artifact":
        request = request.model_copy(update={"video_artifact_id": "artifact_0000000000000000"})
    elif mutation == "missing_metadata":
        request = request.model_construct(**{**request.model_dump(), "title": ""})

    report = fixture.publisher.validate(request)

    assert not report.valid
    assert expected in report.blocking


def test_prepare_rejects_changed_artifact_and_duplicate_revision_video(tmp_path: Path) -> None:
    fixture = PublisherFixture(tmp_path)
    fixture.prepare()
    record = fixture.publisher_store.record_for_request(fixture.request.request_id)
    assert record is not None
    fixture.publisher_store.save_record(
        record.model_copy(
            update={
                "status": PublishRecordStatus.PROCESSING,
                "remote_state": RemotePublishState.PROCESSING,
            }
        )
    )
    duplicate = fixture.request.model_copy(update={"request_id": "request_test_only_002"})
    with pytest.raises(DuplicatePublishBlocked):
        fixture.publisher.prepare(duplicate)

    fixture.thumbnail.path.write_bytes(b"changed-after-prepare")
    with pytest.raises(PublishValidationError):
        fixture.publisher.prepare(fixture.request.model_copy(update={"request_id": "request_test_only_003"}))


def test_human_confirmation_is_a_distinct_action_and_agents_cannot_confirm(tmp_path: Path) -> None:
    fixture = PublisherFixture(tmp_path)
    fixture.prepare()
    with pytest.raises(PermissionError):
        fixture.confirm("agent")
    with pytest.raises(PermissionError):
        fixture.confirm("human:system")

    confirmation = fixture.confirm()

    assert confirmation.actor == "human:publisher"
    actions = [event.action for event in fixture.audit.list()]
    assert actions[-2:] == ["PUBLISH_CONFIRM_REQUESTED", "PUBLISH_CONFIRMED"]


def test_live_is_disabled_by_default_and_confirmation_is_required(tmp_path: Path) -> None:
    disabled = PublisherFixture(tmp_path / "disabled", mode=PublishMode.LIVE)
    assert "LIVE_PUBLISHING_DISABLED" in disabled.publisher.validate(disabled.request).blocking
    with pytest.raises(LivePublishingDisabled):
        disabled.publisher.publish(disabled.request, confirmation=None)

    enabled = PublisherFixture(tmp_path / "enabled", mode=PublishMode.LIVE, live_enabled=True)
    enabled.prepare()
    with pytest.raises(HumanPublishConfirmationRequired):
        enabled.publisher.publish(enabled.request, confirmation=None)


def test_process_lock_and_safe_pre_submit_retry(tmp_path: Path) -> None:
    transport = FakeTransport()
    transport.pre_submit_failures = 1
    fixture = PublisherFixture(
        tmp_path,
        mode=PublishMode.LIVE,
        live_enabled=True,
        transport=transport,
    )
    package = fixture.prepare()
    confirmation = fixture.confirm()
    lock = fixture.publisher._lock_for(
        fixture.publisher.publish_lock_key(
            fixture.request.platform,
            fixture.request.job_id,
            fixture.request.job_revision,
        )
    )
    lock.acquire()
    try:
        with pytest.raises(PublishLockBusy):
            fixture.publisher.publish(fixture.request, confirmation=confirmation)
    finally:
        lock.release()

    record = fixture.publisher.publish(fixture.request, confirmation=confirmation)

    assert transport.upload_calls == 2
    assert transport.submit_calls == 1
    assert record.status == PublishRecordStatus.PUBLISHED
    assert record.metadata["test_only"] is True
    with pytest.raises(DuplicatePublishBlocked):
        fixture.publisher.publish(fixture.request, confirmation=confirmation)
    assert transport.submit_calls == 1


def test_post_submit_timeout_becomes_unknown_and_never_blind_retries(tmp_path: Path) -> None:
    transport = FakeTransport()
    transport.submit_error = PublishTransportError(
        "timeout after submit",
        code="POST_SUBMIT_TIMEOUT",
        retryable=True,
        submission_started=True,
        indeterminate=True,
    )
    fixture = PublisherFixture(
        tmp_path,
        mode=PublishMode.LIVE,
        live_enabled=True,
        transport=transport,
    )
    fixture.prepare()
    confirmation = fixture.confirm()

    record = fixture.publisher.publish(fixture.request, confirmation=confirmation)

    assert record.status == PublishRecordStatus.UNKNOWN
    assert record.remote_state == RemotePublishState.UNKNOWN
    with pytest.raises(DuplicatePublishBlocked):
        fixture.publisher.publish(fixture.request, confirmation=confirmation)
    assert transport.submit_calls == 1


def test_unknown_reconciliation_success_publishes_without_resubmit(tmp_path: Path) -> None:
    transport = FakeTransport()
    transport.submit_error = PublishTransportError(
        "authorization=Bearer secret-token cookie=session-secret",
        code="POST_SUBMIT_TIMEOUT",
        retryable=True,
        submission_started=True,
        indeterminate=True,
    )
    fixture = PublisherFixture(
        tmp_path,
        mode=PublishMode.LIVE,
        live_enabled=True,
        transport=transport,
    )
    fixture.request = fixture.request.model_copy(
        update={
            "metadata": {
                "cookie": "cookie-secret",
                "token": "token-secret",
                "session": "session-secret",
                "authorization": "Bearer auth-secret",
                "SESSDATA": "bilibili-sessdata-secret",
                "bili_jct": "bilibili-jct-secret",
                "test_only": True,
            }
        }
    )
    fixture.prepare()
    unknown = fixture.publisher.publish(fixture.request, confirmation=fixture.confirm())

    reconciled = fixture.publisher.reconcile(unknown.publish_id)

    assert reconciled.status == PublishRecordStatus.PUBLISHED
    assert reconciled.platform_content_id == "TEST_ONLY_BV0000000001"
    assert transport.submit_calls == 1
    assert transport.reconcile_calls == 1
    all_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in tmp_path.rglob("*.json*")
        if path.is_file()
    )
    assert "cookie-secret" not in all_text
    assert "token-secret" not in all_text
    assert "session-secret" not in all_text
    assert "secret-token" not in all_text
    assert "auth-secret" not in all_text
    assert "bilibili-sessdata-secret" not in all_text
    assert "bilibili-jct-secret" not in all_text
    assert "[REDACTED]" in all_text
    assert "secret-token" not in str(transport.submit_error)


@pytest.mark.parametrize("remote_state", [RemotePublishState.NOT_FOUND, RemotePublishState.FAILED])
def test_reconciliation_confirmed_failure_is_safe_to_retry(
    tmp_path: Path,
    remote_state: RemotePublishState,
) -> None:
    transport = FakeTransport()
    transport.submit_error = PublishTransportError(
        "post-submit timeout",
        code="TIMEOUT",
        retryable=True,
        submission_started=True,
        indeterminate=True,
    )
    transport.reconcile_result = TransportPublishResult(remote_state=remote_state, test_only=True)
    fixture = PublisherFixture(
        tmp_path,
        mode=PublishMode.LIVE,
        live_enabled=True,
        transport=transport,
    )
    fixture.prepare()
    unknown = fixture.publisher.publish(fixture.request, confirmation=fixture.confirm())

    record = fixture.publisher.reconcile(unknown.publish_id)

    assert record.status == PublishRecordStatus.FAILED
    assert record.metadata["safe_to_retry"] is True


@pytest.mark.parametrize(
    "state",
    [
        AuthenticationState.AUTH_REQUIRED,
        AuthenticationState.SESSION_EXPIRED,
        AuthenticationState.AUTH_REJECTED,
        AuthenticationState.NEEDS_HUMAN_AUTH,
    ],
)
def test_auth_states_block_live_validation(tmp_path: Path, state: AuthenticationState) -> None:
    fixture = PublisherFixture(
        tmp_path,
        mode=PublishMode.LIVE,
        live_enabled=True,
        session=FakeSessionProvider(state),
    )

    report = fixture.publisher.validate(fixture.request)

    assert not report.valid
    assert state.value in report.blocking


def test_captcha_or_risk_verification_stops_for_human(tmp_path: Path) -> None:
    fixture = PublisherFixture(
        tmp_path,
        mode=PublishMode.LIVE,
        live_enabled=True,
        session=FakeSessionProvider(
            AuthenticationState.READY,
            acquired_state=AuthenticationState.NEEDS_HUMAN_AUTH,
        ),
    )
    fixture.prepare()

    with pytest.raises(AuthenticationRequired) as caught:
        fixture.publisher.publish(fixture.request, confirmation=fixture.confirm())

    assert caught.value.state == AuthenticationState.NEEDS_HUMAN_AUTH
    assert fixture.transport.upload_calls == fixture.transport.submit_calls == 0
    assert fixture.audit.list()[-1].action == "AUTH_REQUIRED"


def test_cancel_is_safe_only_before_remote_submit(tmp_path: Path) -> None:
    fixture = PublisherFixture(tmp_path)
    fixture.prepare()
    record = fixture.publisher_store.record_for_request(fixture.request.request_id)
    assert record is not None

    cancelled = fixture.publisher.cancel(record.publish_id)

    assert cancelled.status == PublishRecordStatus.CANCELLED
    remote = cancelled.model_copy(
        update={
            "status": PublishRecordStatus.UNKNOWN,
            "remote_state": RemotePublishState.UNKNOWN,
            "metadata": {"submission_started": True},
        }
    )
    fixture.publisher_store.save_record(remote)
    with pytest.raises(Exception, match="cannot claim retraction"):
        fixture.publisher.cancel(remote.publish_id)


def test_published_record_requires_reliable_content_id() -> None:
    with pytest.raises(ValueError, match="reliable platform_content_id"):
        PublishRecord(
            publish_id="publish_0000000000000000",
            request_id="request_test",
            job_id="creator_0000000000000000",
            job_revision=1,
            platform="bilibili",
            mode=PublishMode.LIVE,
            status=PublishRecordStatus.PUBLISHED,
        )


def test_checkpoint_models_never_serialize_session_handle() -> None:
    lease = SessionLease(
        AuthenticationState.READY,
        {"cookie": "cookie-super-secret", "authorization": "Bearer secret"},
    )

    assert "cookie-super-secret" not in repr(lease)
    assert "Bearer secret" not in repr(lease)
    assert not hasattr(lease, "model_dump")
