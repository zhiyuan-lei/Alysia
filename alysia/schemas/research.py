from __future__ import annotations

from datetime import datetime
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator


class Source(BaseModel):
    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    url: str = Field(min_length=1)
    publisher: str = Field(min_length=1)
    domain: str = Field(min_length=1)
    retrieved_at: datetime
    note: str = ""
    author: str | None = None
    published_at: datetime | None = None
    source_type: Literal[
        "official", "primary", "academic", "news", "documentation",
        "community", "social", "unknown",
    ] = "unknown"
    content_hash: str | None = None
    access_note: str = ""
    citation_note: str | None = None
    evidence_origin: Literal[
        "research", "manual", "web", "mock", "trend", "simulation",
        "feedback", "system_observation", "user_asserted",
    ] = "research"
    observation_scope: str | None = None

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("source URL 必须是 http(s) 地址")
        return value


class ResearchResult(BaseModel):
    topic: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    key_points: list[str] = Field(min_length=1)
    open_questions: list[str] = Field(default_factory=list)
    sources: list[Source] = Field(default_factory=list)

    def to_markdown(self) -> str:
        key_points = "\n".join(f"- {point}" for point in self.key_points)
        questions = "\n".join(f"- {question}" for question in self.open_questions) or "- 暂无"
        sources = "\n".join(
            f"- [{source.id}] [{source.title}]({source.url}) — {source.publisher}；{source.note}"
            for source in self.sources
        ) or "- 暂无；使用前应补充可靠来源。"
        return (
            f"# 调研：{self.topic}\n\n"
            f"## 摘要\n\n{self.summary}\n\n"
            f"## 关键观点\n\n{key_points}\n\n"
            f"## 待确认问题\n\n{questions}\n\n"
            f"## 来源\n\n{sources}\n"
        )
