from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


TitleStyle = Literal["科普型", "问题型", "冲突型", "数字型", "悬念型"]


class TitleCandidate(BaseModel):
    title: str = Field(min_length=2, max_length=80)
    style: TitleStyle
    reason: str = Field(min_length=1)
    risk: str = "无"


class TitleResult(BaseModel):
    primary_title: str = Field(min_length=2, max_length=80)
    candidates: list[TitleCandidate] = Field(min_length=1)


class PublishPackage(BaseModel):
    title: str = Field(min_length=2, max_length=80)
    subtitle_title: str | None = Field(default=None, max_length=60)
    description: str = Field(min_length=1)
    tags: list[str] = Field(min_length=1)
    category: str = Field(min_length=1)
    cover_path: Path
    video_path: Path
    duration_sec: float = Field(gt=0)
    language: str = Field(min_length=2)
    disclaimer: str = ""
    source_links: list[str] = Field(default_factory=list)
    generated_at: datetime
    qa_status: Literal["pending", "passed", "failed"] = "pending"

    @field_validator("tags")
    @classmethod
    def tags_are_unique(cls, tags: list[str]) -> list[str]:
        normalized = [tag.casefold() for tag in tags]
        if len(normalized) != len(set(normalized)):
            raise ValueError("publish tags 不能重复")
        return tags

    @field_validator("source_links")
    @classmethod
    def source_links_are_unique(cls, links: list[str]) -> list[str]:
        return list(dict.fromkeys(links))


class PublishQAReport(BaseModel):
    passed: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)
