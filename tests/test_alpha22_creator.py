from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from alysia.creator import (
    BilibiliPublicationReceipt,
    ClaimClassification,
    ContentObservation,
    CreatorClaimTrace,
    CreatorJobService,
    CreatorJobStore,
    CreatorQAGate,
    CreatorQAReport,
    CreatorReflection,
    DuplicateCheckReport,
    ResearchEvidenceStatus,
    CreatorDuplicateDetector,
    CreatorMemoryIntegrator,
    BilibiliPublisher,
    ManualPublicationRequired,
)
from alysia.creator.evidence import BetaEvidenceLedger


def now() -> datetime:
    return datetime.now().astimezone()


def passed_qa() -> CreatorQAReport:
    return CreatorQAReport(
        passed=True,
        content_passed=True,
        video_passed=True,
        copy_passed=True,
        safety_passed=True,
        duplicate_passed=True,
        errors=[],
        warnings=[],
        checked_at=now(),
        evidence_refs=["qa/grounding.json", "qa/video.json", "qa/publish.json"],
    )


def ready_job(tmp_path: Path, *, testing: bool = False, dry_run: bool = False):
    store = CreatorJobStore(tmp_path / "creator_jobs")
    service = CreatorJobService(store)
    video = tmp_path / "final.mp4"
    cover = tmp_path / "cover.png"
    video.write_bytes(b"real-video-artifact")
    cover.write_bytes(b"real-cover-artifact")
    job = service.create(
        topic="本地模型资源治理",
        topic_source="manual",
        topic_score=82.5,
        testing=testing,
        dry_run=dry_run,
    )
    job.selected_title = "本地模型资源治理：8GB 显存如何安全运行"
    job.description = "基于可追溯资料的实践说明。"
    job.tags = ["本地模型", "资源治理"]
    job.video_path = video
    job.thumbnail_path = cover
    job.qa_report = passed_qa()
    store.save(job)
    service.submit_for_review(job.job_id)
    service.approve(job.job_id, approved_by="human:tester", package_hash="a" * 64)
    return service.mark_publish_ready(job.job_id, package_path=tmp_path / "bilibili-package.json")


def publication_receipt(tmp_path: Path, content_id: str = "BV1ab411c7DE") -> BilibiliPublicationReceipt:
    proof = tmp_path / "bilibili-proof.json"
    proof.write_text('{"source":"human-captured-platform-receipt"}', encoding="utf-8")
    return BilibiliPublicationReceipt(
        content_id=content_id,
        publication_url=f"https://www.bilibili.com/video/{content_id}",
        published_at=now(),
        recorded_at=now(),
        recorded_by="human:tester",
        source="manual_handoff",
        evidence_path=proof,
    )


def test_creator_job_has_stable_id_and_atomic_persistence(tmp_path: Path) -> None:
    store = CreatorJobStore(tmp_path / "creator_jobs")
    service = CreatorJobService(store)
    job = service.create(topic="Alpha22", topic_source="manual", topic_score=90)
    assert job.job_id.startswith("creator_")
    assert store.load(job.job_id).job_id == job.job_id
    assert store.path_for(job.job_id).is_file()


def test_required_state_machine_cannot_skip_review_or_approval(tmp_path: Path) -> None:
    store = CreatorJobStore(tmp_path / "creator_jobs")
    service = CreatorJobService(store)
    job = service.create(topic="Alpha22", topic_source="manual", topic_score=90)
    with pytest.raises(ValueError, match="PUBLISH_READY"):
        service.mark_publish_ready(job.job_id, package_path=tmp_path / "package.json")
    with pytest.raises(ValueError, match="REVIEW"):
        service.approve(job.job_id, approved_by="human:tester", package_hash="a" * 64)


def test_request_revision_preserves_snapshot_and_blocks_publish(tmp_path: Path) -> None:
    store = CreatorJobStore(tmp_path / "creator_jobs")
    service = CreatorJobService(store)
    job = service.create(topic="Alpha22", topic_source="manual", topic_score=90)
    job.qa_report = passed_qa()
    store.save(job)
    service.submit_for_review(job.job_id)
    revised = service.request_revision(
        job.job_id,
        reason="补充事实来源",
        requested_by="human:reviewer",
    )
    assert revised.status == "DRAFT"
    assert revised.approval_status == "REVISION_REQUIRED"
    assert revised.current_revision == 2
    assert revised.revisions[-1].reason == "补充事实来源"
    assert store.revision_path(job.job_id, 1).is_file()
    with pytest.raises(ValueError, match="APPROVED"):
        service.mark_publish_ready(job.job_id, package_path=tmp_path / "package.json")


def test_creator_qa_blocks_stale_fact_and_declared_inference_as_fact() -> None:
    claims = [
        CreatorClaimTrace(
            claim="过期资料",
            classification=ClaimClassification.VERIFIED_FACT,
            confidence=0.9,
            source_refs=["source-1"],
            stale=True,
        ),
        CreatorClaimTrace(
            claim="推断",
            classification=ClaimClassification.INFERENCE,
            confidence=0.4,
            presented_as_fact=True,
        ),
    ]
    report = CreatorQAGate().evaluate(
        claims=claims,
        research_status=ResearchEvidenceStatus.SUFFICIENT,
        video_passed=True,
        copy_passed=True,
        safety_passed=True,
        duplicate_report=DuplicateCheckReport(passed=True),
        evidence_refs=["grounding.json"],
    )
    assert not report.passed
    assert any("stale" in item for item in report.errors)
    assert any("inference_presented_as_fact" in item for item in report.errors)


def test_publication_requires_real_receipt_and_is_idempotent(tmp_path: Path) -> None:
    job = ready_job(tmp_path)
    service = CreatorJobService(CreatorJobStore(tmp_path / "creator_jobs"))
    receipt = publication_receipt(tmp_path)
    published = service.record_publication(job.job_id, receipt)
    repeated = service.record_publication(job.job_id, receipt)
    assert published.status == "PUBLISHED"
    assert published.publish_status == "PUBLISHED"
    assert published.platform_content_id == receipt.content_id
    assert repeated.model_dump(mode="json") == published.model_dump(mode="json")


def test_dry_run_or_testing_job_can_never_be_published(tmp_path: Path) -> None:
    for testing, dry_run in ((True, False), (False, True)):
        case = tmp_path / f"{testing}-{dry_run}"
        case.mkdir()
        job = ready_job(case, testing=testing, dry_run=dry_run)
        service = CreatorJobService(CreatorJobStore(case / "creator_jobs"))
        with pytest.raises(ValueError, match="real publication"):
            service.record_publication(job.job_id, publication_receipt(case))


def test_observation_keeps_unavailable_fields_and_timestamp(tmp_path: Path) -> None:
    job = ready_job(tmp_path)
    service = CreatorJobService(CreatorJobStore(tmp_path / "creator_jobs"))
    service.record_publication(job.job_id, publication_receipt(tmp_path))
    observation = ContentObservation(
        content_id="BV1ab411c7DE",
        observed_at=now(),
        source="manual_real",
        views=12,
        likes=None,
        comments=None,
        favorites=None,
        shares=None,
        followers_delta=None,
        availability={
            "views": "available",
            "likes": "unavailable",
            "comments": "unavailable",
            "favorites": "unavailable",
            "shares": "unavailable",
            "followers_delta": "unavailable",
        },
        evidence_path=tmp_path / "bilibili-proof.json",
    )
    updated = service.add_observation(job.job_id, observation)
    assert updated.metrics[-1].likes is None
    assert updated.metrics[-1].availability["likes"] == "unavailable"


def test_reflection_separates_facts_from_interpretation(tmp_path: Path) -> None:
    job = ready_job(tmp_path)
    service = CreatorJobService(CreatorJobStore(tmp_path / "creator_jobs"))
    service.record_publication(job.job_id, publication_receipt(tmp_path))
    reflection = CreatorReflection(
        attempted="测试 8GB 显存创作主题",
        actual="发布后获得 12 次播放",
        worked=["投稿包通过 QA"],
        likely_failed=["标题可能不够清晰"],
        supporting_evidence=["bilibili-proof.json", "metrics-1.json"],
        uncertainties=["样本量不足，不能判断标题因果"],
        next_changes=["下一条只改变标题结构"],
        facts=["views=12"],
        interpretations=["标题可能影响点击，但未证明因果"],
        created_at=now(),
    )
    updated = service.set_reflection(job.job_id, reflection)
    assert updated.reflection.facts
    assert updated.reflection.interpretations


def test_beta_ledger_rejects_non_real_and_counts_only_complete_real_rows(tmp_path: Path) -> None:
    real = ready_job(tmp_path / "real")
    service = CreatorJobService(CreatorJobStore(tmp_path / "real" / "creator_jobs"))
    service.record_publication(real.job_id, publication_receipt(tmp_path / "real"))
    service.add_observation(
        real.job_id,
        ContentObservation(
            content_id="BV1ab411c7DE",
            observed_at=now(),
            source="manual_real",
            availability={name: "unavailable" for name in ("views", "likes", "comments", "favorites", "shares", "followers_delta")},
            evidence_path=tmp_path / "real" / "bilibili-proof.json",
        ),
    )
    service.set_reflection(
        real.job_id,
        CreatorReflection(
            attempted="attempt", actual="published", worked=[], likely_failed=[],
            supporting_evidence=["bilibili-proof.json"], uncertainties=["insufficient sample"],
            next_changes=["observe later"], facts=["published"], interpretations=[],
            created_at=now(),
        ),
    )
    evidence = tmp_path / "real" / "evidence.md"
    evidence.write_text("auditable evidence", encoding="utf-8")
    ledger = BetaEvidenceLedger(tmp_path / "alpha22_beta_runs.csv")
    ledger.upsert(service.store.load(real.job_id), evidence_path=evidence)
    assert ledger.qualified_count() == 1

    fake = ready_job(tmp_path / "fake", testing=True)
    with pytest.raises(ValueError, match="real Beta"):
        ledger.upsert(fake, evidence_path=evidence)


def test_duplicate_detection_covers_multiple_creator_dimensions(tmp_path: Path) -> None:
    historical = CreatorJobService(CreatorJobStore(tmp_path / "history")).create(
        topic="8GB 显存运行本地视频模型", topic_source="manual", topic_score=80,
    )
    historical.selected_title = "8GB 显存如何运行本地视频模型"
    historical.claims = [
        CreatorClaimTrace(
            claim="重型 GPU 任务应串行运行",
            classification=ClaimClassification.VERIFIED_FACT,
            confidence=0.9,
            source_refs=["source-1"],
        )
    ]
    historical.visual_plan = {"style": "terminal plus GPU chart"}
    historical.script = "开场\n问题\n三个步骤\n结论"
    candidate = historical.model_copy(deep=True)
    candidate.job_id = "creator_0123456789abcdef"
    report = CreatorDuplicateDetector(threshold=0.6).check(candidate, [historical])
    assert not report.passed
    assert {item.dimension for item in report.matches} >= {
        "topic", "title", "core_claim", "visual_plan", "script_structure"
    }


def test_manual_bilibili_prepare_never_claims_published(tmp_path: Path) -> None:
    job = ready_job(tmp_path)
    publisher = BilibiliPublisher(mode="manual_handoff")
    report = publisher.validate(job)
    assert report.passed
    assert publisher.status(job) == "PUBLISH_READY"
    with pytest.raises(ManualPublicationRequired):
        publisher.publish(job)
    assert CreatorJobStore(tmp_path / "creator_jobs").load(job.job_id).status == "PUBLISH_READY"


def test_memory_integration_writes_compact_episode_only(tmp_path: Path) -> None:
    job = ready_job(tmp_path)
    service = CreatorJobService(CreatorJobStore(tmp_path / "creator_jobs"))
    service.record_publication(job.job_id, publication_receipt(tmp_path))
    service.add_observation(
        job.job_id,
        ContentObservation(
            content_id="BV1ab411c7DE",
            observed_at=now(),
            source="manual_real",
            views=12,
            availability={
                "views": "available",
                "likes": "unavailable",
                "comments": "unavailable",
                "favorites": "unavailable",
                "shares": "unavailable",
                "followers_delta": "unavailable",
            },
            evidence_path=tmp_path / "bilibili-proof.json",
        ),
    )
    service.set_reflection(
        job.job_id,
        CreatorReflection(
            attempted="attempt", actual="published", worked=[], likely_failed=[],
            supporting_evidence=["proof"], uncertainties=["small sample"],
            next_changes=["observe"], facts=["views=12"], interpretations=[], created_at=now(),
        ),
    )
    integrator = CreatorMemoryIntegrator(tmp_path / "memory")
    updated = integrator.record(service.store.load(job.job_id), service.store)
    episode_path = tmp_path / "memory" / "creator_episodes" / f"{job.job_id}.json"
    payload = episode_path.read_text(encoding="utf-8")
    assert episode_path.is_file()
    assert "research_sources" not in payload
    assert "raw_comments" not in payload
    assert str(episode_path.resolve()) in updated.memory_refs
