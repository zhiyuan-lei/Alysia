from __future__ import annotations

import re
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Literal, Self
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator


CreatorJobStatus = Literal["DRAFT", "REVIEW", "APPROVED", "PUBLISH_READY", "PUBLISHED", "BLOCKED", "FAILED"]
MetricAvailability = Literal["available", "unavailable"]
ObservationSource = Literal["platform", "manual_real"]
ReceiptSource = Literal["official_api", "manual_handoff"]


class ApprovalStatus(str, Enum):
    DRAFT = "DRAFT"
    REVIEW = "REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    REVISION_REQUIRED = "REVISION_REQUIRED"


class PublishStatus(str, Enum):
    NOT_READY = "NOT_READY"
    PUBLISH_READY = "PUBLISH_READY"
    PUBLISHING = "PUBLISHING"
    PUBLISHED = "PUBLISHED"
    FAILED = "FAILED"


class ClaimClassification(str, Enum):
    VERIFIED_FACT = "VERIFIED_FACT"
    INFERENCE = "INFERENCE"
    OPINION = "OPINION"
    CREATIVE_CONTENT = "CREATIVE_CONTENT"
    UNKNOWN = "UNKNOWN"


class EvidenceStatus(str, Enum):
    SUPPORTED = "SUPPORTED"
    PARTIALLY_SUPPORTED = "PARTIALLY_SUPPORTED"
    CONFLICTING = "CONFLICTING"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    UNVERIFIED = "UNVERIFIED"


class ResearchEvidenceStatus(str, Enum):
    SUFFICIENT = "SUFFICIENT"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class ResearchSourceTrace(BaseModel):
    source_id: str = Field(min_length=1)
    source: str = Field(min_length=1)
    retrieved_at: datetime
    claim: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    source_type: str = Field(min_length=1)
    evidence_path: Path | None = None
    reliability: str = "UNKNOWN"
    content_hash: str | None = None


class CreatorClaimTrace(BaseModel):
    claim_id: str = Field(default_factory=lambda: f"claim_{uuid4().hex[:16]}", min_length=1)
    claim: str = Field(min_length=1)
    classification: ClaimClassification
    confidence: float = Field(ge=0, le=1)
    source_refs: list[str] = Field(default_factory=list)
    evidence_status: EvidenceStatus = EvidenceStatus.UNVERIFIED
    notes: list[str] = Field(default_factory=list)
    presented_as_fact: bool = False
    stale: bool = False
    conflicted: bool = False
    note: str | None = None

    @model_validator(mode="after")
    def verified_claim_has_evidence(self) -> "CreatorClaimTrace":
        if (
            self.classification == ClaimClassification.VERIFIED_FACT
            and self.evidence_status == EvidenceStatus.SUPPORTED
            and not self.source_refs
        ):
            raise ValueError("VERIFIED_FACT must include source_refs")
        return self


class CreatorScriptSection(BaseModel):
    section_id: str = Field(min_length=1)
    purpose: str = Field(min_length=1)
    text: str = Field(min_length=1)
    factual: bool = False
    claim_refs: list[str] = Field(default_factory=list)
    visual_refs: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def factual_sections_are_traceable(self) -> "CreatorScriptSection":
        if self.factual and not self.claim_refs:
            raise ValueError("factual script section requires claim_refs")
        return self


class CreatorPlan(BaseModel):
    plan_id: str | None = None
    job_id: str | None = None
    revision: int = Field(default=1, ge=1)
    hook: str = ""
    core_message: str = ""
    target_audience: str = ""
    structure: list[str] = Field(default_factory=list)
    script: str = ""
    script_sections: list[CreatorScriptSection] = Field(default_factory=list)
    script_ref: str | None = None
    visual_direction: str = ""
    visual_scenes: list[dict[str, object]] = Field(default_factory=list)
    visuals: dict[str, object] = Field(default_factory=dict)
    voice_direction: str = ""
    audio_direction: str = ""
    voice: dict[str, object] = Field(default_factory=dict)
    music: dict[str, object] = Field(default_factory=dict)
    thumbnail_concept: str = ""
    thumbnail_ref: str | None = None
    title_candidates: list[str] = Field(default_factory=list)
    preferred_title: str = ""
    title: str = ""
    description_draft: str = ""
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    research_refs: list[str] = Field(default_factory=list)
    claim_refs: list[str] = Field(default_factory=list)
    uncertainty_refs: list[str] = Field(default_factory=list)
    production_requirements: dict[str, object] = Field(default_factory=dict)
    estimated_cost: dict[str, object] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now().astimezone())
    updated_at: datetime = Field(default_factory=lambda: datetime.now().astimezone())

    @model_validator(mode="after")
    def bound_plans_are_consistent(self) -> "CreatorPlan":
        if bool(self.plan_id) != bool(self.job_id):
            raise ValueError("CreatorPlan plan_id and job_id must be set together")
        known_claims = set(self.claim_refs)
        unknown = {
            ref
            for section in self.script_sections
            for ref in section.claim_refs
            if ref not in known_claims
        }
        if unknown:
            raise ValueError("script section references unknown claims: " + ", ".join(sorted(unknown)))
        return self


class DuplicateMatch(BaseModel):
    existing_job_id: str
    dimension: Literal["topic", "title", "core_claim", "visual_plan", "script_structure"]
    similarity: float = Field(ge=0, le=1)
    method: str
    reference: str = ""


class DuplicateCheckReport(BaseModel):
    passed: bool
    matches: list[DuplicateMatch] = Field(default_factory=list)
    threshold: float = Field(default=0.72, ge=0, le=1)
    checked_at: datetime = Field(default_factory=lambda: datetime.now().astimezone())


class CreatorQAReport(BaseModel):
    passed: bool
    content_passed: bool
    video_passed: bool
    copy_passed: bool
    safety_passed: bool
    duplicate_passed: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    checked_at: datetime
    evidence_refs: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def pass_matches_checks(self) -> "CreatorQAReport":
        expected = all(
            (
                self.content_passed,
                self.video_passed,
                self.copy_passed,
                self.safety_passed,
                self.duplicate_passed,
            )
        ) and not self.errors
        if self.passed != expected:
            raise ValueError("CreatorQA passed must match component checks and errors")
        return self


class RevisionRecord(BaseModel):
    revision: int = Field(ge=1)
    reason: str = Field(min_length=1)
    requested_by: str = Field(min_length=1)
    requested_at: datetime
    snapshot_path: Path
    status: Literal["REQUESTED", "COMPLETED"] = "REQUESTED"


class PublishAttempt(BaseModel):
    attempt: int = Field(ge=1)
    attempted_at: datetime
    status: Literal["PREPARED", "SUBMITTING", "FAILED", "PUBLISHED", "MANUAL_INTERVENTION"]
    error: str | None = None
    retry_after: datetime | None = None
    terminal: bool = False
    idempotency_key: str = Field(min_length=1)


class ContentObservation(BaseModel):
    content_id: str = Field(min_length=1)
    observed_at: datetime
    source: ObservationSource
    views: int | None = Field(default=None, ge=0)
    likes: int | None = Field(default=None, ge=0)
    comments: int | None = Field(default=None, ge=0)
    favorites: int | None = Field(default=None, ge=0)
    shares: int | None = Field(default=None, ge=0)
    followers_delta: int | None = Field(default=None)
    availability: dict[str, MetricAvailability]
    evidence_path: Path

    @model_validator(mode="after")
    def availability_matches_values(self) -> "ContentObservation":
        names = ("views", "likes", "comments", "favorites", "shares", "followers_delta")
        missing = [name for name in names if name not in self.availability]
        if missing:
            raise ValueError("availability missing fields: " + ", ".join(missing))
        for name in names:
            value = getattr(self, name)
            state = self.availability[name]
            if state == "available" and value is None:
                raise ValueError(f"{name} marked available without a value")
            if state == "unavailable" and value is not None:
                raise ValueError(f"{name} marked unavailable with a value")
        return self


class CreatorReflection(BaseModel):
    attempted: str = Field(min_length=1)
    actual: str = Field(min_length=1)
    worked: list[str] = Field(default_factory=list)
    likely_failed: list[str] = Field(default_factory=list)
    supporting_evidence: list[str] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)
    next_changes: list[str] = Field(default_factory=list)
    facts: list[str] = Field(default_factory=list)
    interpretations: list[str] = Field(default_factory=list)
    created_at: datetime

    @model_validator(mode="after")
    def causal_boundary_is_explicit(self) -> "CreatorReflection":
        if self.interpretations and not self.uncertainties:
            raise ValueError("interpretations require explicit uncertainties")
        return self


class ResourceUsageSnapshot(BaseModel):
    observed_at: datetime
    gpu_vram_used_mb: int | None = Field(default=None, ge=0)
    gpu_vram_peak_mb: int | None = Field(default=None, ge=0)
    system_ram_used_mb: int | None = Field(default=None, ge=0)
    system_ram_peak_mb: int | None = Field(default=None, ge=0)
    disk_growth_bytes: int | None = Field(default=None)
    cache_growth_bytes: int | None = Field(default=None)
    evidence_ref: str | None = None


class RecoveryEvent(BaseModel):
    stage: str = Field(min_length=1)
    failure: str = Field(min_length=1)
    recoverable: bool
    recovery_result: str = Field(min_length=1)
    occurred_at: datetime
    terminal: bool = False


class BilibiliPublicationReceipt(BaseModel):
    content_id: str
    publication_url: str
    published_at: datetime
    recorded_at: datetime
    recorded_by: str = Field(min_length=1)
    source: ReceiptSource
    evidence_path: Path

    @field_validator("content_id")
    @classmethod
    def valid_bvid(cls, value: str) -> str:
        if not re.fullmatch(r"BV[0-9A-Za-z]{10}", value):
            raise ValueError("content_id must be a Bilibili BV identifier")
        return value

    @model_validator(mode="after")
    def receipt_is_consistent(self) -> "BilibiliPublicationReceipt":
        if not self.recorded_by.startswith("human:") and self.source == "manual_handoff":
            raise ValueError("manual_handoff must be recorded by a human actor")
        expected = f"https://www.bilibili.com/video/{self.content_id}"
        if self.publication_url.rstrip("/") != expected:
            raise ValueError("publication_url must match content_id on www.bilibili.com")
        if self.recorded_at < self.published_at:
            raise ValueError("recorded_at cannot precede published_at")
        return self


class CreatorJob(BaseModel):
    job_id: str = Field(pattern=r"^creator_[0-9a-f]{16}$")
    created_at: datetime
    updated_at: datetime
    current_revision: int = Field(default=1, ge=1)
    status: CreatorJobStatus = "DRAFT"
    topic: str = Field(min_length=1)
    topic_source: str = Field(min_length=1)
    topic_score: float = Field(ge=0, le=100)
    research_sources: list[ResearchSourceTrace] = Field(default_factory=list)
    claims: list[CreatorClaimTrace] = Field(default_factory=list)
    research_status: ResearchEvidenceStatus = ResearchEvidenceStatus.INSUFFICIENT_EVIDENCE
    uncertainties: list[str] = Field(default_factory=list)
    creative_direction: str = ""
    creator_plan: CreatorPlan | None = None
    script: str = ""
    title_candidates: list[str] = Field(default_factory=list)
    selected_title: str = ""
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    visual_plan: dict[str, object] = Field(default_factory=dict)
    audio_plan: dict[str, object] = Field(default_factory=dict)
    video_path: Path | None = None
    thumbnail_path: Path | None = None
    qa_report: CreatorQAReport | None = None
    approval_status: ApprovalStatus = ApprovalStatus.DRAFT
    approved_by: str | None = None
    approved_at: datetime | None = None
    approval_ref: str | None = None
    package_hash: str | None = None
    package_path: Path | None = None
    publish_status: PublishStatus = PublishStatus.NOT_READY
    platform: Literal["bilibili"] = "bilibili"
    platform_content_id: str | None = None
    publication_url: str | None = None
    published_at: datetime | None = None
    publication_evidence_path: Path | None = None
    metrics: list[ContentObservation] = Field(default_factory=list)
    reflection: CreatorReflection | None = None
    latest_metrics_summary: dict[str, object] = Field(default_factory=dict)
    observation_refs: list[str] = Field(default_factory=list)
    reflection_ref: str | None = None
    memory_refs: list[str] = Field(default_factory=list)
    revisions: list[RevisionRecord] = Field(default_factory=list)
    publish_attempts: list[PublishAttempt] = Field(default_factory=list)
    resource_usage: list[ResourceUsageSnapshot] = Field(default_factory=list)
    recovery_events: list[RecoveryEvent] = Field(default_factory=list)
    evidence_paths: list[Path] = Field(default_factory=list)
    run_id: str | None = None
    publish_job_id: str | None = None
    failure_count: int = Field(default=0, ge=0)
    recovery_result: str | None = None
    testing: bool = False
    dry_run: bool = False

    @classmethod
    def new(cls, **data: object) -> Self:
        return cls(job_id=f"creator_{uuid4().hex[:16]}", **data)

    def transition_approval(
        self,
        target: ApprovalStatus,
        *,
        approved_by: str | None = None,
        approved_at: datetime | None = None,
    ) -> Self:
        target = ApprovalStatus(target)
        allowed = {
            ApprovalStatus.DRAFT: {ApprovalStatus.REVIEW},
            ApprovalStatus.REVIEW: {
                ApprovalStatus.APPROVED,
                ApprovalStatus.REJECTED,
                ApprovalStatus.REVISION_REQUIRED,
            },
            ApprovalStatus.APPROVED: {ApprovalStatus.REVISION_REQUIRED},
            ApprovalStatus.REJECTED: {ApprovalStatus.DRAFT},
            ApprovalStatus.REVISION_REQUIRED: {ApprovalStatus.DRAFT},
        }
        if target not in allowed[self.approval_status]:
            raise ValueError(f"invalid approval transition: {self.approval_status.value} -> {target.value}")
        if target == ApprovalStatus.APPROVED:
            if not approved_by or not approved_by.startswith("human:"):
                raise ValueError("APPROVED requires a human actor")
            approved_at = approved_at or datetime.now().astimezone()
        else:
            approved_by = None
            approved_at = None
        status_by_approval = {
            ApprovalStatus.DRAFT: "DRAFT",
            ApprovalStatus.REVIEW: "REVIEW",
            ApprovalStatus.APPROVED: "APPROVED",
            ApprovalStatus.REJECTED: "BLOCKED",
            ApprovalStatus.REVISION_REQUIRED: "DRAFT",
        }
        payload = self.model_dump()
        payload.update(
            approval_status=target,
            status=status_by_approval[target],
            approved_by=approved_by,
            approved_at=approved_at,
            publish_status=PublishStatus.NOT_READY,
            updated_at=datetime.now().astimezone(),
        )
        return type(self).model_validate(payload)

    def transition_publish(self, target: PublishStatus) -> Self:
        target = PublishStatus(target)
        allowed = {
            PublishStatus.NOT_READY: {PublishStatus.PUBLISH_READY},
            PublishStatus.PUBLISH_READY: {PublishStatus.PUBLISHING},
            PublishStatus.PUBLISHING: {PublishStatus.PUBLISHED, PublishStatus.FAILED},
            PublishStatus.PUBLISHED: set(),
            PublishStatus.FAILED: {PublishStatus.PUBLISHING},
        }
        if target not in allowed[self.publish_status]:
            raise ValueError(f"invalid publish transition: {self.publish_status.value} -> {target.value}")
        status = self.status
        if target in {PublishStatus.PUBLISH_READY, PublishStatus.PUBLISHING}:
            status = "PUBLISH_READY"
        elif target == PublishStatus.PUBLISHED:
            status = "PUBLISHED"
        elif target == PublishStatus.FAILED:
            status = "FAILED"
        payload = self.model_dump()
        payload.update(
            publish_status=target,
            status=status,
            updated_at=datetime.now().astimezone(),
        )
        return type(self).model_validate(payload)

    @model_validator(mode="after")
    def published_invariants(self) -> "CreatorJob":
        if self.approval_status == ApprovalStatus.APPROVED:
            if not self.approved_by or not self.approved_at:
                raise ValueError("APPROVED CreatorJob requires human approval metadata")
        if self.publish_status in {
            PublishStatus.PUBLISH_READY,
            PublishStatus.PUBLISHING,
            PublishStatus.PUBLISHED,
        } and self.approval_status != ApprovalStatus.APPROVED:
            raise ValueError("CreatorJob must be APPROVED before PUBLISH_READY")
        if self.status == "PUBLISHED" or self.publish_status == PublishStatus.PUBLISHED:
            if self.testing or self.dry_run:
                raise ValueError("testing/dry-run CreatorJob cannot be PUBLISHED")
            if self.approval_status != ApprovalStatus.APPROVED or not self.approved_by or not self.approved_at:
                raise ValueError("PUBLISHED CreatorJob requires human approval")
            if not self.qa_report or not self.qa_report.passed:
                raise ValueError("PUBLISHED CreatorJob requires passing CreatorQA")
            if not self.platform_content_id or not self.published_at or not self.publication_evidence_path:
                raise ValueError("PUBLISHED CreatorJob requires a platform receipt")
        return self
