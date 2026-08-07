from alysia.core.state import Stage


def test_stage_values_are_stable() -> None:
    assert [stage.value for stage in Stage] == [
        "created",
        "researching",
        "writing",
        "storyboarding",
        "generating_assets",
        "generating_voice",
        "generating_subtitles",
        "rendering",
        "qa",
        "completed",
        "failed",
    ]

