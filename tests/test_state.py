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
        "video_qa",
        "packaging",
        "publish_qa",
        "ready_for_review",
        "publish_approval",
        "publish_job",
        "feedback_waiting",
        "learning",
        "analytics_imported",
        "analyzed",
        "memory_updated",
        "strategy_ready",
        "qa",
        "completed",
        "failed",
    ]
