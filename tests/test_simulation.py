from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

import pytest

from alysia.capabilities.store import atomic_json
from alysia.core.config import AlysiaConfig
from alysia.schemas import (
    CandidatePlan,
    Prediction,
    SimulationAssumption,
    SimulationScenario,
    WorkflowRecipe,
    WorkflowRecipeStep,
)
from alysia.simulation import (
    CounterfactualCandidateGenerator,
    CounterfactualComparator,
    ProductionSimulationEngine,
    SimulationQA,
    SimulationService,
    SimulationStore,
    WorldStateSnapshotBuilder,
)
from alysia.supervisor import AutonomousSupervisor


def _config(tmp_path: Path) -> AlysiaConfig:
    config = AlysiaConfig()
    config.simulation.root_dir = tmp_path / "simulations"
    config.runtime.runs_dir = tmp_path / "runs"
    config.workflow.recipe_dir = tmp_path / "memory" / "workflows"
    config.capability.root_dir = tmp_path / "capabilities"
    config.capability.sandbox_dir = tmp_path / "sandbox"
    config.supervisor.root_dir = tmp_path / "supervisor"
    config.learning.memory_dir = tmp_path / "memory"
    config.identity.directory = tmp_path / "identity"
    config.production.offline_mode = True
    return config


def _scenario(scenario_id: str = "test_sim", *, approvals: list[str] | None = None) -> SimulationScenario:
    return SimulationScenario(
        scenario_id=scenario_id, objective="比较两个离线生产方案",
        assumptions=[SimulationAssumption(
            assumption_id="a1", statement="除质量档外其他变量保持一致",
            source="test fixture", confidence="medium",
        )],
        controllable_variables={"quality_profile": ["draft", "standard"]},
        fixed_variables={"real_publish": False},
        candidate_actions=[
            {"candidate_id": "draft", "actions": [{"type": "dry_run"}],
             "changed_variables": {"quality_profile": "draft"}, "rationale": "fast"},
            {"candidate_id": "standard", "actions": [{"type": "dry_run"}],
             "changed_variables": {"quality_profile": "standard"}, "rationale": "quality"},
        ],
        approval_policy={"required_gates": approvals or [], "allow_auto_select": False},
        evaluation_metrics=["quality", "risk"], uncertainty_notes=["offline only"],
        created_at=datetime.now().astimezone(),
    )


def _service(tmp_path: Path) -> SimulationService:
    return SimulationService(_config(tmp_path), project_root=tmp_path, root=tmp_path / "simulations")


def _write_snapshot_sources(tmp_path: Path) -> None:
    channel = tmp_path / "memory" / "channels" / "main" / "channel_memory.json"
    atomic_json(channel, {"channel_id": "main", "current_positioning": "test"})
    identity = tmp_path / "identity" / "creator_identity.yaml"
    identity.parent.mkdir(parents=True, exist_ok=True)
    identity.write_text("creator_name: Alysia\nversion: 1\nmission_statement: test\n", encoding="utf-8")


def _validated_recipe(config: AlysiaConfig, recipe_id: str = "recipe_test") -> None:
    now = datetime.now().astimezone()
    recipe = WorkflowRecipe(
        recipe_id=recipe_id, name="validated test recipe",
        task_pattern={"keywords": ["test"], "inputs": ["storyboard"], "desired_outputs": ["selected_scenes"]},
        required_capabilities=["scene_selection@capability:stable"],
        steps_template=[WorkflowRecipeStep(
            step_id="step_scene", capability_id="scene_selection", owner_agent="designer",
            inputs=["storyboard"], outputs=["selected_scenes"], execution_layer="production",
        )],
        evidence_runs=["test_run_1", "test_run_2", "test_run_3"], success_count=3,
        confidence=0.8, status="validated", created_at=now, updated_at=now,
    )
    atomic_json(config.workflow.recipe_dir / f"{recipe_id}.json", recipe.model_dump(mode="json"))


def test_simulation_scenario_schema() -> None:
    assert _scenario().assumptions[0].source == "test fixture"
    with pytest.raises(ValueError, match="assumptions"):
        SimulationScenario(
            scenario_id="bad", objective="missing assumptions",
            candidate_actions=[{"candidate_id": "a"}], created_at=datetime.now().astimezone(),
        )


def test_world_state_snapshot_sources(tmp_path: Path) -> None:
    _write_snapshot_sources(tmp_path)
    snapshot = WorldStateSnapshotBuilder(_config(tmp_path), tmp_path).build()
    assert snapshot.channel_state["channel_id"] == "main"
    assert snapshot.source_refs["channel_state"] == ["memory/channels/main/channel_memory.json"]
    assert snapshot.current_identity["version"] == 1


def test_candidate_generation_limit() -> None:
    scenario = _scenario().model_copy(update={
        "candidate_actions": [
            {"candidate_id": f"c{i}", "actions": [], "changed_variables": {}, "rationale": "test"}
            for i in range(6)
        ]
    })
    with pytest.raises(ValueError, match="max_candidates"):
        CounterfactualCandidateGenerator(5).generate(scenario)


def test_simulated_values_marked(tmp_path: Path) -> None:
    service = _service(tmp_path); service.create(_scenario())
    results = service.run("test_sim")
    assert all(item.estimate_type for row in results.candidates for item in row.predictions)


def test_unknown_not_fabricated() -> None:
    with pytest.raises(ValueError, match="unknown"):
        Prediction(metric="views", estimate_type="unknown", point_estimate=100, confidence="low")


def test_production_simulator(tmp_path: Path) -> None:
    snapshot = WorldStateSnapshotBuilder(_config(tmp_path), tmp_path).build()
    candidate = CandidatePlan(
        candidate_id="h3", changed_variables={"h3_clip_count": 2, "total_h3_seconds": 10},
        rationale="test",
    )
    predictions, failures, _ = ProductionSimulationEngine(tmp_path).evaluate(_scenario(), candidate, snapshot)
    latency = next(item for item in predictions if item.metric == "production_latency_sec")
    assert latency.estimate_type == "unknown"
    assert any("unavailable" in item for item in failures)


def test_workflow_dry_run(tmp_path: Path) -> None:
    config = _config(tmp_path); _validated_recipe(config)
    service = SimulationService(config, project_root=tmp_path, root=config.simulation.root_dir)
    scenario = _scenario("recipe_dry").model_copy(update={
        "candidate_actions": [
            {"candidate_id": "draft", "actions": [], "changed_variables": {"workflow_recipe_id": "recipe_test", "quality_profile": "draft"}, "rationale": "fast"},
            {"candidate_id": "standard", "actions": [], "changed_variables": {"workflow_recipe_id": "recipe_test", "quality_profile": "standard"}, "rationale": "quality"},
        ]
    })
    service.create(scenario); results = service.run(scenario.scenario_id)
    assert all(row.workflow_dry_run["valid"] for row in results.candidates)
    assert all(not row.workflow_dry_run["real_steps_executed"] for row in results.candidates)


def test_counterfactual_comparator(tmp_path: Path) -> None:
    service = _service(tmp_path); service.create(_scenario()); results = service.run("test_sim")
    comparison = CounterfactualComparator().compare(results)
    assert len(comparison.score_breakdown) == 2
    assert comparison.dominant_tradeoffs


def test_uncertainty_required() -> None:
    with pytest.raises(ValueError, match="assumptions"):
        Prediction(metric="quality", estimate_type="simulated", point_estimate=0.5, confidence="low")


def test_real_metrics_not_overwritten(tmp_path: Path) -> None:
    real = tmp_path / "memory" / "episodes" / "real.json"
    atomic_json(real, {"run_id": "real", "source": "real", "metrics_summary": {"views": 10}})
    before = hashlib.sha256(real.read_bytes()).hexdigest()
    service = _service(tmp_path); service.create(_scenario()); service.run("test_sim"); service.compare("test_sim")
    assert hashlib.sha256(real.read_bytes()).hexdigest() == before


def test_approval_gate_preserved(tmp_path: Path) -> None:
    service = _service(tmp_path); service.create(_scenario(approvals=["human_publish_approval"]))
    service.run("test_sim"); _, decision = service.compare("test_sim")
    assert decision.mode == "recommendation_only" and not decision.dispatch_allowed
    assert "human_publish_approval" in decision.required_approvals


def test_simulation_path_guard(tmp_path: Path) -> None:
    store = SimulationStore(tmp_path / "simulations")
    with pytest.raises(ValueError):
        store.scenario_dir("../escape")


def test_simulation_qa(tmp_path: Path) -> None:
    service = _service(tmp_path); service.create(_scenario()); results = service.run("test_sim")
    report = SimulationQA(service.config.simulation).run(_scenario(), results)
    assert report.passed and report.checks["simulation_reality_isolation"]


def test_calibration_memory(tmp_path: Path) -> None:
    service = _service(tmp_path); service.create(_scenario()); service.run("test_sim")
    actual = tmp_path / "actual.json"
    actual.write_text(json.dumps({"source": "testing", "metrics": {"risk_score": 0.2}}), encoding="utf-8")
    record = service.calibrate("test_sim", actual)
    assert record.is_testing and not record.applies_automatically
    assert not (tmp_path / "memory" / "simulation_calibration.json").exists()


def test_prediction_error_record(tmp_path: Path) -> None:
    service = _service(tmp_path); service.create(_scenario()); service.run("test_sim")
    actual = tmp_path / "actual.json"
    actual.write_text(json.dumps({"source": "testing", "metrics": {"risk_score": 0.0}}), encoding="utf-8")
    record = service.calibrate("test_sim", actual)
    assert record.prediction_errors[0].error is not None
    assert record.prediction_errors[0].direction_bias in {"over", "under", "aligned"}


def test_supervisor_uses_simulation_recommendation_only(tmp_path: Path) -> None:
    config = _config(tmp_path); service = SimulationService(config, project_root=tmp_path, root=config.simulation.root_dir)
    service.create(_scenario()); service.run("test_sim")
    payload = AutonomousSupervisor(config).simulation_recommendation("test_sim", service=service)
    assert payload["decision"]["mode"] == "recommendation_only"
    assert not payload["dispatch_performed"] and not payload["agent_steps_executed"]


def test_recipe_comparison(tmp_path: Path) -> None:
    config = _config(tmp_path); _validated_recipe(config)
    service = SimulationService(config, project_root=tmp_path, root=config.simulation.root_dir)
    scenario = _scenario("recipe_compare").model_copy(update={
        "candidate_actions": [
            {"candidate_id": "fast", "actions": [], "changed_variables": {"workflow_recipe_id": "recipe_test", "quality_profile": "draft"}, "rationale": "fast"},
            {"candidate_id": "standard", "actions": [], "changed_variables": {"workflow_recipe_id": "recipe_test", "quality_profile": "standard"}, "rationale": "standard"},
        ]
    })
    service.create(scenario); service.run(scenario.scenario_id); comparison, _ = service.compare(scenario.scenario_id)
    qualities = {item.candidate_id: item.expected_quality for item in comparison.score_breakdown}
    assert qualities["standard"] > qualities["fast"]


def test_simulation_idempotent(tmp_path: Path) -> None:
    service = _service(tmp_path); service.create(_scenario())
    first = service.run("test_sim"); second = service.run("test_sim")
    assert first.generated_at == second.generated_at
    lines = (tmp_path / "simulations" / "test_sim" / "trace.jsonl").read_text(encoding="utf-8").splitlines()
    assert len([line for line in lines if '"event": "simulation_run"' in line]) == 1


def test_experiment_proposal_stays_separate(tmp_path: Path) -> None:
    service = _service(tmp_path); service.create(_scenario()); service.run("test_sim")
    proposal = service.experiment_proposal("test_sim", hypothesis="draft is faster")
    assert proposal.approval_required and not proposal.real_execution_started
    assert proposal.status == "proposed"
