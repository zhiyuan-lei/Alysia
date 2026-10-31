from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from alysia.capabilities import CapabilityService
from alysia.capabilities.gaps import CapabilityGapStore
from alysia.capabilities.skill_registry import SkillRegistry
from alysia.core.config import AlysiaConfig
from alysia.schemas import (
    CapabilityGap,
    SkillRecord,
    WorkflowApprovalPolicy,
    WorkflowBudgetPolicy,
    WorkflowEvaluationReport,
    WorkflowPlan,
    WorkflowTask,
)
from alysia.workflow import (
    CapabilityMatcher,
    ExecutorSpec,
    RegistryView,
    WorkflowExecutorRegistry,
    WorkflowRepairPlanner,
    WorkflowService,
)
from alysia.workflow.demo import failure_repair_resume_demo
from alysia.workflow.executors import WorkflowExecutionError, _declarative_adapter


def _config(tmp_path: Path) -> AlysiaConfig:
    config = AlysiaConfig()
    config.runtime.runs_dir = tmp_path / "runs"
    config.capability.root_dir = tmp_path / "capabilities"
    config.capability.sandbox_dir = tmp_path / "sandbox"
    config.workflow.recipe_dir = tmp_path / "memory" / "workflows"
    config.production.offline_mode = True
    return config


def _service(tmp_path: Path) -> WorkflowService:
    return WorkflowService(_config(tmp_path))


def _task(task_id: str = "task", *, output: str = "selected_scenes") -> WorkflowTask:
    return WorkflowTask(
        task_id=task_id, objective="从 storyboard 选择关键视觉场景",
        inputs=["storyboard"], desired_outputs=[output], constraints=["offline"],
        execution_mode="testing", success_criteria=["status:completed", f"artifact:{output}"],
        approval_policy=WorkflowApprovalPolicy(allow_mock_artifacts=True),
    )


def _visual_task(task_id: str) -> WorkflowTask:
    return WorkflowTask(
        task_id=task_id, objective="H3 visual enhancement workflow",
        inputs=["storyboard"], desired_outputs=["video_qa_report"],
        constraints=["offline", "mock allowed"], execution_mode="testing",
        budget_policy=WorkflowBudgetPolicy(allow_unknown_resources=True),
        approval_policy=WorkflowApprovalPolicy(allow_mock_artifacts=True),
        success_criteria=["status:completed", "artifact:video_qa_report"],
    )


def _skill(
    registry: SkillRegistry,
    skill_id: str,
    *,
    status: str = "active",
    inputs: list[str] | None = None,
    outputs: list[str] | None = None,
) -> SkillRecord:
    record = SkillRecord(
        skill_id=skill_id, name=skill_id, version=1, status=status,
        provenance={"source": "test"}, proposal_ref="proposal", evaluation_ref="evaluation",
        approved_by="human:test", approved_at=datetime.now().astimezone(), owner_agents=["designer"],
        interface="run(input) -> output", accepted_inputs=inputs or ["scene_visual_plan"],
        produced_outputs=outputs or ["visual_clip"], execution_layer="production",
        resource_requirements=(
            {"gpu_heavy": True, "sequential_gpu_required": True, "peak_vram_mb": "unknown"}
            if skill_id == "h3_visual_generation" else {}
        ),
    )
    return registry._save(record)


def _activate_h3(service: WorkflowService) -> None:
    _skill(service.capability_service.skills.registry, "h3_visual_generation")


def test_workflow_task_schema() -> None:
    task = _task()
    assert task.success_criteria and task.budget_policy.max_local_vram_mb == 6144
    with pytest.raises(ValueError, match="success criteria"):
        WorkflowTask(
            task_id="vague", objective="do something", desired_outputs=["x"],
            success_criteria=["尽可能做好"],
        )


def test_capability_matcher(tmp_path: Path) -> None:
    service = _service(tmp_path)
    candidates = CapabilityMatcher().match(_task(), service.registry)
    selected = next(item for item in candidates if item.candidate_id == "scene_selection")
    assert selected.eligible and "selected_scenes" in selected.produced_outputs
    assert selected.match_score > 0.5


def test_unapproved_skill_not_eligible(tmp_path: Path) -> None:
    config = _config(tmp_path)
    capability = CapabilityService(config)
    gap = CapabilityGap(
        gap_id="gap_unapproved", description="missing test skill", evidence_runs=["run"],
        evidence_ids=["evidence"], affected_agents=["designer"], severity="high", frequency=1,
        current_workaround="blocked", proposed_capability="unapproved_test_skill", confidence=0.9,
    )
    CapabilityGapStore(config.capability.root_dir).save(gap)
    proposal = capability.skills.propose(gap.gap_id)
    registry = RegistryView(capability.registry, capability.skills.registry)
    candidates = CapabilityMatcher().match(_task(), registry)
    assert proposal.state == "PROPOSED"
    assert proposal.skill_id not in {item.candidate_id for item in candidates}


def test_workflow_plan_dag(tmp_path: Path) -> None:
    service = _service(tmp_path)
    plan = service.plan(WorkflowTask(
        task_id="dag", objective="plan visuals", inputs=["storyboard"],
        desired_outputs=["scene_visual_plan"], execution_mode="testing",
        success_criteria=["artifact:scene_visual_plan"],
    ))
    assert [step.capability_id for step in plan.steps] == ["scene_selection", "visual_planning"]
    assert plan.steps[1].depends_on == [plan.steps[0].step_id]


def test_workflow_cycle_rejected(tmp_path: Path) -> None:
    service = _service(tmp_path)
    plan = service.plan(WorkflowTask(
        task_id="cycle", objective="plan visuals", inputs=["storyboard"],
        desired_outputs=["scene_visual_plan"], execution_mode="testing",
        success_criteria=["artifact:scene_visual_plan"],
    ))
    first = plan.steps[0].model_copy(update={"depends_on": [plan.steps[1].step_id]})
    plan = plan.model_copy(update={"steps": [first, plan.steps[1]]})
    report = service.validator.validate(service.store.load_task("cycle"), plan, service.registry)
    assert not report.passed and any("循环" in item for item in report.errors)


def test_workflow_contract_validation(tmp_path: Path) -> None:
    service = _service(tmp_path)
    plan = service.plan(_task("contract"))
    bad = plan.steps[0].model_copy(update={"inputs": ["unknown_input"]})
    report = service.validator.validate(
        service.store.load_task("contract"), plan.model_copy(update={"steps": [bad]}), service.registry,
    )
    assert not report.passed and any("contract" in item for item in report.errors)


def test_resource_policy_inherited(tmp_path: Path) -> None:
    service = _service(tmp_path)
    _activate_h3(service)
    task = WorkflowTask(
        task_id="resource", objective="h3 visual", inputs=["scene_visual_plan"],
        desired_outputs=["visual_clip"], execution_mode="production",
        success_criteria=["artifact:visual_clip"],
    )
    candidates = CapabilityMatcher().match(task, service.registry)
    h3 = [item for item in candidates if item.candidate_id in {"h3_visual_generation", "visual_h3_local"}]
    assert h3 and all(not item.eligible for item in h3)
    assert any("sequential GPU" in note for item in h3 for note in item.resource_notes)


def test_workflow_runtime_resume(tmp_path: Path) -> None:
    result = failure_repair_resume_demo(_config(tmp_path))
    assert result["failed_status"] == "blocked"
    assert result["resumed_status"] == "completed"
    assert result["attempts"] == 2


def test_workflow_idempotent(tmp_path: Path) -> None:
    service = _service(tmp_path)
    plan = service.plan(_task("idempotent"))
    assert service.validate(plan.workflow_id).passed
    first = service.run(plan.workflow_id)
    second = service.run(plan.workflow_id)
    step_id = plan.steps[0].step_id
    assert first.steps[step_id].attempts == second.steps[step_id].attempts == 1


def test_repair_uses_only_approved_fallback(tmp_path: Path) -> None:
    service = _service(tmp_path)
    disabled = _skill(
        service.capability_service.skills.registry, "disabled_fallback", status="disabled",
        inputs=["storyboard"], outputs=["selected_scenes"],
    )
    active = _skill(
        service.capability_service.skills.registry, "active_fallback", status="active",
        inputs=["storyboard"], outputs=["selected_scenes"],
    )
    plan = service.plan(_task("fallback"))
    step = plan.steps[0].model_copy(update={"fallback": [disabled.skill_id, active.skill_id]})
    state = service.store.load_state(plan)
    state.steps[step.step_id].attempts = 2
    repair = WorkflowRepairPlanner(max_repair_rounds=2).propose(plan, state, step, "boom", service.registry)
    assert repair.action == "use_approved_fallback"
    assert repair.selected_implementation == active.skill_id


def test_repair_round_limit(tmp_path: Path) -> None:
    service = _service(tmp_path)
    plan = service.plan(_task("limit"))
    state = service.store.load_state(plan)
    state.repair_rounds = 2
    repair = WorkflowRepairPlanner(max_repair_rounds=2).propose(
        plan, state, plan.steps[0], "persistent failure", service.registry,
    )
    assert repair.action == "escalate_to_human" and repair.approval_required


def test_workflow_evaluation(tmp_path: Path) -> None:
    service = _service(tmp_path)
    plan = service.plan(_task("evaluation"))
    service.validate(plan.workflow_id)
    service.run(plan.workflow_id)
    report = service.store.load_evaluation(plan)
    assert report.task_success and report.overall_score == 1.0
    assert report.resource_observations["adapter"] == "controlled_declarative_testing"


def test_candidate_recipe_after_single_success(tmp_path: Path) -> None:
    service = _service(tmp_path)
    plan = service.plan(_task("recipe_one"))
    service.validate(plan.workflow_id); service.run(plan.workflow_id)
    recipes = service.recipes.list()
    assert len(recipes) == 1 and recipes[0].status == "candidate" and recipes[0].success_count == 1


def test_recipe_validated_after_multiple_successes(tmp_path: Path) -> None:
    service = _service(tmp_path)
    for index in range(3):
        plan = service.plan(_task(f"recipe_{index}"))
        service.validate(plan.workflow_id); service.run(plan.workflow_id)
    recipe = service.recipes.list()[0]
    assert recipe.status == "validated" and recipe.success_count == 3


def test_recipe_confidence_decreases_on_failure(tmp_path: Path) -> None:
    service = _service(tmp_path)
    task = _task("confidence")
    plan = service.plan(task)
    service.validate(plan.workflow_id); service.run(plan.workflow_id)
    before = service.recipes.list()[0].confidence
    failed = WorkflowEvaluationReport(
        workflow_id="failed", run_id="independent_failure", task_success=False,
        step_success_rates={plan.steps[0].step_id: 0.0}, elapsed_time_sec=1,
        unmet_criteria=task.success_criteria, overall_score=0, reliability=0,
        recommendation="do_not_reuse", created_at=datetime.now().astimezone(),
    )
    after = service.recipes.record(task, plan.model_copy(update={"run_id": "independent_failure"}), failed)
    assert after.confidence < before and after.failure_count == 1


def test_recipe_retrieval(tmp_path: Path) -> None:
    service = _service(tmp_path)
    for index in range(3):
        plan = service.plan(_task(f"retrieve_{index}"))
        service.validate(plan.workflow_id); service.run(plan.workflow_id)
    fourth = service.plan(_task("retrieve_4"))
    assert fourth.recipe_id and fourth.recipe_evidence_runs
    assert "current budget/approval policy revalidated" in fourth.recipe_adjustments


def test_recipe_version_invalidation(tmp_path: Path) -> None:
    service = _service(tmp_path)
    _activate_h3(service)
    for index in range(3):
        plan = service.plan(_visual_task(f"h3_recipe_{index}"))
        service.validate(plan.workflow_id); service.run(plan.workflow_id)
    assert any(item.status == "validated" for item in service.recipes.list())
    service.capability_service.skills.registry.disable("h3_visual_generation")
    next_plan = service.plan(_visual_task("h3_recipe_invalidated"))
    assert next_plan.recipe_id is None


def test_novel_task_routes_gap_to_alpha14(tmp_path: Path) -> None:
    service = _service(tmp_path)
    task = WorkflowTask(
        task_id="novel", objective="生成可编辑矢量信息图", inputs=["research"],
        desired_outputs=["editable_vector_infographic"], execution_mode="testing",
        success_criteria=["artifact:editable_vector_infographic"],
    )
    plan = service.plan(task)
    assert plan.status == "blocked_waiting_capability" and plan.gap_links
    assert any(item.startswith("skill:") and item.endswith(":PROPOSED") for item in plan.gap_links)
    assert not service.validate(plan.workflow_id).passed


def test_supervisor_layering_preserved(tmp_path: Path) -> None:
    service = _service(tmp_path)
    plan = service.plan(WorkflowTask(
        task_id="supervisor_layer", objective="decompose long term goal",
        inputs=["long_term_goal"], desired_outputs=["workflow_task"], execution_mode="testing",
        success_criteria=["artifact:workflow_task"],
    ))
    assert len(plan.steps) == 1
    assert plan.steps[0].capability_id == "long_horizon_supervision"
    assert plan.steps[0].execution_layer == "supervisor"


def test_studio_layering_preserved(tmp_path: Path) -> None:
    service = _service(tmp_path)
    plan = service.plan(WorkflowTask(
        task_id="studio_layer", objective="write script", inputs=["topic", "research"],
        desired_outputs=["script"], execution_mode="testing", success_criteria=["artifact:script"],
    ))
    assert plan.steps[0].capability_id == "script"
    assert plan.steps[0].execution_layer == "studio"


def test_publish_approval_gate_preserved(tmp_path: Path) -> None:
    service = _service(tmp_path)
    plan = service.plan(WorkflowTask(
        task_id="publish_gate", objective="prepare publish job", inputs=["publish_package"],
        desired_outputs=["publish_job"], execution_mode="production",
        success_criteria=["artifact:publish_job"],
    ))
    assert "human_publish_approval" in plan.approval_points
    assert service.validate(plan.workflow_id).passed
    state = service.run(plan.workflow_id)
    assert state.status == "blocked"
    assert "没有受信任 runtime adapter" in (state.blocked_reason or "")


def test_workflow_qa(tmp_path: Path) -> None:
    service = _service(tmp_path)
    plan = service.plan(_task("qa"))
    service.validate(plan.workflow_id); service.run(plan.workflow_id)
    report = service.report(plan.workflow_id)["qa"]
    assert report["passed"]
    assert all(report["checks"].values())
