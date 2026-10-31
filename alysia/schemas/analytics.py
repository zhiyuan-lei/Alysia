from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


Confidence = Literal["low", "medium", "high"]
MetricSource = Literal["manual", "mock", "testing", "platform"]


class RetentionPoint(BaseModel):
    second: float = Field(ge=0)
    percentage: float = Field(ge=0, le=1)


class VideoMetrics(BaseModel):
    run_id: str = Field(min_length=1)
    platform: str = Field(default="bilibili", min_length=1)
    collected_at: datetime
    source: MetricSource = "manual"
    impressions: int | None = Field(default=None, ge=0)
    views: int | None = Field(default=None, ge=0)
    likes: int | None = Field(default=None, ge=0)
    comments: int | None = Field(default=None, ge=0)
    favorites: int | None = Field(default=None, ge=0)
    shares: int | None = Field(default=None, ge=0)
    followers_gained: int | None = Field(default=None, ge=0)
    avg_view_duration_sec: float | None = Field(default=None, ge=0)
    avg_view_percentage: float | None = Field(default=None, ge=0, le=1)
    completion_rate: float | None = Field(default=None, ge=0, le=1)
    ctr: float | None = Field(default=None, ge=0, le=1)
    publish_time: datetime | None = None
    retention_points: list[RetentionPoint] = Field(default_factory=list)

    @model_validator(mode="after")
    def retention_is_ordered(self) -> "VideoMetrics":
        seconds = [point.second for point in self.retention_points]
        if seconds != sorted(seconds) or len(seconds) != len(set(seconds)):
            raise ValueError("retention_points 必须按 second 严格递增")
        return self

    @property
    def is_mock(self) -> bool:
        return self.source in {"mock", "testing"}


class DerivedMetricValue(BaseModel):
    value: float | None
    formula: str
    inputs: dict[str, int | float | None]
    missing_inputs: list[str] = Field(default_factory=list)


class DerivedMetrics(BaseModel):
    run_id: str
    engagement_rate: DerivedMetricValue
    like_rate: DerivedMetricValue
    favorite_rate: DerivedMetricValue
    comment_rate: DerivedMetricValue
    share_rate: DerivedMetricValue
    follower_conversion_rate: DerivedMetricValue
    normalized_watch_score: DerivedMetricValue


class ContentFingerprint(BaseModel):
    run_id: str
    topic: str
    title: str
    title_style: str
    duration_sec: float = Field(ge=0)
    hook_length_sec: float | None = Field(default=None, ge=0)
    scene_count: int = Field(ge=0)
    subtitle_density: float | None = Field(default=None, ge=0)
    average_subtitle_chars: float | None = Field(default=None, ge=0)
    narration_chars: int = Field(ge=0)
    narration_speed_chars_per_sec: float | None = Field(default=None, ge=0)
    visual_type_distribution: dict[str, int]
    number_of_sources: int = Field(ge=0)
    cover_template: str
    cover_text_length: int = Field(ge=0)
    tags: list[str]
    category: str


class Evidence(BaseModel):
    kind: Literal["fact", "artifact", "qa"]
    statement: str
    fields: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class AnalysisHypothesis(BaseModel):
    statement: str
    confidence: Confidence
    evidence: list[Evidence] = Field(min_length=1)
    caveat: str = "这是相关性假设，不代表因果关系。"


class PerformanceAnalysis(BaseModel):
    run_id: str
    summary: str
    facts: list[str]
    strengths: list[str]
    weaknesses: list[str]
    anomalies: list[str]
    hypotheses: list[AnalysisHypothesis]
    evidence: list[Evidence]
    missing_data: list[str]
    generated_at: datetime

