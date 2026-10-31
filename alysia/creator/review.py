from __future__ import annotations

import json
import re
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Callable, Iterable, Mapping

from pydantic import BaseModel, Field

from alysia.core.io import atomic_write_json
from alysia.creator.models import (
    ApprovalStatus,
    ClaimClassification,
    CreatorJob,
    CreatorPlan,
    EvidenceStatus,
    PublishStatus,
    RevisionRecord,
)
from alysia.creator.production import (
    ArtifactStatus,
    ProductionArtifact,
    ProductionArtifactRegistry,
    ProductionPlan,
    ProductionStatus,
)
from alysia.creator.store import CreatorJobStore
from alysia.knowledge.models import stable_id
from alysia.security.approvals import ApprovalValidator
from alysia.security.audit import AuditLog
from alysia.security.network import NetworkPolicy
from alysia.security.redaction import Redactor
from alysia.schemas.security import Permission
from alysia.workers.media import find_media_executable, probe_media


def review_now() -> datetime:
    return datetime.now().astimezone()


class QAIssueSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class QAOverallResult(str, Enum):
    PASS = "PASS"
    PASS_WITH_WARNINGS = "PASS_WITH_WARNINGS"
    FAIL = "FAIL"
    INCOMPLETE = "INCOMPLETE"


class QAStatus(str, Enum):
    COMPLETED = "COMPLETED"
    STALE = "STALE"


class ReviewAction(str, Enum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    REQUEST_REVISION = "REQUEST_REVISION"


class QAIssue(BaseModel):
    issue_id: str = Field(min_length=1)
    category: str = Field(min_length=1)
    severity: QAIssueSeverity
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    evidence_refs: list[str] = Field(default_factory=list)
    artifact_refs: list[str] = Field(default_factory=list)
    blocking: bool = False
    suggested_action: str = ""

    @classmethod
    def create(
        cls,
        *,
        category: str,
        severity: QAIssueSeverity,
        code: str,
        message: str,
        evidence_refs: Iterable[str] = (),
        artifact_refs: Iterable[str] = (),
        blocking: bool = False,
        suggested_action: str = "",
    ) -> "QAIssue":
        return cls(
            issue_id=stable_id("qa_issue", category, code, message, *evidence_refs, *artifact_refs),
            category=category,
            severity=severity,
            code=code,
            message=message,
            evidence_refs=list(evidence_refs),
            artifact_refs=list(artifact_refs),
            blocking=blocking,
            suggested_action=suggested_action,
        )


class QAReport(BaseModel):
    qa_id: str = Field(min_length=1)
    job_id: str = Field(pattern=r"^creator_[0-9a-f]{16}$")
    creator_plan_id: str = Field(min_length=1)
    production_id: str = Field(min_length=1)
    job_revision: int = Field(ge=1)
    created_at: datetime = Field(default_factory=review_now)
    status: QAStatus = QAStatus.COMPLETED
    content_checks: list[QAIssue] = Field(default_factory=list)
    grounding_checks: list[QAIssue] = Field(default_factory=list)
    media_checks: list[QAIssue] = Field(default_factory=list)
    metadata_checks: list[QAIssue] = Field(default_factory=list)
    safety_checks: list[QAIssue] = Field(default_factory=list)
    blocking_issues: list[QAIssue] = Field(default_factory=list)
    warnings: list[QAIssue] = Field(default_factory=list)
    informational: list[QAIssue] = Field(default_factory=list)
    overall_result: QAOverallResult
    review_required: bool
    metadata: dict[str, object] = Field(default_factory=dict)

    @property
    def review_eligible(self) -> bool:
        return self.overall_result in {QAOverallResult.PASS, QAOverallResult.PASS_WITH_WARNINGS}


class ReviewDecision(BaseModel):
    review_id: str = Field(min_length=1)
    job_id: str = Field(pattern=r"^creator_[0-9a-f]{16}$")
    qa_id: str = Field(min_length=1)
    action: ReviewAction
    reason: str = Field(min_length=1)
    reviewer: str = Field(min_length=1)
    created_at: datetime = Field(default_factory=review_now)
    job_revision: int = Field(ge=1)
    requested_changes: list[str] = Field(default_factory=list)
    metadata: dict[str, object] = Field(default_factory=dict)


class CreatorQAConfig(BaseModel):
    thumbnail_required: bool = True
    audio_required: bool = True
    max_av_duration_delta: float = Field(default=0.5, ge=0)
    av_delta_blocking_threshold: float = Field(default=2.0, ge=0)


def issue(
    category: str,
    code: str,
    message: str,
    *,
    severity: QAIssueSeverity = QAIssueSeverity.ERROR,
    blocking: bool = True,
    evidence_refs: Iterable[str] = (),
    artifact_refs: Iterable[str] = (),
    suggested_action: str = "",
) -> QAIssue:
    return QAIssue.create(
        category=category,
        severity=severity,
        code=code,
        message=message,
        blocking=blocking,
        evidence_refs=evidence_refs,
        artifact_refs=artifact_refs,
        suggested_action=suggested_action,
    )


class GroundingQAChecker:
    def check(self, job: CreatorJob, plan: CreatorPlan) -> list[QAIssue]:
        issues: list[QAIssue] = []
        claims = {claim.claim_id: claim for claim in job.claims}
        uncertain_ids = {
            claim.claim_id
            for claim in job.claims
            if claim.evidence_status in {
                EvidenceStatus.CONFLICTING,
                EvidenceStatus.INSUFFICIENT_EVIDENCE,
                EvidenceStatus.UNVERIFIED,
            }
        }
        required_uncertainty_refs = {*uncertain_ids, *job.uncertainties}
        missing_uncertainties = required_uncertainty_refs.difference(plan.uncertainty_refs)
        if missing_uncertainties:
            issues.append(issue(
                "grounding",
                "UNCERTAINTY_TRACE_LOST",
                "CreatorPlan no longer retains every current uncertainty reference.",
                evidence_refs=sorted(missing_uncertainties),
                suggested_action="Restore uncertainty_refs and regenerate QA.",
            ))
        for section in plan.script_sections:
            for claim_ref in section.claim_refs:
                claim = claims.get(claim_ref)
                if claim is None:
                    issues.append(issue(
                        "grounding",
                        "UNKNOWN_CLAIM_REF",
                        f"Script section {section.section_id} references an unknown claim.",
                        evidence_refs=[claim_ref],
                    ))
                    continue
                if section.factual and claim.evidence_status in {
                    EvidenceStatus.CONFLICTING,
                    EvidenceStatus.INSUFFICIENT_EVIDENCE,
                    EvidenceStatus.UNVERIFIED,
                }:
                    issues.append(issue(
                        "grounding",
                        "UNCERTAIN_CLAIM_AS_FACT",
                        f"Script section {section.section_id} presents uncertain evidence as factual.",
                        evidence_refs=[claim_ref],
                    ))
                if section.factual and claim.classification in {
                    ClaimClassification.INFERENCE,
                    ClaimClassification.OPINION,
                    ClaimClassification.UNKNOWN,
                }:
                    issues.append(issue(
                        "grounding",
                        "NON_FACTUAL_CLAIM_AS_FACT",
                        f"Script section {section.section_id} presents {claim.classification.value} as verified fact.",
                        evidence_refs=[claim_ref],
                    ))
        if job.script.strip() != plan.script.strip():
            issues.append(issue(
                "grounding",
                "SCRIPT_TRACE_CHANGED",
                "Production script differs from the grounded CreatorPlan script.",
                suggested_action="Create a new revision and rerun QA.",
            ))
        return issues


class ContentQAChecker:
    def check(self, job: CreatorJob, plan: CreatorPlan) -> list[QAIssue]:
        issues: list[QAIssue] = []
        if not job.script.strip():
            issues.append(issue("content", "EMPTY_SCRIPT", "CreatorJob script is empty."))
        if not plan.core_message.strip():
            issues.append(issue("content", "MISSING_CORE_MESSAGE", "CreatorPlan core message is empty."))
        normalized_sections = [self._normalize(section.text) for section in plan.script_sections]
        duplicates = {text for text in normalized_sections if text and normalized_sections.count(text) > 1}
        if duplicates:
            issues.append(issue(
                "content", "DUPLICATE_SECTIONS", "Script contains duplicate sections.",
                suggested_action="Remove repeated sections before review.",
            ))
        positive = {self._normalize(text) for text in normalized_sections if "不是" not in text and " not " not in f" {text} "}
        negative = {
            self._normalize(text.replace("不是", "是").replace(" not ", " "))
            for text in normalized_sections
            if "不是" in text or " not " in f" {text} "
        }
        if positive.intersection(negative):
            issues.append(issue("content", "INTERNAL_CONTRADICTION", "Script contains an obvious direct contradiction."))
        sentences = [self._normalize(value) for value in re.split(r"[。！？.!?]+", job.script) if value.strip()]
        if sentences and len(set(sentences)) / len(sentences) < 0.6:
            issues.append(issue(
                "content",
                "EXCESSIVE_REPETITION",
                "Script repeats a high proportion of sentences.",
                severity=QAIssueSeverity.WARNING,
                blocking=False,
            ))
        return issues

    @staticmethod
    def _normalize(value: str) -> str:
        return re.sub(r"\s+", " ", value.strip().casefold())


class MediaQAChecker:
    def __init__(
        self,
        registry: ProductionArtifactRegistry,
        config: CreatorQAConfig,
        media_probe: Callable[[Path], dict[str, object]] | None = None,
    ) -> None:
        self.registry = registry
        self.config = config
        self.media_probe = media_probe or self._probe

    def check(self, job: CreatorJob, artifacts: list[ProductionArtifact]) -> list[QAIssue]:
        issues: list[QAIssue] = []
        videos = [item for item in artifacts if item.artifact_type in {"VIDEO", "COMPOSITE"}]
        thumbnails = [item for item in artifacts if item.artifact_type == "THUMBNAIL"]
        if not job.video_path or not job.video_path.is_file() or job.video_path.stat().st_size == 0:
            issues.append(issue("media", "MISSING_VIDEO", "Production video is missing or empty."))
        elif not videos:
            issues.append(issue("media", "VIDEO_MANIFEST_MISSING", "Video has no production artifact manifest."))
        elif not any(item.path.resolve() == job.video_path.resolve() for item in videos):
            issues.append(issue("media", "VIDEO_ARTIFACT_MISMATCH", "CreatorJob video path does not match a video artifact manifest."))
        if self.config.thumbnail_required:
            if not job.thumbnail_path or not job.thumbnail_path.is_file():
                issues.append(issue("media", "MISSING_THUMBNAIL", "Required thumbnail is missing."))
            elif not thumbnails:
                issues.append(issue("media", "THUMBNAIL_MANIFEST_MISSING", "Thumbnail has no artifact manifest."))
            elif not any(item.path.resolve() == job.thumbnail_path.resolve() for item in thumbnails):
                issues.append(issue("media", "THUMBNAIL_ARTIFACT_MISMATCH", "CreatorJob thumbnail path does not match a thumbnail artifact manifest."))
        for artifact in [*videos, *thumbnails]:
            if artifact.status != ArtifactStatus.VALID or not self.registry.valid([artifact.artifact_id]):
                issues.append(issue(
                    "media",
                    "INVALID_ARTIFACT",
                    f"Artifact {artifact.artifact_id} is not currently valid.",
                    artifact_refs=[artifact.artifact_id],
                ))
        if job.video_path and job.video_path.is_file() and job.video_path.stat().st_size > 0 and videos:
            try:
                payload = self.media_probe(job.video_path)
                issues.extend(self._validate_probe(payload, videos[0].artifact_id))
            except FileNotFoundError as exc:
                issues.append(issue(
                    "media",
                    "INCOMPLETE_MEDIA_PROBE",
                    str(exc),
                    suggested_action="Install/configure ffprobe before human review.",
                ))
            except (OSError, RuntimeError, ValueError, KeyError, json.JSONDecodeError) as exc:
                issues.append(issue("media", "MEDIA_UNREADABLE", f"Media probe failed: {exc}"))
        return issues

    def _validate_probe(self, payload: dict[str, object], artifact_id: str) -> list[QAIssue]:
        issues: list[QAIssue] = []
        streams = list(payload.get("streams") or [])
        video = next((stream for stream in streams if stream.get("codec_type") == "video"), None)
        audio = next((stream for stream in streams if stream.get("codec_type") == "audio"), None)
        if video is None:
            issues.append(issue("media", "VIDEO_STREAM_MISSING", "No video stream was detected.", artifact_refs=[artifact_id]))
            return issues
        width = int(video.get("width") or 0)
        height = int(video.get("height") or 0)
        duration = float((payload.get("format") or {}).get("duration") or video.get("duration") or 0)
        if width <= 0 or height <= 0:
            issues.append(issue("media", "INVALID_RESOLUTION", "Video resolution is invalid.", artifact_refs=[artifact_id]))
        if duration <= 0:
            issues.append(issue("media", "ZERO_DURATION", "Video duration must be greater than zero.", artifact_refs=[artifact_id]))
        if self.config.audio_required and audio is None:
            issues.append(issue("media", "AUDIO_STREAM_MISSING", "Required audio stream was not detected.", artifact_refs=[artifact_id]))
        if audio is not None:
            audio_duration = float(audio.get("duration") or duration)
            delta = abs(duration - audio_duration)
            if delta > self.config.max_av_duration_delta:
                blocking = delta > self.config.av_delta_blocking_threshold
                issues.append(issue(
                    "media",
                    "AV_DURATION_MISMATCH",
                    f"Audio/video duration delta is {delta:.3f}s.",
                    severity=QAIssueSeverity.ERROR if blocking else QAIssueSeverity.WARNING,
                    blocking=blocking,
                    artifact_refs=[artifact_id],
                ))
        return issues

    @staticmethod
    def _probe(path: Path) -> dict[str, object]:
        ffprobe = find_media_executable("ffprobe")
        if ffprobe is None:
            raise FileNotFoundError("ffprobe is unavailable")
        return probe_media(path, ffprobe)


class MetadataQAChecker:
    def check(self, job: CreatorJob, plan: CreatorPlan) -> list[QAIssue]:
        issues: list[QAIssue] = []
        required = {
            "MISSING_TITLE": job.selected_title,
            "MISSING_DESCRIPTION": job.description,
        }
        for code, value in required.items():
            if not value.strip():
                issues.append(issue("metadata", code, code.replace("_", " ").title()))
        if not job.tags or any(not tag.strip() for tag in job.tags):
            issues.append(issue("metadata", "INVALID_TAGS", "Tags must contain non-empty values."))
        body_tokens = self._tokens(job.script + " " + plan.core_message)
        for label, value in (("TITLE", job.selected_title), ("DESCRIPTION", job.description)):
            value_tokens = self._tokens(value)
            if value_tokens and body_tokens and not value_tokens.intersection(body_tokens):
                issues.append(issue(
                    "metadata",
                    f"{label}_BODY_MISMATCH",
                    f"{label.title()} has no obvious lexical overlap with script/core message.",
                    severity=QAIssueSeverity.WARNING,
                    blocking=False,
                ))
        tag_tokens = {token for tag in job.tags for token in self._tokens(tag)}
        if tag_tokens and body_tokens and not tag_tokens.intersection(body_tokens):
            issues.append(issue(
                "metadata",
                "TAGS_BODY_MISMATCH",
                "Tags have no obvious lexical overlap with content.",
                severity=QAIssueSeverity.WARNING,
                blocking=False,
            ))
        return issues

    @staticmethod
    def _tokens(value: str) -> set[str]:
        ascii_words = set(re.findall(r"[a-z0-9]{2,}", value.casefold()))
        chinese = "".join(re.findall(r"[\u4e00-\u9fff]", value))
        return ascii_words | {chinese[index:index + 2] for index in range(max(0, len(chinese) - 1))}


class SafetyQAChecker:
    def __init__(self, artifact_root: Path, redactor: Redactor | None = None) -> None:
        self.artifact_root = artifact_root.resolve()
        self.redactor = redactor or Redactor()
        self.network = NetworkPolicy()

    def check(self, job: CreatorJob, plan: CreatorPlan) -> list[QAIssue]:
        issues: list[QAIssue] = []
        public_text = "\n".join([
            job.selected_title,
            job.description,
            " ".join(job.tags),
            job.script,
            plan.core_message,
        ])
        if self.redactor.redact(public_text) != public_text:
            issues.append(issue(
                "safety",
                "SECRET_LEAKAGE",
                "Public content contains credential-like material.",
                severity=QAIssueSeverity.CRITICAL,
            ))
        for url in re.findall(r"https?://[^\s)\]>]+", public_text):
            if self.network.classify(url) in {"local_loopback", "denied_private_network"}:
                issues.append(issue(
                    "safety",
                    "PRIVATE_NETWORK_REFERENCE",
                    "Public metadata contains a private or loopback network reference.",
                    severity=QAIssueSeverity.CRITICAL,
                ))
        for path in (job.video_path, job.thumbnail_path):
            if path is not None and not path.resolve().is_relative_to(self.artifact_root):
                issues.append(issue(
                    "safety",
                    "UNSAFE_ARTIFACT_PATH",
                    "CreatorJob media path escapes the configured production artifact root.",
                    severity=QAIssueSeverity.CRITICAL,
                ))
        return issues


class QAReviewStore:
    def __init__(self, root: Path, redactor: Redactor | None = None) -> None:
        self.root = root.resolve()
        self.redactor = redactor or Redactor()
        (self.root / "qa").mkdir(parents=True, exist_ok=True)
        (self.root / "reviews").mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _safe(value: str, prefix: str) -> str:
        if not re.fullmatch(rf"{prefix}_[0-9a-f]{{16}}", value):
            raise ValueError(f"invalid {prefix} id")
        return value

    def save_qa(self, report: QAReport) -> Path:
        path = self.root / "qa" / self._safe_job(report.job_id) / f"{self._safe(report.qa_id, 'qa')}.json"
        return atomic_write_json(path, self.redactor.redact_value(report.model_dump(mode="json")))

    def load_qa(self, job_id: str, qa_id: str) -> QAReport:
        path = self.root / "qa" / self._safe_job(job_id) / f"{self._safe(qa_id, 'qa')}.json"
        if not path.is_file():
            raise FileNotFoundError(path)
        return QAReport.model_validate(json.loads(path.read_text(encoding="utf-8")))

    def qa_history(self, job_id: str) -> list[QAReport]:
        return [
            QAReport.model_validate(json.loads(path.read_text(encoding="utf-8")))
            for path in sorted((self.root / "qa" / self._safe_job(job_id)).glob("qa_*.json"))
        ]

    def save_review(self, decision: ReviewDecision) -> Path:
        path = self.root / "reviews" / self._safe_job(decision.job_id) / f"{self._safe(decision.review_id, 'review')}.json"
        if path.is_file():
            existing = ReviewDecision.model_validate(json.loads(path.read_text(encoding="utf-8")))
            if existing != decision:
                raise FileExistsError("review_id already exists with different content")
            return path
        return atomic_write_json(path, self.redactor.redact_value(decision.model_dump(mode="json")))

    def load_review(self, job_id: str, review_id: str) -> ReviewDecision:
        path = self.root / "reviews" / self._safe_job(job_id) / f"{self._safe(review_id, 'review')}.json"
        if not path.is_file():
            raise FileNotFoundError(path)
        return ReviewDecision.model_validate(json.loads(path.read_text(encoding="utf-8")))

    def review_history(self, job_id: str) -> list[ReviewDecision]:
        return [
            ReviewDecision.model_validate(json.loads(path.read_text(encoding="utf-8")))
            for path in sorted((self.root / "reviews" / self._safe_job(job_id)).glob("review_*.json"))
        ]

    @staticmethod
    def _safe_job(job_id: str) -> str:
        if not re.fullmatch(r"creator_[0-9a-f]{16}", job_id):
            raise ValueError("invalid CreatorJob job_id")
        return job_id


class CreatorQAService:
    def __init__(
        self,
        *,
        jobs: CreatorJobStore,
        production_artifacts: ProductionArtifactRegistry,
        store: QAReviewStore,
        audit: AuditLog,
        config: CreatorQAConfig | None = None,
        media_probe: Callable[[Path], dict[str, object]] | None = None,
    ) -> None:
        self.jobs = jobs
        self.production_artifacts = production_artifacts
        self.store = store
        self.audit = audit
        self.config = config or CreatorQAConfig()
        self.grounding = GroundingQAChecker()
        self.content = ContentQAChecker()
        self.media = MediaQAChecker(production_artifacts, self.config, media_probe)
        self.metadata = MetadataQAChecker()
        self.safety = SafetyQAChecker(production_artifacts.root)

    def run(self, job_id: str, creator_plan: CreatorPlan, production_plan: ProductionPlan) -> QAReport:
        job = self.jobs.load(job_id)
        self._audit("QA_STARTED", job, actor="system:creator_qa", result="started")
        association_issues: list[QAIssue] = []
        if creator_plan.job_id != job_id or production_plan.job_id != job_id:
            association_issues.append(issue("content", "JOB_ASSOCIATION_MISMATCH", "QA inputs belong to different jobs."))
        if creator_plan.plan_id != production_plan.creator_plan_id:
            association_issues.append(issue("content", "PLAN_ASSOCIATION_MISMATCH", "ProductionPlan is not bound to CreatorPlan."))
        if production_plan.status != ProductionStatus.SUCCEEDED:
            association_issues.append(issue(
                "content", "INCOMPLETE_PRODUCTION", "ProductionPlan is not complete."
            ))
        artifacts: list[ProductionArtifact] = []
        for task in production_plan.tasks:
            for artifact_id in task.output_refs:
                try:
                    artifacts.append(self.production_artifacts.load(artifact_id))
                except (FileNotFoundError, ValueError):
                    association_issues.append(issue(
                        "media", "MISSING_ARTIFACT_MANIFEST", f"Artifact manifest is missing: {artifact_id}",
                        artifact_refs=[artifact_id],
                    ))
        grounding = self.grounding.check(job, creator_plan)
        content = [*association_issues, *self.content.check(job, creator_plan)]
        media = self.media.check(job, artifacts)
        metadata = self.metadata.check(job, creator_plan)
        safety = self.safety.check(job, creator_plan)
        all_issues = [*content, *grounding, *media, *metadata, *safety]
        blocking = [item for item in all_issues if item.blocking]
        warnings = [item for item in all_issues if item.severity == QAIssueSeverity.WARNING and not item.blocking]
        informational = [item for item in all_issues if item.severity == QAIssueSeverity.INFO]
        if blocking:
            overall = (
                QAOverallResult.INCOMPLETE
                if any(item.code.startswith("INCOMPLETE_") for item in blocking)
                else QAOverallResult.FAIL
            )
        else:
            overall = QAOverallResult.PASS_WITH_WARNINGS if warnings else QAOverallResult.PASS
        report = QAReport(
            qa_id=stable_id("qa", job.job_id, job.current_revision, creator_plan.plan_id, production_plan.production_id),
            job_id=job.job_id,
            creator_plan_id=creator_plan.plan_id or "",
            production_id=production_plan.production_id,
            job_revision=job.current_revision,
            content_checks=content,
            grounding_checks=grounding,
            media_checks=media,
            metadata_checks=metadata,
            safety_checks=safety,
            blocking_issues=blocking,
            warnings=warnings,
            informational=informational,
            overall_result=overall,
            review_required=overall in {QAOverallResult.PASS, QAOverallResult.PASS_WITH_WARNINGS},
            metadata={"issue_count": len(all_issues)},
        )
        self.store.save_qa(report)
        if report.review_eligible and job.approval_status == ApprovalStatus.DRAFT:
            job = job.transition_approval(ApprovalStatus.REVIEW)
            self.jobs.save(job)
        self._audit("QA_COMPLETED", job, actor="system:creator_qa", result=report.overall_result.value, ref=report.qa_id)
        return report

    @staticmethod
    def stale(report: QAReport, job: CreatorJob) -> bool:
        return report.job_revision != job.current_revision

    def load_report(self, job_id: str, qa_id: str) -> QAReport:
        report = self.store.load_qa(job_id, qa_id)
        job = self.jobs.load(job_id)
        return report.model_copy(update={"status": QAStatus.STALE}) if self.stale(report, job) else report

    def _audit(
        self,
        action: str,
        job: CreatorJob,
        *,
        actor: str,
        result: str,
        ref: str | None = None,
    ) -> None:
        self.audit.record(
            actor=actor,
            action=action,
            resource=f"creator-job:{job.job_id}",
            permission=Permission.READ_ARTIFACT,
            decision="allow",
            result=result,
            approval_ref=ref,
            correlation_id=job.job_id,
            run_id=job.run_id,
            context={"job_revision": job.current_revision},
        )


class HumanReviewService:
    def __init__(
        self,
        *,
        jobs: CreatorJobStore,
        store: QAReviewStore,
        audit: AuditLog,
    ) -> None:
        self.jobs = jobs
        self.store = store
        self.audit = audit

    def submit(
        self,
        *,
        job_id: str,
        qa_id: str,
        action: ReviewAction,
        reason: str,
        reviewer: str,
        job_revision: int,
        requested_changes: Iterable[str] = (),
        metadata: Mapping[str, object] | None = None,
    ) -> ReviewDecision:
        changes = list(requested_changes)
        decision = ReviewDecision(
            review_id=stable_id(
                "review", job_id, qa_id, job_revision, action.value, reviewer, reason, *changes
            ),
            job_id=job_id,
            qa_id=qa_id,
            action=action,
            reason=reason,
            reviewer=reviewer,
            job_revision=job_revision,
            requested_changes=changes,
            metadata=dict(metadata or {}),
        )
        return self.apply_decision(decision)

    def apply_decision(self, decision: ReviewDecision) -> ReviewDecision:
        try:
            existing = self.store.load_review(decision.job_id, decision.review_id)
        except FileNotFoundError:
            existing = None
        if existing is not None:
            existing_request = existing.model_dump(exclude={"created_at"})
            incoming_request = decision.model_dump(exclude={"created_at"})
            if existing_request != incoming_request:
                raise ValueError("review_id conflicts with an existing decision")
            return existing
        reviewer_key = decision.reviewer.removeprefix("human:").strip().casefold()
        if (
            not decision.reviewer.startswith("human:")
            or reviewer_key in ApprovalValidator.FORBIDDEN_APPROVERS
        ):
            raise PermissionError("reviewer must be an explicit human identity")
        job = self.jobs.load(decision.job_id)
        report = self.store.load_qa(decision.job_id, decision.qa_id)
        if job.current_revision != decision.job_revision or report.job_revision != decision.job_revision:
            raise ValueError("stale review or QA revision")
        if report.job_id != job.job_id:
            raise ValueError("QAReport belongs to a different CreatorJob")
        if decision.action == ReviewAction.APPROVE:
            if not report.review_eligible:
                raise PermissionError("QA FAIL/INCOMPLETE cannot be approved")
            job = job.transition_approval(
                ApprovalStatus.APPROVED,
                approved_by=decision.reviewer,
                approved_at=decision.created_at,
            )
            job.approval_ref = decision.review_id
            event = "REVIEW_APPROVED"
        elif decision.action == ReviewAction.REJECT:
            if job.approval_status != ApprovalStatus.REVIEW:
                raise ValueError("REJECT requires CreatorJob in REVIEW")
            job = job.transition_approval(ApprovalStatus.REJECTED)
            event = "REVIEW_REJECTED"
        else:
            if job.approval_status != ApprovalStatus.REVIEW:
                raise ValueError("REQUEST_REVISION requires CreatorJob in REVIEW")
            if not decision.requested_changes:
                raise ValueError("REQUEST_REVISION requires requested_changes")
            snapshot = self.jobs.save_revision(job)
            job.revisions.append(RevisionRecord(
                revision=job.current_revision,
                reason=decision.reason,
                requested_by=decision.reviewer,
                requested_at=decision.created_at,
                snapshot_path=snapshot,
            ))
            job.current_revision += 1
            job.updated_at = review_now()
            job.status = "DRAFT"
            job.approval_status = ApprovalStatus.REVISION_REQUIRED
            job.publish_status = PublishStatus.NOT_READY
            job.approved_by = None
            job.approved_at = None
            job.approval_ref = None
            job.package_hash = None
            job.package_path = None
            event = "REVISION_REQUESTED"
        self.jobs.save(job)
        self.store.save_review(decision)
        self._audit(event, job, decision)
        return decision

    def enter_publish_ready(self, *, job_id: str, qa_id: str, review_id: str) -> CreatorJob:
        job = self.jobs.load(job_id)
        report = self.store.load_qa(job_id, qa_id)
        decision = self.store.load_review(job_id, review_id)
        if not report.review_eligible:
            raise PermissionError("QA does not permit PUBLISH_READY")
        if report.job_revision != job.current_revision:
            raise ValueError("stale QA cannot authorize PUBLISH_READY")
        if (
            decision.action != ReviewAction.APPROVE
            or decision.qa_id != qa_id
            or decision.job_revision != job.current_revision
        ):
            raise ValueError("stale or non-approval review cannot authorize PUBLISH_READY")
        if job.approval_status != ApprovalStatus.APPROVED:
            raise PermissionError("CreatorJob is not APPROVED")
        job = job.transition_publish(PublishStatus.PUBLISH_READY)
        self.jobs.save(job)
        self._audit("PUBLISH_READY_ENTERED", job, decision)
        return job

    def update_content(
        self,
        job_id: str,
        changes: Mapping[str, object],
        *,
        reason: str,
        actor: str,
    ) -> CreatorJob:
        before = self.jobs.load(job_id)
        updated = self.jobs.update(job_id, changes, reason=reason, updated_by=actor)
        if before.approval_status == ApprovalStatus.APPROVED and updated.approval_status != ApprovalStatus.APPROVED:
            decision = ReviewDecision(
                review_id=stable_id("review", job_id, updated.current_revision, "approval_invalidated", actor),
                job_id=job_id,
                qa_id="qa_0000000000000000",
                action=ReviewAction.REQUEST_REVISION,
                reason=reason,
                reviewer=actor,
                job_revision=updated.current_revision,
                requested_changes=sorted(changes),
            )
            self._audit("APPROVAL_INVALIDATED", updated, decision)
        return updated

    def _audit(self, action: str, job: CreatorJob, decision: ReviewDecision) -> None:
        self.audit.record(
            actor=decision.reviewer,
            action=action,
            resource=f"creator-job:{job.job_id}",
            permission=Permission.WRITE_ARTIFACT,
            decision="allow",
            result=action.casefold(),
            approval_ref=decision.review_id,
            correlation_id=job.job_id,
            run_id=job.run_id,
            context={
                "job_revision": job.current_revision,
                "qa_id": decision.qa_id,
                "requested_change_count": len(decision.requested_changes),
            },
        )
