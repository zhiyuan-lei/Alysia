from __future__ import annotations

from datetime import datetime, timedelta
import asyncio
from pathlib import Path

import pytest
from pydantic import ValidationError

from alysia.knowledge import (
    ClaimExtractor,
    ClaimVerifier,
    ConflictDetector,
    FreshnessPolicy,
    GroundingChecker,
    KnowledgeContextSelector,
    KnowledgeGapDetector,
    KnowledgeMaintenanceService,
    KnowledgeQA,
    KnowledgeService,
    KnowledgeStore,
    ResearchKnowledgePipeline,
    ResearchTaskPlanner,
    SourceQualityEvaluator,
    demo_d_h3_observation,
)
from alysia.knowledge.models import (
    ClaimCandidate,
    EvidenceSource,
    KnowledgeClaim,
    ResearchTask,
    normalize_claim_key,
)
from alysia.schemas.research import ResearchResult, Source
from alysia.schemas.script import Script, ScriptSection
from alysia.providers.search.web import WebResearchProvider
from alysia.supervisor import AutonomousSupervisor
from alysia.workflow.executors import WorkflowExecutorRegistry
from tests.helpers import make_config


NOW = datetime.now().astimezone()


def _source(source_id: str = "s1", *, source_type: str = "official", origin: str = "manual", published_at: datetime | None = None) -> EvidenceSource:
    return EvidenceSource(
        source_id=source_id,
        url=f"https://example.invalid/{source_id}",
        title=f"Source {source_id}",
        publisher="Example",
        domain="software",
        author="Author",
        published_at=published_at or NOW,
        retrieved_at=NOW,
        source_type=source_type,  # type: ignore[arg-type]
        freshness_class="current",
        citation_note="fixture",
        evidence_origin=origin,  # type: ignore[arg-type]
    )


def _claim(
    claim_id: str = "c1",
    *,
    source_id: str = "s1",
    status: str = "verified",
    claim_type: str = "stable",
    domain: str = "software",
    verified_at: datetime | None = None,
    ttl: int | None = None,
    normalized_key: str | None = None,
    statement: str = "该软件支持结构化输出。",
    scope: str = "global",
) -> KnowledgeClaim:
    return KnowledgeClaim(
        claim_id=claim_id,
        statement=statement,
        normalized_key=normalized_key or normalize_claim_key(statement),
        topic="测试主题",
        domain=domain,
        claim_type=claim_type,  # type: ignore[arg-type]
        status=status,  # type: ignore[arg-type]
        confidence=0.9,
        last_verified_at=verified_at or NOW,
        evidence_refs=[source_id],
        freshness_policy_days=ttl,
        scope=scope,
    )


def _script(*, claim_refs: list[str] | None = None, source_refs: list[str] | None = None) -> Script:
    return Script(
        title="测试", hook="为什么？", thesis="验证 grounding。", target_audience="测试者",
        target_duration_sec=30,
        sections=[ScriptSection(
            id="facts", purpose="事实", narration="当前 API 价格为 1 元。", key_visual_hint="卡片",
            claim_refs=claim_refs or [], source_refs=source_refs or [],
        )],
        conclusion="结束。",
    )


def test_source_schema() -> None:
    source = _source()
    assert source.source_id == "s1"
    assert source.source_type == "official"
    with pytest.raises(ValidationError):
        EvidenceSource(source_id="bad", url="file:///bad", title="x", publisher="x", domain="x")


def test_claim_schema() -> None:
    claim = _claim()
    assert claim.version == 1
    with pytest.raises(ValidationError):
        _claim(claim_type="time_sensitive", ttl=None)
    with pytest.raises(ValidationError):
        _claim(claim_type="opinion", status="verified")


def test_claim_requires_source_for_verified() -> None:
    with pytest.raises(ValidationError):
        KnowledgeClaim(
            claim_id="x", statement="事实", normalized_key="fact", topic="t", domain="d",
            claim_type="stable", status="verified", confidence=0.8,
        )


def test_source_quality_breakdown() -> None:
    evaluation = SourceQualityEvaluator().evaluate(_source(), topic_domain="software", corroborating_count=1)
    assert evaluation.score > 0.7
    assert evaluation.breakdown.primary_official_proximity == 1
    assert set(evaluation.weights) == set(evaluation.breakdown.model_dump())


def test_claim_extraction_requires_refs() -> None:
    result = ResearchResult(topic="t", summary="s", key_points=["当前版本支持 15 秒。"], sources=[])
    candidate = ClaimExtractor().extract(result, domain="software")[0]
    assert not candidate.supported
    assert candidate.unsupported_reason


def test_claim_verification(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path / "knowledge")
    store.add_source(_source())
    candidate = ClaimCandidate(
        statement="当前版本支持 15 秒。", normalized_key="duration", topic="t", domain="software",
        claim_type="time_sensitive", source_refs=["s1"], time_sensitive=True, supported=True,
    )
    claim, result = ClaimVerifier(store).verify_candidate(candidate, now=NOW)
    assert claim is not None
    assert result.status == "verified"
    assert result.supporting_sources == ["s1"]


def test_conflict_detection(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path / "knowledge")
    store.add_source(_source("s1"))
    store.add_source(_source("s2"))
    first = _claim("c1", normalized_key="same-parameter", statement="参数为 10。")
    second = _claim("c2", source_id="s2", normalized_key="same-parameter", statement="参数为 15。")
    store.add_claim(first)
    store.add_claim(second)
    conflicts = ConflictDetector(store).detect_for(second)
    assert conflicts
    assert store.get_claim("c1").status == "conflicted"
    assert store.get_claim("c2").status == "conflicted"


def test_freshness_policy_by_type() -> None:
    policy = FreshnessPolicy(software_days=14, pricing_days=3, stable_definition_days=365)
    old = NOW - timedelta(days=10)
    pricing = _claim("pricing", claim_type="time_sensitive", domain="pricing", verified_at=old, ttl=3)
    definition = _claim("definition", claim_type="definition", domain="science", verified_at=old)
    assert policy.assess(pricing, now=NOW).state == "stale"
    assert policy.assess(definition, now=NOW).state == "fresh"


def test_stale_claim_blocked_in_script(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path / "knowledge")
    store.add_source(_source())
    claim = _claim("stale", claim_type="time_sensitive", domain="pricing", verified_at=NOW - timedelta(days=8), ttl=3)
    store.add_claim(claim)
    report = GroundingChecker(store, FreshnessPolicy(pricing_days=3)).check(
        _script(claim_refs=[claim.claim_id]), run_id="run", factual_section_ids={"facts"}
    )
    assert not report.passed
    assert claim.claim_id in report.stale_claim_refs


def test_supersession_versioning(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path / "knowledge")
    store.add_source(_source("s1"))
    store.add_source(_source("s2"))
    old = _claim("old", normalized_key="duration", statement="最大 10 秒。")
    new = _claim("new", source_id="s2", normalized_key="duration", statement="最大 15 秒。")
    store.add_claim(old)
    old, new = store.supersede(old.claim_id, new)
    assert old.status == "superseded"
    assert new.version == 2
    assert new.supersedes_claim_id == "old"


def test_old_run_keeps_source_snapshot(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path / "knowledge")
    store.add_source(_source("s1"))
    store.add_source(_source("s2"))
    old = _claim("old", normalized_key="duration", statement="最大 10 秒。")
    store.add_claim(old)
    paths = store.snapshot_run(tmp_path / "runs" / "old_run", [old])
    store.supersede("old", _claim("new", source_id="s2", normalized_key="duration", statement="最大 15 秒。"))
    assert '"status": "verified"' in Path(paths["claims_used"]).read_text(encoding="utf-8")


def _assert_origin_not_promoted(tmp_path: Path, origin: str) -> None:
    store = KnowledgeStore(tmp_path / origin)
    store.add_source(_source(origin, origin=origin))
    candidate = ClaimCandidate(
        statement="候选事实", normalized_key="candidate", topic="t", domain="d",
        source_refs=[origin], supported=True,
    )
    claim, result = ClaimVerifier(store).verify_candidate(candidate)
    assert claim is None
    assert result.status == "unknown"


def test_trend_not_promoted_to_fact(tmp_path: Path) -> None:
    _assert_origin_not_promoted(tmp_path, "trend")


def test_simulation_not_promoted_to_fact(tmp_path: Path) -> None:
    _assert_origin_not_promoted(tmp_path, "simulation")


def test_feedback_not_promoted_to_fact(tmp_path: Path) -> None:
    _assert_origin_not_promoted(tmp_path, "feedback")


def test_grounding_report(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path / "knowledge")
    store.add_source(_source())
    claim = store.add_claim(_claim())
    report = GroundingChecker(store, FreshnessPolicy()).check(
        _script(claim_refs=[claim.claim_id]), run_id="run", factual_section_ids={"facts"}
    )
    assert report.passed
    assert report.citation_coverage == 1
    assert report.supported_sections == ["facts"]


def test_knowledge_context_selector(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path / "knowledge")
    store.add_source(_source())
    store.add_claim(_claim())
    stale = _claim("stale", verified_at=NOW - timedelta(days=20), claim_type="time_sensitive", ttl=3)
    store.add_claim(stale)
    context = KnowledgeContextSelector(store, FreshnessPolicy()).select("测试主题", role="writer")
    assert [item.claim_id for item in context.claims] == ["c1"]
    assert any("stale" in warning for warning in context.warnings)


def test_knowledge_gap(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path / "knowledge")
    gap = KnowledgeGapDetector(store).create(
        "当前价格？", affected_runs=["run"], urgency="critical", required_source_types=["official"]
    )
    assert gap.status == "open"
    assert store.list_gaps()[0].gap_id == gap.gap_id


def test_research_task_stop_condition(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path / "knowledge")
    task = ResearchTaskPlanner(store, max_sources=2, max_rounds=2).create("问题？")
    assert task.max_sources == 2
    assert task.stop_condition
    with pytest.raises(ValidationError):
        ResearchTask(
            task_id="bad", question="q", max_sources=1, max_rounds=1,
            source_refs=["a", "b"], rounds_completed=2,
        )


def test_knowledge_tick_idempotent(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path / "knowledge")
    store.add_source(_source())
    store.add_claim(_claim("stale", claim_type="time_sensitive", domain="pricing", verified_at=NOW - timedelta(days=8), ttl=3))
    service = KnowledgeMaintenanceService(store, FreshnessPolicy(pricing_days=3))
    first = service.tick()
    snapshots_after_first = list((store.root / "snapshots").glob("*.json"))
    second = service.tick()
    assert first.task_ids == second.task_ids
    assert len(store.list_tasks()) == 1
    assert list((store.root / "snapshots").glob("*.json")) == snapshots_after_first


def test_knowledge_qa(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path / "knowledge")
    store.add_source(_source("trend", origin="trend"))
    store.add_claim(_claim("bad", source_id="trend", status="provisional"))
    report = KnowledgeQA(store, FreshnessPolicy()).run()
    assert not report.passed
    assert "source_boundary_violation" in {item.code for item in report.issues}


def test_h3_local_observation_not_global_fact(tmp_path: Path) -> None:
    config = make_config(tmp_path / "runs")
    config.knowledge.root_dir = tmp_path / "knowledge"
    service = KnowledgeService(config)
    result = demo_d_h3_observation(
        service,
        Path(__file__).parents[1] / "evaluation" / "capability_evaluation_h3_runtime.json",
    )
    assert result["scope"] == "current_machine"
    assert result["source_origin"] == "system_observation"
    assert result["global_fact"] is False
    assert result["mock"] is False


def test_research_to_knowledge_rejects_mock(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path / "knowledge")
    result = ResearchResult(
        topic="t", summary="s", key_points=["当前版本支持 15 秒。"],
        sources=[Source(
            id="mock", title="mock", url="https://example.invalid/mock", publisher="mock",
            domain="software", retrieved_at=NOW, evidence_origin="mock",
        )],
    )
    ingested = ResearchKnowledgePipeline(store).ingest(result, domain="software")
    assert not ingested.claim_ids
    assert ingested.unsupported_claims


def test_web_research_captures_source_metadata() -> None:
    class Adapter:
        async def search(self, question: str, *, max_results: int) -> list[dict[str, object]]:
            return [{
                "source_id": "official-doc",
                "url": "https://docs.example.invalid/model",
                "title": "Model documentation",
                "publisher": "Example",
                "author": "Docs Team",
                "published_at": NOW.isoformat(),
                "snippet": "当前模型版本支持结构化输出。",
                "source_type": "documentation",
            }]

    result = asyncio.run(WebResearchProvider(Adapter()).research("model", max_sources=3))
    source = result.sources[0]
    assert source.evidence_origin == "web"
    assert source.published_at is not None
    assert source.content_hash
    assert source.source_type == "documentation"


def test_supervisor_blocks_on_high_priority_knowledge_gap(tmp_path: Path) -> None:
    config = make_config(tmp_path / "runs")
    config.supervisor.root_dir = tmp_path / "supervisor"
    supervisor = AutonomousSupervisor(config)
    blocked = supervisor.knowledge_readiness("新主题", run_id="run-1")
    assert blocked["blocked"]
    assert blocked["dispatch"] is False
    service = KnowledgeService(config)
    gap = service.store.list_gaps()[0]
    gap.status = "resolved"
    service.store.add_gap(gap)
    service.store.add_source(_source())
    service.store.add_claim(_claim())
    ready = supervisor.knowledge_readiness("测试主题")
    assert ready["ready"]


def test_workflow_has_controlled_research_verification_writer_adapters() -> None:
    registry = WorkflowExecutorRegistry.controlled_defaults()
    assert registry.get("capability", "research").execution_layer == "studio"
    assert registry.get("capability", "claim_verification").execution_layer == "knowledge"
    assert registry.get("capability", "writer").execution_layer == "studio"
