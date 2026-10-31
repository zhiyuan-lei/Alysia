from __future__ import annotations

import hashlib
import json
import math
import re
from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Mapping

from pydantic import BaseModel, Field, field_validator, model_validator

from alysia.core.io import atomic_write_json
from alysia.creator.publisher import PublishRecord, PublishRecordStatus, PublisherStore
from alysia.creator.store import CreatorJobStore
from alysia.security.approvals import ApprovalValidator
from alysia.security.audit import AuditLog
from alysia.security.redaction import Redactor
from alysia.schemas.security import Permission


METRIC_NAMES = ("views", "likes", "comments", "favorites", "shares", "followers_delta")


def observation_now() -> datetime:
    return datetime.now().astimezone()


def _stable_id(prefix: str, *parts: object) -> str:
    payload = "\x1f".join(str(part) for part in parts)
    return f"{prefix}_{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:16]}"


class ObservationSourceType(str, Enum):
    REAL_PLATFORM = "REAL_PLATFORM"
    TEST_FIXTURE = "TEST_FIXTURE"
    MANUAL_IMPORT = "MANUAL_IMPORT"


class MetricAvailability(str, Enum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"


class MetricsSnapshot(BaseModel):
    observed_at: datetime = Field(default_factory=observation_now)
    views: int | None = Field(default=None, ge=0)
    likes: int | None = Field(default=None, ge=0)
    comments: int | None = Field(default=None, ge=0)
    favorites: int | None = Field(default=None, ge=0)
    shares: int | None = Field(default=None, ge=0)
    followers_delta: int | None = None
    availability: dict[str, MetricAvailability]

    @model_validator(mode="after")
    def availability_matches_values(self) -> "MetricsSnapshot":
        missing = set(METRIC_NAMES).difference(self.availability)
        if missing:
            raise ValueError("availability missing metrics: " + ", ".join(sorted(missing)))
        for name in METRIC_NAMES:
            value = getattr(self, name)
            state = self.availability[name]
            if state == MetricAvailability.AVAILABLE and value is None:
                raise ValueError(f"{name} is AVAILABLE without a value")
            if state == MetricAvailability.UNAVAILABLE and value is not None:
                raise ValueError(f"{name} is UNAVAILABLE but has a value")
        return self

    def raw(self) -> dict[str, int | None]:
        return {name: getattr(self, name) for name in METRIC_NAMES}

    def derived(self, previous: "MetricsSnapshot | None" = None) -> "DerivedMetrics":
        def rate(value: int | None) -> float | None:
            if self.views is None or self.views == 0 or value is None:
                return None
            result = value / self.views
            return result if math.isfinite(result) else None

        growth_delta = None
        if previous is not None and previous.views is not None and self.views is not None:
            growth_delta = self.views - previous.views
        return DerivedMetrics(
            like_rate=rate(self.likes),
            comment_rate=rate(self.comments),
            favorite_rate=rate(self.favorites),
            share_rate=rate(self.shares),
            growth_delta=growth_delta,
        )


class DerivedMetrics(BaseModel):
    like_rate: float | None = None
    comment_rate: float | None = None
    favorite_rate: float | None = None
    share_rate: float | None = None
    growth_delta: int | None = None

    @field_validator("like_rate", "comment_rate", "favorite_rate", "share_rate")
    @classmethod
    def finite_rates(cls, value: float | None) -> float | None:
        if value is not None and not math.isfinite(value):
            raise ValueError("derived metric must be finite")
        return value


class ContentObservation(BaseModel):
    observation_id: str | None = None
    job_id: str | None = None
    job_revision: int | None = Field(default=None, ge=1)
    platform: str = "bilibili"
    platform_content_id: str | None = None
    source_type: ObservationSourceType | None = None
    observed_at: datetime
    metrics: MetricsSnapshot | None = None
    availability: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(default=1.0, ge=0, le=1)
    raw_snapshot_ref: str | None = None
    notes: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    # Alpha22 Step 1 compatibility fields. New storage uses metrics/platform_content_id.
    content_id: str | None = None
    source: str | None = None
    views: int | None = Field(default=None, ge=0)
    likes: int | None = Field(default=None, ge=0)
    comments: int | None = Field(default=None, ge=0)
    favorites: int | None = Field(default=None, ge=0)
    shares: int | None = Field(default=None, ge=0)
    followers_delta: int | None = None
    evidence_path: Path | None = None

    @field_validator("metadata", mode="before")
    @classmethod
    def redact_metadata(cls, value: object) -> dict[str, Any]:
        return Redactor().redact_value(dict(value)) if isinstance(value, Mapping) else {}

    @field_validator("notes", mode="before")
    @classmethod
    def redact_notes(cls, value: object) -> list[str]:
        values = value if isinstance(value, list) else []
        redactor = Redactor()
        return [redactor.redact(str(item)) for item in values]

    @field_validator("raw_snapshot_ref", mode="before")
    @classmethod
    def redact_raw_snapshot_ref(cls, value: object) -> object:
        return Redactor().redact(str(value)) if value is not None else None

    @model_validator(mode="after")
    def normalize_and_validate(self) -> "ContentObservation":
        self.platform = self.platform.strip().casefold()
        self.platform_content_id = self.platform_content_id or self.content_id
        self.content_id = self.content_id or self.platform_content_id
        if not self.platform_content_id:
            raise ValueError("platform_content_id is required")
        if self.source_type is None:
            self.source_type = {
                "platform": ObservationSourceType.REAL_PLATFORM,
                "manual_real": ObservationSourceType.MANUAL_IMPORT,
                "testing": ObservationSourceType.TEST_FIXTURE,
            }.get(self.source or "", ObservationSourceType.TEST_FIXTURE)
        if self.source is None:
            self.source = {
                ObservationSourceType.REAL_PLATFORM: "platform",
                ObservationSourceType.MANUAL_IMPORT: "manual_real",
                ObservationSourceType.TEST_FIXTURE: "testing",
            }[self.source_type]
        if self.metrics is None:
            converted: dict[str, MetricAvailability] = {}
            for name in METRIC_NAMES:
                legacy = self.availability.get(name)
                converted[name] = (
                    MetricAvailability.AVAILABLE
                    if legacy in {"available", "AVAILABLE", MetricAvailability.AVAILABLE}
                    else MetricAvailability.UNAVAILABLE
                )
            self.metrics = MetricsSnapshot(
                observed_at=self.observed_at,
                **{name: getattr(self, name) for name in METRIC_NAMES},
                availability=converted,
            )
        else:
            self.metrics.observed_at = self.observed_at
            for name in METRIC_NAMES:
                setattr(self, name, getattr(self.metrics, name))
            self.availability = {
                name: (
                    "available"
                    if self.metrics.availability[name] == MetricAvailability.AVAILABLE
                    else "unavailable"
                )
                for name in METRIC_NAMES
            }
        if self.raw_snapshot_ref is None and self.evidence_path is not None:
            self.raw_snapshot_ref = str(self.evidence_path.resolve())
        if self.evidence_path is None and self.raw_snapshot_ref:
            candidate = Path(self.raw_snapshot_ref)
            if candidate.is_absolute():
                self.evidence_path = candidate
        if self.source_type == ObservationSourceType.TEST_FIXTURE:
            if "TEST_ONLY" not in self.platform_content_id.upper():
                raise ValueError("TEST_FIXTURE content identity must be explicitly TEST_ONLY")
            self.metadata["test_only"] = True
        elif "TEST_ONLY" in self.platform_content_id.upper() or self.metadata.get("test_only"):
            raise ValueError("test identity cannot be REAL_PLATFORM or MANUAL_IMPORT")
        self.observation_id = self.observation_id or _stable_id(
            "observation",
            self.job_id or "legacy",
            self.job_revision or 0,
            self.platform,
            self.platform_content_id,
            self.source_type.value,
            self.observed_at.isoformat(),
        )
        return self

    def age_since_publish_seconds(self, published_at: datetime | None) -> float | None:
        if published_at is None:
            return None
        return max(0.0, (self.observed_at - published_at).total_seconds())


class ObservationStore:
    _SAFE = re.compile(r"^[A-Za-z0-9_.-]+$")

    def __init__(self, root: Path, *, environment: str, redactor: Redactor | None = None) -> None:
        if environment not in {"production", "test"}:
            raise ValueError("observation environment must be production or test")
        self.environment = environment
        self.root = (root.resolve() / environment / "observations")
        self.root.mkdir(parents=True, exist_ok=True)
        self.redactor = redactor or Redactor()

    def save(self, observation: ContentObservation) -> Path:
        self._validate_environment(observation)
        assert observation.observation_id
        path = self._path(observation.observation_id)
        payload = self.redactor.redact_value(observation.model_dump(mode="json"))
        if path.is_file():
            existing = ContentObservation.model_validate_json(path.read_text(encoding="utf-8"))
            if existing != observation:
                raise FileExistsError("observation_id already exists with different content")
            return path
        return atomic_write_json(path, payload, backup_count=2)

    def load(self, observation_id: str) -> ContentObservation:
        return ContentObservation.model_validate_json(self._path(observation_id).read_text(encoding="utf-8"))

    def history(self, job_id: str) -> list[ContentObservation]:
        return sorted(
            [item for item in self._all() if item.job_id == job_id],
            key=lambda item: (item.observed_at, item.observation_id or ""),
        )

    def latest(self, job_id: str) -> ContentObservation | None:
        history = self.history(job_id)
        return history[-1] if history else None

    def by_content_id(self, platform_content_id: str) -> list[ContentObservation]:
        return sorted(
            [item for item in self._all() if item.platform_content_id == platform_content_id],
            key=lambda item: (item.observed_at, item.observation_id or ""),
        )

    def reference(self, observation: ContentObservation) -> str:
        assert observation.observation_id
        return f"observation:{self.environment}:{observation.observation_id}"

    def _all(self) -> list[ContentObservation]:
        items: list[ContentObservation] = []
        for path in self.root.glob("observation_*.json"):
            try:
                items.append(ContentObservation.model_validate_json(path.read_text(encoding="utf-8")))
            except ValueError:
                continue
        return items

    def _path(self, observation_id: str) -> Path:
        if not self._SAFE.fullmatch(observation_id):
            raise ValueError("invalid observation_id")
        return self.root / f"{observation_id}.json"

    def _validate_environment(self, observation: ContentObservation) -> None:
        if self.environment == "test" and observation.source_type != ObservationSourceType.TEST_FIXTURE:
            raise ValueError("test ObservationStore only accepts TEST_FIXTURE")
        if self.environment == "production" and observation.source_type == ObservationSourceType.TEST_FIXTURE:
            raise ValueError("TEST_FIXTURE cannot enter production observation storage")


class MetricsProvider(ABC):
    @abstractmethod
    def fetch_metrics(self, record: PublishRecord, *, observed_at: datetime | None = None) -> ContentObservation:
        """Return a provenance-labelled observation without mutating CreatorJob."""


class FakeMetricsProvider(MetricsProvider):
    def __init__(self, metrics: MetricsSnapshot) -> None:
        self.metrics = metrics

    def fetch_metrics(self, record: PublishRecord, *, observed_at: datetime | None = None) -> ContentObservation:
        if not record.metadata.get("test_only") or not record.platform_content_id:
            raise ValueError("FakeMetricsProvider requires a TEST_ONLY publish record")
        return ContentObservation(
            job_id=record.job_id,
            job_revision=record.job_revision,
            platform=record.platform,
            platform_content_id=record.platform_content_id,
            source_type=ObservationSourceType.TEST_FIXTURE,
            observed_at=observed_at or observation_now(),
            metrics=self.metrics,
            confidence=1.0,
            raw_snapshot_ref=f"test-fixture:{record.publish_id}",
            notes=["Synthetic metrics for isolated tests only."],
            metadata={"test_only": True, "publish_id": record.publish_id},
        )


class ManualMetricsProvider(MetricsProvider):
    def __init__(self, metrics: MetricsSnapshot, *, actor: str, raw_snapshot_ref: str) -> None:
        actor_key = actor.removeprefix("human:").strip().casefold()
        if not actor.startswith("human:") or actor_key in ApprovalValidator.FORBIDDEN_APPROVERS:
            raise PermissionError("manual metrics import requires an explicit human actor")
        if not raw_snapshot_ref.strip():
            raise ValueError("manual metrics import requires raw_snapshot_ref")
        self.metrics = metrics
        self.actor = actor
        self.raw_snapshot_ref = raw_snapshot_ref

    def fetch_metrics(self, record: PublishRecord, *, observed_at: datetime | None = None) -> ContentObservation:
        if not record.platform_content_id or record.metadata.get("test_only"):
            raise ValueError("manual real metrics require a non-test platform content identity")
        return ContentObservation(
            job_id=record.job_id,
            job_revision=record.job_revision,
            platform=record.platform,
            platform_content_id=record.platform_content_id,
            source_type=ObservationSourceType.MANUAL_IMPORT,
            observed_at=observed_at or observation_now(),
            metrics=self.metrics,
            confidence=0.9,
            raw_snapshot_ref=self.raw_snapshot_ref,
            notes=["Metrics imported manually; no automatic platform retrieval is claimed."],
            metadata={"actor": self.actor, "imported_at": observation_now().isoformat()},
        )


class ObservationService:
    def __init__(
        self,
        *,
        jobs: CreatorJobStore,
        publishes: PublisherStore,
        observations: ObservationStore,
        audit: AuditLog,
    ) -> None:
        self.jobs = jobs
        self.publishes = publishes
        self.observations = observations
        self.audit = audit

    def record(self, observation: ContentObservation) -> ContentObservation:
        if not observation.job_id or not observation.job_revision:
            raise ValueError("observation must bind job_id and job_revision")
        job = self.jobs.load(observation.job_id)
        if job.current_revision != observation.job_revision:
            raise ValueError("observation revision does not match CreatorJob")
        record = self._matching_publish_record(observation)
        if record.status != PublishRecordStatus.PUBLISHED:
            raise ValueError("observation requires a PUBLISHED PublishRecord")
        is_test_record = bool(record.metadata.get("test_only"))
        if observation.source_type == ObservationSourceType.TEST_FIXTURE and not is_test_record:
            raise ValueError("TEST_FIXTURE must bind a TEST_ONLY PublishRecord")
        if observation.source_type != ObservationSourceType.TEST_FIXTURE and is_test_record:
            raise ValueError("TEST_ONLY PublishRecord cannot become real observation evidence")
        path = self.observations.save(observation)
        history = self.observations.history(observation.job_id)
        previous = history[-2].metrics if len(history) > 1 else None
        summary = {
            "observation_id": observation.observation_id,
            "job_revision": observation.job_revision,
            "platform_content_id": observation.platform_content_id,
            "source_type": observation.source_type.value,
            "observed_at": observation.observed_at.isoformat(),
            "raw": observation.metrics.raw(),
            "availability": {
                key: value.value for key, value in observation.metrics.availability.items()
            },
            "derived": observation.metrics.derived(previous).model_dump(mode="json"),
            "age_since_publish_seconds": observation.age_since_publish_seconds(job.published_at),
        }
        reference = self.observations.reference(observation)
        job.latest_metrics_summary = summary
        if reference not in job.observation_refs:
            job.observation_refs.append(reference)
        job.updated_at = observation_now()
        self.jobs.save(job)
        self._audit("OBSERVATION_RECORDED", job.job_id, observation, result=str(path))
        self._audit("METRICS_UPDATED", job.job_id, observation, result="latest_summary_updated")
        return observation

    def collect(
        self,
        publish_id: str,
        provider: MetricsProvider,
        *,
        observed_at: datetime | None = None,
    ) -> ContentObservation:
        record = self.publishes.load_record(publish_id)
        return self.record(provider.fetch_metrics(record, observed_at=observed_at))

    def _matching_publish_record(self, observation: ContentObservation) -> PublishRecord:
        matches = [
            record
            for record in self.publishes.records()
            if record.job_id == observation.job_id
            and record.job_revision == observation.job_revision
            and record.platform == observation.platform
            and record.platform_content_id == observation.platform_content_id
        ]
        if not matches:
            raise ValueError("observation identity does not match a PublishRecord")
        return matches[-1]

    def _audit(self, action: str, job_id: str, observation: ContentObservation, *, result: str) -> None:
        self.audit.record(
            actor="system:observation",
            action=action,
            resource=f"creator-job:{job_id}",
            permission=Permission.WRITE_ARTIFACT,
            decision="allow",
            result=result,
            correlation_id=observation.observation_id,
            context={
                "job_revision": observation.job_revision,
                "source_type": observation.source_type.value,
                "platform_content_id": observation.platform_content_id,
            },
        )
