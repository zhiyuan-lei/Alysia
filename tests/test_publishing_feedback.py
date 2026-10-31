from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path

import pytest

from alysia.core.config import CoverConfig, VideoConfig
from alysia.core.orchestrator import AlysiaOrchestrator
from alysia.feedback import FeedbackService
from alysia.learning.memory import MemoryStore
from alysia.learning.pipeline import LearningPipeline
from alysia.planning import PlanStore
from alysia.providers.feedback import ManualFeedbackProvider
from alysia.providers.publishing import BilibiliPublishingProvider, PublishingProviderError
from alysia.publishing import PublishingService, PublishingValidationError
from alysia.schemas import ApprovalRecord, CreatorLoopState, PublishJob
from tests.helpers import make_config


def _review_ready(tmp_path: Path):
    config = make_config(tmp_path / "runs")
    config.video = VideoConfig(renderer="mock", width=640, height=360, fps=30)
    config.publish.cover = CoverConfig(width=640, height=360, format="png")
    orchestrator = AlysiaOrchestrator(config)
    state = asyncio.run(orchestrator.create("为什么AI Agent还不是AGI？"))
    state = asyncio.run(orchestrator.resume(state.run_id))
    state = asyncio.run(orchestrator.render(state.run_id))
    state = asyncio.run(orchestrator.package(state.run_id))
    state = asyncio.run(orchestrator.publish_check(state.run_id))
    return config, orchestrator, state


def test_publish_job_schema() -> None:
    approval = ApprovalRecord(
        run_id="run-1",
        approved_at=datetime.now().astimezone(),
        package_hash="a" * 64,
        accepted_warnings=["人工已查看"],
    )
    job = PublishJob(
        job_id="job-1",
        run_id="run-1",
        provider="mock",
        status="approved",
        package_path=Path("publish/publish_package.json"),
        package_hash="a" * 64,
        approval_record=approval,
        created_at=datetime.now().astimezone(),
        updated_at=datetime.now().astimezone(),
    )
    assert job.approval_record is not None
    with pytest.raises(ValueError, match="external_id"):
        job.model_copy(update={"status": "submitted"}).model_validate(
            job.model_copy(update={"status": "submitted"}).model_dump()
        )


def test_publish_validation_and_approval_required(tmp_path: Path) -> None:
    config, _, state = _review_ready(tmp_path)
    service = PublishingService(config)
    before = service.validate(state.run_id)
    assert before.passed is False
    assert "缺少人工 ApprovalRecord" in before.errors
    with pytest.raises(PublishingValidationError, match="验证未通过"):
        service.submit(state.run_id, provider="mock")

    job = service.approve(state.run_id)
    after = service.validate(state.run_id)
    assert job.status == "approved"
    assert after.passed is True
    assert after.approval_present is True
    assert after.warnings


@pytest.fixture(scope="module")
def submitted_run(tmp_path_factory):
    root = tmp_path_factory.mktemp("alpha8-submitted")
    config, orchestrator, state = _review_ready(root)
    service = PublishingService(config)
    approved = service.approve(state.run_id)
    submitted = service.submit(state.run_id, provider="mock")
    return root, config, orchestrator, approved, submitted


def test_mock_publish_is_idempotent(submitted_run) -> None:
    _, config, _, approved, submitted = submitted_run
    service = PublishingService(config)
    repeated = service.submit(submitted.run_id, provider="mock")
    assert submitted.status == "submitted"
    assert submitted.external_id and submitted.external_id.startswith("mock_bv_")
    assert repeated.job_id == approved.job_id == submitted.job_id
    assert repeated.external_id == submitted.external_id


def test_bilibili_missing_credentials_is_safe(monkeypatch, submitted_run) -> None:
    for name in BilibiliPublishingProvider.required_environment:
        monkeypatch.delenv(name, raising=False)
    _, _, orchestrator, _, submitted = submitted_run
    state = orchestrator.manager.load(submitted.run_id)
    package = orchestrator.manager.read_json(state.run_id, state.artifacts["publish_package"])
    from alysia.schemas import PublishPackage

    parsed = PublishPackage.model_validate(package)
    with pytest.raises(PublishingProviderError, match="凭证缺失"):
        BilibiliPublishingProvider().submit(
            submitted,
            parsed,
            video_path=orchestrator.manager.run_dir(state.run_id) / parsed.video_path,
            cover_path=orchestrator.manager.run_dir(state.run_id) / parsed.cover_path,
        )


def test_manual_feedback_json_and_mapping(tmp_path: Path, submitted_run) -> None:
    _, _, _, _, submitted = submitted_run
    source = tmp_path / "feedback.json"
    source.write_text(
        json.dumps(
            {
                "run_id": submitted.run_id,
                "external_id": submitted.external_id,
                "collected_at": datetime.now().astimezone().isoformat(),
                "source": "manual",
                "views": 100,
                "likes": 12,
                "retention_points": [{"second": 0, "percentage": 1.0}],
                "comments_summary": ["讲解清楚", "希望下一期讲配音？"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    record = ManualFeedbackProvider().collect(submitted.run_id, submitted.external_id or "", source)
    assert record.views == 100
    assert record.source == "manual"


def test_feedback_mapping_idempotency_and_publish_memory(submitted_run) -> None:
    _, config, orchestrator, _, submitted = submitted_run
    config.feedback.provider = "mock"
    service = FeedbackService(config)
    first = service.import_feedback(submitted.run_id, provider="mock")
    mapping_path = orchestrator.manager.run_dir(submitted.run_id) / first.artifacts["feedback_mapping"]
    before = mapping_path.read_text(encoding="utf-8")
    second = service.import_feedback(submitted.run_id, provider="mock")
    after = mapping_path.read_text(encoding="utf-8")
    assert first.feedback_imported is True
    assert before == after
    assert second.artifacts["analytics_metrics"] == "analytics/metrics.json"
    episodes = MemoryStore(config.learning.memory_dir).list_publish_episodes()
    assert len([item for item in episodes if item.run_id == submitted.run_id]) == 1
    assert next(item for item in episodes if item.run_id == submitted.run_id).source == "mock"


def test_mock_feedback_never_promotes_lessons(submitted_run) -> None:
    _, config, _, _, submitted = submitted_run
    pipeline = LearningPipeline(
        FeedbackService(config).manager,
        config.learning.memory_dir,
    )
    pipeline.analyze(submitted.run_id)
    learned = pipeline.learn(submitted.run_id)
    lessons = json.loads(
        (pipeline.manager.run_dir(submitted.run_id) / learned.artifacts["lessons"]).read_text(encoding="utf-8")
    )
    assert all(item["source"] == "testing" for item in lessons)
    assert not any(item["status"] == "supported" for item in lessons)
    related = [
        item
        for item in MemoryStore(config.learning.memory_dir).list_lessons()
        if submitted.run_id in item.evidence_run_ids
    ]
    assert not any(item.status == "supported" for item in related)


def test_creator_loop_publish_gate_defaults_to_human_approval(tmp_path: Path) -> None:
    config, orchestrator, state = _review_ready(tmp_path)
    assert config.creator_loop.require_human_approval is True
    assert config.publishing.require_approval is True
    with pytest.raises(PublishingValidationError, match="验证未通过"):
        PublishingService(config).submit(state.run_id, provider="mock")

    state.planning_provenance = {"plan_id": "plan_test", "slot_id": "slot_01", "testing": True}
    orchestrator.manager.save(state)
    store = PlanStore(config.planning.plans_dir)
    store.save_loop_state(
        CreatorLoopState(
            stage="review_ready",
            active_plan_id="plan_test",
            updated_at=datetime.now().astimezone(),
        )
    )
    service = PublishingService(config)
    service.review(state.run_id)
    assert store.load_loop_state().stage == "publish_approval"
    service.approve(state.run_id)
    assert store.load_loop_state().stage == "publish_job"
    service.submit(state.run_id, provider="mock")
    assert store.load_loop_state().stage == "feedback_waiting"
    FeedbackService(config).import_feedback(state.run_id, provider="mock")
    assert store.load_loop_state().stage == "learning"
