import asyncio
import json

from alysia.core.orchestrator import AlysiaOrchestrator
from alysia.core.state import Stage
from tests.helpers import make_config


def test_orchestrator_creates_text_pipeline_artifacts(tmp_path) -> None:
    orchestrator = AlysiaOrchestrator(make_config(tmp_path / "runs"))

    state = asyncio.run(orchestrator.create("为什么AI Agent还不是AGI？"))

    run_dir = orchestrator.manager.run_dir(state.run_id)
    expected = {
        "input.json",
        "run_state.json",
        "research.md",
        "sources.json",
        "script.md",
        "script.json",
        "storyboard.json",
        "metadata.json",
        "text_qa_report.json",
    }
    assert expected <= {path.name for path in run_dir.iterdir()}
    assert state.current_stage is Stage.QA
    assert state.text_pipeline_completed is True
    assert state.milestone == "text_ready"
    for filename in expected & {"input.json", "run_state.json", "sources.json", "script.json", "storyboard.json", "metadata.json", "text_qa_report.json"}:
        json.loads((run_dir / filename).read_text(encoding="utf-8"))
