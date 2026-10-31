from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

GenerationMode = Literal["remotion", "static_image", "h3_t2v", "h3_i2v", "h3_r2v"]
VisualJobStatus = Literal["pending", "running", "completed", "failed", "cancelled"]


class H3VisualPrompt(BaseModel):
    subject: str = Field(min_length=1)
    environment: str = ""
    action_motion: str = ""
    camera: str = "static"
    lighting_style: str = ""
    continuity_constraints: list[str] = Field(default_factory=list)
    negative_constraints: list[str] = Field(default_factory=list)


class SceneVisualPlan(BaseModel):
    scene_id: str = Field(min_length=1)
    generation_mode: GenerationMode
    requested_duration_sec: float = Field(gt=0, le=600)
    prompt: H3VisualPrompt | None = None
    input_image: str | None = None
    reference_images: list[str] = Field(default_factory=list)
    character_reference_id: str | None = None
    identity_constraints: list[str] = Field(default_factory=list)
    wardrobe_style_refs: list[str] = Field(default_factory=list)
    route_reasons: list[str] = Field(default_factory=list)
    budgeted_h3_seconds: float = Field(default=0, ge=0)

    @model_validator(mode="after")
    def h3_requires_prompt(self) -> "SceneVisualPlan":
        if self.generation_mode.startswith("h3_") and self.prompt is None:
            raise ValueError("H3 scene 必须保存结构化 prompt")
        return self


class VisualPlan(BaseModel):
    run_id: str
    quality_target: str
    max_h3_clips: int = Field(ge=0)
    max_h3_seconds: float = Field(ge=0)
    used_h3_clips: int = Field(ge=0)
    used_h3_seconds: float = Field(ge=0)
    scenes: list[SceneVisualPlan]
    warnings: list[str] = Field(default_factory=list)
    created_at: datetime


class VisualGenerationJob(BaseModel):
    job_id: str
    run_id: str
    scene: SceneVisualPlan
    provider: str
    workflow_id: str
    workflow_version: str = "1"
    status: VisualJobStatus = "pending"
    attempts: int = Field(default=0, ge=0)
    max_retries: int = Field(default=1, ge=0, le=5)
    cache_key: str
    created_at: datetime
    updated_at: datetime
    error: str | None = None


class VisualGenerationResult(BaseModel):
    job_id: str
    scene_id: str
    provider: str
    workflow_id: str
    workflow_version: str
    output_files: list[Path]
    duration_sec: float = Field(gt=0)
    resolution: str
    generation_time_sec: float = Field(ge=0)
    seed_config: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    status: Literal["completed", "failed", "cancelled"]
    mock: bool = False


class VisualProviderHealth(BaseModel):
    provider: str
    available: bool
    details: list[str] = Field(default_factory=list)
    workflows: dict[str, bool] = Field(default_factory=dict)


class VisualAsset(BaseModel):
    scene_id: str
    generation_mode: GenerationMode
    asset_path: str | None = None
    provider: str
    provenance_path: str | None = None
    discard_source_audio: bool = True
    optional_ambience: bool = False
    mock: bool = False
    review_eligible: bool = True


class VisualAssetsManifest(BaseModel):
    run_id: str
    assets: list[VisualAsset]
    production_review_eligible: bool
    warnings: list[str] = Field(default_factory=list)


class VisualQAReport(BaseModel):
    run_id: str
    scene_id: str
    passed: bool
    production_eligible: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metrics: dict[str, float | int | str | bool | None] = Field(default_factory=dict)
    provenance_complete: bool = False
    checked_at: datetime
    disclaimer: str = "基础工程 Visual QA；不包含云端语义或审美评分。"
