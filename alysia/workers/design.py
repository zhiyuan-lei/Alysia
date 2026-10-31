from __future__ import annotations

from pathlib import Path
from typing import Any

from alysia.agents import TagAgent, TitleAgent
from alysia.core.config import AlysiaConfig
from alysia.core.run import RunManager, RunState
from alysia.providers.cover import BaseCoverGenerator
from alysia.schemas import Script, Storyboard


class DesignWorker:
    """生成确定性的视觉计划与模板封面；不触发高成本图像生成。"""

    def __init__(
        self,
        manager: RunManager,
        config: AlysiaConfig,
        cover_generator: BaseCoverGenerator,
    ) -> None:
        self.manager = manager
        self.config = config
        self.cover_generator = cover_generator
        self.title_agent = TitleAgent(config.publish.title_candidates)
        self.tag_agent = TagAgent(config.publish.tags.max_count)

    def run(
        self,
        state: RunState,
        script: Script,
        storyboard: Storyboard,
        *,
        force: bool = False,
    ) -> dict[str, Any]:
        run_dir = self.manager.run_dir(state.run_id)
        plan_path = run_dir / "studio" / "design_plan.json"
        cover_suffix = ".jpg" if self.config.publish.cover.format == "jpeg" else ".png"
        cover_relative = Path("publish") / f"cover{cover_suffix}"
        cover_path = run_dir / cover_relative
        if not force and plan_path.is_file() and cover_path.is_file():
            state.artifacts["design_plan"] = "studio/design_plan.json"
            state.artifacts["publish_cover"] = cover_relative.as_posix()
            self.manager.save(state)
            return self.manager.read_json(state.run_id, "studio/design_plan.json")

        title = self.title_agent.run(state.topic, script, storyboard).primary_title
        tags = self.tag_agent.run(state.topic, script, "科技")
        subtitle = _truncate(script.thesis, 60)
        self.cover_generator.generate(
            cover_path,
            title=title,
            subtitle=subtitle,
            theme_elements=tags[:3],
        )
        plan = {
            "run_id": state.run_id,
            "template_version": self.config.visual_identity.template_version,
            "cover_path": cover_relative.as_posix(),
            "cover_title": title,
            "cover_subtitle": subtitle,
            "theme_elements": tags[:3],
            "scene_visual_types": [scene.visual_type for scene in storyboard.scenes],
            "high_cost_generation": False,
            "notes": ["仅使用确定性模板封面和现有程序化 scene；未触发高成本 AI 图像生成。"],
        }
        self.manager.write_json(state.run_id, "studio/design_plan.json", plan)
        state.artifacts["design_plan"] = "studio/design_plan.json"
        state.artifacts["publish_cover"] = cover_relative.as_posix()
        self.manager.save(state)
        return plan


def _truncate(value: str, limit: int) -> str:
    text = " ".join(value.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip("，。；; ") + "…"
