from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from alysia.schemas.analytics import RetentionPoint


FeedbackSource = Literal["real", "mock", "manual"]


class FeedbackRecord(BaseModel):
    run_id: str = Field(min_length=1)
    external_id: str = Field(min_length=1)
    collected_at: datetime
    source: FeedbackSource
    views: int | None = Field(default=None, ge=0)
    likes: int | None = Field(default=None, ge=0)
    comments: int | None = Field(default=None, ge=0)
    favorites: int | None = Field(default=None, ge=0)
    shares: int | None = Field(default=None, ge=0)
    followers_gained: int | None = Field(default=None, ge=0)
    retention_points: list[RetentionPoint] = Field(default_factory=list)
    comments_summary: str | list[str] | None = None

    @model_validator(mode="after")
    def retention_is_ordered(self) -> "FeedbackRecord":
        seconds = [point.second for point in self.retention_points]
        if seconds != sorted(seconds) or len(seconds) != len(set(seconds)):
            raise ValueError("retention_points 必须按 second 严格递增")
        return self


class CommentInsight(BaseModel):
    frequent_topics: list[str] = Field(default_factory=list)
    positive_signals: list[str] = Field(default_factory=list)
    negative_signals: list[str] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)
    possible_content_requests: list[str] = Field(default_factory=list)


class PublishEpisodeMemory(BaseModel):
    run_id: str
    external_id: str
    source: FeedbackSource
    collected_at: datetime
    metrics_summary: dict[str, int | float | str | None]
    comment_insight: CommentInsight
    feedback_digest: str = Field(min_length=64, max_length=64)
    updated_at: datetime

