import asyncio

from alysia.core.orchestrator import AlysiaOrchestrator
from alysia.providers.llm import MockLLMProvider
from alysia.providers.search import MockResearchProvider
from tests.helpers import make_config


def test_resume_does_not_repeat_completed_stages(tmp_path) -> None:
    llm = MockLLMProvider()
    research = MockResearchProvider()
    orchestrator = AlysiaOrchestrator(
        make_config(tmp_path / "runs"),
        llm_provider=llm,
        research_provider=research,
    )
    state = asyncio.run(orchestrator.create("为什么AI Agent还不是AGI？"))
    run_dir = orchestrator.manager.run_dir(state.run_id)
    artifact_times = {
        name: (run_dir / name).stat().st_mtime_ns
        for name in ("sources.json", "script.json", "storyboard.json", "text_qa_report.json")
    }

    resumed = asyncio.run(orchestrator.resume(state.run_id))

    assert resumed.text_pipeline_completed is True
    assert research.call_count == 1
    assert llm.calls == ["Script", "Storyboard"]
    assert artifact_times == {name: (run_dir / name).stat().st_mtime_ns for name in artifact_times}
