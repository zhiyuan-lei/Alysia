from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


PlanSource = Literal["mock", "testing", "manual", "web"]
PlanSlotStatus = Literal["proposed", "approved", "queued", "started", "completed", "skipped"]
CreatorLoopStage = Literal[
    "idle",
    "gather_trends",
    "generate_topics",
    "score_topics",
    "editorial_review",
    "plan_ready",
    "waiting_for_approval",
    "queued",
    "review_ready",
    "publish_approval",
    "publish_job",
    "feedback_waiting",
    "learning",
    "failed",
]


class CreatorProfile(BaseModel):
    creator_name: str = "Alysia"
    channel_goal: str = Field(min_length=1)
    primary_domains: list[str] = Field(min_length=1)
    excluded_domains: list[str] = Field(default_factory=list)
    target_audience: str = Field(min_length=1)
    language: str = "zh-CN"
    preferred_formats: list[str] = Field(min_length=1)
    target_duration_sec_range: tuple[int, int] = (120, 300)
    publishing_frequency: str = "每周 1 至 2 条（仅用于排期）"
    risk_tolerance: Literal["low", "medium", "high"] = "low"
    originality_requirements: str = Field(min_length=1)
    source_quality_requirements: str = Field(min_length=1)

    @model_validator(mode="after")
    def duration_range_is_ordered(self) -> "CreatorProfile":
        minimum, maximum = self.target_duration_sec_range
        if minimum < 30 or minimum > maximum:
            raise ValueError("target_duration_sec_range 必须是有序且不短于 30 秒")
        return self


class TrendItem(BaseModel):
    id: str
    topic: str = Field(min_length=1)
    source: str = Field(min_length=1)
    source_kind: PlanSource
    url: str | None = None
    published_at: datetime | None = None
    observed_at: datetime
    popularity_hint: float | str | None = None
    summary: str = ""
    keywords: list[str] = Field(default_factory=list)
    category: str = "未分类"
    confidence: float = Field(default=0.5, ge=0, le=1)
    freshness_days: float | None = Field(default=None, ge=0)


class DuplicateCandidate(BaseModel):
    candidate_topic: str
    existing_topic: str
    similarity: float = Field(ge=0, le=1)
    method: str = "normalized_keyword_jaccard"


class TopicCandidate(BaseModel):
    id: str
    topic: str = Field(min_length=1)
    angle: str = Field(min_length=1)
    target_audience: str = Field(min_length=1)
    why_now: str = Field(min_length=1)
    source_refs: list[str] = Field(default_factory=list)
    category: str = "未分类"
    novelty_score: float = Field(ge=0, le=1)
    relevance_score: float = Field(ge=0, le=1)
    evidence_score: float = Field(ge=0, le=1)
    expected_effort: Literal["low", "medium", "high"] = "medium"
    experiment_link: str | None = None
    risks: list[str] = Field(default_factory=list)
    requires_current_facts: bool = True


class TopicScore(BaseModel):
    candidate_id: str
    total: float = Field(ge=0, le=100)
    components: dict[str, float]
    explanation: str
    disqualify_reason: str | None = None
    duplicate_candidates: list[DuplicateCandidate] = Field(default_factory=list)


class RankedTopic(BaseModel):
    candidate: TopicCandidate
    score: TopicScore


class EditorialDecision(BaseModel):
    selected_topic: RankedTopic
    alternates: list[RankedTopic] = Field(default_factory=list)
    rationale: str
    evidence: list[str] = Field(default_factory=list)
    linked_strategy: str | None = None
    confidence: float = Field(ge=0, le=1)


class PlanSlot(BaseModel):
    id: str
    planned_date: date
    topic_candidate_id: str
    topic: str
    category: str
    status: PlanSlotStatus = "proposed"
    priority: int = Field(ge=1)
    linked_experiment: str | None = None
    source_refs: list[str] = Field(default_factory=list)
    approved_at: datetime | None = None
    rejected_at: datetime | None = None
    run_id: str | None = None


class ContentPlan(BaseModel):
    plan_id: str
    created_at: datetime
    horizon_days: int = Field(ge=1)
    source: PlanSource
    provider: str
    testing: bool = False
    source_digest: str
    profile_name: str
    channel_id: str = "main"
    status: Literal["plan_ready", "waiting_for_approval", "queued", "completed"] = "plan_ready"
    slots: list[PlanSlot] = Field(default_factory=list)

    @model_validator(mode="after")
    def mock_plan_is_testing(self) -> "ContentPlan":
        if self.source in {"mock", "testing"} and not self.testing:
            raise ValueError("mock/testing plan 必须明确标记 testing=true")
        return self


class PlanningQAReport(BaseModel):
    passed: bool
    errors: list[str]
    warnings: list[str]
    checks: dict[str, bool]


class CreatorLoopState(BaseModel):
    stage: CreatorLoopStage = "idle"
    updated_at: datetime
    last_tick_at: datetime | None = None
    active_plan_id: str | None = None
    last_source_digest: str | None = None
    error_message: str | None = None
    channel_id: str = "main"
    cycle_phase: Literal["observe", "analyze", "experiment", "create", "publish", "learn"] = "observe"
    operations_digest: str | None = None
