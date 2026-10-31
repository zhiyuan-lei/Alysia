from __future__ import annotations

import asyncio
from datetime import timedelta
from pathlib import Path

import pytest

from alysia.core.config import AlysiaConfig
from alysia.schemas import (
    BudgetUsage,
    ContentProject,
    DependencyEdge,
    Goal,
    GoalBudgetPolicy,
    PlannedRun,
    PriorityCandidate,
    SuccessMetric,
)
from alysia.supervisor import (
    AutonomousSupervisor,
    CrossRunContextSelector,
    DependencyGraph,
    GoalDecomposer,
    GovernancePolicy,
    LongHorizonPlanner,
    OfflineSupervisorDispatcher,
    PriorityEngine,
    SupervisorMonitor,
    SupervisorStore,
)
from alysia.supervisor.goals import supervisor_now
from alysia.planning import CreatorLoop
from tests.helpers import make_config


def _config(tmp_path: Path, **supervisor_overrides) -> AlysiaConfig:
    config = make_config(tmp_path / "runs")
    config.supervisor.root_dir = tmp_path / "supervisor"
    config.creator.profile_file = Path("config/creator_profile.yaml").resolve()
    for name, value in supervisor_overrides.items():
        setattr(config.supervisor, name, value)
    return config


def _goal(goal_id: str = "goal_test", *, status: str = "active") -> Goal:
    now = supervisor_now()
    return Goal(
        goal_id=goal_id,
        title="30天内完成 AI Agent 基础四期系列",
        description="制作四条前后关联内容并验证 8 秒 hook。",
        type="content_series",
        status=status,
        priority=90,
        created_at=now,
        updated_at=now,
        start_date=now.date(),
        target_date=now.date() + timedelta(days=30),
        success_metrics=[SuccessMetric(name="完成内容数", target=4, measurement_source="run_state")],
        constraints=["保留人工审批"],
        budget_policy=GoalBudgetPolicy(max_runs=4, max_cloud_cost=0, currency="CNY"),
        stop_conditions=["完成四期", "连续三次失败时暂停"],
    )


def _seed(tmp_path: Path, *, approvals: list[bool] | None = None):
    config = _config(tmp_path)
    store = SupervisorStore(config.supervisor.root_dir)
    goal = _goal()
    plan, project = LongHorizonPlanner().create(goal, testing=True)
    approvals = approvals or [True, False, False, False]
    for index, approved in enumerate(approvals):
        run = project.planned_runs[index]
        run.approval_status = "approved" if approved else "pending"
        run.approved_by = "human:test" if approved else None
    store.save_goal(goal)
    store.save_plan(plan)
    store.save_project(project)
    return config, store, goal, plan, project


def test_goal_schema() -> None:
    goal = _goal()
    assert goal.success_metrics[0].measurement_source == "run_state"
    with pytest.raises(ValueError, match="target_date"):
        Goal.model_validate({**goal.model_dump(), "target_date": goal.start_date - timedelta(days=1)})


def test_goal_decomposition() -> None:
    objectives = GoalDecomposer(max_depth=3, max_children=8).decompose(_goal())
    assert len(objectives) == 4
    assert all(item.owner_component for item in objectives)
    assert objectives[-1].depends_on


def test_goal_max_depth() -> None:
    with pytest.raises(ValueError, match="max_depth"):
        GoalDecomposer(max_depth=1).decompose(_goal(), depth=2)
    assert len(GoalDecomposer(max_children=2).decompose(_goal())) == 2


def test_long_horizon_plan() -> None:
    plan, project = LongHorizonPlanner().create(_goal(), testing=True)
    assert plan.horizon_days == 30
    assert len(plan.review_points) == 4
    assert plan.projects == [project.project_id]
    assert plan.resource_budget.max_runs == 4


def test_project_schema() -> None:
    _, project = LongHorizonPlanner().create(_goal(), testing=True)
    parsed = ContentProject.model_validate(project.model_dump())
    assert len(parsed.planned_runs) == 4
    assert parsed.planned_runs[1].depends_on == [parsed.planned_runs[0].planned_run_id]


def test_dependency_cycle_detection() -> None:
    graph = DependencyGraph()
    graph.add(DependencyEdge(source_id="b", depends_on_id="a", kind="run", reason="a first"))
    with pytest.raises(ValueError, match="循环依赖"):
        graph.add(DependencyEdge(source_id="a", depends_on_id="b", kind="run", reason="b first"))


def test_blocked_item_not_dispatched(tmp_path: Path) -> None:
    config, store, _, _, project = _seed(tmp_path, approvals=[True, True, False, False])
    project.planned_runs[0].status = "blocked"
    project.planned_runs[0].blocked_reason = "provider unavailable"
    store.save_project(project)
    dispatcher = OfflineSupervisorDispatcher()
    state = asyncio.run(AutonomousSupervisor(config, dispatcher=dispatcher, store=store).tick())
    assert dispatcher.calls == []
    assert state.stage == "idle"


def test_priority_engine_breakdown() -> None:
    decision = PriorityEngine().decide(
        [
            PriorityCandidate(item_id="ready", item_type="run", goal_priority=90, dependency_ready=True, expected_value=0.8),
            PriorityCandidate(item_id="blocked", item_type="run", goal_priority=100, dependency_ready=False, expected_value=1),
        ]
    )
    assert decision.selected_item == "ready"
    assert set(decision.score_breakdown) == set(PriorityEngine.weights)
    assert next(item for item in decision.alternatives if item.item_id == "blocked").blocked is True


def test_budget_policy(tmp_path: Path) -> None:
    config = _config(tmp_path)
    policy = GovernancePolicy(config.governance, config.supervisor)
    warning = policy.evaluate_budget(BudgetUsage(runs_today=1, runs_this_week=1, active_projects=1))
    blocked = policy.evaluate_budget(BudgetUsage(runs_today=2, runs_this_week=2, active_projects=1))
    assert warning.allowed is True and warning.warning is False
    assert blocked.allowed is False and blocked.approval_required is True
    plan, _ = LongHorizonPlanner().create(_goal(), testing=True)
    plan_limited = policy.evaluate_plan_budget(plan, BudgetUsage(runs_this_week=4))
    assert plan_limited.allowed is False


def test_failed_run_pause_policy(tmp_path: Path) -> None:
    config = _config(tmp_path)
    result = GovernancePolicy(config.governance, config.supervisor).evaluate_budget(
        BudgetUsage(failed_runs=config.governance.max_failed_runs_before_pause)
    )
    assert result.allowed is False
    assert any("failed runs" in reason for reason in result.reasons)


def test_review_point_trigger(tmp_path: Path) -> None:
    _, _, goal, plan, project = _seed(tmp_path)
    plan.review_points[0].threshold = 1
    project.planned_runs[0].status = "completed"
    triggered = SupervisorMonitor().triggered_review_points(goal, plan, [project], BudgetUsage())
    assert plan.review_points[0].review_id in triggered


def test_replan_versioning(tmp_path: Path) -> None:
    config, store, goal, plan, _ = _seed(tmp_path)
    proposal = AutonomousSupervisor(config, dispatcher=OfflineSupervisorDispatcher(), store=store).propose_replan(
        goal.goal_id,
        what_changed=["provider unavailable"],
        why=["无法继续"],
        impact=["延期"],
        risks=["样本不足"],
    )
    assert proposal.source_plan_version == plan.version
    assert proposal.proposed_plan_version == plan.version + 1
    assert proposal.status == "pending"
    assert store.latest_plan_for_goal(goal.goal_id).version == plan.version


def test_supervisor_tick_action_limit(tmp_path: Path) -> None:
    config, store, _, _, _ = _seed(tmp_path, approvals=[True, False, False, False])
    config.supervisor.max_actions_per_tick = 1
    dispatcher = OfflineSupervisorDispatcher()
    state = asyncio.run(AutonomousSupervisor(config, dispatcher=dispatcher, store=store).tick())
    assert state.actions_this_tick == 1
    assert dispatcher.calls == []


def test_supervisor_dispatches_to_creator_loop(tmp_path: Path) -> None:
    config, store, _, _, project = _seed(tmp_path, approvals=[True, False, False, False])
    dispatcher = OfflineSupervisorDispatcher({project.planned_runs[0].planned_run_id: "dispatched"})
    state = asyncio.run(AutonomousSupervisor(config, dispatcher=dispatcher, store=store).tick())
    assert dispatcher.calls == [project.planned_runs[0].planned_run_id]
    assert state.dispatches_this_tick == 1
    saved = store.load_project(project.project_id)
    assert saved.planned_runs[0].creator_plan_id


def test_supervisor_does_not_bypass_approval(tmp_path: Path) -> None:
    config, store, _, _, project = _seed(tmp_path, approvals=[False, False, False, False])
    dispatcher = OfflineSupervisorDispatcher()
    state = asyncio.run(AutonomousSupervisor(config, dispatcher=dispatcher, store=store).tick())
    assert state.stage == "waiting_approval"
    assert project.planned_runs[0].planned_run_id in (state.waiting_reason or "")
    assert dispatcher.calls == []


def test_cross_run_context_selector(tmp_path: Path) -> None:
    config = _config(tmp_path)
    context = CrossRunContextSelector(config).select()
    assert context.channel_summary["status"] == "not_initialized"
    assert "full_history" not in context.model_dump()
    assert set(context.production_health) == {"recent_plan_count", "failed_stage_count", "status"}


def test_supervisor_trace(tmp_path: Path) -> None:
    config, store, _, _, _ = _seed(tmp_path, approvals=[False, False, False, False])
    service = AutonomousSupervisor(config, dispatcher=OfflineSupervisorDispatcher(), store=store)
    asyncio.run(service.tick())
    records = service.trace_store.records()
    assert any(item["event_type"] == "goal_selected" for item in records)
    assert any(item["event_type"] == "approval_required" for item in records)


def test_supervisor_tick_idempotent(tmp_path: Path) -> None:
    config, store, _, _, project = _seed(tmp_path, approvals=[True, False, False, False])
    dispatcher = OfflineSupervisorDispatcher({project.planned_runs[0].planned_run_id: "dispatched"})
    service = AutonomousSupervisor(config, dispatcher=dispatcher, store=store)
    asyncio.run(service.tick())
    asyncio.run(service.tick())
    assert dispatcher.calls == [project.planned_runs[0].planned_run_id]


def test_supervisor_qa(tmp_path: Path) -> None:
    config, store, _, _, _ = _seed(tmp_path)
    report = AutonomousSupervisor(config, dispatcher=OfflineSupervisorDispatcher(), store=store).qa()
    assert report.passed is True
    bad = _goal("goal_bad")
    bad.success_metrics = []
    bad.stop_conditions = []
    bad.budget_policy = GoalBudgetPolicy()
    store.save_goal(bad)
    failed = AutonomousSupervisor(config, dispatcher=OfflineSupervisorDispatcher(), store=store).qa()
    assert failed.passed is False
    assert failed.checks["goals_measurable"] is False


def test_goal_lifecycle_and_human_run_approval(tmp_path: Path) -> None:
    config, store, goal, _, project = _seed(tmp_path, approvals=[False, False, False, False])
    service = AutonomousSupervisor(config, dispatcher=OfflineSupervisorDispatcher(), store=store)
    assert service.set_goal_status(goal.goal_id, "paused").status == "paused"
    with pytest.raises(ValueError, match="人工"):
        service.approve_planned_run(project.planned_runs[0].planned_run_id, approved_by="system")
    approved = service.approve_planned_run(project.planned_runs[0].planned_run_id, approved_by="human:owner")
    assert approved.approval_status == "approved"


def test_creator_loop_supervisor_bridge_requires_approval(tmp_path: Path) -> None:
    config = _config(tmp_path)
    loop = CreatorLoop(config)
    with pytest.raises(RuntimeError, match="approved_by"):
        loop.create_supervised_run(
            topic="EP1 Agent 是什么",
            goal_id="goal_bridge",
            project_id="project_bridge",
            planned_run_id="planned_bridge",
            approved_by="",
            testing=True,
        )
    plan, run = loop.create_supervised_run(
        topic="EP1 Agent 是什么",
        goal_id="goal_bridge",
        project_id="project_bridge",
        planned_run_id="planned_bridge",
        approved_by="human:test",
        testing=True,
    )
    assert plan.status == "queued"
    assert run.planning_provenance["goal_id"] == "goal_bridge"
    assert run.planning_provenance["approved_by"] == "human:test"
