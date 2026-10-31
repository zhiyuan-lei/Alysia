from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


MetricDirection = Literal["higher_is_better", "lower_is_better", "target_range"]
MeasurementType = Literal["observed", "derived", "rubric", "unknown"]
RegressionSeverity = Literal["info", "warning", "major", "critical"]
GateEffect = Literal["none", "warn", "block"]
EvaluationStatus = Literal["running", "completed", "failed", "blocked"]
EvaluationGateStatus = Literal["PASS", "PASS_WITH_WARNINGS", "BLOCKED"]


class RegressionTolerance(BaseModel):
    absolute: float = Field(default=0.0, ge=0)
    relative: float = Field(default=0.0, ge=0)
    target_min: float | None = None
    target_max: float | None = None

    @model_validator(mode="after")
    def target_is_ordered(self) -> "RegressionTolerance":
        if self.target_min is not None and self.target_max is not None and self.target_min > self.target_max:
            raise ValueError("target_min 不能大于 target_max")
        return self


class BenchmarkCase(BaseModel):
    case_id: str = Field(min_length=1, pattern=r"^[a-z0-9_.-]+$")
    category: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    fixture_refs: list[str] = Field(default_factory=list)
    required_capabilities: list[str] = Field(default_factory=list)
    expected_properties: list[str] = Field(default_factory=list)
    scorer_id: str = Field(min_length=1)
    tolerance: RegressionTolerance = Field(default_factory=RegressionTolerance)
    severity_if_regressed: RegressionSeverity = "warning"
    version: str = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)
    default_enabled: bool = True
    integration: bool = False


class RubricDimension(BaseModel):
    dimension: str = Field(min_length=1)
    level: int = Field(ge=0, le=3)
    reason: str = Field(min_length=1)


class EvaluationMetric(BaseModel):
    metric_id: str = Field(min_length=1)
    benchmark_case_id: str = Field(min_length=1)
    value: float | int | str | bool | None
    unit: str = Field(min_length=1)
    direction: MetricDirection
    baseline_value: float | int | None = None
    tolerance: RegressionTolerance = Field(default_factory=RegressionTolerance)
    source: str = Field(min_length=1)
    confidence: float = Field(default=1.0, ge=0, le=1)
    measurement_type: MeasurementType
    rubric_dimensions: list[RubricDimension] = Field(default_factory=list)
    reason: str | None = None
    affected_capability: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def unknown_is_not_fabricated(self) -> "EvaluationMetric":
        if self.measurement_type == "unknown":
            if self.value is not None:
                raise ValueError("unknown metric 的 value 必须为 None")
            if self.confidence != 0:
                raise ValueError("unknown metric 的 confidence 必须为 0")
        if self.measurement_type == "rubric" and not self.rubric_dimensions:
            raise ValueError("rubric metric 必须包含 dimension breakdown")
        return self


class EnvironmentSnapshot(BaseModel):
    python_version: str
    platform: str
    machine: str
    config_hash: str
    config_snapshot: dict[str, Any]
    hardware: dict[str, Any] = Field(default_factory=dict)
    external_services: dict[str, str] = Field(default_factory=dict)


class EvaluationRun(BaseModel):
    evaluation_id: str
    created_at: datetime
    code_worktree_fingerprint: str
    benchmark_registry_version: str
    metrics: list[EvaluationMetric] = Field(default_factory=list)
    artifacts: list[str] = Field(default_factory=list)
    environment_snapshot: EnvironmentSnapshot
    status: EvaluationStatus
    case_ids: list[str] = Field(default_factory=list)
    label: str = "candidate"
    suite: Literal["offline", "integration"] = "offline"
    failures: list[str] = Field(default_factory=list)
    fixture_manifest_hash: str


class BaselineSnapshot(BaseModel):
    baseline_id: str
    version: str
    created_at: datetime
    evaluation_id: str
    worktree_fingerprint: str
    benchmark_registry_version: str
    environment_snapshot: EnvironmentSnapshot
    metrics: list[EvaluationMetric]


class RegressionFinding(BaseModel):
    metric_id: str
    baseline: float | int | None
    candidate: float | int | None
    delta: float | None
    threshold: dict[str, float | None]
    severity: RegressionSeverity
    affected_capability: str
    evidence_refs: list[str] = Field(default_factory=list)
    gate_effect: GateEffect
    reason: str


class EvaluationComparison(BaseModel):
    comparison_id: str
    baseline_id: str
    candidate_evaluation_id: str
    findings: list[RegressionFinding] = Field(default_factory=list)
    improvements: list[str] = Field(default_factory=list)
    unchanged: list[str] = Field(default_factory=list)
    unknown: list[str] = Field(default_factory=list)
    overall_gate_status: EvaluationGateStatus


class EvaluationGateResult(BaseModel):
    evaluation_id: str
    baseline_id: str
    status: EvaluationGateStatus
    blocking_findings: list[RegressionFinding] = Field(default_factory=list)
    warnings: list[RegressionFinding] = Field(default_factory=list)
    invariant_failures: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    promotion_allowed: bool

