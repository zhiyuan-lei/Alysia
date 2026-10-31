from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

QualityTarget = Literal["draft", "standard", "high"]
TaskType = Literal[
    "research",
    "schema_formatting",
    "metadata",
    "routing",
    "script",
    "storyboard",
    "visual_generation",
    "text_qa",
    "tts",
    "subtitle_alignment",
    "audio_qa",
    "render",
    "video_qa",
    "cover",
    "publish_qa",
]
HealthStatus = Literal["healthy", "degraded", "unavailable", "unknown"]
KnowledgeStatus = Literal["known", "estimated_with_source", "unknown"]


class ProductionConstraints(BaseModel):
    quality_target: QualityTarget = "standard"
    max_local_vram_mb: int = Field(default=6144, ge=256)
    max_cloud_cost: float | None = Field(default=None, ge=0)
    max_wall_time_sec: int | None = Field(default=None, ge=1)
    prefer_local: bool = True
    allow_cloud: bool = True
    allow_fallback: bool = True
    sequential_gpu_required: bool = True
    offline_mode: bool = False
    reproducibility_priority: Literal["low", "medium", "high"] = "high"
    provider_allowlist: list[str] = Field(default_factory=list)
    provider_denylist: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def provider_lists_do_not_conflict(self) -> "ProductionConstraints":
        overlap = set(self.provider_allowlist) & set(self.provider_denylist)
        if overlap:
            raise ValueError(f"provider 同时出现在 allowlist 和 denylist：{sorted(overlap)}")
        return self


class ProductionProfile(ProductionConstraints):
    name: str = "default"
    max_retries_per_stage: int = Field(default=2, ge=0, le=5)
    research_cache_ttl_hours: int = Field(default=24, ge=0, le=24 * 90)
    visual_skill_requirements: list[str] = Field(default_factory=list)
    required_skills: list[str] = Field(default_factory=list)
    skill_resource_requirements: dict[str, dict[str, Any]] = Field(default_factory=dict)


class ProviderCapability(BaseModel):
    provider_id: str = Field(min_length=1)
    task_types: list[TaskType] = Field(min_length=1)
    local_or_cloud: Literal["local", "cloud", "mock"]
    estimated_vram_mb: int | None = Field(default=None, ge=0)
    supports_unload: bool = False
    expected_latency_class: Literal["low", "medium", "high", "unknown"] = "unknown"
    expected_quality_class: Literal["low", "medium", "high", "unknown"] = "unknown"
    monetary_cost_class: Literal["free", "low", "medium", "high", "unknown"] = "unknown"
    requires_network: bool = False
    requires_credentials: bool = False
    health_status: HealthStatus = "unknown"
    gpu_heavy: bool = False
    version: str | None = None
    health_details: str | None = None


class ProductionStagePlan(BaseModel):
    stage_id: str
    task_type: TaskType
    selected_provider: str
    fallback_chain: list[str] = Field(default_factory=list)
    gpu_heavy: bool = False
    expected_vram_mb: int | None = Field(default=None, ge=0)
    reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class PlanAlternative(BaseModel):
    name: str
    provider_by_stage: dict[str, str]
    score: float
    reasons: list[str] = Field(default_factory=list)
    tradeoffs: list[str] = Field(default_factory=list)


class ProductionPlan(BaseModel):
    plan_id: str
    run_id: str
    requested_operation: str = "full"
    profile: ProductionProfile
    stages: list[ProductionStagePlan]
    selected_provider_per_stage: dict[str, str]
    execution_order: list[str]
    fallback_chain: dict[str, list[str]]
    expected_resource_notes: list[str] = Field(default_factory=list)
    expected_cost_notes: list[str] = Field(default_factory=list)
    quality_tradeoffs: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    alternatives: list[PlanAlternative] = Field(default_factory=list)
    policy_blockers: list[str] = Field(default_factory=list)
    requires_human_confirmation: bool = False
    registry_digest: str
    created_at: datetime


class FallbackRecord(BaseModel):
    stage_id: str
    original_choice: str
    failure_reason: str
    fallback_choice: str
    quality_impact: str
    occurred_at: datetime


class CostValue(BaseModel):
    status: KnowledgeStatus
    amount: float | None = Field(default=None, ge=0)
    currency: str | None = None
    source: str | None = None
    details: str | None = None

    @model_validator(mode="after")
    def known_cost_requires_evidence(self) -> "CostValue":
        if self.status == "unknown" and self.amount is not None:
            raise ValueError("unknown cost 不允许携带金额")
        if self.status != "unknown" and (self.amount is None or not self.source):
            raise ValueError("known/estimated cost 必须携带金额与来源")
        return self


class StageExecutionMetric(BaseModel):
    stage_id: str
    start_time: datetime
    end_time: datetime
    elapsed_sec: float = Field(ge=0)
    provider: str
    success: bool
    failure_reason: str | None = None
    retry_count: int = Field(default=0, ge=0)
    peak_vram_mb: int | None = Field(default=None, ge=0)
    input_size: int | None = Field(default=None, ge=0)
    output_size: int | None = Field(default=None, ge=0)
    estimated_cost: CostValue = Field(default_factory=lambda: CostValue(status="unknown"))
    actual_cost: CostValue = Field(default_factory=lambda: CostValue(status="unknown"))
    cache_hit: bool = False
    fallback_used: bool = False
    notes: list[str] = Field(default_factory=list)


class ExecutionMetrics(BaseModel):
    run_id: str
    plan_id: str
    stages: list[StageExecutionMetric] = Field(default_factory=list)
    fallbacks: list[FallbackRecord] = Field(default_factory=list)
    started_at: datetime
    updated_at: datetime


class CacheEntry(BaseModel):
    cache_key: str
    artifact_type: str
    normalized_input_hash: str
    provider_id: str
    provider_version: str | None = None
    config_hash: str
    artifact_path: str
    created_at: datetime
    valid: bool = True
    ttl_hours: int | None = Field(default=None, ge=0)


class ProductionQualityGateReport(BaseModel):
    run_id: str
    plan_id: str
    quality_target: QualityTarget
    passed: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    checked_qa_artifacts: list[str] = Field(default_factory=list)
    retry_budget: int = Field(ge=0)
    checked_at: datetime


class ProductionReport(BaseModel):
    run_id: str
    selected_plan: ProductionPlan
    elapsed_time_per_stage: dict[str, float | None]
    fallbacks: list[FallbackRecord]
    cache_hits: list[str]
    cost: dict[str, CostValue]
    qa_outcome: ProductionQualityGateReport | None = None
    bottlenecks: list[str] = Field(default_factory=list)
    optimization_suggestions: list[str] = Field(default_factory=list)
    generated_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)
