from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

Confidence = Literal["low", "medium", "high"]
EstimateType = Literal["known", "derived", "simulated", "unknown"]


class SimulationAssumption(BaseModel):
    assumption_id: str = Field(min_length=1)
    statement: str = Field(min_length=1)
    source: str = Field(min_length=1)
    confidence: Confidence = "low"


class SimulationResourceBudget(BaseModel):
    max_local_vram_mb: int = Field(default=6144, ge=256)
    max_ram_mb: int = Field(default=24576, ge=1024)
    max_wall_time_sec: int | None = Field(default=None, ge=1)
    max_cloud_cost: float | None = Field(default=None, ge=0)
    allow_unknown_resources: bool = False


class SimulationApprovalPolicy(BaseModel):
    required_gates: list[str] = Field(default_factory=list)
    allow_auto_select: bool = False
    major_replan: bool = False
    identity_change: bool = False
    real_publish: bool = False


class SimulationScenario(BaseModel):
    scenario_id: str = Field(pattern=r"^[A-Za-z0-9_-]+$")
    objective: str = Field(min_length=1)
    baseline_state_refs: list[str] = Field(default_factory=list)
    assumptions: list[SimulationAssumption] = Field(default_factory=list)
    controllable_variables: dict[str, Any] = Field(default_factory=dict)
    fixed_variables: dict[str, Any] = Field(default_factory=dict)
    candidate_actions: list[dict[str, Any]] = Field(default_factory=list)
    horizon: str = Field(default="single_run", min_length=1)
    resource_budget: SimulationResourceBudget = Field(default_factory=SimulationResourceBudget)
    approval_policy: SimulationApprovalPolicy = Field(default_factory=SimulationApprovalPolicy)
    evaluation_metrics: list[str] = Field(default_factory=list)
    uncertainty_notes: list[str] = Field(default_factory=list)
    source_task_ref: str | None = None
    created_at: datetime

    @model_validator(mode="after")
    def assumptions_are_explicit(self) -> "SimulationScenario":
        if self.candidate_actions and not self.assumptions:
            raise ValueError("SimulationScenario 有候选动作时必须显式记录 assumptions")
        return self


class WorldStateSnapshot(BaseModel):
    snapshot_id: str
    channel_state: dict[str, Any] = Field(default_factory=dict)
    active_goals: list[dict[str, Any]] = Field(default_factory=list)
    recent_content_metrics_summaries: list[dict[str, Any]] = Field(default_factory=list)
    current_identity: dict[str, Any] = Field(default_factory=dict)
    active_experiments: list[dict[str, Any]] = Field(default_factory=list)
    production_health: dict[str, Any] = Field(default_factory=dict)
    provider_health: list[dict[str, Any]] = Field(default_factory=list)
    resource_profile: dict[str, Any] = Field(default_factory=dict)
    outstanding_approvals: list[dict[str, Any]] = Field(default_factory=list)
    known_constraints: list[str] = Field(default_factory=list)
    source_refs: dict[str, list[str]] = Field(default_factory=dict)
    missing_sources: list[str] = Field(default_factory=list)
    captured_at: datetime


class CandidatePlan(BaseModel):
    candidate_id: str
    actions: list[dict[str, Any]] = Field(default_factory=list)
    changed_variables: dict[str, Any] = Field(default_factory=dict)
    held_constant: dict[str, Any] = Field(default_factory=dict)
    required_capabilities: list[str] = Field(default_factory=list)
    expected_approvals: list[str] = Field(default_factory=list)
    rationale: str = Field(min_length=1)


class Prediction(BaseModel):
    metric: str = Field(min_length=1)
    estimate_type: EstimateType
    point_estimate: float | str | bool | None = None
    range: tuple[float, float] | None = None
    unit: str | None = None
    confidence: Confidence
    evidence_refs: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def evidence_and_uncertainty_are_honest(self) -> "Prediction":
        if self.estimate_type == "unknown" and (self.point_estimate is not None or self.range is not None):
            raise ValueError("unknown Prediction 不得包含 point_estimate/range")
        if self.estimate_type in {"derived", "simulated"} and not self.assumptions:
            raise ValueError("derived/simulated Prediction 必须记录 assumptions")
        if self.estimate_type == "known" and not self.evidence_refs:
            raise ValueError("known Prediction 必须包含 evidence_refs")
        return self


class CandidateSimulationResult(BaseModel):
    candidate_id: str
    predictions: list[Prediction] = Field(default_factory=list)
    failure_paths: list[str] = Field(default_factory=list)
    approval_gates_preserved: list[str] = Field(default_factory=list)
    workflow_dry_run: dict[str, Any] = Field(default_factory=dict)
    evaluator_notes: dict[str, list[str]] = Field(default_factory=dict)


class SimulationResults(BaseModel):
    scenario_id: str
    scenario_digest: str
    mode: Literal["dry_run"] = "dry_run"
    candidates: list[CandidateSimulationResult]
    real_providers_called: bool = False
    real_metrics_written: bool = False
    generated_at: datetime


class CandidateScoreBreakdown(BaseModel):
    candidate_id: str
    expected_quality: float | None = Field(default=None, ge=0, le=1)
    reliability: float | None = Field(default=None, ge=0, le=1)
    latency: float | None = Field(default=None, ge=0, le=1)
    resource_use: float | None = Field(default=None, ge=0, le=1)
    monetary_cost: float | None = Field(default=None, ge=0, le=1)
    approval_burden: float | None = Field(default=None, ge=0, le=1)
    risk: float | None = Field(default=None, ge=0, le=1)
    experiment_value: float | None = Field(default=None, ge=0, le=1)
    novelty: float | None = Field(default=None, ge=0, le=1)
    total_score: float = Field(ge=0, le=1)
    known_fraction: float = Field(ge=0, le=1)


class RankedCandidate(BaseModel):
    rank: int = Field(ge=1)
    candidate_id: str
    score: float = Field(ge=0, le=1)


class CounterfactualComparison(BaseModel):
    scenario_id: str
    ranked_candidates: list[RankedCandidate]
    score_breakdown: list[CandidateScoreBreakdown]
    dominant_tradeoffs: list[str]
    uncertainty: list[str]
    recommendation: str
    reasons_not_selected: dict[str, list[str]] = Field(default_factory=dict)
    compared_at: datetime


class SimulationDecision(BaseModel):
    scenario_id: str
    mode: Literal["auto_select", "recommendation_only"]
    selected_candidate_id: str | None = None
    recommendation: str
    required_approvals: list[str] = Field(default_factory=list)
    dispatch_allowed: bool = False
    reasons: list[str] = Field(default_factory=list)
    decided_at: datetime


class SimulationQAReport(BaseModel):
    scenario_id: str
    passed: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    checks: dict[str, bool] = Field(default_factory=dict)
    checked_at: datetime


class ExperimentProposal(BaseModel):
    proposal_id: str
    scenario_id: str
    hypothesis: str
    test_plan: dict[str, Any]
    predicted_metrics: list[Prediction]
    status: Literal["proposed"] = "proposed"
    approval_required: bool = True
    real_execution_started: bool = False
    created_at: datetime


class PredictionErrorRecord(BaseModel):
    metric: str
    predicted: Prediction
    actual_value: float | None = None
    actual_source: str
    error: float | None = None
    direction_bias: Literal["over", "under", "aligned", "unknown"] = "unknown"
    evidence_refs: list[str] = Field(default_factory=list)


class SimulationCalibrationRecord(BaseModel):
    scenario_id: str
    actual_source: str
    is_testing: bool
    prediction_errors: list[PredictionErrorRecord]
    estimator_confidence_suggestions: dict[str, str] = Field(default_factory=dict)
    ranking_weight_suggestions: dict[str, float] = Field(default_factory=dict)
    applies_automatically: bool = False
    created_at: datetime
