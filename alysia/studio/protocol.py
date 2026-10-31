from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


def studio_now() -> datetime:
    return datetime.now().astimezone()


def stable_studio_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


HandoffStatus = Literal["pending", "accepted", "completed", "rejected", "escalated"]
AgentResultStatus = Literal["completed", "failed", "blocked", "revision_required", "skipped"]
AgentFailureKind = Literal[
    "recoverable",
    "provider_failure",
    "artifact_invalid",
    "qa_failure",
    "approval_required",
    "human_intervention_required",
]
StudioRunStatus = Literal["idle", "running", "waiting_for_approval", "completed", "failed", "escalated"]


class ArtifactRef(BaseModel):
    artifact_id: str
    kind: str
    path: str
    owner_agent_id: str
    version: int = Field(default=1, ge=1)
    source_run_artifact: str | None = None
    summary: str = ""
    testing: bool = False
    active: bool = True
    created_at: datetime = Field(default_factory=studio_now)


class AgentProfile(BaseModel):
    agent_id: str
    role: str
    capabilities: list[str]
    accepted_inputs: list[str]
    produced_artifacts: list[str]
    required_context: list[str]
    allowed_tools: list[str]
    allowed_providers: list[str]
    quality_responsibilities: list[str]
    escalation_rules: list[str]


class AgentHandoff(BaseModel):
    handoff_id: str
    from_agent: str
    to_agent: str
    objective: str
    required_inputs: list[str]
    provided_artifacts: list[ArtifactRef]
    acceptance_criteria: list[str]
    constraints: list[str]
    open_questions: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=studio_now)
    updated_at: datetime = Field(default_factory=studio_now)
    status: HandoffStatus = "pending"
    status_reason: str | None = None

    @model_validator(mode="after")
    def validate_contract(self) -> "AgentHandoff":
        if self.from_agent == self.to_agent:
            raise ValueError("handoff 的 from_agent 与 to_agent 不能相同")
        if not self.objective.strip():
            raise ValueError("handoff objective 不能为空")
        if not self.acceptance_criteria:
            raise ValueError("handoff 必须包含 acceptance_criteria")
        return self


class AgentDecision(BaseModel):
    decision_id: str
    agent_id: str
    summary: str
    rationale: str
    input_artifact_ids: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=studio_now)


class AgentResult(BaseModel):
    agent_id: str
    task_id: str
    status: AgentResultStatus
    produced_artifacts: list[ArtifactRef] = Field(default_factory=list)
    summary: str
    decisions: list[AgentDecision] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
    next_recommended_agent: str | None = None
    failure: "AgentFailure | None" = None
    completed_at: datetime = Field(default_factory=studio_now)

    @model_validator(mode="after")
    def validate_failure(self) -> "AgentResult":
        if self.status == "failed" and self.failure is None:
            raise ValueError("failed AgentResult 必须包含 failure")
        return self


class AgentFailure(BaseModel):
    kind: AgentFailureKind
    agent_id: str
    message: str
    recoverable: bool
    failed_artifact_kind: str | None = None
    suggested_owner_agent: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime = Field(default_factory=studio_now)


class RevisionRequest(BaseModel):
    request_id: str
    artifact_kind: str
    artifact_id: str | None = None
    requested_by: str
    owner_agent_id: str
    reason: str
    acceptance_criteria: list[str]
    status: Literal["pending", "accepted", "completed", "rejected"] = "pending"
    created_at: datetime = Field(default_factory=studio_now)
    completed_artifact_id: str | None = None


class StudioTraceEvent(BaseModel):
    event_id: str
    run_id: str
    event_type: str
    actor: str
    summary: str
    handoff_id: str | None = None
    task_id: str | None = None
    artifact_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=studio_now)


class StudioState(BaseModel):
    run_id: str
    status: StudioRunStatus = "idle"
    current_agent: str = "studio_director"
    previous_agent: str | None = None
    agent_hops: int = Field(default=0, ge=0)
    review_rounds: int = Field(default=0, ge=0)
    pending_handoff_id: str | None = None
    completed_agents: list[str] = Field(default_factory=list)
    production_plan_id: str | None = None
    escalation: AgentFailure | None = None
    last_error: str | None = None
    updated_at: datetime = Field(default_factory=studio_now)


class StudioQAReport(BaseModel):
    run_id: str
    passed: bool
    checks: dict[str, bool]
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)
    generated_at: datetime = Field(default_factory=studio_now)
