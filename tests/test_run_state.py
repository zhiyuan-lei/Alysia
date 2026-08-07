from alysia.core.run import RunManager
from alysia.core.state import Stage


def test_run_state_persists_utf8_topic_and_artifacts(tmp_path) -> None:
    manager = RunManager(tmp_path / "runs")
    state = manager.create("为什么智能体还不是通用智能？", {"llm": {"provider": "mock"}})
    manager.write_text(state.run_id, "research.md", "# 中文调研")
    state.artifacts["research_markdown"] = "research.md"
    state.complete_stage(Stage.RESEARCHING)
    manager.save(state)

    loaded = manager.load(state.run_id)

    assert loaded.topic == "为什么智能体还不是通用智能？"
    assert loaded.completed_stages == [Stage.RESEARCHING]
    assert manager.artifact_exists(loaded, "research_markdown")
    assert (manager.run_dir(state.run_id) / "input.json").read_text(encoding="utf-8").find("为什么") >= 0
