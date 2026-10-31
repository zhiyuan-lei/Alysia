from __future__ import annotations

from pathlib import Path

from alysia.core.config import H3VisualConfig
from alysia.providers.visual.comfyui import ComfyUIProvider
from typing import Any

from alysia.schemas.visual import SceneVisualPlan, VisualGenerationJob, VisualProviderHealth


class MiniMaxH3LocalProvider(ComfyUIProvider):
    """MiniMax H3 的 ComfyUI workflow adapter；不建立第二套推理栈。"""

    provider_id = "visual.comfyui-h3"

    def __init__(self, config: H3VisualConfig, *, output_dir: Path, security=None) -> None:
        super().__init__(
            base_url=config.comfyui_base_url,
            workflow_dir=config.workflow_dir,
            output_dir=output_dir,
            timeout_sec=config.api_timeout_sec,
            job_timeout_sec=config.job_timeout_sec,
            security=security,
        )
        self.config = config

    def prepare_job(self, run_id: str, scene_spec: SceneVisualPlan) -> VisualGenerationJob:
        from alysia.visual.jobs import build_visual_job
        workflow_id = {
            "h3_t2v": "t2v",
            "h3_i2v": "i2v",
            "h3_r2v": "reference",
        }[scene_spec.generation_mode]
        return build_visual_job(run_id, scene_spec, self.provider_id, workflow_id, self.config.retry_limit)

    def estimated_peak_vram_mb(self, job: VisualGenerationJob) -> int | None:
        # A lower resolution alone is not evidence of a lower model-loading peak.
        return self.config.measured_peak_vram_mb

    def binding_values(self, job: VisualGenerationJob, metadata: dict[str, Any]) -> dict[str, Any]:
        values = super().binding_values(job, metadata)
        values.update(
            {
                "diffusion_model": self.config.diffusion_model,
                "text_encoder": self.config.text_encoder,
                "video_vae": self.config.video_vae,
                "audio_vae": self.config.audio_vae,
                "width": self.config.preview_width,
                "height": self.config.preview_height,
                "steps": self.config.preview_steps,
            }
        )
        return values

    def health_check(self) -> VisualProviderHealth:
        base = super().health_check()
        details = list(base.details)
        if not self.config.enabled:
            details.append("visual_generation.h3.enabled=false")
        model_paths = self.required_model_paths()
        missing = [str(path) for path in model_paths if not path.is_file()]
        if missing:
            details.append(f"H3 必需模型缺失：{missing}")
        if self.config.low_vram:
            details.append("Low-VRAM profile 已启用；GPU-heavy job 必须串行。")
        model_ready = bool(model_paths) and not missing
        return VisualProviderHealth(
            provider=self.provider_id,
            available=base.available and self.config.enabled and model_ready,
            details=details,
            workflows=base.workflows,
        )

    def required_model_paths(self) -> list[Path]:
        if self.config.comfyui_dir is None:
            return [self.config.model_path] if self.config.model_path is not None else []
        models = self.config.comfyui_dir / "models"
        return [
            models / "diffusion_models" / self.config.diffusion_model,
            models / "text_encoders" / self.config.text_encoder,
            models / "vae" / self.config.video_vae,
            models / "vae" / self.config.audio_vae,
        ]
