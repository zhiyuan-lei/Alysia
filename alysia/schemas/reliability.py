from __future__ import annotations

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class FailureCategory(str, Enum):
    TIMEOUT = "timeout"
    OOM = "oom"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    PROVIDER_ERROR = "provider_error"
    NETWORK_ERROR = "network_error"
    ARTIFACT_MISSING = "artifact_missing"
    ARTIFACT_CORRUPT = "artifact_corrupt"
    STATE_CORRUPT = "state_corrupt"
    DISK_LOW = "disk_low"
    DISK_FULL = "disk_full"
    MEMORY_PRESSURE = "memory_pressure"
    GPU_MEMORY_PRESSURE = "gpu_memory_pressure"
    PROCESS_CRASH = "process_crash"
    RENDER_ERROR = "render_error"
    TTS_ERROR = "tts_error"
    ASR_ERROR = "asr_error"
    H3_ERROR = "h3_error"
    COMFYUI_ERROR = "comfyui_error"
    APPROVAL_WAIT = "approval_wait"
    PERMISSION_DENIED = "permission_denied"
    APPROVAL_INVALID = "approval_invalid"
    CREDENTIAL_UNAVAILABLE = "credential_unavailable"
    POLICY_VIOLATION = "policy_violation"
    CANCELLATION = "cancellation"
    UNKNOWN = "unknown"


FailureStatus = Literal["open", "recovering", "recovered", "escalated", "terminal"]
RecoveryAction = Literal[
    "retry_same_step",
    "retry_with_backoff",
    "use_approved_fallback",
    "restore_checkpoint",
    "invalidate_artifact_and_rebuild_stage",
    "rollback_to_artifact_owner",
    "pause_waiting_resource",
    "escalate_human",
    "terminal_fail",
]


class FailureRecord(BaseModel):
    failure_id: str
    run_id: str | None = None
    workflow_id: str | None = None
    stage: str
    agent: str | None = None
    worker: str | None = None
    provider: str | None = None
    category: FailureCategory
    message: str
    evidence_refs: list[str] = Field(default_factory=list)
    occurred_at: datetime
    recoverable: bool
    retryable: bool
    retry_count: int = Field(default=0, ge=0)
    max_retries: int = Field(default=2, ge=0)
    suggested_action: str
    fallback_refs: list[str] = Field(default_factory=list)
    status: FailureStatus = "open"
    quality_impact: str | None = None
    recovery_round: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def has_owner(self) -> "FailureRecord":
        if not self.run_id and not self.workflow_id:
            raise ValueError("FailureRecord 必须包含 run_id 或 workflow_id")
        return self


class RecoveryDecision(BaseModel):
    failure_id: str
    action: RecoveryAction
    reason: str
    retry_after_sec: float = Field(default=0, ge=0)
    fallback_ref: str | None = None
    checkpoint_id: str | None = None
    artifact_owner: str | None = None
    quality_impact: str | None = None
    requires_human: bool = False
    recovery_round: int = Field(default=0, ge=0)
    decided_at: datetime


class ArtifactIntegrityRecord(BaseModel):
    path: Path
    size: int = Field(default=0, ge=0)
    hash: str | None = None
    media_probe: dict[str, Any] | None = None
    created_at: datetime
    producer: str
    validity: Literal["valid", "invalid", "missing", "unknown"]
    errors: list[str] = Field(default_factory=list)


class CheckpointRecord(BaseModel):
    checkpoint_id: str
    run_id: str
    workflow_id: str | None = None
    stage: str
    status: Literal["started", "succeeded", "failed", "invalidated"]
    state_snapshot: Path
    artifacts: list[ArtifactIntegrityRecord] = Field(default_factory=list)
    created_at: datetime
    valid: bool = True
    invalid_reason: str | None = None


class LongRunningTaskRecord(BaseModel):
    task_id: str
    task_type: str
    run_id: str | None = None
    started_at: datetime
    last_heartbeat: datetime
    expected_timeout: float = Field(gt=0)
    status: Literal["running", "completed", "failed", "timed_out", "cancelled"] = "running"
    pid: int | None = None
    job_id: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class ResourceGuardResult(BaseModel):
    status: Literal["safe", "warning", "blocked"]
    observed_values: dict[str, int | float | str | bool | None] = Field(default_factory=dict)
    thresholds: dict[str, int | float | str | bool | None] = Field(default_factory=dict)
    reasons: list[str] = Field(default_factory=list)
    checked_at: datetime


class RecoveryMetrics(BaseModel):
    recovery_success_rate: float = Field(default=0, ge=0, le=1)
    unnecessary_stage_reexecution_count: int = Field(default=0, ge=0)
    checkpoint_restore_success: int = Field(default=0, ge=0)
    duplicate_publish_job_count: int = Field(default=0, ge=0)
    recovery_rounds: int = Field(default=0, ge=0)
