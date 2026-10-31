from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class RuntimeSettings(BaseSettings):
    """从环境变量读取的最小运行设置。"""

    model_config = SettingsConfigDict(
        env_prefix="ALYSIA_",
        env_file=".env",
        extra="ignore",
    )

    config_file: Path = Path("config.yaml")


class ResourceConfig(BaseModel):
    gpu_execution: str = "serial"
    max_concurrent_gpu_models: int = Field(default=1, ge=1, le=1)


class HardwareProfileConfig(BaseModel):
    """当前机器的保守运行预算；检测值由 doctor 单独报告。"""

    gpu: str = "NVIDIA GeForce RTX 4060 Ti"
    vram_mb: int = Field(default=8192, ge=1024)
    ram_gb: int = Field(default=24, ge=8)
    sequential_gpu_required: bool = True


class LLMConfig(BaseModel):
    provider: Literal["mock", "ollama", "cloud"] = "mock"
    model: str = "qwen3.5:4b"
    base_url: str = "http://127.0.0.1:11434"
    timeout_sec: float = Field(default=120.0, gt=0)


class ContentConfig(BaseModel):
    language: str = "zh-CN"
    min_duration_sec: int = Field(default=120, ge=30)
    max_duration_sec: int = Field(default=300, ge=30)
    default_duration_sec: int = Field(default=180, ge=30)

    @model_validator(mode="after")
    def durations_are_ordered(self) -> "ContentConfig":
        if self.min_duration_sec > self.max_duration_sec:
            raise ValueError("min_duration_sec 不能大于 max_duration_sec")
        if not self.min_duration_sec <= self.default_duration_sec <= self.max_duration_sec:
            raise ValueError("default_duration_sec 必须位于时长范围内")
        return self


class ResearchConfig(BaseModel):
    provider: Literal["mock", "manual", "web"] = "mock"
    max_sources: int = Field(default=5, ge=1, le=20)
    manual_source_file: Path | None = None


class TTSConfig(BaseModel):
    provider: Literal["mock", "sapi", "cosyvoice"] = "sapi"
    language: str = "zh-CN"
    voice: str = "default"
    speed: float = Field(default=1.0, gt=0.25, le=4.0)
    sample_rate: int = Field(default=24000, ge=8000, le=96000)
    pause_between_scenes_ms: int = Field(default=250, ge=0, le=5000)
    model_dir: Path | None = None
    allow_test_tone: bool = False


class ASRConfig(BaseModel):
    enabled: bool = False
    provider: Literal["faster-whisper", "mock"] = "faster-whisper"
    model: str = "small"
    device: Literal["cuda", "cpu"] = "cuda"
    compute_type: str = "int8_float16"
    local_files_only: bool = True


class SubtitleConfig(BaseModel):
    max_chars_per_line: int = Field(default=22, ge=6, le=60)
    min_duration_sec: float = Field(default=0.8, gt=0, le=10)
    max_duration_sec: float = Field(default=6.0, gt=0, le=30)
    deterministic_default: bool = True
    font_size: int = Field(default=54, ge=20, le=120)
    position: Literal["bottom", "center", "top"] = "bottom"
    max_width: float = Field(default=0.82, gt=0.3, le=1.0)

    @model_validator(mode="after")
    def durations_are_ordered(self) -> "SubtitleConfig":
        if self.min_duration_sec > self.max_duration_sec:
            raise ValueError("subtitle min_duration_sec 不能大于 max_duration_sec")
        return self


class PipelineRuntimeConfig(BaseModel):
    retries: int = Field(default=1, ge=0, le=5)
    runs_dir: Path = Path("runs")
    sequential_gpu: bool = True


class VideoConfig(BaseModel):
    renderer: Literal["mock", "remotion"] = "mock"
    width: int = Field(default=1920, ge=320, le=7680)
    height: int = Field(default=1080, ge=240, le=4320)
    fps: int = Field(default=30, ge=1, le=120)
    codec: Literal["h264"] = "h264"
    audio_codec: Literal["aac"] = "aac"


class RenderConfig(BaseModel):
    temp_dir: Path = Path("video/temp")
    output_dir: Path = Path("output")
    remotion_dir: Path = Path("video/remotion")
    ffmpeg_path: Path | None = None
    ffprobe_path: Path | None = None


class CoverConfig(BaseModel):
    width: int = Field(default=1280, ge=320, le=7680)
    height: int = Field(default=720, ge=240, le=4320)
    format: Literal["png", "jpeg"] = "png"


class TagConfig(BaseModel):
    max_count: int = Field(default=10, ge=1, le=20)


class PublishConfig(BaseModel):
    title_candidates: int = Field(default=5, ge=1, le=10)
    cover: CoverConfig = Field(default_factory=CoverConfig)
    tags: TagConfig = Field(default_factory=TagConfig)


class PublishingConfig(BaseModel):
    provider: Literal["mock", "bilibili"] = "mock"
    require_approval: bool = True
    save_credentials: bool = False
    workspace_dir: Path = Path("workspace/publishing")


class FeedbackConfig(BaseModel):
    provider: Literal["manual", "mock", "bilibili"] = "manual"


class SecurityConfig(BaseModel):
    enabled: bool = True
    default_deny: bool = True
    redact_credentials: bool = True
    policy_file: Path = Path("config/security_policy.yaml")
    credential_reference_file: Path = Path("config/credential_references.yaml")
    audit_log_path: Path = Path("audit/audit_log.jsonl")
    tool_allowlist: list[str] = Field(
        default_factory=lambda: ["ffmpeg", "ffprobe", "python", "node", "npm", "npx"]
    )


class QAConfig(BaseModel):
    strict: bool = False


class LearningConfig(BaseModel):
    memory_dir: Path = Path("memory")


class OperationsConfig(BaseModel):
    default_channel_id: str = Field(default="main", min_length=1, pattern=r"^[A-Za-z0-9_-]+$")
    recent_window: int = Field(default=10, ge=2, le=100)
    minimum_experiment_group_size: int = Field(default=2, ge=1, le=50)


class CreatorConfig(BaseModel):
    name: str = "Alysia"
    require_human_approval: bool = True
    profile_file: Path = Path("config/creator_profile.yaml")


class TrendsConfig(BaseModel):
    provider: Literal["mock", "manual", "web"] = "mock"
    max_items: int = Field(default=50, ge=1, le=500)
    freshness_days: int = Field(default=7, ge=1, le=90)
    workspace_dir: Path = Path("workspace/trends")
    web_sources: list[str] = Field(default_factory=list)


class PlanningWeights(BaseModel):
    channel_relevance: float = Field(default=0.18, ge=0)
    freshness: float = Field(default=0.12, ge=0)
    audience_fit: float = Field(default=0.14, ge=0)
    novelty_vs_history: float = Field(default=0.16, ge=0)
    evidence_quality: float = Field(default=0.14, ge=0)
    production_feasibility: float = Field(default=0.10, ge=0)
    experiment_value: float = Field(default=0.16, ge=0)
    duplication_penalty: float = Field(default=0.20, ge=0)
    risk_penalty: float = Field(default=0.15, ge=0)


class PlanningConfig(BaseModel):
    candidate_count: int = Field(default=10, ge=1, le=100)
    selected_count: int = Field(default=3, ge=1, le=20)
    horizon_days: int = Field(default=7, ge=1, le=90)
    plans_dir: Path = Path("plans")
    duplicate_threshold: float = Field(default=0.72, ge=0, le=1)
    weights: PlanningWeights = Field(default_factory=PlanningWeights)


class CreatorLoopConfig(BaseModel):
    enabled: bool = False
    planning_interval_hours: int = Field(default=24, ge=1, le=24 * 30)
    horizon_days: int = Field(default=7, ge=1, le=90)
    candidate_count: int = Field(default=10, ge=1, le=100)
    selected_count: int = Field(default=3, ge=1, le=20)
    require_human_approval: bool = True
    jobs_dir: Path | None = None
    beta_evidence_file: Path = Path("evaluation/alpha22/alpha22_beta_runs.csv")


class IdentityConfig(BaseModel):
    enabled: bool = True
    require_approval: bool = True
    version_control: bool = True
    directory: Path = Path("identity")


class BrandVoiceConfig(BaseModel):
    technical_level: Literal["low", "medium", "high"] = "medium"
    humor_level: Literal["none", "low", "medium", "high"] = "low"
    evidence_priority: Literal["low", "medium", "high"] = "high"


class VisualIdentityConfig(BaseModel):
    template_version: str = Field(default="v1", min_length=1)


class H3VisualConfig(BaseModel):
    enabled: bool = True
    mode: Literal["local_comfyui"] = "local_comfyui"
    low_vram: bool = True
    comfyui_base_url: str = "http://127.0.0.1:8188"
    comfyui_dir: Path | None = None
    workflow_dir: Path = Path("workflows/comfyui/h3")
    model_path: Path | None = None
    diffusion_model: str = "minimax_h3_fl2va_pruned_int8_convrot.safetensors"
    text_encoder: str = "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors"
    video_vae: str = "minimax_h3_video_vae_fp16.safetensors"
    audio_vae: str = "minimax_h3_audio_vae_fp32.safetensors"
    default_clip_duration_sec: float = Field(default=5.0, ge=3.0, le=8.0)
    max_clip_duration_sec: float = Field(default=8.0, ge=3.0, le=15.0)
    default_resolution_profile: Literal["low", "medium"] = "low"
    max_generated_seconds_per_video: float = Field(default=30.0, ge=0, le=120)
    max_clips_per_video: int = Field(default=5, ge=0, le=20)
    draft_max_generated_seconds: float = Field(default=0.0, ge=0, le=30)
    draft_max_clips: int = Field(default=0, ge=0, le=3)
    standard_max_generated_seconds: float = Field(default=18.0, ge=0, le=30)
    standard_max_clips: int = Field(default=3, ge=0, le=5)
    high_max_generated_seconds: float = Field(default=30.0, ge=0, le=60)
    high_max_clips: int = Field(default=5, ge=0, le=8)
    preview_width: int = Field(default=608, ge=320, le=1344, multiple_of=32)
    preview_height: int = Field(default=352, ge=240, le=768, multiple_of=32)
    preview_steps: int = Field(default=6, ge=1, le=20)
    preview_seed: int = Field(default=20260808, ge=0)
    job_timeout_sec: float = Field(default=7200.0, ge=60, le=21600)
    measured_peak_vram_mb: int | None = Field(default=None, ge=0)
    measured_peak_ram_mb: int | None = Field(default=None, ge=0)
    measured_wall_time_sec: float | None = Field(default=None, ge=0)
    measurement_profile: str | None = None
    sequential_gpu_required: bool = True
    unload_other_gpu_models: bool = True
    retry_limit: int = Field(default=1, ge=0, le=3)
    api_timeout_sec: float = Field(default=30.0, gt=0, le=600)


class VisualGenerationConfig(BaseModel):
    enabled: bool = True
    provider: Literal["mock", "comfyui-h3"] = "mock"
    cache_dir: Path = Path("workspace/visual_cache")
    queue_dir: Path = Path("workspace/visual_queue")
    h3: H3VisualConfig = Field(default_factory=H3VisualConfig)
    preserve_h3_audio_as_ambience: bool = False
    upscale: Literal["none", "ffmpeg"] = "ffmpeg"


class ProductionConfig(BaseModel):
    quality_target: Literal["draft", "standard", "high"] = "standard"
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
    max_retries_per_stage: int = Field(default=2, ge=0, le=5)
    research_cache_ttl_hours: int = Field(default=24, ge=0, le=24 * 90)
    cache_dir: Path = Path("workspace/production_cache")


class OptimizationWeights(BaseModel):
    quality: float = Field(default=0.4, ge=0)
    reliability: float = Field(default=0.3, ge=0)
    latency: float = Field(default=0.15, ge=0)
    cost: float = Field(default=0.1, ge=0)
    local_preference: float = Field(default=0.05, ge=0)


class OptimizationConfig(BaseModel):
    weights: OptimizationWeights = Field(default_factory=OptimizationWeights)
    routing: dict[str, dict[str, list[str]]] = Field(default_factory=dict)


class StudioConfig(BaseModel):
    enabled: bool = True
    mode: Literal["sequential"] = "sequential"
    max_review_rounds: int = Field(default=2, ge=0, le=10)
    max_agent_hops: int = Field(default=20, ge=1, le=100)
    require_handoff_records: bool = True
    enforce_artifact_ownership: bool = True
    human_escalation_on_loop_limit: bool = True


class SupervisorConfig(BaseModel):
    enabled: bool = True
    root_dir: Path = Path("supervisor")
    max_actions_per_tick: int = Field(default=3, ge=1, le=50)
    max_dispatches_per_tick: int = Field(default=1, ge=0, le=10)
    max_goal_depth: int = Field(default=3, ge=1, le=10)
    max_children_per_goal: int = Field(default=8, ge=1, le=50)
    max_active_projects: int = Field(default=3, ge=1, le=20)
    require_approval_for_major_replan: bool = True


class GovernanceConfig(BaseModel):
    max_runs_per_day: int = Field(default=2, ge=0, le=100)
    max_runs_per_week: int = Field(default=7, ge=0, le=500)
    max_cloud_cost_per_day: float | None = Field(default=None, ge=0)
    max_cloud_cost_per_week: float | None = Field(default=None, ge=0)
    max_failed_runs_before_pause: int = Field(default=3, ge=1, le=100)
    budget_warning_ratio: float = Field(default=0.8, gt=0, le=1)


class CapabilityConfig(BaseModel):
    root_dir: Path = Path("workspace/capabilities")
    sandbox_dir: Path = Path("workspace/sandbox/skills")
    evidence_files: list[Path] = Field(default_factory=lambda: [Path("evaluation/capability_evidence_alpha14.json")])
    minimum_evidence_count: int = Field(default=1, ge=1, le=20)
    require_human_approval: bool = True
    allow_network_in_sandbox: bool = False
    allow_credentials_in_sandbox: bool = False
    allow_core_source_write: bool = False


class WorkflowConfig(BaseModel):
    enabled: bool = True
    mode: Literal["sequential"] = "sequential"
    max_steps: int = Field(default=20, ge=1, le=100)
    max_repair_rounds: int = Field(default=2, ge=0, le=10)
    max_skill_hops: int = Field(default=12, ge=1, le=100)
    require_validation: bool = True
    allow_unapproved_skills: bool = False
    auto_recipe_candidate: bool = True
    recipe_validation_successes: int = Field(default=3, ge=2, le=20)
    recipe_dir: Path = Path("memory/workflows")


class SimulationConfig(BaseModel):
    enabled: bool = True
    max_candidates: int = Field(default=5, ge=2, le=5)
    max_depth: int = Field(default=2, ge=1, le=2)
    mode: Literal["dry_run"] = "dry_run"
    allow_real_provider_preview: bool = False
    write_to_real_memory: bool = False
    require_uncertainty: bool = True
    auto_select_low_risk_only: bool = True
    root_dir: Path = Path("simulations")


class KnowledgeConfig(BaseModel):
    enabled: bool = True
    root_dir: Path = Path("knowledge")
    require_sources_for_facts: bool = True
    block_stale_critical_claims: bool = True
    preserve_historical_versions: bool = True
    maintenance_tick_enabled: bool = True
    max_research_sources: int = Field(default=8, ge=1, le=50)
    max_research_rounds: int = Field(default=2, ge=1, le=5)


class FreshnessConfig(BaseModel):
    software_days: int = Field(default=14, ge=1)
    pricing_days: int = Field(default=3, ge=1)
    current_roles_days: int = Field(default=7, ge=1)
    stable_definition_days: int = Field(default=365, ge=1)


class ReliabilityResourceGuardConfig(BaseModel):
    min_disk_free_gb: float = Field(default=5.0, ge=0)
    warning_disk_free_gb: float = Field(default=10.0, ge=0)
    min_ram_available_mb: int = Field(default=2048, ge=0)
    warning_ram_available_mb: int = Field(default=4096, ge=0)
    min_vram_free_mb: int = Field(default=768, ge=0)
    warning_vram_free_mb: int = Field(default=1536, ge=0)


class ReliabilityConfig(BaseModel):
    max_retries_per_stage: int = Field(default=2, ge=0, le=5)
    max_recovery_rounds: int = Field(default=3, ge=1, le=10)
    exponential_backoff: bool = True
    backoff_base_sec: float = Field(default=1.0, ge=0, le=300)
    require_checkpoint_before_destructive_rebuild: bool = True
    state_backup_count: int = Field(default=2, ge=1, le=5)
    artifact_hash_enabled: bool = False
    fault_injection_enabled: bool = False
    resource_guard: ReliabilityResourceGuardConfig = Field(default_factory=ReliabilityResourceGuardConfig)


class AlysiaConfig(BaseModel):
    project: dict[str, Any] = Field(default_factory=dict)
    video: VideoConfig = Field(default_factory=VideoConfig)
    resources: ResourceConfig = Field(default_factory=ResourceConfig)
    hardware_profile: HardwareProfileConfig = Field(default_factory=HardwareProfileConfig)
    providers: dict[str, Any] = Field(default_factory=dict)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    content: ContentConfig = Field(default_factory=ContentConfig)
    research: ResearchConfig = Field(default_factory=ResearchConfig)
    tts: TTSConfig = Field(default_factory=TTSConfig)
    asr: ASRConfig = Field(default_factory=ASRConfig)
    subtitle: SubtitleConfig = Field(default_factory=SubtitleConfig)
    render: RenderConfig = Field(default_factory=RenderConfig)
    publish: PublishConfig = Field(default_factory=PublishConfig)
    publishing: PublishingConfig = Field(default_factory=PublishingConfig)
    feedback: FeedbackConfig = Field(default_factory=FeedbackConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    qa: QAConfig = Field(default_factory=QAConfig)
    learning: LearningConfig = Field(default_factory=LearningConfig)
    operations: OperationsConfig = Field(default_factory=OperationsConfig)
    creator: CreatorConfig = Field(default_factory=CreatorConfig)
    trends: TrendsConfig = Field(default_factory=TrendsConfig)
    planning: PlanningConfig = Field(default_factory=PlanningConfig)
    creator_loop: CreatorLoopConfig = Field(default_factory=CreatorLoopConfig)
    identity: IdentityConfig = Field(default_factory=IdentityConfig)
    brand_voice: BrandVoiceConfig = Field(default_factory=BrandVoiceConfig)
    visual_identity: VisualIdentityConfig = Field(default_factory=VisualIdentityConfig)
    visual_generation: VisualGenerationConfig = Field(default_factory=VisualGenerationConfig)
    production: ProductionConfig = Field(default_factory=ProductionConfig)
    optimization: OptimizationConfig = Field(default_factory=OptimizationConfig)
    studio: StudioConfig = Field(default_factory=StudioConfig)
    supervisor: SupervisorConfig = Field(default_factory=SupervisorConfig)
    governance: GovernanceConfig = Field(default_factory=GovernanceConfig)
    capability: CapabilityConfig = Field(default_factory=CapabilityConfig)
    workflow: WorkflowConfig = Field(default_factory=WorkflowConfig)
    simulation: SimulationConfig = Field(default_factory=SimulationConfig)
    knowledge: KnowledgeConfig = Field(default_factory=KnowledgeConfig)
    freshness: FreshnessConfig = Field(default_factory=FreshnessConfig)
    reliability: ReliabilityConfig = Field(default_factory=ReliabilityConfig)
    runtime: PipelineRuntimeConfig = Field(default_factory=PipelineRuntimeConfig)


def load_config(path: Path | None = None) -> AlysiaConfig:
    """读取 YAML 配置；缺少本地配置时回退到仓库示例配置。"""
    config_path = path or RuntimeSettings().config_file
    if path is None and not config_path.exists():
        config_path = Path("config.example.yaml")
    with config_path.open("r", encoding="utf-8") as stream:
        payload = yaml.safe_load(stream) or {}
    return AlysiaConfig.model_validate(payload)
