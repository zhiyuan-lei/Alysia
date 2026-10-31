from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from alysia.creator import (
    ClaimClassification,
    CreatorClaimTrace,
    CreatorJob,
    CreatorJobStore,
    EvidenceStatus,
    PublishMode,
    ResearchSourceTrace,
)
from alysia.creator.memory import (
    CreatorMemoryGate,
    MemoryCandidate,
    MemoryCandidateStatus,
    MemoryType,
)
from alysia.creator.observation import (
    ContentObservation,
    FakeMetricsProvider,
    ManualMetricsProvider,
    MetricAvailability,
    MetricsSnapshot,
    ObservationService,
    ObservationSourceType,
    ObservationStore,
)
from alysia.creator.publisher import PublishRecord, PublishRecordStatus, PublisherStore, RemotePublishState
from alysia.creator.reflection import (
    CreatorReflection,
    CreatorReflectionService,
    ObservedFact,
    ReflectionHypothesis,
    ReflectionInterpretation,
    ReflectionStatus,
    ReflectionStore,
)
from alysia.learning.memory import MemoryStore
from alysia.security.audit import AuditLog
from tests.test_creator_publisher import PublisherFixture


def metrics(
    *,
    views: int | None = 100,
    likes: int | None = 10,
    comments: int | None = 2,
    favorites: int | None = 3,
    shares: int | None = 1,
    followers_delta: int | None = None,
) -> MetricsSnapshot:
    values = {
        "views": views,
        "likes": likes,
        "comments": comments,
        "favorites": favorites,
        "shares": shares,
        "followers_delta": followers_delta,
    }
    return MetricsSnapshot(
        **values,
        availability={
            name: MetricAvailability.AVAILABLE if value is not None else MetricAvailability.UNAVAILABLE
            for name, value in values.items()
        },
    )


class Step6Fixture:
    def __init__(self, tmp_path: Path) -> None:
        self.publish_fixture = PublisherFixture(
            tmp_path,
            mode=PublishMode.LIVE,
            live_enabled=True,
        )
        self.publish_fixture.prepare()
        self.publish_record = self.publish_fixture.publisher.publish(
            self.publish_fixture.request,
            confirmation=self.publish_fixture.confirm(),
        )
        self.jobs = self.publish_fixture.jobs
        self.job = self.jobs.load(self.publish_fixture.job.job_id)
        self.audit = self.publish_fixture.audit
        self.observations = ObservationStore(tmp_path / "creator_learning", environment="test")
        self.observation_service = ObservationService(
            jobs=self.jobs,
            publishes=self.publish_fixture.publisher_store,
            observations=self.observations,
            audit=self.audit,
        )
        self.reflections = ReflectionStore(tmp_path / "creator_learning", environment="test")
        self.reflection_service = CreatorReflectionService(
            jobs=self.jobs,
            observations=self.observations,
            reflections=self.reflections,
            audit=self.audit,
        )
        self.memory_gate = CreatorMemoryGate(
            tmp_path / "memory",
            environment="test",
            jobs=self.jobs,
            reflections=self.reflections,
            audit=self.audit,
        )

    def observe(
        self,
        snapshot: MetricsSnapshot | None = None,
        *,
        observed_at: datetime | None = None,
    ) -> ContentObservation:
        provider = FakeMetricsProvider(snapshot or metrics())
        return self.observation_service.collect(
            self.publish_record.publish_id,
            provider,
            observed_at=observed_at,
        )

    def reflect(self, *, observation: ContentObservation | None = None) -> CreatorReflection:
        observation = observation or self.observe()
        ref = self.observations.reference(observation)
        return self.reflection_service.create(
            job_id=self.job.job_id,
            job_revision=self.job.current_revision,
            platform_content_id=self.publish_record.platform_content_id or "",
            interpretations=[
                ReflectionInterpretation(
                    statement="The packaging may have influenced engagement.",
                    confidence=0.35,
                    evidence_refs=[ref],
                    alternative_explanations=["topic timing", "platform distribution"],
                )
            ],
            hypotheses=[
                ReflectionHypothesis(
                    statement="A clearer title may improve future engagement.",
                    confidence=0.25,
                    evidence_refs=[ref],
                    alternative_explanations=["thumbnail", "audience fit", "insufficient sample"],
                )
            ],
            uncertainties=["A single TEST_ONLY observation cannot establish causality."],
            what_worked=["The approved artifact completed the test observation loop."],
            what_did_not_work=[],
            recommended_changes=["Test one packaging variable in a future controlled run."],
            confidence=0.4,
        )


def test_metrics_missing_is_not_zero_and_zero_views_is_safe() -> None:
    unavailable = metrics(views=None, likes=None, comments=None, favorites=None, shares=None)
    zero = metrics(views=0, likes=0, comments=0, favorites=0, shares=0)

    assert unavailable.views is None
    assert unavailable.availability["views"] == MetricAvailability.UNAVAILABLE
    assert zero.views == 0
    assert zero.availability["views"] == MetricAvailability.AVAILABLE
    assert zero.observed_at is not None
    assert zero.derived().like_rate is None
    assert "NaN" not in zero.derived().model_dump_json()
    assert "Infinity" not in zero.derived().model_dump_json()


def test_derived_rates_and_growth_recompute_from_raw_snapshots() -> None:
    first = metrics(views=100, likes=10, comments=5, favorites=2, shares=1)
    second = metrics(views=150, likes=30, comments=6, favorites=3, shares=3)

    derived = second.derived(first)

    assert derived.like_rate == pytest.approx(0.2)
    assert derived.comment_rate == pytest.approx(0.04)
    assert derived.favorite_rate == pytest.approx(0.02)
    assert derived.share_rate == pytest.approx(0.02)
    assert derived.growth_delta == 50
    assert second.raw()["views"] == 150


def test_observation_store_latest_history_and_content_query_preserve_timestamps(tmp_path: Path) -> None:
    store = ObservationStore(tmp_path, environment="test")
    now = datetime.now().astimezone()
    newer = ContentObservation(
        job_id="creator_0000000000000001",
        job_revision=1,
        platform_content_id="TEST_ONLY_CONTENT_1",
        source_type=ObservationSourceType.TEST_FIXTURE,
        observed_at=now,
        metrics=metrics(views=20),
        raw_snapshot_ref="test:newer",
    )
    older = ContentObservation(
        job_id=newer.job_id,
        job_revision=1,
        platform_content_id=newer.platform_content_id,
        source_type=ObservationSourceType.TEST_FIXTURE,
        observed_at=now - timedelta(hours=1),
        metrics=metrics(views=10),
        raw_snapshot_ref="test:older",
    )
    store.save(newer)
    store.save(older)

    assert store.load(older.observation_id or "") == older
    assert store.history(newer.job_id or "") == [older, newer]
    assert store.latest(newer.job_id or "") == newer
    assert store.by_content_id(newer.platform_content_id or "") == [older, newer]


def test_observation_service_updates_compact_creator_job_only(tmp_path: Path) -> None:
    fixture = Step6Fixture(tmp_path)
    revision = fixture.job.current_revision

    observation = fixture.observe(observed_at=datetime.now().astimezone())
    job = fixture.jobs.load(fixture.job.job_id)

    assert job.current_revision == revision
    assert job.metrics == []
    assert len(job.observation_refs) == 1
    assert job.latest_metrics_summary["observation_id"] == observation.observation_id
    assert job.latest_metrics_summary["raw"]["views"] == 100
    assert observation.metrics.observed_at == observation.observed_at
    assert fixture.observations.history(job.job_id) == [observation]
    assert [event.action for event in fixture.audit.list()][-2:] == [
        "OBSERVATION_RECORDED",
        "METRICS_UPDATED",
    ]


def test_wrong_content_id_and_revision_are_rejected(tmp_path: Path) -> None:
    fixture = Step6Fixture(tmp_path)
    valid = FakeMetricsProvider(metrics()).fetch_metrics(fixture.publish_record)
    wrong_content = valid.model_copy(update={"platform_content_id": "TEST_ONLY_WRONG", "content_id": "TEST_ONLY_WRONG"})
    wrong_revision = valid.model_copy(update={"job_revision": valid.job_revision + 1})

    with pytest.raises(ValueError, match="PublishRecord"):
        fixture.observation_service.record(wrong_content)
    with pytest.raises(ValueError, match="revision"):
        fixture.observation_service.record(wrong_revision)


def test_test_fixture_and_manual_real_sources_cannot_be_misrepresented(tmp_path: Path) -> None:
    fixture = Step6Fixture(tmp_path)
    observation = FakeMetricsProvider(metrics()).fetch_metrics(fixture.publish_record)
    production = ObservationStore(tmp_path / "learning", environment="production")
    with pytest.raises(ValueError, match="TEST_FIXTURE"):
        production.save(observation)
    with pytest.raises(ValueError, match="test identity"):
        ContentObservation(
            job_id=observation.job_id,
            job_revision=observation.job_revision,
            platform_content_id=observation.platform_content_id,
            source_type=ObservationSourceType.REAL_PLATFORM,
            observed_at=observation.observed_at,
            metrics=observation.metrics,
        )

    real_record = PublishRecord(
        publish_id="publish_0000000000000099",
        request_id="manual_metrics_request",
        job_id=fixture.job.job_id,
        job_revision=fixture.job.current_revision,
        platform="bilibili",
        mode=PublishMode.LIVE,
        status=PublishRecordStatus.PUBLISHED,
        platform_content_id="REAL_CONTENT_ID_FOR_MANUAL_IMPORT",
        remote_state=RemotePublishState.PUBLISHED,
    )
    manual = ManualMetricsProvider(
        metrics(),
        actor="human:metrics-importer",
        raw_snapshot_ref="manual-evidence:receipt-1",
    ).fetch_metrics(real_record)
    assert manual.source_type == ObservationSourceType.MANUAL_IMPORT
    assert manual.metadata["actor"] == "human:metrics-importer"
    with pytest.raises(PermissionError):
        ManualMetricsProvider(metrics(), actor="agent", raw_snapshot_ref="manual:test")


def test_reflection_requires_observation_and_persists_compact_reference(tmp_path: Path) -> None:
    fixture = Step6Fixture(tmp_path)
    with pytest.raises(ValueError, match="at least one"):
        fixture.reflection_service.create(
            job_id=fixture.job.job_id,
            job_revision=fixture.job.current_revision,
            platform_content_id=fixture.publish_record.platform_content_id or "",
        )

    reflection = fixture.reflect()
    job = fixture.jobs.load(fixture.job.job_id)

    assert reflection.status == ReflectionStatus.COMPLETE
    assert reflection.observed_facts
    assert all(item.classification == "OBSERVED_FACT" for item in reflection.observed_facts)
    assert reflection.interpretations[0].classification == "MODEL_INTERPRETATION"
    assert reflection.hypotheses[0].classification == "HYPOTHESIS"
    assert reflection.interpretations[0].alternative_explanations
    assert reflection.uncertainties
    assert set(reflection.observation_refs).issubset(reflection.evidence_refs)
    assert fixture.reflections.load(reflection.reflection_id or "") == reflection
    assert fixture.reflections.history(job.job_id) == [reflection]
    assert job.reflection_ref == fixture.reflections.reference(reflection)
    assert job.reflection is None


def test_insufficient_observation_produces_limited_reflection(tmp_path: Path) -> None:
    fixture = Step6Fixture(tmp_path)
    observation = fixture.observe(
        metrics(views=None, likes=None, comments=None, favorites=None, shares=None)
    )

    reflection = fixture.reflection_service.create(
        job_id=fixture.job.job_id,
        job_revision=fixture.job.current_revision,
        platform_content_id=observation.platform_content_id or "",
        recommended_changes=["Collect more observations before changing strategy."],
        confidence=0.9,
    )

    assert reflection.status == ReflectionStatus.INSUFFICIENT_OBSERVATION
    assert reflection.observed_facts == []
    assert reflection.uncertainties
    assert reflection.confidence <= 0.5


def test_interpretation_requires_known_evidence_and_alternatives(tmp_path: Path) -> None:
    fixture = Step6Fixture(tmp_path)
    fixture.observe()

    with pytest.raises(ValueError, match="unknown evidence"):
        fixture.reflection_service.create(
            job_id=fixture.job.job_id,
            job_revision=fixture.job.current_revision,
            platform_content_id=fixture.publish_record.platform_content_id or "",
            interpretations=[
                ReflectionInterpretation(
                    statement="Unsupported causal story.",
                    confidence=0.8,
                    evidence_refs=["observation:test:unknown"],
                    alternative_explanations=["unknown"],
                )
            ],
            uncertainties=["The statement is not established."],
        )
    with pytest.raises(ValueError):
        ReflectionHypothesis(
            statement="One explanation only.",
            confidence=0.3,
            evidence_refs=["evidence"],
            alternative_explanations=[],
        )


def test_episodic_candidate_is_accepted_with_provenance_and_no_raw_history(tmp_path: Path) -> None:
    fixture = Step6Fixture(tmp_path)
    reflection = fixture.reflect()
    candidate = fixture.memory_gate.create_candidate(
        reflection_id=reflection.reflection_id or "",
        memory_type=MemoryType.EPISODIC,
        statement="This TEST_ONLY CreatorJob completed the observation and reflection loop.",
        confidence=0.8,
        importance=0.7,
    )

    accepted = fixture.memory_gate.evaluate(candidate.candidate_id or "")

    assert accepted.status == MemoryCandidateStatus.ACCEPTED
    assert accepted.evidence_refs
    assert accepted.job_id == reflection.job_id
    assert accepted.reflection_id == reflection.reflection_id
    assert accepted.candidate_id in fixture.reflections.load(reflection.reflection_id or "").memory_candidates
    episodes = MemoryStore(tmp_path / "memory" / "test").list_episodes()
    assert len(episodes) == 1
    assert episodes[0].source == "testing"
    assert "views" not in episodes[0].metrics_summary
    assert fixture.jobs.load(fixture.job.job_id).memory_refs == [
        f"memory:test:{accepted.candidate_id}"
    ]


def make_memory_reflection(
    *,
    jobs: CreatorJobStore,
    reflections: ReflectionStore,
    index: int,
) -> CreatorReflection:
    now = datetime.now().astimezone()
    job = CreatorJob.new(
        created_at=now,
        updated_at=now,
        topic=f"TEST_ONLY semantic job {index}",
        topic_source="test",
        topic_score=50,
        research_sources=[
            ResearchSourceTrace(
                source_id=f"source_{index}",
                source="https://example.com/test",
                retrieved_at=now,
                claim="Test-only semantic evidence.",
                confidence=0.5,
                source_type="test",
            )
        ],
        claims=[
            CreatorClaimTrace(
                claim_id=f"claim_{index}",
                claim="Test-only semantic evidence.",
                classification=ClaimClassification.VERIFIED_FACT,
                confidence=0.5,
                source_refs=[f"source_{index}"],
                evidence_status=EvidenceStatus.SUPPORTED,
            )
        ],
        latest_metrics_summary={"TEST_ONLY": True},
        observation_refs=[f"observation:test:TEST_ONLY_{index}"],
    )
    jobs.create(job)
    reflection = CreatorReflection(
        job_id=job.job_id,
        job_revision=job.current_revision,
        platform_content_id=f"TEST_ONLY_CONTENT_{index}",
        attempt_summary="TEST_ONLY semantic threshold fixture.",
        observed_facts=[
            ObservedFact(
                statement=f"views={index + 1} observed in TEST_ONLY fixture.",
                evidence_refs=[f"observation:test:TEST_ONLY_{index}"],
                observed_at=now,
            )
        ],
        uncertainties=["Synthetic observations do not establish a production rule."],
        evidence_refs=[f"observation:test:TEST_ONLY_{index}"],
        observation_refs=[f"observation:test:TEST_ONLY_{index}"],
        confidence=0.8,
        metadata={"test_only": True, "source_types": ["TEST_FIXTURE"]},
    )
    reflections.save(reflection)
    return reflection


def test_semantic_gate_counts_distinct_jobs_not_same_job_snapshots(tmp_path: Path) -> None:
    jobs = CreatorJobStore(tmp_path / "jobs")
    reflections = ReflectionStore(tmp_path / "learning", environment="test")
    audit = AuditLog(tmp_path / "audit" / "memory.jsonl")
    gate = CreatorMemoryGate(
        tmp_path / "memory",
        environment="test",
        jobs=jobs,
        reflections=reflections,
        audit=audit,
        semantic_support_threshold=3,
    )
    reflection = make_memory_reflection(jobs=jobs, reflections=reflections, index=1)
    first = gate.create_candidate(
        reflection_id=reflection.reflection_id or "",
        memory_type=MemoryType.SEMANTIC,
        statement="A controlled packaging experiment may be worth testing.",
        confidence=0.8,
    )
    first_result = gate.evaluate(first.candidate_id or "")
    repeated = gate.create_candidate(
        reflection_id=reflection.reflection_id or "",
        memory_type=MemoryType.SEMANTIC,
        statement=first.statement,
        confidence=0.8,
    )
    repeated_result = gate.evaluate(repeated.candidate_id or "")

    assert first_result.status == MemoryCandidateStatus.CANDIDATE
    assert repeated_result.support_count == 1
    assert repeated_result.status == MemoryCandidateStatus.CANDIDATE


def test_semantic_gate_accepts_three_distinct_jobs_then_deduplicates(tmp_path: Path) -> None:
    jobs = CreatorJobStore(tmp_path / "jobs")
    reflections = ReflectionStore(tmp_path / "learning", environment="test")
    audit = AuditLog(tmp_path / "audit" / "memory.jsonl")
    gate = CreatorMemoryGate(
        tmp_path / "memory",
        environment="test",
        jobs=jobs,
        reflections=reflections,
        audit=audit,
        semantic_support_threshold=3,
    )
    statement = "A controlled packaging experiment may be worth testing."
    results = []
    for index in range(3):
        reflection = make_memory_reflection(jobs=jobs, reflections=reflections, index=index)
        candidate = gate.create_candidate(
            reflection_id=reflection.reflection_id or "",
            memory_type=MemoryType.SEMANTIC,
            statement=statement,
            confidence=0.8,
        )
        results.append(gate.evaluate(candidate.candidate_id or ""))

    assert [item.status for item in results] == [
        MemoryCandidateStatus.CANDIDATE,
        MemoryCandidateStatus.CANDIDATE,
        MemoryCandidateStatus.ACCEPTED,
    ]
    assert results[-1].support_count == 3
    assert len(set(results[-1].support_job_ids)) == 3
    fourth_reflection = make_memory_reflection(jobs=jobs, reflections=reflections, index=4)
    duplicate = gate.create_candidate(
        reflection_id=fourth_reflection.reflection_id or "",
        memory_type=MemoryType.SEMANTIC,
        statement=statement,
        confidence=0.9,
    )
    duplicate = gate.evaluate(duplicate.candidate_id or "")
    assert duplicate.status == MemoryCandidateStatus.REJECTED
    assert duplicate.metadata["gate_reason"] == "duplicate_memory"


def test_contradiction_and_low_confidence_require_review_or_rejection(tmp_path: Path) -> None:
    jobs = CreatorJobStore(tmp_path / "jobs")
    reflections = ReflectionStore(tmp_path / "learning", environment="test")
    audit = AuditLog(tmp_path / "audit" / "memory.jsonl")
    gate = CreatorMemoryGate(
        tmp_path / "memory",
        environment="test",
        jobs=jobs,
        reflections=reflections,
        audit=audit,
    )
    reflection = make_memory_reflection(jobs=jobs, reflections=reflections, index=1)
    contradicted = gate.create_candidate(
        reflection_id=reflection.reflection_id or "",
        memory_type=MemoryType.SEMANTIC,
        statement="Packaging never matters.",
        confidence=0.8,
        contradiction_refs=["memory:test:existing_semantic"],
    )
    low = gate.create_candidate(
        reflection_id=reflection.reflection_id or "",
        memory_type=MemoryType.SEMANTIC,
        statement="A weakly supported pattern.",
        confidence=0.2,
    )

    assert gate.evaluate(contradicted.candidate_id or "").status == MemoryCandidateStatus.CONTRADICTED
    assert gate.evaluate(low.candidate_id or "").status == MemoryCandidateStatus.REVIEW_REQUIRED
    actions = [event.action for event in audit.list()]
    assert "MEMORY_CONTRADICTION_FOUND" in actions
    assert "MEMORY_REJECTED" in actions


def test_memory_secret_redaction_and_production_isolation(tmp_path: Path) -> None:
    fixture = Step6Fixture(tmp_path)
    reflection = fixture.reflect()
    candidate = fixture.memory_gate.create_candidate(
        reflection_id=reflection.reflection_id or "",
        memory_type=MemoryType.EPISODIC,
        statement="token=TEST_ONLY_SECRET_VALUE cookie=TEST_ONLY_COOKIE_VALUE",
        confidence=0.8,
        metadata={"session": "TEST_ONLY_SESSION_VALUE", "test_only": True},
    )
    accepted = fixture.memory_gate.evaluate(candidate.candidate_id or "")

    text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (tmp_path / "memory" / "test").rglob("*.json")
    )
    assert accepted.status == MemoryCandidateStatus.ACCEPTED
    assert "TEST_ONLY_SECRET_VALUE" not in text
    assert "TEST_ONLY_COOKIE_VALUE" not in text
    assert "TEST_ONLY_SESSION_VALUE" not in text
    assert "[REDACTED]" in text
    assert not (tmp_path / "memory" / "production").exists()

    from alysia.creator.memory import MemoryCandidateStore

    production_store = MemoryCandidateStore(tmp_path / "memory", environment="production")
    with pytest.raises(ValueError, match="TEST_FIXTURE"):
        production_store.save(
            MemoryCandidate(
                job_id=fixture.job.job_id,
                reflection_id=reflection.reflection_id or "",
                memory_type=MemoryType.EPISODIC,
                statement="Test data must stay isolated.",
                evidence_refs=reflection.evidence_refs,
                confidence=0.8,
                source_type=ObservationSourceType.TEST_FIXTURE,
            )
        )
    assert not list(production_store.root.glob("*.json"))


def test_no_reflection_or_memory_mutates_creator_strategy(tmp_path: Path) -> None:
    fixture = Step6Fixture(tmp_path)
    before = fixture.jobs.load(fixture.job.job_id)
    reflection = fixture.reflect()
    candidate = fixture.memory_gate.create_candidate(
        reflection_id=reflection.reflection_id or "",
        memory_type=MemoryType.EPISODIC,
        statement="Compact episode only; recommendations are not commands.",
        confidence=0.8,
    )
    fixture.memory_gate.evaluate(candidate.candidate_id or "")
    after = fixture.jobs.load(fixture.job.job_id)

    assert after.current_revision == before.current_revision
    assert after.topic_score == before.topic_score
    assert after.creator_plan == before.creator_plan
    assert after.publish_status == before.publish_status
