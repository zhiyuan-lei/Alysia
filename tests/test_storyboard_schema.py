import pytest
from pydantic import ValidationError

from alysia.schemas.storyboard import Scene, Storyboard, VisualType


def test_storyboard_accepts_controlled_visual_type_and_duration() -> None:
    storyboard = Storyboard(
        title="标题",
        target_duration_sec=180,
        scenes=[
            Scene(
                id="scene-1",
                section_id="section-1",
                duration_sec=180,
                narration="旁白",
                visual_type=VisualType.DIAGRAM,
                screen_text="关键结论",
            )
        ],
    )

    assert storyboard.total_duration_sec == 180


def test_storyboard_rejects_large_duration_gap() -> None:
    with pytest.raises(ValidationError):
        Storyboard(
            title="标题",
            target_duration_sec=180,
            scenes=[
                Scene(
                    id="scene-1",
                    section_id="section-1",
                    duration_sec=30,
                    narration="旁白",
                    visual_type="text",
                )
            ],
        )
