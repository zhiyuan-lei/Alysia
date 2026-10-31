from __future__ import annotations

from alysia.schemas import Scene, VisualIdentity
from alysia.schemas.visual import H3VisualPrompt


class H3VisualPromptBuilder:
    def build(
        self,
        scene: Scene,
        visual_identity: VisualIdentity,
        *,
        continuity_context: list[str] | None = None,
        camera: str = "slow push-in",
        motion: str = "subtle, physically plausible motion",
    ) -> H3VisualPrompt:
        subject = scene.visual_prompt.strip() or scene.screen_text.strip() or scene.narration.strip()
        subject = subject[:300] or "abstract technology concept"
        style = "; ".join(visual_identity.scene_preferences[:5])
        colors = ", ".join(visual_identity.color_theme.values())
        return H3VisualPrompt(
            subject=subject,
            environment="clean cinematic technology explainer environment",
            action_motion=motion,
            camera=camera,
            lighting_style=f"brand palette {colors}; {style}",
            continuity_constraints=list(continuity_context or []),
            negative_constraints=[
                "no embedded captions", "no logos", "no watermarks", "no talking-head lip sync",
                "no abrupt identity change",
            ],
        )
