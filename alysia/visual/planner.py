from __future__ import annotations

from datetime import datetime

from alysia.core.config import AlysiaConfig
from alysia.schemas import ProductionPlan, Storyboard, VisualIdentity, VisualType
from alysia.schemas.visual import SceneVisualPlan, VisualPlan
from alysia.visual.prompt import H3VisualPromptBuilder


_DYNAMIC_MARKERS = {
    "动态", "运动", "镜头", "推进", "穿越", "奔跑", "流动", "爆炸", "生长", "变形",
    "cinematic", "motion", "camera", "video", "b-roll", "animate",
}


class VisualPlanner:
    def __init__(self, config: AlysiaConfig, prompt_builder: H3VisualPromptBuilder | None = None) -> None:
        self.config = config
        self.prompt_builder = prompt_builder or H3VisualPromptBuilder()

    def plan(
        self,
        run_id: str,
        storyboard: Storyboard,
        production_plan: ProductionPlan | None,
        visual_identity: VisualIdentity,
    ) -> VisualPlan:
        quality = production_plan.profile.quality_target if production_plan else self.config.production.quality_target
        h3 = self.config.visual_generation.h3
        if quality == "draft":
            max_clips = min(h3.max_clips_per_video, h3.draft_max_clips)
            max_seconds = min(h3.max_generated_seconds_per_video, h3.draft_max_generated_seconds)
        elif quality == "high":
            max_clips = min(h3.max_clips_per_video, h3.high_max_clips)
            max_seconds = min(h3.max_generated_seconds_per_video, h3.high_max_generated_seconds)
        else:
            max_clips = min(h3.max_clips_per_video, h3.standard_max_clips)
            max_seconds = min(h3.max_generated_seconds_per_video, h3.standard_max_generated_seconds)

        used_clips = 0
        used_seconds = 0.0
        scenes: list[SceneVisualPlan] = []
        warnings: list[str] = []
        h3_feasible = self._h3_feasible(production_plan) and self.config.visual_generation.enabled and h3.enabled
        for scene in storyboard.scenes:
            mode = "remotion"
            reasons: list[str] = []
            requested = min(max(scene.duration_sec, 3.0), h3.max_clip_duration_sec)
            text = f"{scene.visual_prompt} {scene.narration}".casefold()
            dynamic = any(marker in text for marker in _DYNAMIC_MARKERS)
            if scene.visual_type in {VisualType.TITLE, VisualType.TEXT, VisualType.DIAGRAM, VisualType.CODE, VisualType.CHART, VisualType.QUOTE}:
                reasons.append("文字、图表、代码或结构图优先使用 Remotion")
            elif scene.visual_type == VisualType.IMAGE and not dynamic:
                mode = "static_image"
                reasons.append("概念静态说明优先静态图")
            elif dynamic and h3_feasible and used_clips < max_clips and used_seconds + requested <= max_seconds:
                mode = "h3_t2v"
                used_clips += 1
                used_seconds += requested
                reasons.append("镜头明确要求动态/氛围 B-roll，且 H3 预算允许")
            elif dynamic:
                mode = "static_image" if scene.visual_type == VisualType.IMAGE else "remotion"
                reasons.append("动态诉求因 H3 可行性或预算限制降级")
            prompt = self.prompt_builder.build(scene, visual_identity) if mode.startswith("h3_") else None
            scenes.append(
                SceneVisualPlan(
                    scene_id=scene.id, generation_mode=mode,
                    requested_duration_sec=requested if mode.startswith("h3_") else scene.duration_sec,
                    prompt=prompt, route_reasons=reasons,
                    budgeted_h3_seconds=requested if mode.startswith("h3_") else 0,
                )
            )
        if sum(item.generation_mode.startswith("h3_") for item in scenes) == len(scenes):
            warnings.append("整条视频不可默认 H3 化；planner 已保留 Remotion/静态路由。")
        return VisualPlan(
            run_id=run_id, quality_target=quality, max_h3_clips=max_clips,
            max_h3_seconds=max_seconds, used_h3_clips=used_clips,
            used_h3_seconds=round(used_seconds, 3), scenes=scenes,
            warnings=warnings, created_at=datetime.now().astimezone(),
        )

    def _h3_feasible(self, production_plan: ProductionPlan | None) -> bool:
        if not self.config.visual_generation.h3.sequential_gpu_required:
            return False
        if production_plan and production_plan.profile.max_local_vram_mb < 4096:
            return False
        return True
