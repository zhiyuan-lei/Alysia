from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


GoalType = Literal[
    "channel_growth", "content_series", "learning", "quality", "experiment", "operations"
]
GoalStatus = Literal["draft", "active", "paused", "completed", "cancelled", "blocked"]
PlanStatus = Literal["draft", "active", "paused", "completed", "cancelled", "blocked", "waiting_approval"]
ProjectStatus = Literal["planned", "active", "paused", "completed", "cancelled", "blocked"]
WorkStatus = Literal["planned", "ready", "dispatched", "completed", "blocked", "cancelled"]


class SuccessMetric(BaseModel):
    name: str = Field(min_length=1)
    target: float
    direction: Literal["increase", "decrease", "at_least", "at_most", "equal"] = "at_least"
    measurement_source: str = Field(min_length=1)
    current_value: float | None = None


class GoalBudgetPolicy(BaseModel):
    max_runs: int | None = Field(default=None, ge=0)
    max_cloud_cost: float | None = Field(default=None, ge=0)
    currency: str | None = None
    max_wall_time_hours: float | None = Field(default=None, ge=0)


class GoalApprovalPolicy(BaseModel):
    require_content_approval: bool = True
    require_publish_approval: bool = True
    require_major_replan_approval: bool = True
    require_identity_change_approval: bool = True


class Goal(BaseModel):
    goal_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    type: GoalType
    status: GoalStatus = "draft"
    priority: int = Field(default=50, ge=0, le=100)
    created_at: datetime
    updated_at: datetime
    start_date: date
    target_date: date | None = None
    success_metrics: list[SuccessMetric] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    budget_policy: GoalBudgetPolicy = Field(default_factory=GoalBudgetPolicy)
    approval_policy: GoalApprovalPolicy = Field(default_factory=GoalApprovalPolicy)
    stop_conditions: list[str] = Field(default_factory=list)
    parent_goal_id: str | None = None
    child_goal_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def dates_are_ordered(self) -> "Goal":
        if self.target_date is not None and self.target_date < self.start_date:
            raise ValueError("target_date 不能早于 start_date")
        if self.goal_id in self.child_goal_ids:
            raise ValueError("goal 不能把自己列为 child")
        return self


class Objective(BaseModel):
    objective_id: str = Field(min_length=1)
    goal_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    owner_component: Literal["supervisor", "creator_loop", "studio_director", "operations", "human"]
    status: WorkStatus = "planned"
    priority: int = Field(default=50, ge=0, le=100)
    depth: int = Field(default=1, ge=1)
    depends_on: list[str] = Field(default_factory=list)
    success_metrics: list[SuccessMetric] = Field(default_factory=list)
    deadline: date | None = None


class Milestone(BaseModel):
    milestone_id: str = Field(min_length=1)
    goal_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    owner_component: Literal["supervisor", "creator_loop", "studio_director", "operations", "human"]
    status: WorkStatus = "planned"
    depends_on: list[str] = Field(default_factory=list)
    objective_ids: list[str] = Field(default_factory=list)
    planned_date: date | None = None
    expected_value: float = Field(default=0.5, ge=0, le=1)
    resource_cost: float = Field(default=0.5, ge=0, le=1)
    risk: float = Field(default=0.2, ge=0, le=1)


class PlannedRun(BaseModel):
    planned_run_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    topic: str = Field(min_length=1)
    sequence: int = Field(ge=1)
    status: WorkStatus = "planned"
    depends_on: list[str] = Field(default_factory=list)
    linked_experiment_id: str | None = None
    run_id: str | None = None
    creator_plan_id: str | None = None
    approval_status: Literal["pending", "approved", "rejected"] = "pending"
    approved_by: str | None = None
    expected_value: float = Field(default=0.5, ge=0, le=1)
    resource_cost: float = Field(default=0.5, ge=0, le=1)
    risk: float = Field(default=0.2, ge=0, le=1)
    deadline: date | None = None
    testing: bool = False
    blocked_reason: str | None = None

    @model_validator(mode="after")
    def approved_has_actor(self) -> "PlannedRun":
        if self.approval_status == "approved" and not self.approved_by:
            raise ValueError("approved planned run 必须记录 approved_by")
        return self


class ContentProject(BaseModel):
    project_id: str = Field(min_length=1)
    goal_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    theme: str = Field(min_length=1)
    planned_runs: list[PlannedRun] = Field(default_factory=list)
    experiment_refs: list[str] = Field(default_factory=list)
    status: ProjectStatus = "planned"
    progress: float = Field(default=0, ge=0, le=1)
    dependencies: list[str] = Field(default_factory=list)
    deadline: date | None = None
    created_at: datetime
    updated_at: datetime


class DependencyEdge(BaseModel):
    source_id: str = Field(min_length=1)
    depends_on_id: str = Field(min_length=1)
    kind: Literal["goal", "milestone", "project", "run", "approval", "research", "experiment"]
    reason: str = Field(min_length=1)

    @model_validator(mode="after")
    def not_self_referential(self) -> "DependencyEdge":
        if self.source_id == self.depends_on_id:
            raise ValueError("依赖边不能指向自身")
        return self


class ReviewPoint(BaseModel):
    review_id: str = Field(min_length=1)
    trigger_type: Literal["runs_completed", "days_elapsed", "experiment_completed", "budget_ratio"]
    threshold: float = Field(gt=0)
    triggered: bool = False
    triggered_at: datetime | None = None
    completed_at: datetime | None = None


class ResourceBudget(BaseModel):
    max_runs: int | None = Field(default=None, ge=0)
    max_cloud_cost: float | None = Field(default=None, ge=0)
    currency: str | None = None
    max_active_projects: int = Field(default=3, ge=1)


class RiskRegisterItem(BaseModel):
    risk_id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    probability: float = Field(ge=0, le=1)
    impact: float = Field(ge=0, le=1)
    mitigation: str = Field(min_length=1)
    status: Literal["open", "mitigated", "accepted", "closed"] = "open"


class LongHorizonPlan(BaseModel):
    plan_id: str = Field(min_length=1)
    goal_id: str = Field(min_length=1)
    horizon_days: int = Field(ge=1, le=3650)
    milestones: list[Milestone] = Field(default_factory=list)
    projects: list[str] = Field(default_factory=list)
    dependencies: list[DependencyEdge] = Field(default_factory=list)
    review_points: list[ReviewPoint] = Field(default_factory=list)
    resource_budget: ResourceBudget = Field(default_factory=ResourceBudget)
    risk_register: list[RiskRegisterItem] = Field(default_factory=list)
    status: PlanStatus = "draft"
    version: int = Field(default=1, ge=1)
    created_at: datetime
    updated_at: datetime


class PriorityCandidate(BaseModel):
    item_id: str
    item_type: Literal["goal", "milestone", "project", "run", "review"]
    goal_priority: int = Field(ge=0, le=100)
    deadline: date | None = None
    dependency_ready: bool = True
    expected_value: float = Field(default=0.5, ge=0, le=1)
    experiment_importance: float = Field(default=0, ge=0, le=1)
    resource_cost: float = Field(default=0.5, ge=0, le=1)
    risk: float = Field(default=0.2, ge=0, le=1)


class PriorityAlternative(BaseModel):
    item_id: str
    score: float
    blocked: bool


class PriorityDecision(BaseModel):
    selected_item: str | None
    score: float | None = None
    score_breakdown: dict[str, float] = Field(default_factory=dict)
    alternatives: list[PriorityAlternative] = Field(default_factory=list)
    rationale: str


class BudgetUsage(BaseModel):
    runs_today: int = Field(default=0, ge=0)
    runs_this_week: int = Field(default=0, ge=0)
    cloud_cost_today: float | None = Field(default=None, ge=0)
    cloud_cost_this_week: float | None = Field(default=None, ge=0)
    failed_runs: int = Field(default=0, ge=0)
    active_projects: int = Field(default=0, ge=0)


class BudgetDecision(BaseModel):
    allowed: bool
    warning: bool = False
    approval_required: bool = False
    reasons: list[str] = Field(default_factory=list)
    usage: BudgetUsage


class SupervisorReview(BaseModel):
    review_id: str
    goal_id: str
    plan_id: str
    progress: float = Field(ge=0, le=1)
    metrics: dict[str, float | None]
    deviations: list[str]
    risks: list[str]
    decisions_needed: list[str]
    recommendation: Literal["continue", "pause", "replan"]
    created_at: datetime


class ReplanProposal(BaseModel):
    proposal_id: str
    goal_id: str
    source_plan_id: str
    source_plan_version: int = Field(ge=1)
    proposed_plan_version: int = Field(ge=2)
    what_changed: list[str]
    why: list[str]
    impact: list[str]
    new_plan: LongHorizonPlan
    risks: list[str]
    approval_required: bool = True
    status: Literal["pending", "approved", "rejected"] = "pending"
    created_at: datetime

    @model_validator(mode="after")
    def versions_advance(self) -> "ReplanProposal":
        if self.proposed_plan_version <= self.source_plan_version:
            raise ValueError("replan 必须提高 plan version")
        if self.new_plan.version != self.proposed_plan_version:
            raise ValueError("new_plan.version 必须等于 proposed_plan_version")
        return self


class CrossRunContext(BaseModel):
    channel_id: str
    channel_summary: dict[str, Any] = Field(default_factory=dict)
    supported_lessons: list[dict[str, Any]] = Field(default_factory=list)
    active_strategies: list[dict[str, Any]] = Field(default_factory=list)
    active_experiments: list[dict[str, Any]] = Field(default_factory=list)
    identity_summary: dict[str, Any] = Field(default_factory=dict)
    production_health: dict[str, Any] = Field(default_factory=dict)
    generated_at: datetime


SupervisorStage = Literal[
    "idle", "evaluate_goals", "select_priority", "check_dependencies", "plan_action",
    "dispatch", "monitor", "review", "waiting_approval", "paused",
]


class SupervisorState(BaseModel):
    stage: SupervisorStage = "idle"
    active_goal_id: str | None = None
    active_plan_id: str | None = None
    selected_item_id: str | None = None
    actions_this_tick: int = Field(default=0, ge=0)
    dispatches_this_tick: int = Field(default=0, ge=0)
    last_tick_id: str | None = None
    last_input_digest: str | None = None
    waiting_reason: str | None = None
    updated_at: datetime


class SupervisorTraceEvent(BaseModel):
    event_id: str
    tick_id: str
    event_type: str
    goal_id: str | None = None
    plan_id: str | None = None
    project_id: str | None = None
    run_id: str | None = None
    selected_item_id: str | None = None
    summary: str
    rationale: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class SupervisorQAReport(BaseModel):
    passed: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    checks: dict[str, bool] = Field(default_factory=dict)
    checked_goal_ids: list[str] = Field(default_factory=list)
    generated_at: datetime


class DispatchResult(BaseModel):
    accepted: bool
    status: Literal["dispatched", "completed", "blocked", "waiting_approval", "failed"]
    run_id: str | None = None
    creator_plan_id: str | None = None
    reason: str

