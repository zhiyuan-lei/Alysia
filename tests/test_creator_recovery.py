from __future__ import annotations

from pathlib import Path

import pytest

from alysia.core.resources import ResourceManager
from alysia.creator import (
    AdapterResult,
    BilibiliPublisher,
    CreatorMemoryGate,
    CreatorRecoveryService,
    FailureCategory,
    HumanReviewService,
    MemoryCandidateStatus,
    MemoryType,
    ApprovalStatus,
    ProductionAdapter,
    ProductionArtifactRegistry,
    ProductionFailure,
    ProductionOrchestrator,
    ProductionPlanner,
    ProductionPlanStore,
    ProductionStatus,
    ProductionTask,
    ProductionTaskStatus,
    ProductionTaskType,
    PublishMode,
    PublishStatus,
    PublishRecordStatus,
    PublishTransportError,
    RecoveryClassification,
    RemotePublishState,
    ReviewAction,
    ResourceClass,
    RetryPolicy,
    TransportPublishResult,
)
from alysia.reliability.fault_injection import FaultInjector
from alysia.security.audit import AuditLog
from tests.test_creator_production import FakeAdapter, make_creator_plan, make_job, make_tasks
from tests.test_creator_publisher import FakeTransport, PublisherFixture
from tests.test_creator_observation_memory import Step6Fixture
from tests.test_creator_qa_review import ReviewFixture


class InjectedAdapter(ProductionAdapter):
    adapter_id = "test.fault-injected"

    def __init__(self, injector: FaultInjector, point: str) -> None:
        self.injector = injector
        self.point = point
        self.calls = 0
        self.cleanup_calls = 0

    def execute(self, task: ProductionTask, output_dir: Path) -> AdapterResult:
        self.calls += 1
        path = output_dir / f"{task.task_id}.txt"
        path.write_bytes(b"")
        try:
            self.injector.trigger(self.point)
        except ProductionFailure as exc:
            exc.partial_paths = [path]
            raise
        path.write_text(f"TEST recovered call={self.calls}", encoding="utf-8")
        return AdapterResult(output_paths=[path], artifact_type=task.task_type.value)

    def cleanup(self) -> None:
        self.cleanup_calls += 1


def recovery_service(
    tmp_path: Path,
    plans: ProductionPlanStore,
    artifacts: ProductionArtifactRegistry,
    *,
    publishers=None,
    audit: AuditLog | None = None,
) -> CreatorRecoveryService:
    return CreatorRecoveryService(
        plans=plans,
        artifacts=artifacts,
        publishers=publishers,
        audit=audit or AuditLog(tmp_path / "audit" / "recovery.jsonl"),
    )


def test_fault_injector_is_disabled_by_default_and_named_only() -> None:
    dormant = FaultInjector(faults={"comfyui.timeout": TimeoutError("TEST fault")})
    dormant.trigger("comfyui.timeout")
    enabled = FaultInjector(enabled=True, faults={"comfyui.timeout": TimeoutError("TEST fault")})
    enabled.trigger("different.point")
    with pytest.raises(TimeoutError, match="TEST fault"):
        enabled.trigger("comfyui.timeout")


@pytest.mark.parametrize(
    ("failure_point", "failure_code", "category"),
    [
        ("comfyui.connection", "COMFYUI_UNAVAILABLE", FailureCategory.TRANSIENT),
        ("comfyui.timeout", "COMFYUI_TIMEOUT", FailureCategory.TRANSIENT),
        ("comfyui.provider", "COMFYUI_PROVIDER_ERROR", FailureCategory.TRANSIENT),
        ("h3.timeout", "H3_TIMEOUT", FailureCategory.TRANSIENT),
        ("h3.process", "H3_PROCESS_FAILURE", FailureCategory.TRANSIENT),
        ("h3.resource", "RESOURCE_EXHAUSTED", FailureCategory.RESOURCE),
    ],
)
def test_f1_f2_bounded_failure_restart_resumes_only_failed_task(
    tmp_path: Path,
    failure_point: str,
    failure_code: str,
    category: FailureCategory,
) -> None:
    plans = ProductionPlanStore(tmp_path / "plans")
    artifacts = ProductionArtifactRegistry(tmp_path / "artifacts", probe_media=False)
    resources = ResourceManager(sequential_gpu=True)
    injector = FaultInjector(
        enabled=True,
        faults={
            failure_point: ProductionFailure(
                "TEST injected provider failure",
                code=failure_code,
                category=category,
                retryable=True,
            )
        },
    )
    events: list[str] = []
    voice = FakeAdapter(events)
    visual = InjectedAdapter(injector, failure_point)
    composite = FakeAdapter(events)
    orchestrator = ProductionOrchestrator(
        adapters={
            ProductionTaskType.VOICE: voice,
            ProductionTaskType.IMAGE: visual,
            ProductionTaskType.COMPOSITE: composite,
        },
        store=plans,
        artifacts=artifacts,
        resources=resources,
        retry_policy=RetryPolicy(max_attempts=3, backoff_seconds=[0, 0, 0]),
        preflight=lambda task: None,
        sleep=lambda seconds: None,
    )
    creator_plan = make_creator_plan(make_job())
    plan = ProductionPlanner().build(creator_plan, make_tasks())

    failed = orchestrator.start(plan)

    assert failed.status == ProductionStatus.FAILED
    assert failed.task("voice").status == ProductionTaskStatus.SUCCEEDED
    assert failed.task("visual").attempt_count == 2
    assert failed.task("composite").status == ProductionTaskStatus.BLOCKED
    partials = list((tmp_path / "artifacts" / "manifests").glob("*.json"))
    assert any('"status": "PARTIAL"' in path.read_text(encoding="utf-8") for path in partials)
    assert resources.current_gpu_phase is None

    report = recovery_service(tmp_path, plans, artifacts).recover()
    injector.enabled = False
    resumed = orchestrator.resume(plan.production_id)

    assert {item.classification for item in report.findings} == {RecoveryClassification.SAFE_TO_RETRY}
    assert resumed.status == ProductionStatus.SUCCEEDED
    assert resumed.task("visual").metadata["recovery_attempt_history"] == [2]
    assert voice.calls == 1
    assert visual.calls == 3
    assert composite.calls == 1
    assert resources.current_gpu_phase is None


def test_f4_f5_orphan_artifact_is_registered_then_missing_file_is_rebuilt(tmp_path: Path) -> None:
    plans = ProductionPlanStore(tmp_path / "plans")
    artifacts = ProductionArtifactRegistry(tmp_path / "artifacts", probe_media=False)
    creator_plan = make_creator_plan(make_job())
    plan = ProductionPlanner().build(
        creator_plan,
        [
            ProductionTask(
                task_id="visual",
                task_type=ProductionTaskType.IMAGE,
                status=ProductionTaskStatus.RUNNING,
                resource_class=ResourceClass.GPU_HEAVY,
                attempt_count=1,
            )
        ],
    )
    plan.status = ProductionStatus.RUNNING
    plans.save(plan)
    orphan = artifacts.task_dir(plan.job_id, "visual") / "visual.txt"
    orphan.write_text("TEST complete artifact before manifest", encoding="utf-8")

    first = recovery_service(tmp_path, plans, artifacts).recover()
    recovered = plans.load(plan.production_id)

    assert first.findings[0].action == "REGISTER_ARTIFACT"
    assert recovered.task("visual").status == ProductionTaskStatus.SUCCEEDED
    assert artifacts.valid(recovered.task("visual").output_refs)

    orphan.unlink()
    second = recovery_service(tmp_path, plans, artifacts).recover()
    reset = plans.load(plan.production_id)

    assert second.findings[0].classification == RecoveryClassification.SAFE_TO_RETRY
    assert reset.task("visual").status == ProductionTaskStatus.PENDING
    assert reset.task("visual").output_refs == []


def test_startup_retry_budget_is_bounded_across_restarts(tmp_path: Path) -> None:
    plans = ProductionPlanStore(tmp_path / "plans")
    artifacts = ProductionArtifactRegistry(tmp_path / "artifacts", probe_media=False)
    plan = ProductionPlanner().build(
        make_creator_plan(make_job()),
        [
            ProductionTask(
                task_id="h3",
                task_type=ProductionTaskType.VIDEO,
                status=ProductionTaskStatus.FAILED,
                attempt_count=2,
                metadata={"retryable": True},
            )
        ],
    )
    plan.status = ProductionStatus.FAILED
    plans.save(plan)
    service = recovery_service(tmp_path, plans, artifacts)

    first = service.recover()
    retried = plans.load(plan.production_id)
    retried.task("h3").status = ProductionTaskStatus.FAILED
    retried.task("h3").attempt_count = 2
    retried.task("h3").metadata["retryable"] = True
    plans.save(retried)
    second = service.recover()

    assert first.findings[0].classification == RecoveryClassification.SAFE_TO_RETRY
    assert second.findings[0].classification == RecoveryClassification.MANUAL_INTERVENTION
    assert plans.load(plan.production_id).task("h3").status == ProductionTaskStatus.FAILED


@pytest.mark.parametrize(
    ("remote_state", "expected_status"),
    [
        (RemotePublishState.PUBLISHED, PublishRecordStatus.PUBLISHED),
        (RemotePublishState.NOT_FOUND, PublishRecordStatus.FAILED),
        (RemotePublishState.UNKNOWN, PublishRecordStatus.UNKNOWN),
    ],
)
def test_f3_unknown_restart_reconciles_without_second_submit(
    tmp_path: Path,
    remote_state: RemotePublishState,
    expected_status: PublishRecordStatus,
) -> None:
    transport = FakeTransport()
    transport.submit_error = PublishTransportError(
        "TEST timeout after submit",
        code="POST_SUBMIT_TIMEOUT",
        retryable=True,
        submission_started=True,
        indeterminate=True,
    )
    transport.reconcile_result = TransportPublishResult(
        remote_state=remote_state,
        platform_content_id="TEST_ONLY_BV_RECOVERED" if remote_state == RemotePublishState.PUBLISHED else None,
        platform_url_ref="TEST_ONLY://bilibili/video/BV_RECOVERED"
        if remote_state == RemotePublishState.PUBLISHED
        else None,
        test_only=True,
    )
    fixture = PublisherFixture(
        tmp_path,
        mode=PublishMode.LIVE,
        live_enabled=True,
        transport=transport,
    )
    fixture.prepare()
    unknown = fixture.publisher.publish(fixture.request, confirmation=fixture.confirm())
    assert unknown.status == PublishRecordStatus.UNKNOWN

    plans = ProductionPlanStore(tmp_path / "plans")
    report = recovery_service(
        tmp_path,
        plans,
        fixture.artifacts,
        publishers=fixture.publisher_store,
        audit=fixture.audit,
    ).recover()
    restarted = BilibiliPublisher(
        mode=PublishMode.LIVE,
        jobs=fixture.jobs,
        qa_reviews=fixture.qa_reviews,
        artifacts=fixture.artifacts,
        store=fixture.publisher_store,
        audit=fixture.audit,
        session_provider=fixture.session,
        transport=transport,
        live_enabled=True,
    )
    reconciled = restarted.reconcile(unknown.publish_id)

    assert report.for_resource(unknown.publish_id)[0].classification == RecoveryClassification.RECONCILE_FIRST
    assert reconciled.status == expected_status
    assert transport.submit_calls == 1
    assert transport.reconcile_calls == 1


def test_f4_submitting_restart_becomes_unknown_and_requires_reconciliation(tmp_path: Path) -> None:
    fixture = PublisherFixture(tmp_path)
    fixture.prepare()
    record = fixture.publisher_store.record_for_request(fixture.request.request_id)
    assert record is not None
    record.status = PublishRecordStatus.SUBMITTING
    record.remote_state = RemotePublishState.UNKNOWN
    record.metadata["submission_started"] = True
    fixture.publisher_store.save_record(record)

    report = recovery_service(
        tmp_path,
        ProductionPlanStore(tmp_path / "plans"),
        fixture.artifacts,
        publishers=fixture.publisher_store,
        audit=fixture.audit,
    ).recover()
    persisted = fixture.publisher_store.load_record(record.publish_id)

    assert persisted.status == PublishRecordStatus.UNKNOWN
    assert persisted.metadata["safe_to_retry"] is False
    assert report.for_resource(record.publish_id)[0].action == "MARK_UNKNOWN"
    assert "RECOVERY_RECONCILIATION_REQUIRED" in [event.action for event in fixture.audit.list()]


def test_f5_qa_and_review_survive_restart_without_duplicate_human_action(tmp_path: Path) -> None:
    fixture = ReviewFixture(tmp_path)
    report = fixture.run_qa()
    restarted_reviews = HumanReviewService(
        jobs=fixture.jobs,
        store=fixture.review_store,
        audit=fixture.audit,
    )
    first = restarted_reviews.submit(
        job_id=fixture.job.job_id,
        qa_id=report.qa_id,
        action=ReviewAction.APPROVE,
        reason="Human approved persisted QA evidence.",
        reviewer="human:reviewer",
        job_revision=report.job_revision,
    )
    duplicate = restarted_reviews.submit(
        job_id=fixture.job.job_id,
        qa_id=report.qa_id,
        action=ReviewAction.APPROVE,
        reason="Human approved persisted QA evidence.",
        reviewer="human:reviewer",
        job_revision=report.job_revision,
    )
    ready = restarted_reviews.enter_publish_ready(
        job_id=fixture.job.job_id,
        qa_id=report.qa_id,
        review_id=first.review_id,
    )

    assert fixture.review_store.load_qa(fixture.job.job_id, report.qa_id) == report
    assert duplicate.review_id == first.review_id
    assert len(fixture.review_store.review_history(fixture.job.job_id)) == 1
    assert ready.publish_status.value == "PUBLISH_READY"

    publisher = PublisherFixture(tmp_path / "confirm")
    publisher.prepare()
    publisher.confirm()
    with pytest.raises(FileExistsError):
        publisher.confirm()
    assert len(list((tmp_path / "confirm" / "publisher" / "confirmations").glob("*.json"))) == 1


def test_f6_revision_and_grounding_change_invalidate_old_approval(tmp_path: Path) -> None:
    fixture = ReviewFixture(tmp_path)
    report, decision = fixture.approve()

    revised = fixture.reviews.update_content(
        fixture.job.job_id,
        {"claims": []},
        reason="Grounding changed after approval.",
        actor="human:editor",
    )

    assert revised.current_revision == report.job_revision + 1
    assert revised.approval_status.value == "DRAFT"
    assert revised.publish_status.value == "NOT_READY"
    with pytest.raises(ValueError, match="stale QA"):
        fixture.reviews.enter_publish_ready(
            job_id=revised.job_id,
            qa_id=report.qa_id,
            review_id=decision.review_id,
        )

    revision_fixture = ReviewFixture(tmp_path / "request-revision")
    revision_report = revision_fixture.run_qa()
    revision_fixture.reviews.submit(
        job_id=revision_fixture.job.job_id,
        qa_id=revision_report.qa_id,
        action=ReviewAction.REQUEST_REVISION,
        reason="Research needs a fresher source.",
        reviewer="human:editor",
        job_revision=revision_report.job_revision,
        requested_changes=["Refresh grounding"],
    )
    with pytest.raises(ValueError, match="stale review or QA"):
        revision_fixture.reviews.submit(
            job_id=revision_fixture.job.job_id,
            qa_id=revision_report.qa_id,
            action=ReviewAction.APPROVE,
            reason="Old evidence must not approve a new revision.",
            reviewer="human:reviewer",
            job_revision=revision_report.job_revision,
        )


def test_f6_reject_blocks_prepared_publish_and_stale_request(tmp_path: Path) -> None:
    fixture = PublisherFixture(tmp_path, mode=PublishMode.LIVE, live_enabled=True)
    fixture.prepare()
    confirmation = fixture.confirm()
    job = fixture.jobs.load(fixture.job.job_id)
    job.status = "BLOCKED"
    job.approval_status = ApprovalStatus.REJECTED
    job.publish_status = PublishStatus.NOT_READY
    job.approved_by = None
    job.approved_at = None
    fixture.jobs.save(job)

    with pytest.raises(Exception, match="validation failed"):
        fixture.publisher.prepare(fixture.request)
    with pytest.raises(Exception, match="validation failed"):
        fixture.publisher.publish(fixture.request, confirmation=confirmation)
    assert fixture.transport.submit_calls == 0

    changed = HumanReviewService(
        jobs=fixture.jobs,
        store=fixture.qa_reviews,
        audit=fixture.audit,
    ).update_content(
        fixture.job.job_id,
        {"description": "New revision after the browser opened."},
        reason="Invalidate the open browser request.",
        actor="human:editor",
    )
    validation = fixture.publisher.validate(fixture.request)
    assert changed.current_revision == fixture.request.job_revision + 1
    assert "STALE_JOB_REVISION" in validation.blocking
    assert "JOB_NOT_PUBLISH_READY" in validation.blocking


def test_f7_conflicting_research_cannot_pass_qa(tmp_path: Path) -> None:
    fixture = ReviewFixture(tmp_path, uncertain=True)
    fixture.creator_plan.script_sections.append(
        fixture.creator_plan.script_sections[0].model_copy(
            update={
                "section_id": "conflicting",
                "text": "The disputed result is definitely true.",
                "claim_refs": ["claim_uncertain"],
                "factual": True,
            }
        )
    )
    fixture.creator_plan.script += "\n\nThe disputed result is definitely true."
    fixture.jobs.update(
        fixture.job.job_id,
        {"script": fixture.creator_plan.script},
        reason="TEST inject conflicting claim as fact",
        updated_by="system:test",
    )

    report = fixture.run_qa()

    assert not report.review_eligible
    assert "UNCERTAIN_CLAIM_AS_FACT" in {item.code for item in report.blocking_issues}


def test_observation_identity_and_test_memory_cannot_pollute_production(tmp_path: Path) -> None:
    fixture = Step6Fixture(tmp_path)
    observation = fixture.observe()
    forged = observation.model_copy(
        update={
            "observation_id": None,
            "platform_content_id": "TEST_ONLY_WRONG_CONTENT",
            "content_id": "TEST_ONLY_WRONG_CONTENT",
        }
    )
    with pytest.raises(ValueError, match="identity does not match"):
        fixture.observation_service.record(forged)

    reflection = fixture.reflect(observation=observation)
    candidate = fixture.memory_gate.create_candidate(
        reflection_id=reflection.reflection_id or "",
        memory_type=MemoryType.SEMANTIC,
        statement="One TEST_ONLY run must remain a candidate.",
        confidence=0.9,
    )
    first = fixture.memory_gate.evaluate(candidate.candidate_id or "")
    repeated = fixture.memory_gate.evaluate(candidate.candidate_id or "")
    assert first.status == MemoryCandidateStatus.CANDIDATE
    assert repeated.support_count == 1

    production_gate = CreatorMemoryGate(
        tmp_path / "production-memory",
        environment="production",
        jobs=fixture.jobs,
        reflections=fixture.reflections,
        audit=fixture.audit,
    )
    with pytest.raises(ValueError, match="TEST_FIXTURE cannot enter production memory"):
        production_gate.create_candidate(
            reflection_id=reflection.reflection_id or "",
            memory_type=MemoryType.EPISODIC,
            statement="TEST fixture must not enter production memory.",
            confidence=0.9,
        )


def test_memory_candidate_retry_repairs_interrupted_reflection_link(tmp_path: Path) -> None:
    fixture = Step6Fixture(tmp_path)
    reflection = fixture.reflect()
    candidate = fixture.memory_gate.create_candidate(
        reflection_id=reflection.reflection_id or "",
        memory_type=MemoryType.EPISODIC,
        statement="TEST interrupted memory link can be repaired idempotently.",
        confidence=0.8,
    )
    stored_reflection = fixture.reflections.load(reflection.reflection_id or "")
    stored_reflection.memory_candidates = []
    fixture.reflections._path(reflection.reflection_id or "").unlink()
    fixture.reflections.save(stored_reflection)

    repeated = fixture.memory_gate.create_candidate(
        reflection_id=reflection.reflection_id or "",
        memory_type=MemoryType.EPISODIC,
        statement=candidate.statement,
        confidence=0.8,
    )

    assert repeated.candidate_id == candidate.candidate_id
    assert fixture.reflections.load(reflection.reflection_id or "").memory_candidates == [candidate.candidate_id]
