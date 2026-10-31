from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from alysia.schemas.analytics import MetricSource


StrategyStatus = Literal["tentative", "supported", "deprecated"]
ExperimentStatus = Literal["draft", "approved", "running", "completed", "cancelled"]
ExperimentOutcome = Literal["positive", "negative", "inconclusive"]


class VideoPerformanceSnapshot(BaseModel):
    channel_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    external_id: str | None = None
    topic: str = Field(min_length=1)
    category: str = "未分类"
    published_at: datetime
    source: MetricSource
    metrics: dict[str, int | float | None]
    fingerprint: dict[str, int | float | str | None]

    @property
    def is_testing(self) -> bool:
        return self.source in {"mock", "testing"}


class MetricAggregate(BaseModel):
    metric: str
    sample_count: int = Field(ge=0)
    mean: float | None = None
    minimum: float | None = None
    maximum: float | None = None
    previous_mean: float | None = None
    recent_mean: float | None = None
    relative_change: float | None = None


class TrendChange(BaseModel):
    metric: str
    direction: Literal["improving", "declining", "stable", "insufficient"]
    statement: str
    evidence_run_ids: list[str] = Field(default_factory=list)


class MetricComparison(BaseModel):
    metric: str
    best_run_id: str | None = None
    best_value: float | None = None
    weakest_run_id: str | None = None
    weakest_value: float | None = None
    comparable_run_ids: list[str] = Field(default_factory=list)


class ContentFatigueSignal(BaseModel):
    dimension: Literal["category", "topic"]
    value: str
    status: Literal["possible", "not_observed", "insufficient"]
    statement: str
    evidence_run_ids: list[str] = Field(default_factory=list)


class TopicLifecycle(BaseModel):
    topic_key: str
    stage: Literal["exploring", "growing", "stable", "declining", "insufficient"]
    sample_count: int = Field(ge=0)
    statement: str
    evidence_run_ids: list[str] = Field(default_factory=list)


class MultiVideoPerformanceAnalysis(BaseModel):
    channel_id: str
    sample_size: int = Field(ge=0)
    non_testing_sample_size: int = Field(ge=0)
    run_ids: list[str]
    metric_aggregates: list[MetricAggregate]
    comparisons: list[MetricComparison]
    trend_changes: list[TrendChange]
    fatigue_signals: list[ContentFatigueSignal]
    topic_lifecycles: list[TopicLifecycle]
    missing_data: list[str]
    evidence: list[str]
    source_digest: str = Field(min_length=64, max_length=64)
    generated_at: datetime


class AudiencePreference(BaseModel):
    subject: str
    signal: Literal["positive", "negative", "mixed", "unknown"]
    confidence: float = Field(ge=0, le=1)
    evidence_run_ids: list[str] = Field(default_factory=list)


class AudienceModel(BaseModel):
    channel_id: str
    liked_topics: list[AudiencePreference] = Field(default_factory=list)
    common_questions: list[str] = Field(default_factory=list)
    content_preferences: list[AudiencePreference] = Field(default_factory=list)
    viewing_behavior: list[str] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)
    updated_at: datetime


class ChannelCase(BaseModel):
    run_id: str
    topic: str
    reason: str
    metrics: dict[str, int | float | None]


class PublishedTopic(BaseModel):
    run_id: str
    topic: str
    category: str
    published_at: datetime
    source: MetricSource


class ChannelMemory(BaseModel):
    channel_id: str = Field(min_length=1)
    channel_name: str = Field(min_length=1)
    current_positioning: str = Field(min_length=1)
    content_directions: list[str] = Field(default_factory=list)
    published_topics: list[PublishedTopic] = Field(default_factory=list)
    audience_hypotheses: list[str] = Field(default_factory=list)
    success_cases: list[ChannelCase] = Field(default_factory=list)
    failure_cases: list[ChannelCase] = Field(default_factory=list)
    long_term_strategy: list[str] = Field(default_factory=list)
    active_experiment_ids: list[str] = Field(default_factory=list)
    strategy_ids: list[str] = Field(default_factory=list)
    source_digest: str | None = None
    revision: int = Field(default=1, ge=1)
    created_at: datetime
    updated_at: datetime


class ExperimentMetric(BaseModel):
    metric: str = Field(min_length=1)
    direction: Literal["increase", "decrease"] = "increase"
    minimum_relative_change: float = Field(default=0.0, ge=0)


class ExperimentAssignment(BaseModel):
    run_id: str = Field(min_length=1)
    experiment_group: Literal["control", "treatment"]
    source: MetricSource


class ExperimentResult(BaseModel):
    outcome: ExperimentOutcome
    metric_results: dict[str, dict[str, float | int | None]]
    evidence_run_ids: list[str]
    evaluated_at: datetime
    caveat: str = "观察结果仅在当前实验样本和控制条件内有效。"


class ContentExperiment(BaseModel):
    id: str = Field(min_length=1)
    channel_id: str = Field(min_length=1)
    hypothesis: str = Field(min_length=1)
    variable_changed: str = Field(min_length=1)
    control_variables: list[str] = Field(min_length=1)
    success_metrics: list[ExperimentMetric] = Field(min_length=1)
    linked_strategy_id: str | None = None
    status: ExperimentStatus = "draft"
    assignments: list[ExperimentAssignment] = Field(default_factory=list)
    result: ExperimentResult | None = None
    conclusion: str | None = None
    approved_by: str | None = None
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def completed_experiment_has_result(self) -> "ContentExperiment":
        if self.status == "completed" and (self.result is None or not self.conclusion):
            raise ValueError("completed experiment 必须包含 result 和 conclusion")
        return self


class StrategyEvidenceChain(BaseModel):
    strategy_id: str
    rule: str
    status: StrategyStatus
    confidence: float = Field(ge=0, le=1)
    experiment_ids: list[str] = Field(default_factory=list)
    metric_evidence: dict[str, dict[str, float | int | None]] = Field(default_factory=dict)


class CreatorDashboard(BaseModel):
    channel_id: str
    channel_state: ChannelMemory
    recent_performance: MultiVideoPerformanceAnalysis
    audience_model: AudienceModel
    current_experiments: list[ContentExperiment]
    pending_strategies: list[StrategyEvidenceChain]
    next_recommendations: list[str]
    source_digest: str = Field(min_length=64, max_length=64)
    generated_at: datetime
