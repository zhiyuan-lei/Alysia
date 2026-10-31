from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


Level = Literal["none", "low", "medium", "high"]


class BrandVoiceProfile(BaseModel):
    tone: list[str] = Field(min_length=1)
    sentence_style: str = Field(min_length=1)
    vocabulary_preferences: list[str] = Field(default_factory=list)
    forbidden_phrases: list[str] = Field(default_factory=list)
    explanation_depth: Literal["low", "medium", "high"] = "medium"
    humor_level: Level = "low"
    technical_level: Literal["low", "medium", "high"] = "medium"
    opening_style: str = Field(min_length=1)
    conclusion_style: str = Field(min_length=1)

    @field_validator("tone", "vocabulary_preferences", "forbidden_phrases")
    @classmethod
    def list_values_are_unique(cls, values: list[str]) -> list[str]:
        cleaned = [item.strip() for item in values if item.strip()]
        if len(cleaned) != len(set(cleaned)):
            raise ValueError("Brand Voice 列表项不能重复")
        return cleaned


class VisualIdentity(BaseModel):
    color_theme: dict[str, str] = Field(min_length=1)
    typography: dict[str, str] = Field(min_length=1)
    cover_layout: str = Field(min_length=1)
    thumbnail_rules: list[str] = Field(default_factory=list)
    scene_preferences: list[str] = Field(default_factory=list)


class CreatorIdentity(BaseModel):
    creator_name: str = Field(min_length=1)
    mission_statement: str = Field(min_length=1)
    channel_purpose: str = Field(min_length=1)
    content_philosophy: str = Field(min_length=1)
    target_audience: str = Field(min_length=1)
    expertise_domains: list[str] = Field(min_length=1)
    excluded_topics: list[str] = Field(default_factory=list)
    communication_style: BrandVoiceProfile
    visual_identity: VisualIdentity
    narrative_patterns: list[str] = Field(default_factory=list)
    values: list[str] = Field(min_length=1)
    disclosure_policy: str = Field(min_length=1)
    version: int = Field(default=1, ge=1)
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def disclosure_identifies_system(self) -> "CreatorIdentity":
        disclosure = self.disclosure_policy.casefold()
        if "ai" not in disclosure or not any(marker in disclosure for marker in ("系统", "system")):
            raise ValueError("disclosure_policy 必须明确 Alysia 是 AI 系统")
        return self


class StyleEvidence(BaseModel):
    run_id: str = Field(min_length=1)
    experiment_id: str | None = None
    metrics: dict[str, int | float | None] = Field(default_factory=dict)
    title_pattern: str
    opening_pattern: str
    video_structure: list[str]
    visual_style: list[str]
    subtitle_style: str
    narrative_pacing: str
    source: Literal["manual", "platform", "mock", "testing"]


class ContentStyleRule(BaseModel):
    dimension: str
    value: str
    evidence_run_ids: list[str] = Field(min_length=1)
    experiment_ids: list[str] = Field(default_factory=list)
    metrics: dict[str, dict[str, int | float | None]] = Field(default_factory=dict)
    confidence: float = Field(ge=0, le=1)
    status: Literal["tentative", "supported"] = "tentative"


class ContentStyleMemory(BaseModel):
    channel_id: str = Field(min_length=1)
    observations: list[StyleEvidence] = Field(default_factory=list)
    rules: list[ContentStyleRule] = Field(default_factory=list)
    source_digest: str = Field(min_length=64, max_length=64)
    updated_at: datetime


class StyleConsistencyReport(BaseModel):
    run_id: str
    identity_version: int = Field(ge=1)
    matched_elements: list[str] = Field(default_factory=list)
    violations: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    score: float = Field(ge=0, le=1)
    confidence: float = Field(ge=0, le=1)
    input_digest: str = Field(min_length=64, max_length=64)
    disclaimer: str = "Style QA 只提供审计建议，不自动修改内容、身份或频道方向。"


class NarrativeFramework(BaseModel):
    id: str = Field(min_length=1)
    purpose: str = Field(min_length=1)
    structure: list[str] = Field(min_length=1)
    suitable_topics: list[str] = Field(min_length=1)
    examples: list[str] = Field(min_length=1)
    limitations: list[str] = Field(min_length=1)


class PromptContextArtifact(BaseModel):
    identity_version: int = Field(ge=1)
    base_task_prompt: str = Field(min_length=1)
    creator_identity: dict[str, Any]
    brand_voice: dict[str, Any]
    relevant_strategies: list[dict[str, Any]] = Field(default_factory=list)
    content_experiment: dict[str, Any] | None = None
    rendered_context: str = Field(min_length=1)
    input_digest: str = Field(min_length=64, max_length=64)


class IdentityChangeProposal(BaseModel):
    id: str = Field(min_length=1)
    identity_version: int = Field(ge=1)
    proposed_change: dict[str, Any] = Field(min_length=1)
    reason: str = Field(min_length=1)
    evidence: list[str] = Field(min_length=1)
    expected_effect: str = Field(min_length=1)
    risk: str = Field(min_length=1)
    approval_required: bool = True
    status: Literal["pending", "approved", "rejected"] = "pending"
    approved_by: str | None = None
    created_at: datetime
    approved_at: datetime | None = None

    @model_validator(mode="after")
    def approval_fields_are_consistent(self) -> "IdentityChangeProposal":
        if not self.approval_required:
            raise ValueError("Identity 变更必须要求人工批准")
        if self.status == "approved" and (not self.approved_by or self.approved_at is None):
            raise ValueError("approved proposal 必须记录人工审核者和审批时间")
        return self


class IdentityRunCheckReport(BaseModel):
    run_id: str
    identity_version: int
    valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    prompt_context_path: str
    input_digest: str = Field(min_length=64, max_length=64)
    disclaimer: str = "身份检查只验证配置与内容边界，不代表内容已获发布批准。"
