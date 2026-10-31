from __future__ import annotations

from alysia.core.config import AlysiaConfig
from alysia.schemas import BudgetUsage, DependencyEdge, Goal, GoalBudgetPolicy, SuccessMetric
from alysia.supervisor.goals import SupervisorStore, supervisor_now
from alysia.supervisor.planner import LongHorizonPlanner
from alysia.supervisor.scheduler import OfflineSupervisorDispatcher
from alysia.supervisor.supervisor import AutonomousSupervisor


DEMO_GOAL_ID = "demo_goal"
DEMO_PLAN_ID = "demo_plan_v1"
DEMO_PROJECT_ID = "demo_project_ai_agent"


def initialize_demo(config: AlysiaConfig) -> dict:
    store = SupervisorStore(config.supervisor.root_dir)
    now = supervisor_now()
    goal = Goal(
        goal_id=DEMO_GOAL_ID,
        title="30天内完成一个 AI Agent 基础四期系列",
        description="完成四期有前后依赖的 AI Agent 科普内容，并验证 8 秒内进入核心问题的 hook 策略。",
        type="content_series",
        status="active",
        priority=90,
        created_at=now,
        updated_at=now,
        start_date=now.date(),
        target_date=now.date().fromordinal(now.date().toordinal() + 30),
        success_metrics=[
            SuccessMetric(name="完成内容数", target=4, measurement_source="run_state"),
            SuccessMetric(name="完成 hook 实验数", target=1, measurement_source="channel_experiments"),
        ],
        constraints=["只允许 mock/offline", "发布和重大 replan 必须人工批准"],
        budget_policy=GoalBudgetPolicy(max_runs=4, max_cloud_cost=0, currency="CNY"),
        stop_conditions=["完成四期内容和月底复盘", "连续三次 run 失败时暂停", "预算达到硬限制时暂停"],
    )
    plan, project = LongHorizonPlanner(
        max_depth=config.supervisor.max_goal_depth,
        max_children=config.supervisor.max_children_per_goal,
    ).create(goal, testing=True)
    old_project_id = project.project_id
    project.project_id = DEMO_PROJECT_ID
    run_ids = [f"demo_run_ep{index}" for index in range(1, 5)]
    for index, run in enumerate(project.planned_runs):
        run.project_id = DEMO_PROJECT_ID
        run.planned_run_id = run_ids[index]
        run.depends_on = [run_ids[index - 1]] if index else []
        run.linked_experiment_id = "demo_experiment_hook_8s"
        run.approval_status = "approved" if index < 3 else "pending"
        run.approved_by = "human:alpha13-demo" if index < 3 else None
        run.testing = True
    project.experiment_refs = ["demo_experiment_hook_8s"]
    project.planned_runs[0].status = "completed"
    project.planned_runs[0].run_id = "mock_completed_ep1"
    project.progress = 0.25
    plan.plan_id = DEMO_PLAN_ID
    plan.projects = [DEMO_PROJECT_ID]
    plan.dependencies = [
        DependencyEdge(
            source_id=run_ids[index],
            depends_on_id=run_ids[index - 1],
            kind="run",
            reason="系列前后依赖",
        )
        for index in range(1, len(run_ids))
    ] + [edge for edge in plan.dependencies if edge.kind != "run"]
    store.save_goal(goal)
    store.save_plan(plan)
    store.save_project(project)
    return {
        "goal_id": goal.goal_id,
        "plan_id": plan.plan_id,
        "project_id": project.project_id,
        "experiment_id": project.experiment_refs[0],
        "milestones": [item.title for item in plan.milestones],
        "planned_runs": [item.planned_run_id for item in project.planned_runs],
    }


async def exercise_demo(config: AlysiaConfig) -> dict:
    ids = initialize_demo(config)
    store = SupervisorStore(config.supervisor.root_dir)
    dispatcher = OfflineSupervisorDispatcher({"demo_run_ep2": "blocked"})
    supervisor = AutonomousSupervisor(config, dispatcher=dispatcher, store=store)
    tick = await supervisor.tick(
        usage=BudgetUsage(runs_today=1, runs_this_week=1, failed_runs=0, active_projects=1)
    )
    blockers = supervisor.blockers(DEMO_GOAL_ID)
    budget_tick = await supervisor.tick(
        usage=BudgetUsage(
            runs_today=config.governance.max_runs_per_day,
            runs_this_week=config.governance.max_runs_per_week,
            cloud_cost_today=0,
            cloud_cost_this_week=0,
            failed_runs=1,
            active_projects=1,
        )
    )
    review = supervisor.review(DEMO_GOAL_ID)
    replan = supervisor.propose_replan(
        DEMO_GOAL_ID,
        what_changed=["EP2 mock 执行被阻塞", "当日 run 配额达到上限"],
        why=["验证依赖阻塞与预算治理"],
        impact=["后续 EP3/EP4 等待 EP2 处理", "当前计划不被直接覆盖"],
        risks=["延期", "实验样本不足"],
    )
    qa = supervisor.qa()
    return {
        **ids,
        "tick": tick.model_dump(mode="json"),
        "dispatch_calls": dispatcher.calls,
        "blockers": blockers,
        "budget_pause": budget_tick.model_dump(mode="json"),
        "review": review.model_dump(mode="json"),
        "replan": replan.model_dump(mode="json"),
        "qa": qa.model_dump(mode="json"),
    }
