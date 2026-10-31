from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

WorkflowStatus = Literal[
    "planned", "validated", "running", "completed", "failed", "blocked",
    "blocked_waiting_capability",
]
WorkflowStepStatus = Literal[
    "pending", "running", "completed", "failed", "skipped", "blocked",
]


class WorkflowBudgetPolicy(BaseModel):
    max_local_vram_mb: int = Field(default=6144, ge=256)
    max_wall_time_sec: int | None = Field(default=None, ge=1)
    max_cloud_cost: float | None = Field(default=None, ge=0)
    allow_unknown_resources: bool = False


class WorkflowApprovalPolicy(BaseModel):
    require_human_approval: bool = True
    required_gates: list[str] = Field(default_factory=list)
    allow_mock_artifacts: bool = False


class WorkflowTask(BaseModel):
    task_id: str = Field(min_length=1)
    objective: str = Field(min_length=1)
    inputs: list[str] = Field(default_factory=list)
    desired_outputs: list[str] = Field(min_length=1)
    constraints: list[str] = Field(default_factory=list)
    quality_target: Literal["draft", "standard", "high"] = "standard"
    deadline: datetime | None = None
    budget_policy: WorkflowBudgetPolicy = Field(default_factory=WorkflowBudgetPolicy)
    approval_policy: WorkflowApprovalPolicy = Field(default_factory=WorkflowApprovalPolicy)
    context_refs: list[str] = Field(default_factory=list)
    success_criteria: list[str] = Field(min_length=1)
    execution_mode: Literal["testing", "production"] = "production"

    @model_validator(mode="after")
    def success_is_explicit(self) -> "WorkflowTask":
        vague = {"尽可能做好", "best effort", "do your best"}
        if all(item.strip().lower() in vague for item in self.success_criteria):
            raise ValueError("WorkflowTask 必须包含可验证 success criteria")
        return self


class CandidateCapability(BaseModel):
    candidate_id: str
    source_type: Literal["capability", "skill"]
    version: int | None = None
    status: str
    match_score: float = Field(ge=0, le=1)
    matched_requirements: list[str] = Field(default_factory=list)
    missing_requirements: list[str] = Field(default_factory=list)
    prerequisites: list[str] = Field(default_factory=list)
    accepted_inputs: list[str] = Field(default_factory=list)
    produced_outputs: list[str] = Field(default_factory=list)
    owner_agent: str
    execution_layer: Literal["workflow", "studio", "production", "supervisor"] = "workflow"
    resource_notes: list[str] = Field(default_factory=list)
    risk_notes: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
    eligible: bool = True


class WorkflowStep(BaseModel):
    step_id: str
    capability_id: str | None = None
    skill_id: str | None = None
    owner_agent: str
    inputs: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(min_length=1)
    depends_on: list[str] = Field(default_factory=list)
    retry_policy: dict[str, Any] = Field(default_factory=lambda: {"max_retries": 0})
    fallback: list[str] = Field(default_factory=list)
    validation: list[str] = Field(default_factory=list)
    optional: bool = False
    execution_layer: Literal["workflow", "studio", "production", "supervisor"] = "workflow"

    @model_validator(mode="after")
    def exactly_one_implementation(self) -> "WorkflowStep":
        if bool(self.capability_id) == bool(self.skill_id):
            raise ValueError("WorkflowStep 必须且只能引用 capability_id 或 skill_id")
        return self

    @property
    def implementation_id(self) -> str:
        return self.capability_id or self.skill_id or ""


class WorkflowPlan(BaseModel):
    workflow_id: str
    version: int = Field(default=1, ge=1)
    run_id: str
    task_id: str
    status: WorkflowStatus = "planned"
    steps: list[WorkflowStep] = Field(default_factory=list)
    dependencies: list[tuple[str, str]] = Field(default_factory=list)
    selected_capabilities: list[str] = Field(default_factory=list)
    fallback_steps: list[str] = Field(default_factory=list)
    expected_artifacts: list[str] = Field(default_factory=list)
    approval_points: list[str] = Field(default_factory=list)
    quality_gates: list[str] = Field(default_factory=list)
    resource_notes: list[str] = Field(default_factory=list)
    unresolved_gaps: list[str] = Field(default_factory=list)
    gap_links: list[str] = Field(default_factory=list)
    recipe_id: str | None = None
    recipe_evidence_runs: list[str] = Field(default_factory=list)
    recipe_adjustments: list[str] = Field(default_factory=list)
    registry_versions: dict[str, str] = Field(default_factory=dict)
    created_at: datetime


class WorkflowStepState(BaseModel):
    step_id: str
    status: WorkflowStepStatus = "pending"
    attempts: int = Field(default=0, ge=0)
    repair_rounds: int = Field(default=0, ge=0)
    selected_implementation: str | None = None
    artifact_refs: dict[str, str] = Field(default_factory=dict)
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


class WorkflowState(BaseModel):
    workflow_id: str
    run_id: str
    status: WorkflowStatus = "planned"
    steps: dict[str, WorkflowStepState] = Field(default_factory=dict)
    artifacts: dict[str, str] = Field(default_factory=dict)
    repair_rounds: int = Field(default=0, ge=0)
    blocked_reason: str | None = None
    created_at: datetime
    updated_at: datetime


class StepExecutionResult(BaseModel):
    step_id: str
    implementation_id: str
    status: Literal["completed", "failed", "skipped", "blocked"]
    outputs: dict[str, str] = Field(default_factory=dict)
    elapsed_sec: float = Field(default=0, ge=0)
    retry_count: int = Field(default=0, ge=0)
    fallback_used: bool = False
    error: str | None = None
    resource_observations: dict[str, Any] = Field(default_factory=dict)
    qa_outcomes: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class RepairPlan(BaseModel):
    repair_id: str
    workflow_id: str
    failed_step_id: str
    action: Literal[
        "retry_same_step", "use_approved_fallback", "return_to_artifact_owner",
        "skip_optional_step", "escalate_to_human", "create_capability_gap_proposal",
    ]
    selected_implementation: str | None = None
    reason: str
    approval_required: bool = False
    created_at: datetime


class WorkflowValidationReport(BaseModel):
    workflow_id: str
    passed: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    checked_steps: int = Field(ge=0)
    checked_at: datetime


class WorkflowEvaluationReport(BaseModel):
    workflow_id: str
    run_id: str
    task_success: bool
    step_success_rates: dict[str, float]
    elapsed_time_sec: float = Field(ge=0)
    fallbacks: list[str] = Field(default_factory=list)
    retries: dict[str, int] = Field(default_factory=dict)
    resource_observations: dict[str, Any] = Field(default_factory=dict)
    qa_outcomes: dict[str, Any] = Field(default_factory=dict)
    unmet_criteria: list[str] = Field(default_factory=list)
    overall_score: float = Field(ge=0, le=1)
    reliability: float = Field(ge=0, le=1)
    recommendation: Literal["reuse", "revise", "do_not_reuse"]
    created_at: datetime


class WorkflowRecipeStep(BaseModel):
    step_id: str
    capability_id: str | None = None
    skill_id: str | None = None
    owner_agent: str
    inputs: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)
    fallback: list[str] = Field(default_factory=list)
    execution_layer: Literal["workflow", "studio", "production", "supervisor"] = "workflow"


class WorkflowRecipe(BaseModel):
    recipe_id: str
    name: str
    task_pattern: dict[str, Any]
    required_capabilities: list[str]
    steps_template: list[WorkflowRecipeStep]
    constraints: list[str] = Field(default_factory=list)
    quality_gates: list[str] = Field(default_factory=list)
    evidence_runs: list[str] = Field(default_factory=list)
    success_count: int = Field(default=0, ge=0)
    failure_count: int = Field(default=0, ge=0)
    confidence: float = Field(default=0, ge=0, le=1)
    status: Literal["candidate", "validated", "deprecated"] = "candidate"
    created_at: datetime
    updated_at: datetime


class WorkflowQAReport(BaseModel):
    workflow_id: str
    passed: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    checks: dict[str, bool] = Field(default_factory=dict)
    checked_at: datetime
