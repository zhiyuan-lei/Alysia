from __future__ import annotations

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Mapping

from pydantic import BaseModel, Field, field_validator

from alysia.core.io import atomic_write_json
from alysia.creator.models import CreatorJob
from alysia.creator.observation import ObservationSourceType
from alysia.creator.reflection import CreatorReflection, ReflectionStore
from alysia.creator.store import CreatorJobStore
from alysia.learning.memory import MemoryStore
from alysia.schemas import EpisodeMemory, LessonCandidate
from alysia.schemas.security import Permission
from alysia.security.audit import AuditLog
from alysia.security.redaction import Redactor


class CreatorMemoryIntegrator:
    """Writes a compact episodic record; raw evidence remains in job/run artifacts."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.episodes_dir = self.root / "creator_episodes"
        self.episodes_dir.mkdir(parents=True, exist_ok=True)

    def record(self, job: CreatorJob, store: CreatorJobStore) -> CreatorJob:
        if job.status != "PUBLISHED" or not job.reflection:
            raise ValueError("creator memory requires a PUBLISHED job with reflection")
        latest = job.metrics[-1] if job.metrics else None
        episode = {
            "job_id": job.job_id,
            "run_id": job.run_id,
            "topic": job.topic,
            "platform": job.platform,
            "platform_content_id": job.platform_content_id,
            "published_at": job.published_at,
            "source": "testing" if job.testing or job.dry_run else "platform",
            "attempted": job.reflection.attempted,
            "actual": job.reflection.actual,
            "facts": job.reflection.facts,
            "interpretations": job.reflection.interpretations,
            "uncertainties": job.reflection.uncertainties,
            "next_changes": job.reflection.next_changes,
            "latest_metrics": (
                {
                    "observed_at": latest.observed_at,
                    "views": latest.views,
                    "likes": latest.likes,
                    "comments": latest.comments,
                    "favorites": latest.favorites,
                    "shares": latest.shares,
                    "followers_delta": latest.followers_delta,
                    "availability": latest.availability,
                }
                if latest
                else None
            ),
            "evidence_refs": [str(path) for path in job.evidence_paths],
            "created_at": datetime.now().astimezone(),
            "semantic_promotion": "not_attempted_single_episode",
        }
        path = self.episodes_dir / f"{job.job_id}.json"
        atomic_write_json(path, episode, backup_count=2)
        reference = str(path.resolve())
        if reference not in job.memory_refs:
            job.memory_refs.append(reference)
            job.updated_at = datetime.now().astimezone()
            store.save(job)
        return job

    def real_episode_count(self) -> int:
        count = 0
        for path in self.episodes_dir.glob("creator_*.json"):
            import json

            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if payload.get("source") == "platform":
                count += 1
        return count


class MemoryType(str, Enum):
    EPISODIC = "EPISODIC"
    SEMANTIC = "SEMANTIC"


class MemoryCandidateStatus(str, Enum):
    CANDIDATE = "CANDIDATE"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    CONTRADICTED = "CONTRADICTED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


def _candidate_id(job_id: str, reflection_id: str, memory_type: MemoryType, statement: str) -> str:
    import hashlib

    value = "\x1f".join((job_id, reflection_id, memory_type.value, statement.casefold().strip()))
    return f"memory_candidate_{hashlib.sha256(value.encode('utf-8')).hexdigest()[:16]}"


class MemoryCandidate(BaseModel):
    candidate_id: str | None = None
    job_id: str = Field(pattern=r"^creator_[0-9a-f]{16}$")
    reflection_id: str = Field(pattern=r"^reflection_[0-9a-f]{16}$")
    memory_type: MemoryType
    statement: str = Field(min_length=1, max_length=1000)
    evidence_refs: list[str] = Field(min_length=1)
    support_count: int = Field(default=1, ge=1)
    confidence: float = Field(ge=0, le=1)
    novelty: float = Field(default=1.0, ge=0, le=1)
    importance: float = Field(default=0.5, ge=0, le=1)
    contradiction_refs: list[str] = Field(default_factory=list)
    status: MemoryCandidateStatus = MemoryCandidateStatus.CANDIDATE
    created_at: datetime = Field(default_factory=lambda: datetime.now().astimezone())
    source_type: ObservationSourceType
    support_job_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("statement", mode="before")
    @classmethod
    def redact_statement(cls, value: object) -> str:
        return Redactor().redact(str(value))

    @field_validator("evidence_refs", "contradiction_refs", mode="before")
    @classmethod
    def redact_refs(cls, value: object) -> list[str]:
        values = value if isinstance(value, list) else []
        redactor = Redactor()
        return [redactor.redact(str(item)) for item in values]

    @field_validator("metadata", mode="before")
    @classmethod
    def redact_metadata(cls, value: object) -> dict[str, Any]:
        return Redactor().redact_value(dict(value)) if isinstance(value, Mapping) else {}

    def model_post_init(self, context: Any) -> None:
        del context
        self.candidate_id = self.candidate_id or _candidate_id(
            self.job_id, self.reflection_id, self.memory_type, self.statement
        )
        self.support_job_ids = list(dict.fromkeys(self.support_job_ids or [self.job_id]))


class MemoryCandidateStore:
    def __init__(self, root: Path, *, environment: str, redactor: Redactor | None = None) -> None:
        if environment not in {"production", "test"}:
            raise ValueError("memory environment must be production or test")
        self.environment = environment
        self.root = root.resolve() / environment / "creator_candidates"
        self.root.mkdir(parents=True, exist_ok=True)
        self.redactor = redactor or Redactor()

    def save(self, candidate: MemoryCandidate) -> Path:
        self._validate_environment(candidate)
        path = self._path(candidate.candidate_id or "")
        payload = self.redactor.redact_value(candidate.model_dump(mode="json"))
        return atomic_write_json(path, payload, backup_count=2)

    def load(self, candidate_id: str) -> MemoryCandidate:
        return MemoryCandidate.model_validate_json(self._path(candidate_id).read_text(encoding="utf-8"))

    def all(self) -> list[MemoryCandidate]:
        items: list[MemoryCandidate] = []
        for path in self.root.glob("memory_candidate_*.json"):
            try:
                items.append(MemoryCandidate.model_validate_json(path.read_text(encoding="utf-8")))
            except ValueError:
                continue
        return sorted(items, key=lambda item: (item.created_at, item.candidate_id or ""))

    def _path(self, candidate_id: str) -> Path:
        import re

        if not re.fullmatch(r"memory_candidate_[0-9a-f]{16}", candidate_id):
            raise ValueError("invalid memory candidate id")
        return self.root / f"{candidate_id}.json"

    def _validate_environment(self, candidate: MemoryCandidate) -> None:
        if self.environment == "test" and candidate.source_type != ObservationSourceType.TEST_FIXTURE:
            raise ValueError("test memory store only accepts TEST_FIXTURE")
        if self.environment == "production" and candidate.source_type == ObservationSourceType.TEST_FIXTURE:
            raise ValueError("TEST_FIXTURE cannot enter production memory")


class CreatorMemoryGate:
    def __init__(
        self,
        root: Path,
        *,
        environment: str,
        jobs: CreatorJobStore,
        reflections: ReflectionStore,
        audit: AuditLog,
        semantic_support_threshold: int = 3,
        semantic_confidence_threshold: float = 0.65,
        minimum_novelty: float = 0.2,
        minimum_importance: float = 0.2,
    ) -> None:
        if semantic_support_threshold < 2:
            raise ValueError("semantic support threshold must require multiple CreatorJobs")
        self.environment = environment
        self.jobs = jobs
        self.reflections = reflections
        self.audit = audit
        self.semantic_support_threshold = semantic_support_threshold
        self.semantic_confidence_threshold = semantic_confidence_threshold
        self.minimum_novelty = minimum_novelty
        self.minimum_importance = minimum_importance
        self.candidates = MemoryCandidateStore(root, environment=environment)
        self.memory = MemoryStore(root.resolve() / environment)

    def create_candidate(
        self,
        *,
        reflection_id: str,
        memory_type: MemoryType,
        statement: str,
        evidence_refs: list[str] | None = None,
        confidence: float,
        novelty: float = 1.0,
        importance: float = 0.5,
        contradiction_refs: list[str] | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> MemoryCandidate:
        reflection = self.reflections.load(reflection_id)
        if not reflection.job_id:
            raise ValueError("memory candidate requires a job-bound reflection")
        refs = list(evidence_refs or reflection.evidence_refs)
        if not refs or not set(refs).issubset(set(reflection.evidence_refs)):
            raise ValueError("memory evidence must be traceable to the reflection")
        source_types = set(reflection.metadata.get("source_types", []))
        if reflection.metadata.get("test_only"):
            source_type = ObservationSourceType.TEST_FIXTURE
        elif source_types == {ObservationSourceType.REAL_PLATFORM.value}:
            source_type = ObservationSourceType.REAL_PLATFORM
        else:
            source_type = ObservationSourceType.MANUAL_IMPORT
        candidate = MemoryCandidate(
            job_id=reflection.job_id,
            reflection_id=reflection_id,
            memory_type=memory_type,
            statement=statement,
            evidence_refs=refs,
            confidence=confidence,
            novelty=novelty,
            importance=importance,
            contradiction_refs=list(contradiction_refs or []),
            source_type=source_type,
            metadata={**dict(metadata or {}), "test_only": source_type == ObservationSourceType.TEST_FIXTURE},
        )
        try:
            existing = self.candidates.load(candidate.candidate_id or "")
        except FileNotFoundError:
            existing = None
        if existing is not None:
            immutable = {
                "job_id",
                "reflection_id",
                "memory_type",
                "statement",
                "evidence_refs",
                "confidence",
                "novelty",
                "importance",
                "contradiction_refs",
                "source_type",
            }
            if any(getattr(existing, field) != getattr(candidate, field) for field in immutable):
                raise FileExistsError("memory candidate identity conflicts with existing content")
            self.reflections.attach_memory_candidate(reflection_id, existing.candidate_id or "")
            return existing
        self.candidates.save(candidate)
        self.reflections.attach_memory_candidate(reflection_id, candidate.candidate_id or "")
        self._audit("MEMORY_CANDIDATE_CREATED", candidate, result="candidate")
        return candidate

    def evaluate(self, candidate_id: str) -> MemoryCandidate:
        candidate = self.candidates.load(candidate_id)
        reflection = self.reflections.load(candidate.reflection_id)
        if reflection.job_id != candidate.job_id or not candidate.evidence_refs:
            return self._finish(candidate, MemoryCandidateStatus.REJECTED, "invalid_provenance")
        if candidate.contradiction_refs:
            self._audit("MEMORY_CONTRADICTION_FOUND", candidate, result="contradicted")
            return self._finish(candidate, MemoryCandidateStatus.CONTRADICTED, "contradiction_found")
        if candidate.novelty < self.minimum_novelty:
            return self._finish(candidate, MemoryCandidateStatus.REJECTED, "duplicate_or_low_novelty")
        if candidate.importance < self.minimum_importance:
            return self._finish(candidate, MemoryCandidateStatus.REJECTED, "low_importance")
        if candidate.memory_type == MemoryType.EPISODIC:
            return self._accept_episodic(candidate)
        return self._evaluate_semantic(candidate)

    def _evaluate_semantic(self, candidate: MemoryCandidate) -> MemoryCandidate:
        normalized = self._normalize(candidate.statement)
        all_candidates = self.candidates.all()
        accepted_duplicate = next(
            (
                item
                for item in all_candidates
                if item.candidate_id != candidate.candidate_id
                and item.memory_type == MemoryType.SEMANTIC
                and item.status == MemoryCandidateStatus.ACCEPTED
                and self._normalize(item.statement) == normalized
            ),
            None,
        )
        if accepted_duplicate is not None:
            candidate.metadata["duplicate_of"] = accepted_duplicate.candidate_id
            return self._finish(candidate, MemoryCandidateStatus.REJECTED, "duplicate_memory")
        supporting = [
            item
            for item in all_candidates
            if item.memory_type == MemoryType.SEMANTIC
            and not item.contradiction_refs
            and self._normalize(item.statement) == normalized
        ]
        by_job = {item.job_id: item for item in supporting}
        candidate.support_job_ids = sorted(by_job)
        candidate.support_count = len(by_job)
        aggregate_confidence = sum(item.confidence for item in by_job.values()) / max(1, len(by_job))
        candidate.metadata["aggregate_confidence"] = round(aggregate_confidence, 4)
        if aggregate_confidence < self.semantic_confidence_threshold:
            return self._finish(candidate, MemoryCandidateStatus.REVIEW_REQUIRED, "low_confidence")
        if candidate.support_count < self.semantic_support_threshold:
            return self._finish(candidate, MemoryCandidateStatus.CANDIDATE, "insufficient_distinct_jobs")
        source = {
            ObservationSourceType.TEST_FIXTURE: "testing",
            ObservationSourceType.REAL_PLATFORM: "platform",
            ObservationSourceType.MANUAL_IMPORT: "manual",
        }[candidate.source_type]
        lesson_candidate = LessonCandidate(
            statement=candidate.statement,
            category="creator_reflection",
            scope="creator_loop",
            supporting_metrics={},
            confidence=aggregate_confidence,
        )
        for job_id in candidate.support_job_ids:
            self.memory.upsert_lesson(lesson_candidate, job_id, source)
        return self._finish(candidate, MemoryCandidateStatus.ACCEPTED, "semantic_threshold_met")

    def _accept_episodic(self, candidate: MemoryCandidate) -> MemoryCandidate:
        job = self.jobs.load(candidate.job_id)
        source = {
            ObservationSourceType.TEST_FIXTURE: "testing",
            ObservationSourceType.REAL_PLATFORM: "platform",
            ObservationSourceType.MANUAL_IMPORT: "manual",
        }[candidate.source_type]
        self.memory.record_episode(
            EpisodeMemory(
                run_id=candidate.candidate_id or candidate.job_id,
                topic=job.topic,
                source=source,
                metrics_summary={
                    "job_id": candidate.job_id,
                    "reflection_id": candidate.reflection_id,
                    "evidence_refs": "|".join(candidate.evidence_refs),
                    "observation_count": len(job.observation_refs),
                    "latest_observation_ref": job.observation_refs[-1] if job.observation_refs else None,
                },
                fingerprint_summary={"job_revision": job.current_revision},
                analysis_summary=candidate.statement,
                created_at=datetime.now().astimezone(),
            )
        )
        return self._finish(candidate, MemoryCandidateStatus.ACCEPTED, "episodic_provenance_valid")

    def _finish(
        self,
        candidate: MemoryCandidate,
        status: MemoryCandidateStatus,
        reason: str,
    ) -> MemoryCandidate:
        candidate.status = status
        candidate.metadata["gate_reason"] = reason
        self.candidates.save(candidate)
        if status == MemoryCandidateStatus.ACCEPTED:
            reference = f"memory:{self.environment}:{candidate.candidate_id}"
            target_jobs = (
                candidate.support_job_ids
                if candidate.memory_type == MemoryType.SEMANTIC
                else [candidate.job_id]
            )
            for job_id in target_jobs:
                job = self.jobs.load(job_id)
                if reference not in job.memory_refs:
                    job.memory_refs.append(reference)
                    job.updated_at = datetime.now().astimezone()
                    self.jobs.save(job)
            self._audit("MEMORY_ACCEPTED", candidate, result=reason)
        else:
            self._audit("MEMORY_REJECTED", candidate, result=reason)
        return candidate

    def _audit(self, action: str, candidate: MemoryCandidate, *, result: str) -> None:
        self.audit.record(
            actor="system:creator_memory_gate",
            action=action,
            resource=f"memory-candidate:{candidate.candidate_id}",
            permission=Permission.WRITE_ARTIFACT,
            decision="allow",
            result=result,
            correlation_id=candidate.candidate_id,
            context={
                "job_id": candidate.job_id,
                "memory_type": candidate.memory_type.value,
                "support_count": candidate.support_count,
                "status": candidate.status.value,
                "environment": self.environment,
            },
        )

    @staticmethod
    def _normalize(statement: str) -> str:
        return " ".join(statement.casefold().split())
