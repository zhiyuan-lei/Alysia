from __future__ import annotations

import hashlib
import re
from datetime import datetime
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator, model_validator


SourceType = Literal[
    "official", "primary", "academic", "news", "documentation",
    "community", "social", "unknown",
]
EvidenceOrigin = Literal[
    "research", "manual", "web", "mock", "trend", "simulation",
    "feedback", "system_observation", "user_asserted",
]
ClaimType = Literal["stable", "time_sensitive", "estimate", "opinion", "definition", "historical"]
ClaimStatus = Literal[
    "verified", "provisional", "conflicted", "stale", "retracted",
    "unknown", "superseded",
]
FreshnessState = Literal["fresh", "aging", "stale", "reverify_required"]


def knowledge_now() -> datetime:
    return datetime.now().astimezone()


def stable_id(prefix: str, *parts: object) -> str:
    raw = "\x1f".join(str(part).strip() for part in parts)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def normalize_claim_key(statement: str) -> str:
    normalized = re.sub(r"\s+", " ", statement.strip().lower())
    normalized = re.sub(r"[，。！？；：,.!?;:\s]", "", normalized)
    return normalized[:160]


class EvidenceSource(BaseModel):
    source_id: str = Field(min_length=1)
    url: str = Field(min_length=1)
    title: str = Field(min_length=1)
    publisher: str = Field(min_length=1)
    domain: str = Field(min_length=1)
    author: str | None = None
    published_at: datetime | None = None
    retrieved_at: datetime = Field(default_factory=knowledge_now)
    source_type: SourceType = "unknown"
    authority_score: float | None = Field(default=None, ge=0, le=1)
    freshness_class: str = "unknown"
    content_hash: str | None = None
    access_note: str = ""
    license: str | None = None
    citation_note: str | None = None
    reliability_notes: list[str] = Field(default_factory=list)
    evidence_origin: EvidenceOrigin = "research"
    observation_scope: str | None = None

    @field_validator("url")
    @classmethod
    def valid_url(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("EvidenceSource URL 必须是 http(s) 地址")
        return value

    @model_validator(mode="after")
    def local_observations_are_scoped(self) -> "EvidenceSource":
        if self.evidence_origin == "system_observation" and not self.observation_scope:
            raise ValueError("system_observation 必须声明 observation_scope")
        return self


class KnowledgeClaim(BaseModel):
    claim_id: str = Field(min_length=1)
    statement: str = Field(min_length=1)
    normalized_key: str = Field(min_length=1)
    topic: str = Field(min_length=1)
    domain: str = Field(min_length=1)
    claim_type: ClaimType
    status: ClaimStatus = "unknown"
    confidence: float = Field(default=0, ge=0, le=1)
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    last_verified_at: datetime | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    contradicting_evidence_refs: list[str] = Field(default_factory=list)
    scope: str = "global"
    conditions: list[str] = Field(default_factory=list)
    version: int = Field(default=1, ge=1)
    supersedes_claim_id: str | None = None
    freshness_policy_days: int | None = Field(default=None, ge=1)
    created_at: datetime = Field(default_factory=knowledge_now)
    updated_at: datetime = Field(default_factory=knowledge_now)

    @model_validator(mode="after")
    def evidence_and_type_rules(self) -> "KnowledgeClaim":
        if self.status == "verified" and not self.evidence_refs:
            raise ValueError("verified claim 必须绑定 evidence_refs")
        if self.claim_type == "opinion" and self.status == "verified":
            raise ValueError("opinion 不得升级为 verified fact")
        if self.claim_type == "time_sensitive" and self.freshness_policy_days is None:
            raise ValueError("time_sensitive claim 必须声明 freshness_policy_days")
        if self.valid_from and self.valid_until and self.valid_from > self.valid_until:
            raise ValueError("valid_from 不能晚于 valid_until")
        return self


class ClaimCandidate(BaseModel):
    statement: str = Field(min_length=1)
    normalized_key: str = Field(min_length=1)
    topic: str = Field(min_length=1)
    domain: str = Field(min_length=1)
    claim_type: ClaimType = "stable"
    source_refs: list[str] = Field(default_factory=list)
    time_sensitive: bool = False
    scope: str = "global"
    supported: bool = False
    unsupported_reason: str | None = None


class SourceQualityBreakdown(BaseModel):
    primary_official_proximity: float = Field(ge=0, le=1)
    publication_recency: float = Field(ge=0, le=1)
    domain_relevance: float = Field(ge=0, le=1)
    corroboration: float = Field(ge=0, le=1)
    identifiable_authorship: float = Field(ge=0, le=1)
    citation_quality: float = Field(ge=0, le=1)
    conflict_history: float = Field(ge=0, le=1)


class SourceQualityEvaluation(BaseModel):
    source_id: str
    score: float = Field(ge=0, le=1)
    breakdown: SourceQualityBreakdown
    weights: dict[str, float]
    notes: list[str] = Field(default_factory=list)


class ClaimVerificationResult(BaseModel):
    claim_id: str
    status: ClaimStatus
    confidence: float = Field(ge=0, le=1)
    supporting_sources: list[str] = Field(default_factory=list)
    conflicting_sources: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    reasoning_summary: str


class KnowledgeConflict(BaseModel):
    conflict_id: str
    claim_refs: list[str] = Field(min_length=2)
    conflict_type: Literal["value", "date", "scope", "definition", "version"]
    evidence_refs: list[str] = Field(default_factory=list)
    resolution_status: Literal["open", "resolved", "superseded", "needs_primary_source"] = "open"
    recommended_action: str
    created_at: datetime = Field(default_factory=knowledge_now)
    updated_at: datetime = Field(default_factory=knowledge_now)


class FreshnessAssessment(BaseModel):
    claim_id: str
    state: FreshnessState
    ttl_days: int = Field(ge=1)
    age_days: float | None = Field(default=None, ge=0)
    reason: str
    assessed_at: datetime = Field(default_factory=knowledge_now)


class ReverificationTask(BaseModel):
    task_id: str
    claim_id: str
    question: str
    priority: Literal["low", "medium", "high", "critical"]
    required_source_types: list[SourceType] = Field(default_factory=list)
    status: Literal["pending", "in_progress", "completed", "blocked"] = "pending"
    reason: str
    created_at: datetime = Field(default_factory=knowledge_now)
    updated_at: datetime = Field(default_factory=knowledge_now)


class ResearchTask(BaseModel):
    task_id: str
    question: str = Field(min_length=1)
    required_evidence_quality: Literal["low", "medium", "high", "primary"] = "medium"
    freshness_requirement_days: int | None = Field(default=None, ge=1)
    max_sources: int = Field(default=8, ge=1, le=50)
    max_rounds: int = Field(default=2, ge=1, le=5)
    deadline: datetime | None = None
    stop_condition: str = "enough_corroboration_or_limits_reached"
    result_status: Literal["pending", "answered", "partially_answered", "unresolved"] = "pending"
    source_refs: list[str] = Field(default_factory=list)
    claim_refs: list[str] = Field(default_factory=list)
    rounds_completed: int = Field(default=0, ge=0)
    created_at: datetime = Field(default_factory=knowledge_now)
    updated_at: datetime = Field(default_factory=knowledge_now)

    @model_validator(mode="after")
    def bounded_research(self) -> "ResearchTask":
        if self.rounds_completed > self.max_rounds:
            raise ValueError("ResearchTask 不得超过 max_rounds")
        if len(self.source_refs) > self.max_sources:
            raise ValueError("ResearchTask 不得超过 max_sources")
        return self


class KnowledgeGap(BaseModel):
    gap_id: str
    question: str = Field(min_length=1)
    affected_topics: list[str] = Field(default_factory=list)
    affected_runs: list[str] = Field(default_factory=list)
    urgency: Literal["low", "medium", "high", "critical"] = "medium"
    required_source_types: list[SourceType] = Field(default_factory=list)
    current_evidence: list[str] = Field(default_factory=list)
    status: Literal["open", "researching", "resolved", "blocked"] = "open"
    created_at: datetime = Field(default_factory=knowledge_now)
    updated_at: datetime = Field(default_factory=knowledge_now)


class SectionGrounding(BaseModel):
    section_id: str
    claim_refs: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    factual: bool = True
    supported: bool = False
    issues: list[str] = Field(default_factory=list)


class GroundingReport(BaseModel):
    run_id: str
    supported_sections: list[str] = Field(default_factory=list)
    unsupported_sections: list[str] = Field(default_factory=list)
    stale_claim_refs: list[str] = Field(default_factory=list)
    conflicted_claim_refs: list[str] = Field(default_factory=list)
    citation_coverage: float = Field(ge=0, le=1)
    sections: list[SectionGrounding] = Field(default_factory=list)
    passed: bool
    generated_at: datetime = Field(default_factory=knowledge_now)


class KnowledgeQAIssue(BaseModel):
    code: str
    severity: Literal["warning", "error"]
    message: str
    reference: str | None = None


class KnowledgeQAReport(BaseModel):
    passed: bool
    issues: list[KnowledgeQAIssue] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=knowledge_now)


class KnowledgeMaintenanceReport(BaseModel):
    scanned_claims: int = 0
    fresh: int = 0
    aging: int = 0
    stale: int = 0
    reverify_required: int = 0
    task_ids: list[str] = Field(default_factory=list)
    conflict_ids: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=knowledge_now)


class KnowledgeContext(BaseModel):
    topic: str
    role: str
    claims: list[KnowledgeClaim] = Field(default_factory=list)
    sources: list[EvidenceSource] = Field(default_factory=list)
    conflicts: list[KnowledgeConflict] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ResearchKnowledgeResult(BaseModel):
    topic: str
    source_ids: list[str] = Field(default_factory=list)
    claim_ids: list[str] = Field(default_factory=list)
    unsupported_claims: list[ClaimCandidate] = Field(default_factory=list)
    verification_results: list[ClaimVerificationResult] = Field(default_factory=list)
    conflict_ids: list[str] = Field(default_factory=list)
