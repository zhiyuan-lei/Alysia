from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Iterable, Literal, Mapping
from urllib.parse import parse_qsl, urlparse

from pydantic import BaseModel, Field, field_validator, model_validator

from alysia.core.io import atomic_write_json
from alysia.creator.models import (
    ClaimClassification,
    CreatorClaimTrace,
    CreatorJob,
    EvidenceStatus,
    ResearchEvidenceStatus,
    ResearchSourceTrace,
)
from alysia.creator.store import CreatorJobStore
from alysia.creator.topics import TopicCandidate
from alysia.knowledge.models import stable_id
from alysia.security.network import NetworkPolicy
from alysia.security.redaction import Redactor


ResearchSourceType = Literal["web", "document", "manual", "mock"]
_SECRET_QUERY_KEY = re.compile(r"(?i)token|api[_-]?key|authorization|cookie|session|password|secret")


def research_now() -> datetime:
    return datetime.now().astimezone()


class SourceReliability(str, Enum):
    PRIMARY = "PRIMARY"
    OFFICIAL = "OFFICIAL"
    ESTABLISHED_SECONDARY = "ESTABLISHED_SECONDARY"
    COMMUNITY = "COMMUNITY"
    UNKNOWN = "UNKNOWN"


RELIABILITY_SCORES: dict[SourceReliability, float] = {
    SourceReliability.PRIMARY: 0.90,
    SourceReliability.OFFICIAL: 0.85,
    SourceReliability.ESTABLISHED_SECONDARY: 0.72,
    SourceReliability.COMMUNITY: 0.45,
    SourceReliability.UNKNOWN: 0.20,
}


class ResearchLimits(BaseModel):
    max_sources: int = Field(default=12, ge=1, le=100)
    max_claims: int = Field(default=40, ge=1, le=500)
    max_excerpt_chars: int = Field(default=2_000, ge=64, le=20_000)
    max_artifact_chars: int = Field(default=100_000, ge=256, le=1_000_000)
    max_metadata_bytes: int = Field(default=4_096, ge=128, le=65_536)


def validate_research_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.username or parsed.password:
        raise ValueError("research URL must not contain credentials")
    if any(_SECRET_QUERY_KEY.search(key) for key, _ in parse_qsl(parsed.query, keep_blank_values=True)):
        raise ValueError("research URL must not contain credential query parameters")
    decision = NetworkPolicy().check("ResearcherAgent", value)
    if not decision.allowed:
        raise ValueError(f"research URL blocked by network policy: {decision.reason}")
    return value


class ResearchSource(BaseModel):
    source_id: str = Field(min_length=1)
    url: str = Field(min_length=1)
    title: str = Field(min_length=1)
    publisher: str = Field(min_length=1)
    source_type: ResearchSourceType
    retrieved_at: datetime = Field(default_factory=research_now)
    published_at: datetime | None = None
    content_excerpt: str = ""
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    reliability: SourceReliability = SourceReliability.UNKNOWN
    metadata: dict[str, object] = Field(default_factory=dict)

    @field_validator("url")
    @classmethod
    def safe_public_url(cls, value: str) -> str:
        return validate_research_url(value)

    @classmethod
    def from_content(
        cls,
        *,
        url: str,
        title: str,
        publisher: str,
        source_type: ResearchSourceType,
        content: str,
        reliability: SourceReliability = SourceReliability.UNKNOWN,
        published_at: datetime | None = None,
        metadata: Mapping[str, object] | None = None,
        limits: ResearchLimits | None = None,
        redactor: Redactor | None = None,
    ) -> "ResearchSource":
        limits = limits or ResearchLimits()
        redactor = redactor or Redactor()
        safe_metadata = redactor.redact_value(dict(metadata or {}))
        encoded_metadata = json.dumps(safe_metadata, ensure_ascii=False, default=str).encode("utf-8")
        if len(encoded_metadata) > limits.max_metadata_bytes:
            safe_metadata = {
                "truncated": True,
                "metadata_hash": hashlib.sha256(encoded_metadata).hexdigest(),
            }
        safe_content = redactor.redact(content)
        excerpt = safe_content[: limits.max_excerpt_chars]
        if len(safe_content) > limits.max_excerpt_chars:
            excerpt += "\n[TRUNCATED; full bounded artifact stored separately]"
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        return cls(
            source_id=stable_id("source", url, content_hash),
            url=url,
            title=redactor.redact(title),
            publisher=redactor.redact(publisher),
            source_type=source_type,
            published_at=published_at,
            content_excerpt=excerpt,
            content_hash=content_hash,
            reliability=reliability,
            metadata=safe_metadata,
        )


class Claim(BaseModel):
    claim_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    claim_type: ClaimClassification
    confidence: float = Field(default=0, ge=0, le=1)
    source_refs: list[str] = Field(default_factory=list)
    evidence_status: EvidenceStatus = EvidenceStatus.UNVERIFIED
    notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def supported_fact_has_source(self) -> "Claim":
        if (
            self.claim_type == ClaimClassification.VERIFIED_FACT
            and self.evidence_status == EvidenceStatus.SUPPORTED
            and not self.source_refs
        ):
            raise ValueError("VERIFIED_FACT + SUPPORTED requires source_refs")
        return self

    @classmethod
    def create(
        cls,
        *,
        text: str,
        claim_type: ClaimClassification,
        source_refs: Iterable[str] = (),
        confidence: float = 0,
        notes: Iterable[str] = (),
    ) -> "Claim":
        refs = list(dict.fromkeys(source_refs))
        return cls(
            claim_id=stable_id("claim", text, *refs),
            text=text,
            claim_type=claim_type,
            confidence=confidence,
            source_refs=refs,
            notes=list(notes),
        )


class GroundingResult(BaseModel):
    claims: list[Claim]
    source_refs: list[str] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)


class ClaimExtractor:
    def __init__(self, limits: ResearchLimits | None = None) -> None:
        self.limits = limits or ResearchLimits()

    def extract(
        self,
        source: ResearchSource,
        statements: Iterable[str],
        *,
        claim_type: ClaimClassification = ClaimClassification.UNKNOWN,
    ) -> list[Claim]:
        values = [statement.strip() for statement in statements if statement.strip()]
        if len(values) > self.limits.max_claims:
            raise ValueError(f"claim count exceeds configured limit: {self.limits.max_claims}")
        return [
            Claim.create(
                text=statement,
                claim_type=claim_type,
                source_refs=[source.source_id],
                confidence=0.5,
                notes=["extracted_from_source"],
            )
            for statement in values
        ]


class GroundingService:
    def __init__(self, limits: ResearchLimits | None = None) -> None:
        self.limits = limits or ResearchLimits()

    def ground(
        self,
        claims: Iterable[Claim],
        sources: Iterable[ResearchSource],
        *,
        contradicting_source_refs: Mapping[str, Iterable[str]] | None = None,
    ) -> GroundingResult:
        claim_items = list(claims)
        source_items = list(sources)
        if len(source_items) > self.limits.max_sources:
            raise ValueError(f"source count exceeds configured limit: {self.limits.max_sources}")
        if len(claim_items) > self.limits.max_claims:
            raise ValueError(f"claim count exceeds configured limit: {self.limits.max_claims}")
        source_by_id = {source.source_id: source for source in source_items}
        conflicts = {key: set(value) for key, value in (contradicting_source_refs or {}).items()}
        grounded = [self._ground_claim(claim, source_by_id, conflicts.get(claim.claim_id, set())) for claim in claim_items]
        uncertainties = [
            f"{claim.claim_id}: {claim.evidence_status.value}"
            for claim in grounded
            if claim.evidence_status in {
                EvidenceStatus.CONFLICTING,
                EvidenceStatus.INSUFFICIENT_EVIDENCE,
                EvidenceStatus.UNVERIFIED,
            }
        ]
        return GroundingResult(
            claims=grounded,
            source_refs=sorted(source_by_id),
            uncertainties=uncertainties,
        )

    @staticmethod
    def _ground_claim(
        claim: Claim,
        source_by_id: Mapping[str, ResearchSource],
        contradicting_refs: set[str],
    ) -> Claim:
        if claim.claim_type == ClaimClassification.CREATIVE_CONTENT and not claim.source_refs:
            return claim.model_copy(update={
                "evidence_status": EvidenceStatus.SUPPORTED,
                "notes": [*claim.notes, "creative_content_does_not_require_factual_source"],
            })

        missing = [ref for ref in claim.source_refs if ref not in source_by_id]
        usable = [
            source_by_id[ref]
            for ref in claim.source_refs
            if ref in source_by_id and source_by_id[ref].metadata.get("available", True) is not False
        ]
        notes = list(claim.notes)
        if missing:
            notes.append("missing_sources=" + ",".join(sorted(missing)))
        unavailable = [
            ref for ref in claim.source_refs
            if ref in source_by_id and source_by_id[ref].metadata.get("available", True) is False
        ]
        if unavailable:
            notes.append("unavailable_sources=" + ",".join(sorted(unavailable)))
        if not usable:
            return claim.model_copy(update={
                "evidence_status": EvidenceStatus.INSUFFICIENT_EVIDENCE,
                "confidence": min(claim.confidence, 0.2),
                "notes": notes or ["no_usable_source"],
            })
        if contradicting_refs.intersection(source.source_id for source in usable):
            return claim.model_copy(update={
                "evidence_status": EvidenceStatus.CONFLICTING,
                "confidence": min(claim.confidence, 0.5),
                "notes": [*notes, "conflicting_sources_present"],
            })
        scores = [RELIABILITY_SCORES[source.reliability] for source in usable]
        status = (
            EvidenceStatus.PARTIALLY_SUPPORTED
            if all(source.reliability == SourceReliability.UNKNOWN for source in usable)
            else EvidenceStatus.SUPPORTED
        )
        return claim.model_copy(update={
            "evidence_status": status,
            "confidence": min(claim.confidence, sum(scores) / len(scores)),
            "notes": notes,
        })


class ResearchArtifactStore:
    def __init__(
        self,
        root: Path,
        limits: ResearchLimits | None = None,
        redactor: Redactor | None = None,
    ) -> None:
        self.root = root.resolve()
        self.limits = limits or ResearchLimits()
        self.redactor = redactor or Redactor()
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, source_id: str) -> Path:
        if not re.fullmatch(r"source_[0-9a-f]{16}", source_id):
            raise ValueError("invalid research source_id")
        return self.root / f"{source_id}.json"

    def save_source(self, source: ResearchSource, raw_content: str) -> Path:
        safe_content = self.redactor.redact(raw_content)
        truncated = len(safe_content) > self.limits.max_artifact_chars
        payload = {
            "source": source.model_dump(mode="json"),
            "content": safe_content[: self.limits.max_artifact_chars],
            "artifact_truncated": truncated,
            "stored_at": research_now().isoformat(),
        }
        path = self.path_for(source.source_id)
        atomic_write_json(path, self.redactor.redact_value(payload))
        return path


class CreatorJobResearchIntegrator:
    def __init__(
        self,
        store: CreatorJobStore,
        artifacts: ResearchArtifactStore,
        limits: ResearchLimits | None = None,
    ) -> None:
        self.store = store
        self.artifacts = artifacts
        self.limits = limits or ResearchLimits()

    def apply(
        self,
        job_id: str,
        *,
        selected_topic: TopicCandidate,
        sources: Iterable[ResearchSource],
        grounding: GroundingResult,
        raw_contents: Mapping[str, str] | None = None,
    ) -> CreatorJob:
        if selected_topic.rejection_reason:
            raise ValueError("rejected TopicCandidate cannot be selected")
        source_items = list(sources)
        if len(source_items) > self.limits.max_sources:
            raise ValueError(f"source count exceeds configured limit: {self.limits.max_sources}")
        if len(grounding.claims) > self.limits.max_claims:
            raise ValueError(f"claim count exceeds configured limit: {self.limits.max_claims}")
        raw_contents = raw_contents or {}
        paths = {
            source.source_id: self.artifacts.save_source(
                source,
                raw_contents.get(source.source_id, source.content_excerpt),
            )
            for source in source_items
        }
        traces = [
            ResearchSourceTrace(
                source_id=source.source_id,
                source=source.url,
                retrieved_at=source.retrieved_at,
                claim=source.content_excerpt[:240] or source.title,
                confidence=RELIABILITY_SCORES[source.reliability],
                source_type=source.source_type,
                evidence_path=paths[source.source_id],
                reliability=source.reliability.value,
                content_hash=source.content_hash,
            )
            for source in source_items
        ]
        claim_traces = [
            CreatorClaimTrace(
                claim_id=claim.claim_id,
                claim=claim.text,
                classification=claim.claim_type,
                confidence=claim.confidence,
                source_refs=claim.source_refs,
                evidence_status=claim.evidence_status,
                notes=claim.notes,
                conflicted=claim.evidence_status == EvidenceStatus.CONFLICTING,
                note=f"grounding={claim.evidence_status.value}",
            )
            for claim in grounding.claims
        ]
        incomplete = any(
            claim.evidence_status in {
                EvidenceStatus.CONFLICTING,
                EvidenceStatus.INSUFFICIENT_EVIDENCE,
                EvidenceStatus.UNVERIFIED,
            }
            for claim in grounding.claims
        )
        return self.store.update(
            job_id,
            {
                "topic": selected_topic.title,
                "topic_source": selected_topic.source,
                "topic_score": selected_topic.score * 100,
                "research_sources": traces,
                "claims": claim_traces,
                "research_status": (
                    ResearchEvidenceStatus.INSUFFICIENT_EVIDENCE
                    if incomplete else ResearchEvidenceStatus.SUFFICIENT
                ),
                "uncertainties": grounding.uncertainties,
            },
            reason="Alpha22 Step 2 topic selection and grounded research",
            updated_by="system:topic_research",
        )
