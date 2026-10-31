from __future__ import annotations

import hashlib
import re
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Protocol

from pydantic import BaseModel, Field, field_validator, model_validator

from alysia.core.io import atomic_write_json
from alysia.creator.models import ApprovalStatus, ContentObservation, CreatorJob, PublishStatus
from alysia.creator.production import ArtifactStatus, ProductionArtifact, ProductionArtifactRegistry
from alysia.creator.review import QAOverallResult, QAReviewStore, QAStatus, ReviewAction
from alysia.creator.store import CreatorJobStore
from alysia.security.approvals import ApprovalValidator
from alysia.security.audit import AuditLog
from alysia.security.redaction import Redactor
from alysia.schemas.security import Permission


BILIBILI_LIVE_PUBLISH_ENABLED = False


def publisher_now() -> datetime:
    return datetime.now().astimezone()


def _stable_id(prefix: str, *parts: object) -> str:
    payload = "\x1f".join(str(part) for part in parts)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


class PublishMode(str, Enum):
    VALIDATE_ONLY = "VALIDATE_ONLY"
    PREPARE_ONLY = "PREPARE_ONLY"
    LIVE = "LIVE"


class PublishRecordStatus(str, Enum):
    QUEUED = "QUEUED"
    VALIDATING = "VALIDATING"
    READY = "READY"
    UPLOADING = "UPLOADING"
    SUBMITTING = "SUBMITTING"
    PROCESSING = "PROCESSING"
    PUBLISHED = "PUBLISHED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    UNKNOWN = "UNKNOWN"


class AuthenticationState(str, Enum):
    READY = "READY"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    SESSION_EXPIRED = "SESSION_EXPIRED"
    AUTH_REJECTED = "AUTH_REJECTED"
    NEEDS_HUMAN_AUTH = "NEEDS_HUMAN_AUTH"


class CopyrightType(str, Enum):
    ORIGINAL = "ORIGINAL"
    REPOST = "REPOST"
    REQUIRES_HUMAN_SELECTION = "REQUIRES_HUMAN_SELECTION"


class RemotePublishState(str, Enum):
    NOT_SUBMITTED = "NOT_SUBMITTED"
    PROCESSING = "PROCESSING"
    PUBLISHED = "PUBLISHED"
    FAILED = "FAILED"
    NOT_FOUND = "NOT_FOUND"
    UNKNOWN = "UNKNOWN"


def _redacted_mapping(value: Mapping[str, Any] | None) -> dict[str, Any]:
    return Redactor().redact_value(dict(value or {}))


class PublishRequest(BaseModel):
    request_id: str = Field(min_length=1)
    job_id: str = Field(pattern=r"^creator_[0-9a-f]{16}$")
    job_revision: int = Field(ge=1)
    review_id: str = Field(min_length=1)
    qa_id: str = Field(min_length=1)
    platform: str = Field(min_length=1)
    video_artifact_id: str = Field(min_length=1)
    thumbnail_artifact_id: str = Field(min_length=1)
    video_artifact_hash: str | None = None
    thumbnail_artifact_hash: str | None = None
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    tags: list[str] = Field(min_length=1)
    category: str = Field(min_length=1)
    copyright_type: CopyrightType
    scheduled_at: datetime | None = None
    created_at: datetime = Field(default_factory=publisher_now)
    mode: PublishMode = PublishMode.PREPARE_ONLY
    idempotency_key: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("platform")
    @classmethod
    def normalize_platform(cls, value: str) -> str:
        return value.strip().casefold()

    @field_validator("tags")
    @classmethod
    def non_empty_tags(cls, values: list[str]) -> list[str]:
        cleaned = [value.strip() for value in values if value.strip()]
        if not cleaned:
            raise ValueError("tags must contain at least one non-empty value")
        return cleaned

    @field_validator("metadata", mode="before")
    @classmethod
    def redact_metadata(cls, value: object) -> dict[str, Any]:
        return _redacted_mapping(value if isinstance(value, Mapping) else {})

    @model_validator(mode="after")
    def stable_idempotency_key(self) -> "PublishRequest":
        if self.idempotency_key and len(self.idempotency_key) < 12:
            raise ValueError("idempotency_key is too short")
        return self


class PublishRecord(BaseModel):
    publish_id: str = Field(pattern=r"^publish_[0-9a-f]{16}$")
    request_id: str = Field(min_length=1)
    job_id: str = Field(pattern=r"^creator_[0-9a-f]{16}$")
    job_revision: int = Field(ge=1)
    platform: str = Field(min_length=1)
    mode: PublishMode
    status: PublishRecordStatus
    started_at: datetime | None = None
    finished_at: datetime | None = None
    platform_content_id: str | None = None
    platform_url_ref: str | None = None
    attempt_count: int = Field(default=0, ge=0)
    error_code: str | None = None
    error_message: str | None = None
    remote_state: RemotePublishState = RemotePublishState.NOT_SUBMITTED
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("error_message", mode="before")
    @classmethod
    def redact_error(cls, value: object) -> object:
        return Redactor().redact(str(value)) if value is not None else None

    @field_validator("metadata", mode="before")
    @classmethod
    def redact_metadata(cls, value: object) -> dict[str, Any]:
        return _redacted_mapping(value if isinstance(value, Mapping) else {})

    @model_validator(mode="after")
    def published_requires_reliable_id(self) -> "PublishRecord":
        if self.status == PublishRecordStatus.PUBLISHED and not self.platform_content_id:
            raise ValueError("PUBLISHED requires a reliable platform_content_id")
        return self


class PublishValidationReport(BaseModel):
    valid: bool
    blocking_issues: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    platform_requirements: dict[str, Any] = Field(default_factory=dict)
    auth_state: AuthenticationState
    job_revision: int
    artifact_hashes: dict[str, str | None] = Field(default_factory=dict)
    checked_at: datetime = Field(default_factory=publisher_now)

    @property
    def blocking(self) -> list[str]:
        """Compatibility accessor; persisted schema uses blocking_issues."""

        return self.blocking_issues

    @property
    def video_artifact_hash(self) -> str | None:
        return self.artifact_hashes.get("video")

    @property
    def thumbnail_artifact_hash(self) -> str | None:
        return self.artifact_hashes.get("thumbnail")


class PublishConfirmation(BaseModel):
    confirmation_id: str = Field(pattern=r"^confirm_[0-9a-f]{16}$")
    request_id: str = Field(min_length=1)
    job_id: str = Field(pattern=r"^creator_[0-9a-f]{16}$")
    job_revision: int = Field(ge=1)
    actor: str = Field(min_length=1)
    confirmed_at: datetime = Field(default_factory=publisher_now)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("metadata", mode="before")
    @classmethod
    def redact_metadata(cls, value: object) -> dict[str, Any]:
        return _redacted_mapping(value if isinstance(value, Mapping) else {})


class PreparedPublishPackage(BaseModel):
    package_id: str = Field(pattern=r"^publish_package_[0-9a-f]{16}$")
    request_id: str
    job_id: str
    job_revision: int
    platform: str
    mode: PublishMode
    video_artifact_id: str
    video_artifact_hash: str
    thumbnail_artifact_id: str
    thumbnail_artifact_hash: str
    title: str
    description: str
    tags: list[str]
    category: str
    copyright_type: CopyrightType
    scheduled_at: datetime | None = None
    qa_id: str
    review_id: str
    idempotency_key: str
    validation: PublishValidationReport
    platform_payload: "BilibiliPublishPayload"
    created_at: datetime = Field(default_factory=publisher_now)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("metadata", mode="before")
    @classmethod
    def redact_metadata(cls, value: object) -> dict[str, Any]:
        return _redacted_mapping(value if isinstance(value, Mapping) else {})


class BilibiliCapabilityConfig(BaseModel):
    platform: str = "bilibili"
    title_constraint: str = "UNKNOWN"
    description_constraint: str = "UNKNOWN"
    tag_constraint: str = "UNKNOWN"
    category_required: bool = True
    copyright_type_required: bool = True
    scheduling_support: str = "UNKNOWN"
    transport_contract: str = "NOT_CONFIGURED"


class BilibiliPublishPayload(BaseModel):
    """Semantic platform payload; a verified transport owns any wire-format mapping."""

    title: str
    description: str
    tags: list[str]
    thumbnail_artifact_id: str
    category: str
    copyright_type: CopyrightType
    scheduled_at: datetime | None = None


@dataclass(frozen=True, repr=False)
class SessionLease:
    """Runtime-only lease. The opaque handle must never enter a Pydantic model or log."""

    state: AuthenticationState
    handle: object | None = None

    def __repr__(self) -> str:
        return f"SessionLease(state={self.state.value!r}, handle=[REDACTED])"


class SessionProvider(Protocol):
    def auth_state(self, platform: str) -> AuthenticationState: ...
    def acquire(self, platform: str) -> SessionLease: ...


class UnavailableSessionProvider:
    def auth_state(self, platform: str) -> AuthenticationState:
        del platform
        return AuthenticationState.AUTH_REQUIRED

    def acquire(self, platform: str) -> SessionLease:
        del platform
        return SessionLease(AuthenticationState.AUTH_REQUIRED)


class UploadReceipt(BaseModel):
    upload_ref: str = Field(min_length=1)
    test_only: bool = False


class TransportPublishResult(BaseModel):
    remote_state: RemotePublishState
    platform_content_id: str | None = None
    platform_url_ref: str | None = None
    test_only: bool = False

    @model_validator(mode="after")
    def published_has_id(self) -> "TransportPublishResult":
        if self.remote_state == RemotePublishState.PUBLISHED and not self.platform_content_id:
            raise ValueError("remote PUBLISHED result requires platform_content_id")
        return self


class BilibiliTransport(Protocol):
    """Injected verified transport or automation backend; no endpoint is assumed here."""

    def upload(
        self,
        package: PreparedPublishPackage,
        *,
        session_handle: object,
        idempotency_key: str,
    ) -> UploadReceipt: ...

    def submit(
        self,
        upload_ref: str,
        package: PreparedPublishPackage,
        *,
        session_handle: object,
        idempotency_key: str,
    ) -> TransportPublishResult: ...

    def status(self, platform_content_id: str, *, session_handle: object) -> TransportPublishResult: ...

    def cancel(self, upload_ref: str, *, session_handle: object) -> bool: ...

    def reconcile(
        self,
        *,
        idempotency_key: str,
        session_handle: object,
    ) -> TransportPublishResult: ...


class PublishError(RuntimeError):
    def __init__(self, message: str, *, code: str = "PUBLISH_ERROR") -> None:
        safe = Redactor().redact(message)
        super().__init__(safe)
        self.code = code


class PublishValidationError(PublishError):
    def __init__(self, report: PublishValidationReport) -> None:
        super().__init__("publish validation failed: " + "; ".join(report.blocking), code="VALIDATION_FAILED")
        self.report = report


class LivePublishingDisabled(PublishError):
    pass


class DuplicatePublishBlocked(PublishError):
    pass


class PublishLockBusy(PublishError):
    pass


class HumanPublishConfirmationRequired(PublishError):
    pass


class AuthenticationRequired(PublishError):
    def __init__(self, state: AuthenticationState, message: str = "human authentication required") -> None:
        super().__init__(message, code=state.value)
        self.state = state


class HumanAuthenticationChallenge(AuthenticationRequired):
    def __init__(self, message: str = "platform verification requires a human") -> None:
        super().__init__(AuthenticationState.NEEDS_HUMAN_AUTH, message)


class PublishTransportError(PublishError):
    def __init__(
        self,
        message: str,
        *,
        code: str,
        retryable: bool,
        submission_started: bool,
        indeterminate: bool = False,
    ) -> None:
        super().__init__(message, code=code)
        self.retryable = retryable
        self.submission_started = submission_started
        self.indeterminate = indeterminate


class ManualPublicationRequired(RuntimeError):
    pass


class OfficialContractUnavailable(RuntimeError):
    pass


class BilibiliValidationReport(BaseModel):
    """Compatibility report for the Alpha22 Step 1 legacy manual handoff."""

    passed: bool
    mode: str
    checks: dict[str, bool]
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class Publisher(ABC):
    @abstractmethod
    def prepare(self, request: PublishRequest) -> PreparedPublishPackage | PublishValidationReport: ...

    @abstractmethod
    def validate(self, request: PublishRequest) -> PublishValidationReport: ...

    @abstractmethod
    def publish(self, request: PublishRequest, *, confirmation: PublishConfirmation) -> PublishRecord: ...

    @abstractmethod
    def status(self, publish_id: str) -> PublishRecord: ...

    @abstractmethod
    def cancel(self, publish_id: str) -> PublishRecord: ...


class PublisherStore:
    _SAFE_ID = re.compile(r"^[A-Za-z0-9_.-]+$")

    def __init__(self, root: Path, redactor: Redactor | None = None) -> None:
        self.root = root.resolve()
        self.redactor = redactor or Redactor()
        for name in ("requests", "records", "confirmations", "packages"):
            (self.root / name).mkdir(parents=True, exist_ok=True)

    def _path(self, area: str, value: str) -> Path:
        if not self._SAFE_ID.fullmatch(value):
            raise ValueError("invalid publisher state identifier")
        return self.root / area / f"{value}.json"

    def _save(self, area: str, value: str, model: BaseModel) -> Path:
        payload = self.redactor.redact_value(model.model_dump(mode="json"))
        return atomic_write_json(self._path(area, value), payload, backup_count=2)

    def save_request(self, request: PublishRequest) -> Path:
        return self._save("requests", request.request_id, request)

    def load_request(self, request_id: str) -> PublishRequest:
        return PublishRequest.model_validate_json(self._path("requests", request_id).read_text(encoding="utf-8"))

    def save_record(self, record: PublishRecord) -> Path:
        return self._save("records", record.publish_id, record)

    def load_record(self, publish_id: str) -> PublishRecord:
        return PublishRecord.model_validate_json(self._path("records", publish_id).read_text(encoding="utf-8"))

    def records(self) -> list[PublishRecord]:
        records: list[PublishRecord] = []
        for path in sorted((self.root / "records").glob("publish_*.json")):
            try:
                records.append(PublishRecord.model_validate_json(path.read_text(encoding="utf-8")))
            except ValueError:
                continue
        return records

    def save_confirmation(self, confirmation: PublishConfirmation) -> Path:
        path = self._path("confirmations", confirmation.confirmation_id)
        if path.is_file():
            existing = PublishConfirmation.model_validate_json(path.read_text(encoding="utf-8"))
            if existing != confirmation:
                raise FileExistsError("confirmation_id already exists with different content")
            return path
        return self._save("confirmations", confirmation.confirmation_id, confirmation)

    def load_confirmation(self, confirmation_id: str) -> PublishConfirmation:
        return PublishConfirmation.model_validate_json(
            self._path("confirmations", confirmation_id).read_text(encoding="utf-8")
        )

    def save_package(self, package: PreparedPublishPackage) -> Path:
        return self._save("packages", package.request_id, package)

    def load_package(self, request_id: str) -> PreparedPublishPackage:
        return PreparedPublishPackage.model_validate_json(
            self._path("packages", request_id).read_text(encoding="utf-8")
        )

    def record_for_request(self, request_id: str) -> PublishRecord | None:
        return next((record for record in self.records() if record.request_id == request_id), None)

    def duplicate_for(self, request: PublishRequest, *, exclude_publish_id: str | None = None) -> PublishRecord | None:
        guarded = {
            PublishRecordStatus.UPLOADING,
            PublishRecordStatus.SUBMITTING,
            PublishRecordStatus.PROCESSING,
            PublishRecordStatus.PUBLISHED,
            PublishRecordStatus.UNKNOWN,
        }
        for record in self.records():
            if record.publish_id == exclude_publish_id or record.status not in guarded:
                continue
            try:
                other = self.load_request(record.request_id)
            except (FileNotFoundError, ValueError):
                continue
            if (
                other.platform == request.platform
                and other.job_id == request.job_id
                and other.job_revision == request.job_revision
                and other.idempotency_key == request.idempotency_key
            ):
                return record
        return None


class BilibiliPublisher(Publisher):
    _locks_guard = threading.Lock()
    _locks: dict[str, threading.Lock] = {}

    def __init__(
        self,
        *,
        mode: str | PublishMode = "manual_handoff",
        transport: BilibiliTransport | Any | None = None,
        jobs: CreatorJobStore | None = None,
        qa_reviews: QAReviewStore | None = None,
        artifacts: ProductionArtifactRegistry | None = None,
        store: PublisherStore | None = None,
        audit: AuditLog | None = None,
        session_provider: SessionProvider | None = None,
        live_enabled: bool = BILIBILI_LIVE_PUBLISH_ENABLED,
        capabilities: BilibiliCapabilityConfig | None = None,
        max_pre_submit_attempts: int = 2,
    ) -> None:
        self.mode = mode.value if isinstance(mode, PublishMode) else mode
        self.transport = transport
        self.jobs = jobs
        self.qa_reviews = qa_reviews
        self.artifacts = artifacts
        self.store = store
        self.audit = audit
        self.session_provider = session_provider or UnavailableSessionProvider()
        self.live_enabled = live_enabled
        self.capabilities = capabilities or BilibiliCapabilityConfig()
        self.max_pre_submit_attempts = max(1, max_pre_submit_attempts)
        supplied = (jobs, qa_reviews, artifacts, store, audit)
        self._legacy = all(item is None for item in supplied)
        if not self._legacy and any(item is None for item in supplied):
            raise ValueError("safe publisher requires jobs, qa_reviews, artifacts, store, and audit")

    @staticmethod
    def idempotency_key(platform: str, job_id: str, job_revision: int, video_hash: str) -> str:
        return _stable_id("publish_key", platform.casefold(), job_id, job_revision, video_hash)

    @staticmethod
    def publish_lock_key(platform: str, job_id: str, job_revision: int) -> str:
        return _stable_id("publish_lock", platform.casefold(), job_id, job_revision)

    def prepare(self, request: PublishRequest | CreatorJob) -> PreparedPublishPackage | Path:
        if isinstance(request, CreatorJob):
            return self._legacy_prepare(request)
        self._require_safe_mode()
        report = self.validate(request)
        if not report.valid:
            raise PublishValidationError(report)
        if request.mode == PublishMode.VALIDATE_ONLY:
            self._audit("PUBLISH_VALIDATED", request, result="valid", actor="system:publisher")
            return report
        assert report.video_artifact_hash and report.thumbnail_artifact_hash
        expected_key = self.idempotency_key(
            request.platform, request.job_id, request.job_revision, report.video_artifact_hash
        )
        if request.idempotency_key and request.idempotency_key != expected_key:
            report.blocking.append("IDEMPOTENCY_KEY_MISMATCH")
            report.valid = False
            raise PublishValidationError(report)
        request = request.model_copy(
            update={
                "idempotency_key": expected_key,
                "video_artifact_hash": report.video_artifact_hash,
                "thumbnail_artifact_hash": report.thumbnail_artifact_hash,
            }
        )
        existing = self.store.record_for_request(request.request_id)
        if existing is not None:
            return self.store.load_package(request.request_id)
        duplicate = self.store.duplicate_for(request)
        if duplicate is not None:
            raise DuplicatePublishBlocked(
                f"duplicate publish blocked by {duplicate.publish_id}", code="DUPLICATE_PUBLISH"
            )
        package = PreparedPublishPackage(
            package_id=_stable_id("publish_package", request.request_id, expected_key),
            request_id=request.request_id,
            job_id=request.job_id,
            job_revision=request.job_revision,
            platform=request.platform,
            mode=request.mode,
            video_artifact_id=request.video_artifact_id,
            video_artifact_hash=report.video_artifact_hash,
            thumbnail_artifact_id=request.thumbnail_artifact_id,
            thumbnail_artifact_hash=report.thumbnail_artifact_hash,
            title=request.title,
            description=request.description,
            tags=request.tags,
            category=request.category,
            copyright_type=request.copyright_type,
            scheduled_at=request.scheduled_at,
            qa_id=request.qa_id,
            review_id=request.review_id,
            idempotency_key=expected_key,
            validation=report,
            platform_payload=self.translate_metadata(request),
            metadata={
                **request.metadata,
                "test_only": bool(request.metadata.get("test_only", False)),
                "transport_contract": self.capabilities.transport_contract,
            },
        )
        record = PublishRecord(
            publish_id=_stable_id("publish", request.request_id, expected_key),
            request_id=request.request_id,
            job_id=request.job_id,
            job_revision=request.job_revision,
            platform=request.platform,
            mode=request.mode,
            status=PublishRecordStatus.READY,
            metadata={"submission_started": False, "test_only": package.metadata.get("test_only", False)},
        )
        self.store.save_request(request)
        self.store.save_package(package)
        self.store.save_record(record)
        self._audit("PUBLISH_VALIDATED", request, result="valid", actor="system:publisher")
        self._audit("PUBLISH_PREPARED", request, result="ready", actor="system:publisher")
        return package

    def validate(self, request: PublishRequest | CreatorJob) -> PublishValidationReport | BilibiliValidationReport:
        if isinstance(request, CreatorJob):
            return self._legacy_validate(request)
        self._require_safe_mode()
        blocking: list[str] = []
        warnings: list[str] = []
        video: ProductionArtifact | None = None
        thumbnail: ProductionArtifact | None = None
        try:
            job = self.jobs.load(request.job_id)
        except (FileNotFoundError, ValueError):
            job = None
            blocking.append("JOB_NOT_FOUND")
        if request.platform != "bilibili":
            blocking.append("PLATFORM_MISMATCH")
        if job is not None:
            if job.current_revision != request.job_revision:
                blocking.append("STALE_JOB_REVISION")
            if job.approval_status != ApprovalStatus.APPROVED or not job.approved_by:
                blocking.append("HUMAN_APPROVAL_REQUIRED")
            if job.publish_status != PublishStatus.PUBLISH_READY or job.status != "PUBLISH_READY":
                blocking.append("JOB_NOT_PUBLISH_READY")
            if job.approval_ref != request.review_id:
                blocking.append("REVIEW_NOT_CURRENT")
            if job.selected_title != request.title or job.description != request.description or job.tags != request.tags:
                blocking.append("METADATA_CHANGED_SINCE_REVIEW")
            if job.testing or job.dry_run:
                warnings.append("TEST_ONLY_JOB")
                if request.mode == PublishMode.LIVE:
                    blocking.append("TEST_JOB_CANNOT_LIVE_PUBLISH")
        try:
            qa = self.qa_reviews.load_qa(request.job_id, request.qa_id)
            if qa.job_revision != request.job_revision or qa.status != QAStatus.COMPLETED:
                blocking.append("STALE_QA")
            if qa.overall_result not in {QAOverallResult.PASS, QAOverallResult.PASS_WITH_WARNINGS}:
                blocking.append("QA_NOT_PASSED")
            if qa.blocking_issues or any(issue.blocking for issue in qa.content_checks + qa.grounding_checks + qa.media_checks + qa.metadata_checks + qa.safety_checks):
                blocking.append("BLOCKING_QA_ISSUES")
        except (FileNotFoundError, ValueError):
            blocking.append("QA_NOT_FOUND")
        try:
            review = self.qa_reviews.load_review(request.job_id, request.review_id)
            if (
                review.job_revision != request.job_revision
                or review.qa_id != request.qa_id
                or review.action != ReviewAction.APPROVE
            ):
                blocking.append("STALE_OR_NON_APPROVAL_REVIEW")
        except (FileNotFoundError, ValueError):
            blocking.append("REVIEW_NOT_FOUND")
        video = self._validate_artifact(request.video_artifact_id, request.job_id, "VIDEO", blocking)
        thumbnail = self._validate_artifact(
            request.thumbnail_artifact_id, request.job_id, "THUMBNAIL", blocking
        )
        if request.video_artifact_hash and video is not None and request.video_artifact_hash != video.hash:
            blocking.append("VIDEO_ARTIFACT_HASH_CHANGED")
        if (
            request.thumbnail_artifact_hash
            and thumbnail is not None
            and request.thumbnail_artifact_hash != thumbnail.hash
        ):
            blocking.append("THUMBNAIL_ARTIFACT_HASH_CHANGED")
        if job is not None and video is not None and job.video_path and job.video_path.resolve() != video.path.resolve():
            blocking.append("VIDEO_ARTIFACT_NOT_CURRENT")
        if job is not None and thumbnail is not None and job.thumbnail_path and job.thumbnail_path.resolve() != thumbnail.path.resolve():
            blocking.append("THUMBNAIL_ARTIFACT_NOT_CURRENT")
        if not request.title.strip():
            blocking.append("TITLE_REQUIRED")
        if not request.description.strip():
            blocking.append("DESCRIPTION_REQUIRED")
        if not request.tags:
            blocking.append("TAGS_REQUIRED")
        if not request.category.strip():
            blocking.append("CATEGORY_REQUIRED")
        if request.copyright_type == CopyrightType.REQUIRES_HUMAN_SELECTION:
            blocking.append("COPYRIGHT_TYPE_REQUIRES_HUMAN_SELECTION")
        if request.scheduled_at is not None and self.capabilities.scheduling_support == "UNKNOWN":
            blocking.append("SCHEDULING_CAPABILITY_UNKNOWN")
        auth_state = self._safe_auth_state(request.platform)
        if request.mode == PublishMode.LIVE:
            if not self.live_enabled:
                blocking.append("LIVE_PUBLISHING_DISABLED")
            if self.transport is None:
                blocking.append("VERIFIED_TRANSPORT_REQUIRED")
            if auth_state != AuthenticationState.READY:
                blocking.append(auth_state.value)
        elif auth_state != AuthenticationState.READY:
            warnings.append(auth_state.value)
        requirements = self.capabilities.model_dump(mode="json")
        report = PublishValidationReport(
            valid=not blocking,
            blocking_issues=list(dict.fromkeys(blocking)),
            warnings=list(dict.fromkeys(warnings)),
            platform_requirements=requirements,
            auth_state=auth_state,
            job_revision=request.job_revision,
            artifact_hashes={
                "video": video.hash if video else None,
                "thumbnail": thumbnail.hash if thumbnail else None,
            },
        )
        return report

    @staticmethod
    def translate_metadata(request: PublishRequest) -> BilibiliPublishPayload:
        return BilibiliPublishPayload(
            title=request.title,
            description=request.description,
            tags=request.tags,
            thumbnail_artifact_id=request.thumbnail_artifact_id,
            category=request.category,
            copyright_type=request.copyright_type,
            scheduled_at=request.scheduled_at,
        )

    def confirm(
        self,
        request_id: str,
        *,
        actor: str,
        job_revision: int,
        metadata: Mapping[str, Any] | None = None,
    ) -> PublishConfirmation:
        self._require_safe_mode()
        request = self.store.load_request(request_id)
        actor_key = actor.removeprefix("human:").strip().casefold()
        if not actor.startswith("human:") or actor_key in ApprovalValidator.FORBIDDEN_APPROVERS:
            raise PermissionError("publish confirmation requires an explicit human identity")
        if request.job_revision != job_revision or self.jobs.load(request.job_id).current_revision != job_revision:
            raise ValueError("publish confirmation revision is stale")
        confirmation = PublishConfirmation(
            confirmation_id=_stable_id("confirm", request_id, job_revision, actor),
            request_id=request_id,
            job_id=request.job_id,
            job_revision=job_revision,
            actor=actor,
            metadata=dict(metadata or {}),
        )
        self._audit("PUBLISH_CONFIRM_REQUESTED", request, result="requested", actor=actor)
        self.store.save_confirmation(confirmation)
        self._audit(
            "PUBLISH_CONFIRMED",
            request,
            result="confirmed",
            actor=actor,
            approval_ref=confirmation.confirmation_id,
        )
        return confirmation

    def publish(
        self,
        request: PublishRequest | CreatorJob,
        *,
        confirmation: PublishConfirmation | None = None,
    ) -> PublishRecord | str:
        if isinstance(request, CreatorJob):
            return self._legacy_publish(request)
        self._require_safe_mode()
        if request.mode != PublishMode.LIVE or not self.live_enabled:
            raise LivePublishingDisabled("LIVE publishing is disabled", code="LIVE_DISABLED")
        if confirmation is None:
            raise HumanPublishConfirmationRequired(
                "a distinct human publish confirmation is required", code="HUMAN_CONFIRMATION_REQUIRED"
            )
        persisted = self.store.load_request(request.request_id)
        package = self.store.load_package(request.request_id)
        record = self.store.record_for_request(request.request_id)
        if record is None:
            raise PublishError("request has not been prepared", code="NOT_PREPARED")
        self._validate_confirmation(persisted, confirmation)
        lock = self._lock_for(
            self.publish_lock_key(persisted.platform, persisted.job_id, persisted.job_revision)
        )
        if not lock.acquire(blocking=False):
            raise PublishLockBusy("publish lock is already held", code="PUBLISH_LOCK_BUSY")
        try:
            duplicate = self.store.duplicate_for(persisted, exclude_publish_id=record.publish_id)
            if duplicate is not None:
                raise DuplicatePublishBlocked(
                    f"duplicate publish blocked by {duplicate.publish_id}", code="DUPLICATE_PUBLISH"
                )
            if record.status in {
                PublishRecordStatus.PUBLISHED,
                PublishRecordStatus.PROCESSING,
                PublishRecordStatus.UNKNOWN,
                PublishRecordStatus.UPLOADING,
                PublishRecordStatus.SUBMITTING,
            }:
                raise DuplicatePublishBlocked(
                    f"publish record {record.publish_id} is {record.status.value}", code="DUPLICATE_PUBLISH"
                )
            if record.status == PublishRecordStatus.CANCELLED:
                raise PublishError("cancelled publish cannot resume", code="CANCELLED")
            if record.status == PublishRecordStatus.FAILED and not record.metadata.get("safe_to_retry", False):
                raise DuplicatePublishBlocked("failed publish is not proven safe to retry", code="UNSAFE_RETRY")
            report = self.validate(persisted)
            assert isinstance(report, PublishValidationReport)
            snapshot_errors = self._snapshot_errors(package, persisted, report)
            if snapshot_errors:
                report.blocking.extend(snapshot_errors)
                report.valid = False
            if not report.valid:
                raise PublishValidationError(report)
            try:
                lease = self.session_provider.acquire(persisted.platform)
            except Exception as exc:
                safe = Redactor().redact(str(exc))
                self._auth_required(persisted, record, AuthenticationState.AUTH_REQUIRED)
                raise AuthenticationRequired(
                    AuthenticationState.AUTH_REQUIRED,
                    f"session provider failed: {safe}",
                ) from None
            if lease.state != AuthenticationState.READY or lease.handle is None:
                self._auth_required(persisted, record, lease.state)
                raise AuthenticationRequired(lease.state)
            if self.transport is None:
                raise OfficialContractUnavailable("verified Bilibili transport is not configured")
            record.started_at = record.started_at or publisher_now()
            record.status = PublishRecordStatus.UPLOADING
            record.error_code = None
            record.error_message = None
            record.metadata.update({"safe_to_retry": False, "submission_started": False})
            self.store.save_record(record)
            self._audit("PUBLISH_STARTED", persisted, result="uploading", actor=confirmation.actor)
            try:
                upload = self._upload_with_safe_retry(package, lease.handle, record)
            except HumanAuthenticationChallenge as exc:
                self._auth_required(persisted, record, exc.state)
                raise
            # The second revision/hash check is deliberately immediately before submit.
            second = self.validate(persisted)
            assert isinstance(second, PublishValidationReport)
            snapshot_errors = self._snapshot_errors(package, persisted, second)
            if not second.valid or snapshot_errors:
                second.blocking.extend(snapshot_errors)
                second.valid = False
                record.status = PublishRecordStatus.FAILED
                record.finished_at = publisher_now()
                record.error_code = "STALE_BEFORE_SUBMIT"
                record.error_message = "revision or artifact snapshot changed before submit"
                record.metadata["safe_to_retry"] = True
                self.store.save_record(record)
                raise PublishValidationError(second)
            record.status = PublishRecordStatus.SUBMITTING
            record.metadata.update({"submission_started": True, "upload_ref": upload.upload_ref})
            self.store.save_record(record)
            try:
                result = self.transport.submit(
                    upload.upload_ref,
                    package,
                    session_handle=lease.handle,
                    idempotency_key=package.idempotency_key,
                )
            except HumanAuthenticationChallenge as exc:
                self._auth_required(persisted, record, exc.state)
                return self._mark_unknown(
                    persisted,
                    record,
                    PublishTransportError(
                        str(exc),
                        code=exc.code,
                        retryable=False,
                        submission_started=True,
                        indeterminate=True,
                    ),
                )
            except PublishTransportError as exc:
                if exc.submission_started or exc.indeterminate:
                    return self._mark_unknown(persisted, record, exc)
                return self._mark_failed(persisted, record, exc, safe_to_retry=exc.retryable)
            except Exception as exc:
                return self._mark_unknown(
                    persisted,
                    record,
                    PublishTransportError(
                        Redactor().redact(str(exc)),
                        code="UNEXPECTED_POST_SUBMIT_ERROR",
                        retryable=False,
                        submission_started=True,
                        indeterminate=True,
                    ),
                )
            return self._apply_transport_result(persisted, record, result)
        finally:
            lock.release()

    def status(self, publish_id: str | CreatorJob) -> PublishRecord | str:
        if isinstance(publish_id, CreatorJob):
            return self._legacy_status(publish_id)
        self._require_safe_mode()
        return self.store.load_record(publish_id)

    def cancel(self, publish_id: str) -> PublishRecord:
        self._require_safe_mode()
        record = self.store.load_record(publish_id)
        if record.status in {
            PublishRecordStatus.SUBMITTING,
            PublishRecordStatus.PROCESSING,
            PublishRecordStatus.PUBLISHED,
            PublishRecordStatus.UNKNOWN,
        } or record.metadata.get("submission_started", False):
            raise PublishError(
                "remote submission may already exist; local cancellation cannot claim retraction",
                code="REMOTE_STATE_MAY_EXIST",
            )
        if record.status == PublishRecordStatus.CANCELLED:
            return record
        record.status = PublishRecordStatus.CANCELLED
        record.finished_at = publisher_now()
        record.remote_state = RemotePublishState.NOT_SUBMITTED
        self.store.save_record(record)
        return record

    def reconcile(self, publish_id: str) -> PublishRecord:
        self._require_safe_mode()
        record = self.store.load_record(publish_id)
        if record.status not in {PublishRecordStatus.UNKNOWN, PublishRecordStatus.PROCESSING}:
            raise PublishError("reconciliation requires UNKNOWN or PROCESSING", code="RECONCILE_NOT_ALLOWED")
        request = self.store.load_request(record.request_id)
        try:
            lease = self.session_provider.acquire(request.platform)
        except Exception as exc:
            safe = Redactor().redact(str(exc))
            self._auth_required(request, record, AuthenticationState.AUTH_REQUIRED)
            raise AuthenticationRequired(
                AuthenticationState.AUTH_REQUIRED,
                f"session provider failed: {safe}",
            ) from None
        if lease.state != AuthenticationState.READY or lease.handle is None:
            self._auth_required(request, record, lease.state)
            raise AuthenticationRequired(lease.state)
        if self.transport is None:
            raise OfficialContractUnavailable("verified Bilibili transport is not configured")
        try:
            result = self.transport.reconcile(
                idempotency_key=request.idempotency_key,
                session_handle=lease.handle,
            )
        except Exception as exc:
            record.error_code = "RECONCILIATION_UNAVAILABLE"
            record.error_message = Redactor().redact(str(exc))
            record.status = PublishRecordStatus.UNKNOWN
            record.remote_state = RemotePublishState.UNKNOWN
            record.metadata["safe_to_retry"] = False
            self.store.save_record(record)
            self._audit("PUBLISH_RECONCILED", request, result="unknown", actor="system:publisher")
            return record
        if result.remote_state in {RemotePublishState.NOT_FOUND, RemotePublishState.FAILED}:
            record.status = PublishRecordStatus.FAILED
            record.finished_at = publisher_now()
            record.remote_state = result.remote_state
            record.error_code = "RECONCILED_NOT_PUBLISHED"
            record.error_message = "remote reconciliation confirmed no successful publication"
            record.metadata["safe_to_retry"] = True
            self.store.save_record(record)
            self._audit("PUBLISH_RECONCILED", request, result="confirmed_not_published", actor="system:publisher")
            return record
        updated = self._apply_transport_result(request, record, result, reconciled=True)
        self._audit("PUBLISH_RECONCILED", request, result=updated.status.value, actor="system:publisher")
        return updated

    def fetch_metrics(self, job: CreatorJob) -> ContentObservation:
        if job.status != "PUBLISHED" or not job.platform_content_id:
            raise ValueError("metrics require a PUBLISHED CreatorJob")
        if self.mode != "official_api" or self.transport is None:
            raise ManualPublicationRequired(
                "Import a timestamped real Bilibili observation with evidence; no metric is synthesized"
            )
        return self.transport.fetch_metrics(job.platform_content_id)

    def _validate_artifact(
        self,
        artifact_id: str,
        job_id: str,
        expected_type: str,
        blocking: list[str],
    ) -> ProductionArtifact | None:
        try:
            artifact = self.artifacts.load(artifact_id)
        except (FileNotFoundError, ValueError):
            blocking.append(f"{expected_type}_ARTIFACT_NOT_FOUND")
            return None
        if artifact.job_id != job_id:
            blocking.append(f"{expected_type}_ARTIFACT_JOB_MISMATCH")
        accepted = {"VIDEO", "COMPOSITE"} if expected_type == "VIDEO" else {expected_type}
        if artifact.artifact_type not in accepted:
            blocking.append(f"{expected_type}_ARTIFACT_TYPE_MISMATCH")
        if artifact.status != ArtifactStatus.VALID or not self.artifacts.valid([artifact_id]):
            blocking.append(f"{expected_type}_ARTIFACT_INVALID_OR_CHANGED")
        return artifact

    @staticmethod
    def _snapshot_errors(
        package: PreparedPublishPackage,
        request: PublishRequest,
        report: PublishValidationReport,
    ) -> list[str]:
        errors: list[str] = []
        if package.job_revision != request.job_revision or report.job_revision != package.job_revision:
            errors.extend(["STALE_PUBLISH_REQUEST", "REVISION_SNAPSHOT_CHANGED"])
        if package.video_artifact_hash != report.video_artifact_hash:
            errors.append("VIDEO_HASH_CHANGED")
        if package.thumbnail_artifact_hash != report.thumbnail_artifact_hash:
            errors.append("THUMBNAIL_HASH_CHANGED")
        if (
            package.title != request.title
            or package.description != request.description
            or package.tags != request.tags
            or package.qa_id != request.qa_id
            or package.review_id != request.review_id
        ):
            errors.append("PUBLISH_SNAPSHOT_CHANGED")
        return errors

    def _validate_confirmation(self, request: PublishRequest, confirmation: PublishConfirmation) -> None:
        try:
            stored = self.store.load_confirmation(confirmation.confirmation_id)
        except FileNotFoundError as exc:
            raise HumanPublishConfirmationRequired(
                "confirmation must be persisted by the explicit confirm action",
                code="CONFIRMATION_NOT_PERSISTED",
            ) from exc
        actor_key = stored.actor.removeprefix("human:").strip().casefold()
        if not stored.actor.startswith("human:") or actor_key in ApprovalValidator.FORBIDDEN_APPROVERS:
            raise HumanPublishConfirmationRequired("confirmation actor is not human", code="INVALID_ACTOR")
        if (
            stored != confirmation
            or stored.request_id != request.request_id
            or stored.job_id != request.job_id
            or stored.job_revision != request.job_revision
        ):
            raise HumanPublishConfirmationRequired("confirmation does not match request snapshot", code="STALE_CONFIRMATION")

    def _upload_with_safe_retry(
        self,
        package: PreparedPublishPackage,
        session_handle: object,
        record: PublishRecord,
    ) -> UploadReceipt:
        assert self.transport is not None
        while record.attempt_count < self.max_pre_submit_attempts:
            record.attempt_count += 1
            self.store.save_record(record)
            try:
                return self.transport.upload(
                    package,
                    session_handle=session_handle,
                    idempotency_key=package.idempotency_key,
                )
            except PublishTransportError as exc:
                if exc.submission_started or exc.indeterminate:
                    request = self.store.load_request(record.request_id)
                    self._mark_unknown(request, record, exc)
                    raise DuplicatePublishBlocked(
                        "upload outcome is UNKNOWN; reconcile before any retry", code="UNKNOWN_NO_RETRY"
                    ) from exc
                if not exc.retryable or record.attempt_count >= self.max_pre_submit_attempts:
                    request = self.store.load_request(record.request_id)
                    self._mark_failed(request, record, exc, safe_to_retry=exc.retryable)
                    raise
            except HumanAuthenticationChallenge:
                raise
            except Exception as exc:
                request = self.store.load_request(record.request_id)
                unknown = PublishTransportError(
                    Redactor().redact(str(exc)),
                    code="UNEXPECTED_UPLOAD_ERROR",
                    retryable=False,
                    submission_started=True,
                    indeterminate=True,
                )
                self._mark_unknown(request, record, unknown)
                raise DuplicatePublishBlocked(
                    "upload outcome is UNKNOWN; reconcile before any retry", code="UNKNOWN_NO_RETRY"
                ) from None
        raise AssertionError("unreachable")

    def _apply_transport_result(
        self,
        request: PublishRequest,
        record: PublishRecord,
        result: TransportPublishResult,
        *,
        reconciled: bool = False,
    ) -> PublishRecord:
        record.remote_state = result.remote_state
        record.platform_content_id = result.platform_content_id
        record.platform_url_ref = result.platform_url_ref
        record.metadata["test_only"] = bool(result.test_only or record.metadata.get("test_only", False))
        if result.remote_state == RemotePublishState.PUBLISHED:
            if not result.platform_content_id:
                raise PublishError("PUBLISHED requires reliable content ID", code="MISSING_CONTENT_ID")
            record.status = PublishRecordStatus.PUBLISHED
            record.finished_at = publisher_now()
            record.error_code = None
            record.error_message = None
            event = "PUBLISHED"
        elif result.remote_state == RemotePublishState.PROCESSING:
            record.status = PublishRecordStatus.PROCESSING
            event = "PUBLISH_RECONCILED" if reconciled else "PUBLISH_STARTED"
        elif result.remote_state in {RemotePublishState.UNKNOWN, RemotePublishState.NOT_FOUND}:
            error = PublishTransportError(
                "remote result is indeterminate",
                code="REMOTE_UNKNOWN",
                retryable=False,
                submission_started=True,
                indeterminate=True,
            )
            return self._mark_unknown(request, record, error)
        else:
            record.status = PublishRecordStatus.FAILED
            record.finished_at = publisher_now()
            record.error_code = "REMOTE_FAILED"
            record.error_message = "remote transport reported failure"
            record.metadata["safe_to_retry"] = False
            event = "PUBLISH_FAILED"
        self.store.save_record(record)
        self._audit(event, request, result=record.status.value, actor="system:publisher")
        return record

    def _mark_unknown(
        self,
        request: PublishRequest,
        record: PublishRecord,
        error: PublishTransportError,
    ) -> PublishRecord:
        record.status = PublishRecordStatus.UNKNOWN
        record.remote_state = RemotePublishState.UNKNOWN
        record.error_code = error.code
        record.error_message = str(error)
        record.metadata.update({"submission_started": True, "safe_to_retry": False})
        self.store.save_record(record)
        self._audit("PUBLISH_UNKNOWN", request, result="unknown", actor="system:publisher")
        return record

    def _mark_failed(
        self,
        request: PublishRequest,
        record: PublishRecord,
        error: PublishTransportError,
        *,
        safe_to_retry: bool,
    ) -> PublishRecord:
        record.status = PublishRecordStatus.FAILED
        record.finished_at = publisher_now()
        record.error_code = error.code
        record.error_message = str(error)
        record.metadata["safe_to_retry"] = safe_to_retry
        self.store.save_record(record)
        self._audit("PUBLISH_FAILED", request, result="failed", actor="system:publisher")
        return record

    def _auth_required(
        self,
        request: PublishRequest,
        record: PublishRecord,
        state: AuthenticationState,
    ) -> None:
        record.error_code = state.value
        record.error_message = "human authentication is required"
        self.store.save_record(record)
        self._audit("AUTH_REQUIRED", request, result=state.value, actor="system:publisher")

    def _safe_auth_state(self, platform: str) -> AuthenticationState:
        try:
            return self.session_provider.auth_state(platform)
        except Exception:
            return AuthenticationState.AUTH_REQUIRED

    def _audit(
        self,
        action: str,
        request: PublishRequest,
        *,
        result: str,
        actor: str,
        approval_ref: str | None = None,
    ) -> None:
        self.audit.record(
            actor=actor,
            action=action,
            resource=f"publish-request:{request.request_id}",
            permission=Permission.PUBLISH,
            decision="allow",
            result=result,
            approval_ref=approval_ref,
            correlation_id=request.request_id,
            run_id=self.jobs.load(request.job_id).run_id,
            context={
                "job_id": request.job_id,
                "job_revision": request.job_revision,
                "mode": request.mode.value,
                "platform": request.platform,
            },
        )

    @classmethod
    def _lock_for(cls, key: str) -> threading.Lock:
        with cls._locks_guard:
            return cls._locks.setdefault(key, threading.Lock())

    def _require_safe_mode(self) -> None:
        if self._legacy:
            raise RuntimeError("safe publisher dependencies are not configured")

    def _legacy_prepare(self, job: CreatorJob) -> Path:
        report = self._legacy_validate(job)
        if not report.passed:
            raise ValueError("Bilibili package validation failed: " + "; ".join(report.errors))
        if not job.package_path:
            raise ValueError("CreatorJob has no prepared Bilibili package")
        return job.package_path

    def _legacy_validate(self, job: CreatorJob) -> BilibiliValidationReport:
        checks = {
            "publish_ready": job.status == "PUBLISH_READY",
            "human_approved": job.approval_status == "APPROVED" and bool(job.approved_by),
            "creator_qa_passed": bool(job.qa_report and job.qa_report.passed),
            "package_exists": bool(job.package_path and job.package_path.is_file()),
            "video_exists": bool(job.video_path and job.video_path.is_file()),
            "thumbnail_exists": bool(job.thumbnail_path and job.thumbnail_path.is_file()),
            "real_provenance": not job.testing and not job.dry_run,
            "official_transport_configured": self.mode == "manual_handoff" or self.transport is not None,
        }
        errors = [name for name, value in checks.items() if not value]
        warnings = (
            ["manual_handoff requires a human to publish on Bilibili and record a real receipt"]
            if self.mode == "manual_handoff"
            else []
        )
        return BilibiliValidationReport(
            passed=not errors,
            mode=self.mode,
            checks=checks,
            errors=errors,
            warnings=warnings,
        )

    def _legacy_publish(self, job: CreatorJob) -> str:
        report = self._legacy_validate(job)
        if not report.passed:
            raise ValueError("Bilibili package validation failed: " + "; ".join(report.errors))
        if self.mode == "manual_handoff":
            raise ManualPublicationRequired(
                f"Upload the immutable package manually, then record the BV receipt: {job.package_path}"
            )
        if self.transport is None:
            raise OfficialContractUnavailable(
                "Authenticated Bilibili Open Platform contract/transport is not configured"
            )
        return self.transport.publish(job)

    def _legacy_status(self, job: CreatorJob) -> str:
        if job.status == "PUBLISHED":
            if self.mode == "official_api" and self.transport and job.platform_content_id:
                return self.transport.status(job.platform_content_id)
            return "PUBLISHED"
        if job.status == "PUBLISH_READY":
            return "PUBLISH_READY"
        return job.publish_status.value
