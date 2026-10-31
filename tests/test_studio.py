from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path

import pytest

from alysia.core.orchestrator import AlysiaOrchestrator
from alysia.core.run import RunManager, RunState
from alysia.feedback import FeedbackService
from alysia.production import ProductionService
from alysia.publishing import PublishingService
from alysia.studio.agents import StudioRuntime, classify_failure
from alysia.studio.context import ContextSelector, StudioContextFactory
from alysia.studio.director import DirectorDecisionEngine, StudioDirector
from alysia.studio.handoff import HandoffProtocol
from alysia.studio.ownership import ArtifactCatalog
from alysia.studio.protocol import (
    AgentHandoff,
    AgentResult,
    ArtifactRef,
    StudioState,
    StudioTraceEvent,
)
from alysia.studio.qa import StudioQA
from alysia.studio.registry import AgentRegistry
from alysia.studio.trace import StudioTraceStore
from tests.helpers import make_config


def _run(config, topic: str = "为什么 AI Agent 还不是 AGI？") -> RunState:
    manager = RunManager(config.runtime.runs_dir)
    state = manager.create(topic, config.model_dump(mode="json"))
    ProductionService(config).plan(state.run_id, requested_operation="full")
    return manager.load(state.run_id)


@pytest.fixture(scope="module")
def completed_studio(tmp_path_factory):
    root = tmp_path_factory.mktemp("studio_full")
    config = make_config(root / "runs")
    config.content.min_duration_sec = 30
    config.content.max_duration_sec = 60
    config.content.default_duration_sec = 30
    state = _run(config)
    director = StudioDirector(config)
    first = asyncio.run(director.run(state.run_id))
    return config, state.run_id, first


def test_agent_registry() -> None:
    registry = AgentRegistry()
    assert [item.agent_id for item in registry.list()] == [
        "researcher",
        "writer",
        "storyboard_director",
        "designer",
        "voice",
        "editor",
        "critic",
        "analyst",
        "publisher",
    ]
    assert registry.get("voice").allowed_providers == [
        "tts.*",
        "asr.*",
        "subtitle.*",
        "deterministic.*",
    ]


def test_studio_context_snapshot(tmp_path: Path) -> None:
    config = make_config(tmp_path / "runs")
    state = _run(config)
    manager = RunManager(config.runtime.runs_dir)
    store = StudioTraceStore(manager, state.run_id)
    context = StudioContextFactory(config, AgentRegistry()).build(state.run_id, store)
    assert context.production_plan_id
    assert context.creator_identity_version == 1
    assert (store.context_dir / "context.v0001.json").is_file()


def test_handoff_schema() -> None:
    handoff = AgentHandoff(
        handoff_id="handoff_1",
        from_agent="researcher",
        to_agent="writer",
        objective="基于可验证资料生成脚本",
        required_inputs=["research"],
        provided_artifacts=[
            ArtifactRef(
                artifact_id="artifact_1",
                kind="research",
                path="sources.json",
                owner_agent_id="researcher",
            )
        ],
        acceptance_criteria=["不得编造来源"],
        constraints=["ProductionPlan 控制 provider"],
    )
    assert handoff.status == "pending"


def test_handoff_acceptance() -> None:
    handoff = HandoffProtocol.create(
        run_id="run",
        sequence=1,
        from_agent="researcher",
        to_agent="writer",
        objective="生成脚本",
        required_inputs=["research"],
        provided_artifacts=[],
        acceptance_criteria=["结构完整"],
        constraints=[],
    )
    rejected = HandoffProtocol.accept(handoff, available_kinds=set())
    assert rejected.status == "rejected"
    accepted = HandoffProtocol.accept(handoff, available_kinds={"research"})
    assert HandoffProtocol.complete(accepted).status == "completed"


def test_agent_result_contract() -> None:
    result = AgentResult(
        agent_id="writer",
        task_id="task_1",
        status="completed",
        summary="完成脚本",
        confidence=0.9,
        next_recommended_agent="critic",
    )
    assert result.produced_artifacts == []
    with pytest.raises(ValueError):
        AgentResult(
            agent_id="writer",
            task_id="task_2",
            status="failed",
            summary="失败",
            confidence=0.2,
        )


def test_director_rule_routing(tmp_path: Path) -> None:
    config = make_config(tmp_path / "runs")
    state = _run(config)
    decision = DirectorDecisionEngine().decide(
        state,
        StudioState(run_id=state.run_id),
        set(),
        {},
        manager=RunManager(config.runtime.runs_dir),
    )
    assert decision.agent_id == "researcher"
    assert "research" in decision.reason


def test_agent_role_boundaries(tmp_path: Path) -> None:
    config = make_config(tmp_path / "runs")
    state = _run(config)
    manager = RunManager(config.runtime.runs_dir)
    store = StudioTraceStore(manager, state.run_id)
    catalog = ArtifactCatalog(store, AgentRegistry())
    path = manager.write_json(state.run_id, "script.json", {"value": 1})
    assert path.is_file()
    with pytest.raises(PermissionError):
        catalog.register(
            run_id=state.run_id,
            agent_id="researcher",
            kind="script",
            path="script.json",
        )


def test_artifact_ownership(tmp_path: Path) -> None:
    config = make_config(tmp_path / "runs")
    state = _run(config)
    manager = RunManager(config.runtime.runs_dir)
    store = StudioTraceStore(manager, state.run_id)
    catalog = ArtifactCatalog(store, AgentRegistry())
    artifact = catalog.register(
        run_id=state.run_id,
        agent_id="writer",
        kind="script",
        path="script.json",
    )
    assert artifact.owner_agent_id == "writer"
    assert artifact.version == 1


def test_revision_request(tmp_path: Path) -> None:
    config = make_config(tmp_path / "runs")
    state = _run(config)
    manager = RunManager(config.runtime.runs_dir)
    store = StudioTraceStore(manager, state.run_id)
    catalog = ArtifactCatalog(store, AgentRegistry())
    catalog.register(run_id=state.run_id, agent_id="writer", kind="script", path="script.json")
    request = catalog.request_revision(
        run_id=state.run_id,
        artifact_kind="script",
        requested_by="critic",
        reason="缺少 hook",
        acceptance_criteria=["补充 hook"],
    )
    accepted = catalog.accept_revision(request.request_id, agent_id="writer")
    revised = catalog.register(
        run_id=state.run_id,
        agent_id="writer",
        kind="script",
        path="script.json",
        revision_request=accepted,
    )
    assert revised.version == 2
    assert next(item for item in store.revisions() if item.request_id == request.request_id).status == "completed"


def test_review_round_limit(tmp_path: Path) -> None:
    config = make_config(tmp_path / "runs")
    config.studio.max_review_rounds = 1
    state = _run(config)
    director = StudioDirector(config)
    store = StudioTraceStore(director.manager, state.run_id)
    studio_state = StudioState(run_id=state.run_id, review_rounds=2)
    limited = director._loop_limit(store, studio_state, "max_review_rounds")
    assert limited.status == "escalated"
    assert limited.escalation.kind == "human_intervention_required"


def test_max_agent_hops(tmp_path: Path) -> None:
    config = make_config(tmp_path / "runs")
    config.studio.max_agent_hops = 1
    state = _run(config)
    director = StudioDirector(config)
    store = StudioTraceStore(director.manager, state.run_id)
    limited = director._loop_limit(
        store,
        StudioState(run_id=state.run_id, agent_hops=1),
        "max_agent_hops",
    )
    assert limited.status == "escalated"


def test_context_selector(tmp_path: Path) -> None:
    config = make_config(tmp_path / "runs")
    state = _run(config)
    store = StudioTraceStore(RunManager(config.runtime.runs_dir), state.run_id)
    context = StudioContextFactory(config, AgentRegistry()).build(state.run_id, store)
    selector = ContextSelector(AgentRegistry())
    writer = selector.select(context, "writer")
    voice = selector.select(context, "voice")
    assert "brand_voice_summary" in writer.role_context
    assert "strategy_refs" in writer.role_context
    assert voice.role_context == {}


def test_failure_escalation() -> None:
    failure = classify_failure("publisher", RuntimeError("缺少人工 ApprovalRecord"))
    assert failure.kind == "approval_required"
    assert not failure.recoverable


def test_studio_trace(tmp_path: Path) -> None:
    config = make_config(tmp_path / "runs")
    state = _run(config)
    store = StudioTraceStore(RunManager(config.runtime.runs_dir), state.run_id)
    store.append_trace(
        StudioTraceEvent(
            event_id="trace_1",
            run_id=state.run_id,
            event_type="test",
            actor="studio_director",
            summary="trace",
            metadata={"api_token": "secret-value", "safe": "value"},
        )
    )
    record = store.trace_records()[0]
    assert record["metadata"]["api_token"] == "[REDACTED]"
    assert record["metadata"]["safe"] == "value"


def test_audio_failure_routes_to_voice(tmp_path: Path) -> None:
    config = make_config(tmp_path / "runs")
    state = _run(config)
    manager = RunManager(config.runtime.runs_dir)
    manager.write_json(state.run_id, "audio_qa_report.json", {"passed": False})
    state.artifacts["audio_qa_report"] = "audio_qa_report.json"
    manager.save(state)
    artifacts = {
        "research",
        "script",
        "script_review",
        "storyboard",
        "text_qa",
        "design_plan",
        "publish_cover",
        "audio",
        "subtitles",
        "audio_qa",
    }
    decision = DirectorDecisionEngine().decide(
        state,
        StudioState(run_id=state.run_id),
        artifacts,
        {},
        manager=manager,
    )
    assert decision.agent_id == "voice"


def test_publish_approval_gate_preserved(tmp_path: Path) -> None:
    config = make_config(tmp_path / "runs")
    state = _run(config)
    artifacts = {
        "research",
        "script",
        "script_review",
        "storyboard",
        "text_qa",
        "design_plan",
        "publish_cover",
        "audio",
        "subtitles",
        "audio_qa",
        "composition",
        "final_video",
        "video_qa",
        "final_review",
        "publish_package",
        "publish_qa",
    }
    decision = DirectorDecisionEngine().decide(
        state,
        StudioState(run_id=state.run_id),
        artifacts,
        {"publish_approved": False},
        manager=RunManager(config.runtime.runs_dir),
    )
    assert decision.agent_id is None
    assert decision.wait_status == "waiting_for_approval"


def test_production_plan_controls_provider(tmp_path: Path) -> None:
    config = make_config(tmp_path / "runs")
    state = _run(config)
    director = StudioDirector(config)
    store = StudioTraceStore(director.manager, state.run_id)
    runtime = StudioRuntime(
        config=config,
        orchestrator=director.orchestrator,
        registry=director.registry,
        catalog=ArtifactCatalog(store, director.registry),
        store=store,
    )
    plan = ProductionService(config).load_plan(state.run_id)
    assert runtime.provider_for(state.run_id, "script", "writer") == plan.selected_provider_per_stage["script"]


def test_studio_resume_idempotent(completed_studio) -> None:
    config, run_id, first = completed_studio
    assert first.status == "waiting_for_approval"
    director = StudioDirector(config)
    before = director.status(run_id)
    second = asyncio.run(director.resume(run_id))
    after = director.status(run_id)
    assert second.status == "waiting_for_approval"
    assert before["handoff_count"] == after["handoff_count"]
    assert before["result_count"] == after["result_count"]


def test_studio_qa(completed_studio) -> None:
    config, run_id, state = completed_studio
    director = StudioDirector(config)
    store = StudioTraceStore(director.manager, run_id)
    report = StudioQA(config).run(run_id, store, state)
    assert report.passed, report.errors
    assert report.checks["artifact_owners_valid"]


def test_analyst_runs_after_feedback_and_approval(completed_studio) -> None:
    config, run_id, _ = completed_studio
    publishing = PublishingService(config)
    publishing.approve(run_id, approved_by="human:studio-test")
    publishing.submit(run_id, provider="mock")
    FeedbackService(config).import_feedback(run_id, provider="mock")
    director = StudioDirector(config)
    final = asyncio.run(director.resume(run_id))
    results = StudioTraceStore(director.manager, run_id).results()
    assert final.status == "completed"
    assert [item.agent_id for item in results].count("analyst") == 1


def test_audio_failure_recovery_resumes_from_voice(tmp_path: Path) -> None:
    config = make_config(tmp_path / "runs")
    config.content.min_duration_sec = 30
    config.content.max_duration_sec = 60
    config.content.default_duration_sec = 30
    state = _run(config)
    director = StudioDirector(config)
    first = asyncio.run(director.run(state.run_id))
    assert first.status == "waiting_for_approval"
    manager = RunManager(config.runtime.runs_dir)
    current = manager.load(state.run_id)
    qa_path = manager.run_dir(state.run_id) / current.artifacts["audio_qa_report"]
    payload = json.loads(qa_path.read_text(encoding="utf-8"))
    payload["passed"] = False
    payload.setdefault("errors", []).append("simulated audio failure")
    qa_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    recovered = asyncio.run(director.resume(state.run_id))
    assert recovered.status == "waiting_for_approval"
    store = StudioTraceStore(manager, state.run_id)
    agents = [item.agent_id for item in store.results()]
    assert agents.count("researcher") == 1
    assert agents.count("writer") == 1
    assert agents.count("voice") == 2
    assert agents.count("editor") == 2
    assert agents.count("critic") == 4
    assert store.artifacts()[-1].version >= 1
    assert ArtifactCatalog(store, AgentRegistry()).latest("audio").version == 2
    assert ArtifactCatalog(store, AgentRegistry()).latest("final_video").version == 2
