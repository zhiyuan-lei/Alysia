from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from alysia.creator import (
    ApprovalStatus,
    Claim,
    ClaimClassification,
    ClaimExtractor,
    CreatorJob,
    CreatorJobResearchIntegrator,
    CreatorJobStore,
    EvidenceStatus,
    GroundingService,
    PublishStatus,
    ResearchArtifactStore,
    ResearchLimits,
    ResearchSource,
    SourceReliability,
    TopicCandidate,
    TopicDiscoveryService,
    TopicRanker,
)
from alysia.providers.trends.mock import MockTrendProvider


def make_job(*, topic: str = "old topic", created_at: datetime | None = None) -> CreatorJob:
    now = created_at or datetime.now().astimezone()
    return CreatorJob.new(
        created_at=now,
        updated_at=now,
        topic=topic,
        topic_source="human",
        topic_score=50,
    )


def make_candidate(title: str = "Reliable creator loops", **changes: object) -> TopicCandidate:
    values: dict[str, object] = {
        "summary": "A grounded candidate",
        "relevance": 0.9,
        "freshness": 0.8,
        "evidence_quality": 0.8,
        "audience_fit": 0.9,
        "novelty": 0.9,
        "production_cost": 0.3,
        "safety_risk": 0.1,
    }
    values.update(changes)
    return TopicCandidate.create(title=title, source="fixture", source_type="testing", **values)


def make_source(
    *,
    url: str = "https://example.com/research",
    reliability: SourceReliability = SourceReliability.PRIMARY,
    content: str = "Documented evidence.",
    metadata: dict[str, object] | None = None,
    limits: ResearchLimits | None = None,
) -> ResearchSource:
    return ResearchSource.from_content(
        url=url,
        title="Research source",
        publisher="Example publisher",
        source_type="web",
        content=content,
        reliability=reliability,
        metadata=metadata,
        limits=limits,
    )


def test_discovery_creates_structured_candidates_and_scores_explainably() -> None:
    discovery = TopicDiscoveryService()
    trends = MockTrendProvider().gather(max_items=2, freshness_days=7)

    candidates = discovery.discover_from_sources(trends)
    result = discovery.rank(candidates)

    assert len(candidates) == 2
    assert candidates[0].topic_id.startswith("topic_")
    assert result.accepted[0].score > 0
    assert result.accepted[0].score_breakdown["total"] == result.accepted[0].score
    assert "evidence_quality" in result.accepted[0].score_breakdown


def test_topic_ranking_is_deterministic_and_rejects_high_safety_risk() -> None:
    ranker = TopicRanker()
    high = make_candidate("High relevance")
    low = make_candidate("Low relevance", relevance=0.2, audience_fit=0.2, novelty=0.2)
    unsafe = make_candidate("Unsafe instructions", safety_risk=0.95)

    result = ranker.rank([low, unsafe, high])

    assert [item.title for item in result.accepted] == ["High relevance", "Low relevance"]
    assert result.rejected[0].title == "Unsafe instructions"
    assert "safety_risk" in (result.rejected[0].rejection_reason or "")


@pytest.mark.parametrize(
    ("candidate_title", "history_topic", "expected_method"),
    [
        ("Creator loop reliability", "Creator loop reliability", "exact"),
        ("Alpha-22: Creator Loop", "alpha22 creator loop", "normalized"),
        ("AI Agent 长任务可靠性检查", "AI Agent 长任务可靠性恢复", "recent"),
    ],
)
def test_duplicate_detection_covers_exact_normalized_and_recent(
    candidate_title: str,
    history_topic: str,
    expected_method: str,
) -> None:
    result = TopicRanker().rank([make_candidate(candidate_title)], [make_job(topic=history_topic)])

    assert result.rejected
    assert any(f":{expected_method}:" in ref for ref in result.rejected[0].duplicate_refs)


def test_old_similar_topic_is_recorded_as_semantic_like_duplicate() -> None:
    old = make_job(
        topic="AI Agent 长任务可靠性恢复",
        created_at=datetime.now().astimezone() - timedelta(days=365),
    )
    result = TopicRanker().rank([make_candidate("AI Agent 长任务可靠性检查")], [old])
    candidate = (result.accepted + result.rejected)[0]

    assert any(":semantic_like:" in ref for ref in candidate.duplicate_refs)


def test_research_source_serializes_and_claims_reference_source() -> None:
    source = make_source()
    restored = ResearchSource.model_validate_json(source.model_dump_json())
    claims = ClaimExtractor().extract(
        source,
        ["The documented behavior is reproducible."],
        claim_type=ClaimClassification.VERIFIED_FACT,
    )

    assert restored == source
    assert claims[0].source_refs == [source.source_id]
    assert claims[0].claim_id.startswith("claim_")


def test_long_source_is_redacted_truncated_and_externalized(tmp_path: Path) -> None:
    limits = ResearchLimits(max_excerpt_chars=64, max_artifact_chars=256, max_metadata_bytes=128)
    secret = "very-secret-token"
    content = f"authorization: Bearer {secret}\n" + "x" * 1_000
    source = make_source(
        content=content,
        metadata={"api_key": secret, "oversized": "y" * 500},
        limits=limits,
    )
    store = ResearchArtifactStore(tmp_path / "alpha22" / "research", limits=limits)
    path = store.save_source(source, content)
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert "[TRUNCATED" in source.content_excerpt
    assert secret not in source.model_dump_json()
    assert secret not in path.read_text(encoding="utf-8")
    assert len(payload["content"]) <= limits.max_artifact_chars
    assert payload["artifact_truncated"] is True
    assert source.metadata["truncated"] is True


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "http://localhost/admin",
        "http://127.0.0.1/admin",
        "http://10.0.0.1/internal",
        "ftp://example.com/file",
        "https://user:password@example.com/research",
        "https://example.com/research?api_key=secret",
    ],
)
def test_research_url_reuses_network_security_boundary(url: str) -> None:
    with pytest.raises((ValueError, ValidationError), match="URL|network policy|credential"):
        make_source(url=url)


def test_grounding_supports_fact_with_evidence_but_not_at_full_certainty() -> None:
    source = make_source(reliability=SourceReliability.OFFICIAL)
    claim = Claim.create(
        text="The official documentation describes the feature.",
        claim_type=ClaimClassification.VERIFIED_FACT,
        source_refs=[source.source_id],
        confidence=0.99,
    )

    grounded = GroundingService().ground([claim], [source]).claims[0]

    assert grounded.claim_type == ClaimClassification.VERIFIED_FACT
    assert grounded.evidence_status == EvidenceStatus.SUPPORTED
    assert grounded.confidence == 0.85


def test_fact_without_evidence_is_insufficient_and_cannot_be_prevalidated() -> None:
    claim = Claim.create(text="An unsupported fact.", claim_type=ClaimClassification.VERIFIED_FACT, confidence=0.9)

    grounded = GroundingService().ground([claim], []).claims[0]

    assert grounded.evidence_status == EvidenceStatus.INSUFFICIENT_EVIDENCE
    with pytest.raises(ValidationError, match="requires source_refs"):
        Claim(
            claim_id="claim_invalid",
            text="An unsupported fact.",
            claim_type=ClaimClassification.VERIFIED_FACT,
            confidence=0.9,
            evidence_status=EvidenceStatus.SUPPORTED,
        )


def test_inference_stays_inference_when_supported() -> None:
    source = make_source()
    claim = Claim.create(
        text="This evidence suggests a likely outcome.",
        claim_type=ClaimClassification.INFERENCE,
        source_refs=[source.source_id],
        confidence=0.7,
    )

    grounded = GroundingService().ground([claim], [source]).claims[0]

    assert grounded.claim_type == ClaimClassification.INFERENCE
    assert grounded.evidence_status == EvidenceStatus.SUPPORTED


def test_conflicting_sources_are_not_silently_resolved() -> None:
    supporting = make_source(url="https://example.com/support")
    contradicting = make_source(url="https://example.org/contradict")
    claim = Claim.create(
        text="The measured result increased.",
        claim_type=ClaimClassification.VERIFIED_FACT,
        source_refs=[supporting.source_id, contradicting.source_id],
        confidence=0.8,
    )

    grounded = GroundingService().ground(
        [claim],
        [supporting, contradicting],
        contradicting_source_refs={claim.claim_id: [contradicting.source_id]},
    )

    assert grounded.claims[0].evidence_status == EvidenceStatus.CONFLICTING
    assert grounded.uncertainties


def test_unavailable_source_produces_insufficient_evidence() -> None:
    source = make_source(metadata={"available": False})
    claim = Claim.create(
        text="The unavailable page proves this.",
        claim_type=ClaimClassification.VERIFIED_FACT,
        source_refs=[source.source_id],
        confidence=0.8,
    )

    grounded = GroundingService().ground([claim], [source]).claims[0]

    assert grounded.evidence_status == EvidenceStatus.INSUFFICIENT_EVIDENCE
    assert any("unavailable_sources" in note for note in grounded.notes)


def test_creative_content_needs_no_factual_source() -> None:
    claim = Claim.create(
        text="Open with an imagined conversation.",
        claim_type=ClaimClassification.CREATIVE_CONTENT,
        confidence=0.8,
    )

    grounded = GroundingService().ground([claim], []).claims[0]

    assert grounded.evidence_status == EvidenceStatus.SUPPORTED
    assert grounded.source_refs == []


def test_unknown_source_reliability_is_only_partial_support() -> None:
    source = make_source(reliability=SourceReliability.UNKNOWN)
    claim = Claim.create(
        text="A community page reports the behavior.",
        claim_type=ClaimClassification.UNKNOWN,
        source_refs=[source.source_id],
        confidence=0.9,
    )

    grounded = GroundingService().ground([claim], [source]).claims[0]

    assert grounded.evidence_status == EvidenceStatus.PARTIALLY_SUPPORTED
    assert grounded.confidence == 0.2


def test_grounded_research_updates_existing_creator_job_and_preserves_states(tmp_path: Path) -> None:
    store = CreatorJobStore(tmp_path / "creator_jobs")
    job = make_job(topic="seed")
    store.create(job)
    candidate = TopicRanker().rank([make_candidate("Grounded creator systems")]).accepted[0]
    source = make_source()
    claims = [
        Claim.create(
            text="The primary source documents the system.",
            claim_type=ClaimClassification.VERIFIED_FACT,
            source_refs=[source.source_id],
            confidence=0.9,
        ),
        Claim.create(
            text="A remaining unknown.",
            claim_type=ClaimClassification.UNKNOWN,
            confidence=0.4,
        ),
    ]
    grounding = GroundingService().ground(claims, [source])
    integrator = CreatorJobResearchIntegrator(
        store,
        ResearchArtifactStore(tmp_path / "alpha22" / "research"),
    )

    updated = integrator.apply(
        job.job_id,
        selected_topic=candidate,
        sources=[source],
        grounding=grounding,
        raw_contents={source.source_id: "Full bounded research artifact."},
    )
    loaded = store.load(job.job_id)

    assert loaded == updated
    assert loaded.topic == candidate.title
    assert loaded.research_sources[0].source_id == source.source_id
    assert loaded.research_sources[0].evidence_path.is_file()
    assert loaded.claims[0].source_refs == [source.source_id]
    assert loaded.uncertainties == grounding.uncertainties
    assert loaded.current_revision == 2
    assert store.revision_path(job.job_id, 1).is_file()
    assert loaded.approval_status == ApprovalStatus.DRAFT
    assert loaded.publish_status == PublishStatus.NOT_READY

