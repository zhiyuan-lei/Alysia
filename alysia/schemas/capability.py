from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

CapabilityMaturity = Literal["experimental", "stable", "deprecated"]
SkillPipelineState = Literal[
    "PROPOSED", "DESIGNED", "SANDBOX_READY", "TESTING", "EVALUATED",
    "WAITING_APPROVAL", "APPROVED", "REGISTERED", "REJECTED", "FAILED",
]


class Capability(BaseModel):
    capability_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    category: str = Field(min_length=1)
    owner_agent: str = Field(min_length=1)
    implementation_refs: list[str] = Field(min_length=1)
    maturity: CapabilityMaturity = "experimental"
    known_limits: list[str] = Field(default_factory=list)
    prerequisites: list[str] = Field(default_factory=list)
    evaluation_suite: list[str] = Field(default_factory=list)
    last_verified_at: datetime | None = None
    tags: list[str] = Field(default_factory=list)
    accepted_inputs: list[str] = Field(default_factory=list)
    produced_outputs: list[str] = Field(default_factory=list)
    resource_requirements: dict[str, Any] = Field(default_factory=dict)
    policy_restrictions: list[str] = Field(default_factory=list)
    execution_layer: Literal["workflow", "studio", "production", "supervisor"] = "workflow"


class EvaluationEvidence(BaseModel):
    evidence_id: str
    source: str
    run_id: str | None = None
    kind: Literal["observed_failure", "manual_rating", "qa_report", "trace", "metric"]
    summary: str = Field(min_length=1)
    capability_id: str | None = None
    severity: Literal["low", "medium", "high", "critical"] = "medium"
    data: dict[str, Any] = Field(default_factory=dict)


class SelfEvaluationReport(BaseModel):
    report_id: str
    strengths: list[str] = Field(default_factory=list)
    recurring_failures: list[str] = Field(default_factory=list)
    weak_capabilities: list[str] = Field(default_factory=list)
    missing_capabilities: list[str] = Field(default_factory=list)
    reliability_metrics: dict[str, float | int | None] = Field(default_factory=dict)
    evidence: list[EvaluationEvidence] = Field(default_factory=list)
    cause_hypotheses: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
    created_at: datetime


class CapabilityGap(BaseModel):
    gap_id: str
    description: str = Field(min_length=1)
    evidence_runs: list[str] = Field(min_length=1)
    evidence_ids: list[str] = Field(min_length=1)
    affected_agents: list[str] = Field(min_length=1)
    severity: Literal["low", "medium", "high", "critical"]
    frequency: int = Field(ge=1)
    current_workaround: str
    proposed_capability: str
    confidence: float = Field(gt=0, le=1)
    status: Literal["open", "proposed", "resolved", "dismissed"] = "open"


class SkillSecurityPolicy(BaseModel):
    network_allowed: bool = False
    credentials_allowed: bool = False
    core_source_write_allowed: bool = False
    allowed_write_roots: list[str] = Field(default_factory=lambda: ["workspace/sandbox", "tests/fixtures"])


class SkillProposal(BaseModel):
    skill_id: str
    name: str = Field(min_length=1)
    purpose: str = Field(min_length=1)
    gap_refs: list[str] = Field(min_length=1)
    proposed_interface: str = Field(min_length=1)
    required_tools_providers: list[str] = Field(default_factory=list)
    security_risks: list[str] = Field(default_factory=list)
    resource_cost: dict[str, Any] = Field(default_factory=dict)
    expected_benefit: str = Field(min_length=1)
    evaluation_plan: list[str] = Field(min_length=1)
    sandbox_required: bool = True
    approval_required: bool = True
    owner_agents: list[str] = Field(min_length=1)
    state: SkillPipelineState = "PROPOSED"
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def safety_gates_are_mandatory(self) -> "SkillProposal":
        if not self.sandbox_required or not self.approval_required:
            raise ValueError("alpha14 skill 必须经过 sandbox 和人工审批")
        return self


class SkillEvaluationCase(BaseModel):
    name: str
    category: Literal["functional", "quality", "regression", "resource", "security"]
    passed: bool
    observation: str


class SkillEvaluationReport(BaseModel):
    evaluation_id: str
    skill_id: str
    passed: bool
    score: float = Field(ge=0, le=1)
    cases: list[SkillEvaluationCase] = Field(min_length=5)
    failures: list[str] = Field(default_factory=list)
    regressions: list[str] = Field(default_factory=list)
    resource_observations: dict[str, Any] = Field(default_factory=dict)
    recommendation: Literal["reject", "revise", "approve_for_human_review"]
    sandbox_path: str
    created_at: datetime


class SkillRecord(BaseModel):
    skill_id: str
    name: str
    version: int = Field(ge=1)
    status: Literal["active", "disabled", "deprecated", "rolled_back"] = "active"
    provenance: dict[str, str]
    proposal_ref: str
    evaluation_ref: str
    approved_by: str
    approved_at: datetime
    owner_agents: list[str]
    interface: str
    resource_requirements: dict[str, Any] = Field(default_factory=dict)
    rollback_target: int | None = Field(default=None, ge=1)
    tags: list[str] = Field(default_factory=list)
    accepted_inputs: list[str] = Field(default_factory=list)
    produced_outputs: list[str] = Field(default_factory=list)
    prerequisites: list[str] = Field(default_factory=list)
    policy_restrictions: list[str] = Field(default_factory=list)
    execution_layer: Literal["workflow", "studio", "production", "supervisor"] = "production"


class SkillReviewRecord(BaseModel):
    skill_id: str
    reviewer: str
    decision: Literal["ready_for_approval", "rejected", "revision_required"]
    notes: str
    created_at: datetime
