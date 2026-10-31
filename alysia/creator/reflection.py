from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Mapping

from pydantic import BaseModel, Field, field_validator, model_validator

from alysia.core.io import atomic_write_json
from alysia.creator.observation import (
    METRIC_NAMES,
    ContentObservation,
    MetricAvailability,
    ObservationSourceType,
    ObservationStore,
)
from alysia.creator.store import CreatorJobStore
from alysia.security.audit import AuditLog
from alysia.security.redaction import Redactor
from alysia.schemas.security import Permission


def reflection_now() -> datetime:
    return datetime.now().astimezone()


def _stable_id(prefix: str, *parts: object) -> str:
    payload = "\x1f".join(str(part) for part in parts)
    return f"{prefix}_{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:16]}"


class ReflectionStatus(str, Enum):
    COMPLETE = "COMPLETE"
    INSUFFICIENT_OBSERVATION = "INSUFFICIENT_OBSERVATION"


class ObservedFact(BaseModel):
    classification: str = "OBSERVED_FACT"
    statement: str = Field(min_length=1)
    evidence_refs: list[str] = Field(min_length=1)
    observed_at: datetime


class ReflectionInterpretation(BaseModel):
    classification: str = "MODEL_INTERPRETATION"
    statement: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    evidence_refs: list[str] = Field(min_length=1)
    alternative_explanations: list[str] = Field(min_length=1)


class ReflectionHypothesis(BaseModel):
    classification: str = "HYPOTHESIS"
    statement: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    evidence_refs: list[str] = Field(min_length=1)
    alternative_explanations: list[str] = Field(min_length=1)


class CreatorReflection(BaseModel):
    reflection_id: str | None = None
    job_id: str | None = None
    job_revision: int | None = Field(default=None, ge=1)
    platform_content_id: str | None = None
    created_at: datetime = Field(default_factory=reflection_now)
    status: ReflectionStatus = ReflectionStatus.COMPLETE
    attempt_summary: str = ""
    observed_facts: list[ObservedFact] = Field(default_factory=list)
    interpretations: list[ReflectionInterpretation] = Field(default_factory=list)
    hypotheses: list[ReflectionHypothesis] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)
    what_worked: list[str] = Field(default_factory=list)
    what_did_not_work: list[str] = Field(default_factory=list)
    recommended_changes: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    observation_refs: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0, ge=0, le=1)
    memory_candidates: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    # Alpha22 Step 1 compatibility fields.
    attempted: str = ""
    actual: str = ""
    worked: list[str] = Field(default_factory=list)
    likely_failed: list[str] = Field(default_factory=list)
    supporting_evidence: list[str] = Field(default_factory=list)
    next_changes: list[str] = Field(default_factory=list)
    facts: list[str] = Field(default_factory=list)

    @field_validator(
        "uncertainties",
        "what_worked",
        "what_did_not_work",
        "recommended_changes",
        "evidence_refs",
        "observation_refs",
        "memory_candidates",
        "worked",
        "likely_failed",
        "supporting_evidence",
        "next_changes",
        "facts",
        mode="before",
    )
    @classmethod
    def redact_string_lists(cls, value: object) -> list[str]:
        values = value if isinstance(value, list) else []
        redactor = Redactor()
        return [redactor.redact(str(item)) for item in values]

    @field_validator("metadata", mode="before")
    @classmethod
    def redact_metadata(cls, value: object) -> dict[str, Any]:
        return Redactor().redact_value(dict(value)) if isinstance(value, Mapping) else {}

    @model_validator(mode="after")
    def compatibility_and_boundaries(self) -> "CreatorReflection":
        self.attempt_summary = self.attempt_summary or self.attempted
        self.attempted = self.attempted or self.attempt_summary
        self.what_worked = self.what_worked or self.worked
        self.worked = self.worked or self.what_worked
        self.what_did_not_work = self.what_did_not_work or self.likely_failed
        self.likely_failed = self.likely_failed or self.what_did_not_work
        self.recommended_changes = self.recommended_changes or self.next_changes
        self.next_changes = self.next_changes or self.recommended_changes
        self.evidence_refs = list(dict.fromkeys(self.evidence_refs + self.supporting_evidence))
        self.supporting_evidence = self.supporting_evidence or self.evidence_refs
        self.facts = self.facts or [item.statement for item in self.observed_facts]
        if not self.actual and self.observed_facts:
            self.actual = "; ".join(item.statement for item in self.observed_facts[:3])
        if self.interpretations and not self.uncertainties:
            raise ValueError("interpretations require explicit uncertainties")
        known_refs = set(self.observation_refs + self.evidence_refs)
        for item in [*self.interpretations, *self.hypotheses]:
            if not set(item.evidence_refs).issubset(known_refs):
                raise ValueError("interpretation/hypothesis contains unknown evidence refs")
        if self.status == ReflectionStatus.INSUFFICIENT_OBSERVATION and not self.uncertainties:
            raise ValueError("INSUFFICIENT_OBSERVATION requires explicit uncertainty")
        if self.job_id and self.job_revision and self.platform_content_id:
            self.reflection_id = self.reflection_id or _stable_id(
                "reflection",
                self.job_id,
                self.job_revision,
                self.platform_content_id,
                *self.observation_refs,
            )
        return self


class ReflectionStore:
    _SAFE = re.compile(r"^[A-Za-z0-9_.-]+$")

    def __init__(self, root: Path, *, environment: str, redactor: Redactor | None = None) -> None:
        if environment not in {"production", "test"}:
            raise ValueError("reflection environment must be production or test")
        self.environment = environment
        self.root = root.resolve() / environment / "reflections"
        self.root.mkdir(parents=True, exist_ok=True)
        self.redactor = redactor or Redactor()

    def save(self, reflection: CreatorReflection) -> Path:
        if not reflection.reflection_id:
            raise ValueError("persisted reflection requires reflection_id")
        is_test = bool(reflection.metadata.get("test_only"))
        if self.environment == "test" and not is_test:
            raise ValueError("test ReflectionStore only accepts TEST_ONLY")
        if self.environment == "production" and is_test:
            raise ValueError("TEST_ONLY reflection cannot enter production storage")
        path = self._path(reflection.reflection_id)
        payload = self.redactor.redact_value(reflection.model_dump(mode="json"))
        if path.is_file():
            existing = CreatorReflection.model_validate_json(path.read_text(encoding="utf-8"))
            if existing != reflection:
                raise FileExistsError("reflection_id already exists with different content")
            return path
        return atomic_write_json(path, payload, backup_count=2)

    def load(self, reflection_id: str) -> CreatorReflection:
        return CreatorReflection.model_validate_json(self._path(reflection_id).read_text(encoding="utf-8"))

    def history(self, job_id: str) -> list[CreatorReflection]:
        items: list[CreatorReflection] = []
        for path in self.root.glob("reflection_*.json"):
            try:
                item = CreatorReflection.model_validate_json(path.read_text(encoding="utf-8"))
            except ValueError:
                continue
            if item.job_id == job_id:
                items.append(item)
        return sorted(items, key=lambda item: (item.created_at, item.reflection_id or ""))

    def attach_memory_candidate(self, reflection_id: str, candidate_id: str) -> CreatorReflection:
        reflection = self.load(reflection_id)
        if candidate_id not in reflection.memory_candidates:
            reflection.memory_candidates.append(candidate_id)
            atomic_write_json(
                self._path(reflection_id),
                self.redactor.redact_value(reflection.model_dump(mode="json")),
                backup_count=2,
            )
        return reflection

    def reference(self, reflection: CreatorReflection) -> str:
        return f"reflection:{self.environment}:{reflection.reflection_id}"

    def _path(self, reflection_id: str) -> Path:
        if not self._SAFE.fullmatch(reflection_id):
            raise ValueError("invalid reflection_id")
        return self.root / f"{reflection_id}.json"


class CreatorReflectionService:
    def __init__(
        self,
        *,
        jobs: CreatorJobStore,
        observations: ObservationStore,
        reflections: ReflectionStore,
        audit: AuditLog,
    ) -> None:
        self.jobs = jobs
        self.observations = observations
        self.reflections = reflections
        self.audit = audit

    def create(
        self,
        *,
        job_id: str,
        job_revision: int,
        platform_content_id: str,
        interpretations: Iterable[ReflectionInterpretation] = (),
        hypotheses: Iterable[ReflectionHypothesis] = (),
        uncertainties: Iterable[str] = (),
        what_worked: Iterable[str] = (),
        what_did_not_work: Iterable[str] = (),
        recommended_changes: Iterable[str] = (),
        confidence: float = 0.5,
        metadata: Mapping[str, Any] | None = None,
    ) -> CreatorReflection:
        job = self.jobs.load(job_id)
        if job.current_revision != job_revision:
            raise ValueError("reflection revision does not match CreatorJob")
        history = [
            item
            for item in self.observations.history(job_id)
            if item.job_revision == job_revision and item.platform_content_id == platform_content_id
        ]
        if not history:
            raise ValueError("reflection requires at least one valid observation")
        observation_refs = [self.observations.reference(item) for item in history]
        facts = self._facts(history, observation_refs)
        available_count = sum(
            1
            for item in history
            for name in METRIC_NAMES
            if item.metrics.availability[name] == MetricAvailability.AVAILABLE
        )
        status = (
            ReflectionStatus.COMPLETE
            if available_count >= 2
            else ReflectionStatus.INSUFFICIENT_OBSERVATION
        )
        uncertainty_items = list(uncertainties)
        if status == ReflectionStatus.INSUFFICIENT_OBSERVATION:
            uncertainty_items.append("Available observations are insufficient for a broad conclusion.")
        test_only = all(item.source_type == ObservationSourceType.TEST_FIXTURE for item in history)
        reflection = CreatorReflection(
            job_id=job_id,
            job_revision=job_revision,
            platform_content_id=platform_content_id,
            status=status,
            attempt_summary=(
                f"CreatorJob {job_id} revision {job_revision} attempted '{job.selected_title or job.topic}'."
            ),
            observed_facts=facts,
            interpretations=list(interpretations),
            hypotheses=list(hypotheses),
            uncertainties=list(dict.fromkeys(uncertainty_items)),
            what_worked=list(what_worked),
            what_did_not_work=list(what_did_not_work),
            recommended_changes=list(recommended_changes),
            evidence_refs=observation_refs,
            observation_refs=observation_refs,
            confidence=min(confidence, 0.5) if status == ReflectionStatus.INSUFFICIENT_OBSERVATION else confidence,
            metadata={
                **dict(metadata or {}),
                "test_only": test_only,
                "source_types": sorted({item.source_type.value for item in history}),
            },
        )
        self.reflections.save(reflection)
        job.reflection_ref = self.reflections.reference(reflection)
        job.updated_at = reflection_now()
        self.jobs.save(job)
        self.audit.record(
            actor="system:creator_reflection",
            action="REFLECTION_CREATED",
            resource=f"creator-job:{job_id}",
            permission=Permission.WRITE_ARTIFACT,
            decision="allow",
            result=reflection.status.value,
            correlation_id=reflection.reflection_id,
            run_id=job.run_id,
            context={
                "job_revision": job_revision,
                "observation_count": len(history),
                "test_only": test_only,
            },
        )
        return reflection

    @staticmethod
    def _facts(
        observations: list[ContentObservation],
        observation_refs: list[str],
    ) -> list[ObservedFact]:
        facts: list[ObservedFact] = []
        for observation, reference in zip(observations, observation_refs, strict=True):
            for name in METRIC_NAMES:
                if observation.metrics.availability[name] != MetricAvailability.AVAILABLE:
                    continue
                value = getattr(observation.metrics, name)
                facts.append(
                    ObservedFact(
                        statement=(
                            f"{name}={value} observed for {observation.platform_content_id} "
                            f"at {observation.observed_at.isoformat()}."
                        ),
                        evidence_refs=[reference],
                        observed_at=observation.observed_at,
                    )
                )
        return facts
