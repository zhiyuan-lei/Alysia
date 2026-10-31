from __future__ import annotations

from datetime import datetime, timedelta
from typing import Iterable

from pydantic import BaseModel, Field

from alysia.creator.models import CreatorJob
from alysia.knowledge.models import stable_id
from alysia.planning.novelty import normalize_topic, topic_similarity
from alysia.schemas import TrendItem
from alysia.security.redaction import Redactor


def topic_now() -> datetime:
    return datetime.now().astimezone()


class TopicScoringWeights(BaseModel):
    relevance: float = 0.25
    freshness: float = 0.15
    evidence_quality: float = 0.20
    audience_fit: float = 0.20
    novelty: float = 0.20
    production_cost: float = 0.10
    duplication_risk: float = 0.35
    safety_risk: float = 0.45


class TopicCandidate(BaseModel):
    topic_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    summary: str = ""
    source: str = Field(min_length=1)
    source_type: str = Field(min_length=1)
    discovered_at: datetime = Field(default_factory=topic_now)
    relevance: float = Field(default=0.5, ge=0, le=1)
    freshness: float = Field(default=0.5, ge=0, le=1)
    evidence_quality: float = Field(default=0.5, ge=0, le=1)
    audience_fit: float = Field(default=0.5, ge=0, le=1)
    novelty: float = Field(default=0.5, ge=0, le=1)
    production_cost: float = Field(default=0.5, ge=0, le=1)
    duplication_risk: float = Field(default=0, ge=0, le=1)
    safety_risk: float = Field(default=0, ge=0, le=1)
    score: float = Field(default=0, ge=0, le=1)
    score_breakdown: dict[str, float] = Field(default_factory=dict)
    supporting_refs: list[str] = Field(default_factory=list)
    duplicate_refs: list[str] = Field(default_factory=list)
    rejection_reason: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)

    @classmethod
    def create(cls, *, title: str, source: str, source_type: str, **data: object) -> "TopicCandidate":
        return cls(
            topic_id=stable_id("topic", title, source, source_type),
            title=title,
            source=source,
            source_type=source_type,
            **data,
        )


class TopicRankingResult(BaseModel):
    accepted: list[TopicCandidate] = Field(default_factory=list)
    rejected: list[TopicCandidate] = Field(default_factory=list)


class TopicRanker:
    def __init__(
        self,
        weights: TopicScoringWeights | None = None,
        *,
        duplicate_threshold: float = 0.80,
        semantic_threshold: float = 0.45,
        safety_threshold: float = 0.75,
        recent_days: int = 90,
    ) -> None:
        self.weights = weights or TopicScoringWeights()
        self.duplicate_threshold = duplicate_threshold
        self.semantic_threshold = semantic_threshold
        self.safety_threshold = safety_threshold
        self.recent_days = recent_days

    def score(self, candidate: TopicCandidate) -> TopicCandidate:
        weights = self.weights
        breakdown = {
            "relevance": candidate.relevance * weights.relevance,
            "freshness": candidate.freshness * weights.freshness,
            "evidence_quality": candidate.evidence_quality * weights.evidence_quality,
            "audience_fit": candidate.audience_fit * weights.audience_fit,
            "novelty": candidate.novelty * weights.novelty,
            "production_cost": -candidate.production_cost * weights.production_cost,
            "duplication_risk": -candidate.duplication_risk * weights.duplication_risk,
            "safety_risk": -candidate.safety_risk * weights.safety_risk,
        }
        total = max(0.0, min(1.0, sum(breakdown.values())))
        breakdown["total"] = total
        return candidate.model_copy(update={
            "score": round(total, 6),
            "score_breakdown": {key: round(value, 6) for key, value in breakdown.items()},
        })

    def rank(
        self,
        candidates: Iterable[TopicCandidate],
        history: Iterable[CreatorJob] = (),
        *,
        now: datetime | None = None,
    ) -> TopicRankingResult:
        now = now or topic_now()
        accepted: list[TopicCandidate] = []
        rejected: list[TopicCandidate] = []
        history_items = list(history)
        for candidate in candidates:
            risk, refs = self._duplicate_risk(candidate, history_items, now=now)
            candidate = candidate.model_copy(update={
                "duplication_risk": max(candidate.duplication_risk, risk),
                "duplicate_refs": refs,
            })
            reason = None
            if candidate.safety_risk >= self.safety_threshold:
                reason = f"safety_risk={candidate.safety_risk:.3f} exceeds {self.safety_threshold:.3f}"
            elif candidate.duplication_risk >= self.duplicate_threshold:
                reason = f"duplication_risk={candidate.duplication_risk:.3f} exceeds {self.duplicate_threshold:.3f}"
            candidate = self.score(candidate).model_copy(update={"rejection_reason": reason})
            (rejected if reason else accepted).append(candidate)
        accepted.sort(key=lambda item: (-item.score, item.topic_id))
        rejected.sort(key=lambda item: (-item.score, item.topic_id))
        return TopicRankingResult(accepted=accepted, rejected=rejected)

    def _duplicate_risk(
        self,
        candidate: TopicCandidate,
        history: list[CreatorJob],
        *,
        now: datetime,
    ) -> tuple[float, list[str]]:
        best = candidate.duplication_risk
        refs: list[str] = []
        for job in history:
            values = {
                "topic": job.topic,
                "selected_title": job.selected_title,
                "core_claim": " ".join(claim.claim for claim in job.claims[:3]),
            }
            for dimension, value in values.items():
                if not value:
                    continue
                similarity = topic_similarity(candidate.title, value)
                method = "semantic_like"
                risk = similarity
                if candidate.title.strip().casefold() == value.strip().casefold():
                    method, risk = "exact", 1.0
                elif normalize_topic(candidate.title) == normalize_topic(value):
                    method, risk = "normalized", 1.0
                elif now - job.created_at <= timedelta(days=self.recent_days) and similarity >= self.semantic_threshold:
                    method, risk = "recent", max(0.85, similarity)
                elif similarity < self.semantic_threshold:
                    continue
                if risk > best:
                    best = risk
                refs.append(f"{job.job_id}:{dimension}:{method}:{similarity:.3f}")
        return min(1.0, best), sorted(set(refs))


class TopicDiscoveryService:
    def __init__(self, ranker: TopicRanker | None = None, redactor: Redactor | None = None) -> None:
        self.ranker = ranker or TopicRanker()
        self.redactor = redactor or Redactor()

    def discover_from_sources(self, items: Iterable[TrendItem]) -> list[TopicCandidate]:
        candidates: list[TopicCandidate] = []
        for item in items:
            freshness = 0.5 if item.freshness_days is None else max(0.0, 1.0 - item.freshness_days / 30)
            candidates.append(TopicCandidate.create(
                title=item.topic,
                summary=self.redactor.redact(item.summary),
                source=item.source,
                source_type=item.source_kind,
                discovered_at=item.observed_at,
                relevance=item.confidence,
                freshness=freshness,
                evidence_quality=item.confidence * (0.8 if item.url else 0.5),
                audience_fit=0.7,
                novelty=0.8,
                production_cost=0.5,
                supporting_refs=[item.id],
                metadata=self.redactor.redact_value({"category": item.category, "url": item.url or ""}),
            ))
        return candidates

    def discover_from_seed(self, seed: str, *, source: str = "human") -> list[TopicCandidate]:
        return [TopicCandidate.create(
            title=seed,
            summary="Seed topic; freshness and factual claims require research.",
            source=source,
            source_type="manual",
            relevance=0.7,
            freshness=0.5,
            evidence_quality=0.25,
            audience_fit=0.7,
            novelty=0.8,
            production_cost=0.5,
        )]

    def rank(self, candidates: Iterable[TopicCandidate], history: Iterable[CreatorJob] = ()) -> TopicRankingResult:
        return self.ranker.rank(candidates, history)
