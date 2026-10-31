from __future__ import annotations

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class Permission(str, Enum):
    READ_ARTIFACT = "READ_ARTIFACT"
    WRITE_ARTIFACT = "WRITE_ARTIFACT"
    NETWORK_PUBLIC = "NETWORK_PUBLIC"
    GPU_EXECUTE = "GPU_EXECUTE"
    EXECUTE_LOCAL_TOOL = "EXECUTE_LOCAL_TOOL"
    PUBLISH = "PUBLISH"
    READ_CREDENTIAL_REF = "READ_CREDENTIAL_REF"
    MODIFY_IDENTITY = "MODIFY_IDENTITY"
    MODIFY_BUDGET = "MODIFY_BUDGET"
    APPROVE_SKILL = "APPROVE_SKILL"
    MODIFY_POLICY = "MODIFY_POLICY"
    SYSTEM_CONFIG = "SYSTEM_CONFIG"


PermissionDecisionValue = Literal["allow", "deny", "require_approval"]


class PermissionDecision(BaseModel):
    actor: str = Field(min_length=1)
    permission: Permission
    resource: str = Field(min_length=1)
    decision: PermissionDecisionValue
    reason: str = Field(min_length=1)
    policy_refs: list[str] = Field(default_factory=list)
    approval_ref: str | None = None
    timestamp: datetime


class CredentialReference(BaseModel):
    credential_id: str = Field(min_length=1, pattern=r"^[A-Za-z0-9_.-]+$")
    provider: str = Field(min_length=1)
    source_type: Literal["env", "os_store_ref", "manual_runtime_ref"]
    key_names: list[str] = Field(min_length=1)
    metadata: dict[str, str] = Field(default_factory=dict)


class AuditEvent(BaseModel):
    event_id: str = Field(min_length=1)
    timestamp: datetime
    actor: str = Field(min_length=1)
    action: str = Field(min_length=1)
    resource: str = Field(min_length=1)
    permission: Permission
    decision: PermissionDecisionValue
    approval_ref: str | None = None
    result: str = Field(min_length=1)
    correlation_id: str | None = None
    run_id: str | None = None
    workflow_id: str | None = None
    redacted_context: dict[str, Any] = Field(default_factory=dict)


class SecurityFinding(BaseModel):
    finding_id: str
    path: Path
    category: str
    line: int | None = Field(default=None, ge=1)
    redacted_excerpt: str
    severity: Literal["low", "medium", "high", "critical"] = "high"


class SecurityScanReport(BaseModel):
    root: Path
    scanned_files: int = Field(ge=0)
    findings: list[SecurityFinding] = Field(default_factory=list)
    generated_at: datetime


class ApprovalValidationResult(BaseModel):
    valid: bool
    errors: list[str] = Field(default_factory=list)
    approval_ref: str | None = None
    replay: bool = False


class NetworkDecision(BaseModel):
    actor: str
    url: str
    category: Literal["public_web_research", "approved_api", "local_loopback", "denied_private_network"]
    allowed: bool
    reason: str


class ToolDecision(BaseModel):
    actor: str
    tool: str
    allowed: bool
    reason: str


class SecurityStatus(BaseModel):
    enabled: bool
    default_deny: bool
    policy_version: str
    roles: int = Field(ge=0)
    permissions: int = Field(ge=0)
    audit_log: Path
    audit_events: int = Field(ge=0)
    credential_references: int = Field(ge=0)
    system_config_open_to_agents: bool
    limitations: list[str] = Field(default_factory=list)


class SecurityActionError(PermissionError):
    def __init__(self, decision: PermissionDecision, *, code: str = "permission_denied") -> None:
        super().__init__(f"{code}: {decision.actor} {decision.permission.value} {decision.resource}: {decision.reason}")
        self.code = code
        self.decision = decision


class ApprovalBoundAction(BaseModel):
    action_type: str
    subject_id: str
    artifact_hash: str | None = None
    required_scope: str
    consumption_ref: str | None = None

    @model_validator(mode="after")
    def hash_is_sha256_when_present(self) -> "ApprovalBoundAction":
        if self.artifact_hash is not None and (
            len(self.artifact_hash) != 64 or any(character not in "0123456789abcdef" for character in self.artifact_hash.lower())
        ):
            raise ValueError("artifact_hash 必须为 SHA-256 hex")
        return self
