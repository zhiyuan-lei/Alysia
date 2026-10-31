from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from alysia.schemas.analytics import Confidence


LessonStatus = Literal["tentative", "supported", "rejected"]
StrategyStatus = Literal["tentative", "supported", "deprecated"]
MemorySource = Literal["manual", "platform", "mock", "testing"]


class EpisodeMemory(BaseModel):
    run_id: str
    topic: str
    source: MemorySource
    metrics_summary: dict[str, int | float | str | None]
    fingerprint_summary: dict[str, int | float | str | None]
    analysis_summary: str
    created_at: datetime


class LessonCandidate(BaseModel):
    statement: str
    category: str
    scope: str
    supporting_metrics: dict[str, int | float | str | None]
    confidence: float = Field(ge=0, le=1)
    direction: Literal["supports", "contradicts"] = "supports"


class LessonMemory(BaseModel):
    id: str
    statement: str
    evidence_run_ids: list[str]
    counter_evidence_run_ids: list[str] = Field(default_factory=list)
    supporting_metrics: dict[str, dict[str, int | float | str | None]]
    confidence: float = Field(ge=0, le=1)
    status: LessonStatus
    category: str
    scope: str
    source: MemorySource
    created_at: datetime
    updated_at: datetime


class StrategyRecommendation(BaseModel):
    objective: str
    proposed_change: str
    rationale: str
    evidence: list[str] = Field(min_length=1)
    confidence: Confidence
    risk: str
    test_plan: str


class StrategyMemory(BaseModel):
    id: str
    channel_id: str = "main"
    rule: str
    rationale: str
    evidence_run_ids: list[str]
    confidence: float = Field(ge=0, le=1)
    status: StrategyStatus = "tentative"
    evidence_experiment_ids: list[str] = Field(default_factory=list)
    evidence_metrics: dict[str, dict[str, int | float | str | None]] = Field(default_factory=dict)
    applies_to: str
    source: MemorySource
    created_at: datetime
    updated_at: datetime


class NextExperimentProposal(BaseModel):
    topic: str
    angle: str
    target_audience: str
    primary_hypothesis: str
    variable_to_change: str
    variables_to_hold_constant: list[str]
    success_metrics: list[str] = Field(min_length=1)


class LearningQAReport(BaseModel):
    passed: bool
    errors: list[str]
    warnings: list[str]
    checks: dict[str, bool]
    disclaimer: str = "Learning QA 仅检查证据与推断边界，不证明策略具有因果效果。"
