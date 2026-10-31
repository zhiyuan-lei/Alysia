from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from alysia.core.config import AlysiaConfig
from alysia.identity import IdentityService
from alysia.learning.memory import MemoryStore
from alysia.operations import ChannelStore
from alysia.schemas import (
    BudgetUsage,
    CrossRunContext,
    Goal,
    LongHorizonPlan,
    ReplanProposal,
    SupervisorQAReport,
    SupervisorReview,
)
from alysia.supervisor.goals import stable_id, supervisor_now
from alysia.supervisor.planner import DependencyGraph


class CrossRunContextSelector:
    """只挑选长期决策需要的摘要，不传递完整历史或大产物正文。"""

    def __init__(self, config: AlysiaConfig) -> None:
        self.config = config

    def select(self, channel_id: str | None = None) -> CrossRunContext:
        channel_id = channel_id or self.config.operations.default_channel_id
        memory_store = MemoryStore(self.config.learning.memory_dir)
        channel_store = ChannelStore(self.config.learning.memory_dir)
        channel = channel_store.load_memory(channel_id)
        lessons = [item for item in memory_store.list_lessons() if item.status == "supported"][-5:]
        strategies = [item for item in memory_store.list_strategies(channel_id) if item.status == "supported"][-5:]
        experiments = [
            item for item in channel_store.list_experiments(channel_id) if item.status in {"approved", "running"}
        ][-3:]
        identity_summary: dict = {}
        if self.config.identity.enabled:
            try:
                identity = IdentityService(self.config).ensure()
                identity_summary = {
                    "version": identity.version,
                    "creator_name": identity.creator_name,
                    "mission_statement": identity.mission_statement,
                    "target_audience": identity.target_audience,
                }
            except (OSError, ValueError):
                identity_summary = {"status": "unavailable"}
        return CrossRunContext(
            channel_id=channel_id,
            channel_summary=(
                {
                    "positioning": channel.current_positioning,
                    "content_directions": channel.content_directions[:5],
                    "published_topic_count": len(channel.published_topics),
                    "active_experiment_ids": channel.active_experiment_ids[:5],
                    "revision": channel.revision,
                }
                if channel
                else {"status": "not_initialized"}
            ),
            supported_lessons=[
                {"id": item.id, "statement": item.statement, "confidence": item.confidence}
                for item in lessons
            ],
            active_strategies=[
                {"id": item.id, "rule": item.rule, "confidence": item.confidence}
                for item in strategies
            ],
            active_experiments=[
                {"id": item.id, "hypothesis": item.hypothesis, "status": item.status}
                for item in experiments
            ],
            identity_summary=identity_summary,
            production_health=self._production_health(),
            generated_at=supervisor_now(),
        )

    def _production_health(self) -> dict:
        runs_root = self.config.runtime.runs_dir
        plan_count = 0
        failed_stage_count = 0
        for path in sorted(runs_root.glob("*/production/production_plan.json"))[-20:]:
            plan_count += 1
            metrics = path.parent / "execution_metrics.json"
            if not metrics.is_file():
                continue
            try:
                payload = json.loads(metrics.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            failed_stage_count += sum(1 for item in payload.get("stages", []) if not item.get("success", False))
        return {
            "recent_plan_count": plan_count,
            "failed_stage_count": failed_stage_count,
            "status": "degraded" if failed_stage_count else "healthy_or_unknown",
        }


class SupervisorMonitor:
    def review(self, goal: Goal, plan: LongHorizonPlan, projects: list, usage: BudgetUsage) -> SupervisorReview:
        runs = [run for project in projects for run in project.planned_runs]
        completed = sum(1 for run in runs if run.status == "completed")
        progress = completed / len(runs) if runs else 0.0
        metrics = {metric.name: metric.current_value for metric in goal.success_metrics}
        deviations: list[str] = []
        if goal.target_date and supervisor_now().date() > goal.target_date and progress < 1:
            deviations.append("已超过 target_date 但目标未完成")
        if any(run.status == "blocked" for run in runs):
            deviations.append("存在 blocked planned run")
        risks = [item.description for item in plan.risk_register if item.status == "open"]
        decisions: list[str] = []
        if usage.failed_runs:
            decisions.append("确认失败 run 的恢复或停止方案")
        if progress < 1 and deviations:
            recommendation = "replan"
            decisions.append("是否批准重规划提案")
        elif usage.runs_today >= (plan.resource_budget.max_runs or 10**9):
            recommendation = "pause"
            decisions.append("预算恢复前保持暂停")
        else:
            recommendation = "continue"
        now = supervisor_now()
        return SupervisorReview(
            review_id=stable_id("review", goal.goal_id, plan.plan_id, now.isoformat()),
            goal_id=goal.goal_id,
            plan_id=plan.plan_id,
            progress=progress,
            metrics=metrics,
            deviations=deviations,
            risks=risks,
            decisions_needed=decisions,
            recommendation=recommendation,
            created_at=now,
        )

    def triggered_review_points(self, goal: Goal, plan: LongHorizonPlan, projects: list, usage: BudgetUsage) -> list[str]:
        completed = sum(1 for project in projects for run in project.planned_runs if run.status == "completed")
        elapsed = max(0, (supervisor_now().date() - goal.start_date).days)
        experiment_completed = any(
            run.status == "completed" and run.linked_experiment_id
            for project in projects
            for run in project.planned_runs
        )
        run_budget = plan.resource_budget.max_runs
        ratio = (usage.runs_this_week / run_budget) if run_budget else 0
        triggered: list[str] = []
        for point in plan.review_points:
            if point.completed_at or point.triggered:
                continue
            condition = (
                (point.trigger_type == "runs_completed" and completed >= point.threshold)
                or (point.trigger_type == "days_elapsed" and elapsed >= point.threshold)
                or (point.trigger_type == "experiment_completed" and experiment_completed)
                or (point.trigger_type == "budget_ratio" and ratio >= point.threshold)
            )
            if condition:
                triggered.append(point.review_id)
        return triggered


class Replanner:
    def propose(
        self,
        goal: Goal,
        current: LongHorizonPlan,
        *,
        what_changed: list[str],
        why: list[str],
        impact: list[str],
        risks: list[str],
    ) -> ReplanProposal:
        new_version = current.version + 1
        new_plan = current.model_copy(
            deep=True,
            update={
                "version": new_version,
                "status": "waiting_approval",
                "updated_at": supervisor_now(),
            },
        )
        return ReplanProposal(
            proposal_id=stable_id("replan", goal.goal_id, current.plan_id, str(new_version), "|".join(why)),
            goal_id=goal.goal_id,
            source_plan_id=current.plan_id,
            source_plan_version=current.version,
            proposed_plan_version=new_version,
            what_changed=what_changed,
            why=why,
            impact=impact,
            new_plan=new_plan,
            risks=risks,
            approval_required=True,
            created_at=supervisor_now(),
        )


class SupervisorQA:
    def __init__(self, config: AlysiaConfig) -> None:
        self.config = config

    def run(self, goals: list[Goal], plans: list[LongHorizonPlan], projects: list) -> SupervisorQAReport:
        errors: list[str] = []
        warnings: list[str] = []
        checks = {
            "goals_measurable": True,
            "stop_conditions_present": True,
            "no_goal_conflicts": True,
            "dependency_acyclic": True,
            "budget_present": True,
            "approval_gates_preserved": True,
            "bounded_expansion": True,
        }
        seen_titles: dict[str, str] = {}
        for goal in goals:
            if not goal.success_metrics:
                checks["goals_measurable"] = False
                errors.append(f"{goal.goal_id} 缺少 success_metrics")
            if not goal.stop_conditions:
                checks["stop_conditions_present"] = False
                errors.append(f"{goal.goal_id} 缺少 stop_conditions")
            normalized = goal.title.strip().lower()
            if goal.status == "active" and normalized in seen_titles:
                checks["no_goal_conflicts"] = False
                errors.append(f"active goal 标题冲突：{goal.goal_id}/{seen_titles[normalized]}")
            seen_titles[normalized] = goal.goal_id
            if goal.budget_policy.max_runs is None and goal.budget_policy.max_cloud_cost is None:
                checks["budget_present"] = False
                errors.append(f"{goal.goal_id} 缺少显式 run/cost budget")
        for plan in plans:
            cycle = DependencyGraph(plan.dependencies).find_cycle()
            if cycle:
                checks["dependency_acyclic"] = False
                errors.append("循环依赖：" + " -> ".join(cycle))
            if len(plan.milestones) > self.config.supervisor.max_children_per_goal:
                checks["bounded_expansion"] = False
                errors.append(f"{plan.plan_id} milestones 超过配置上限")
        for project in projects:
            if len(project.planned_runs) > self.config.supervisor.max_children_per_goal:
                checks["bounded_expansion"] = False
                errors.append(f"{project.project_id} planned runs 超过配置上限")
            for run in project.planned_runs:
                if run.status in {"dispatched", "completed"} and run.approval_status != "approved":
                    checks["approval_gates_preserved"] = False
                    errors.append(f"{run.planned_run_id} 未批准却已派发")
        if any(goal.status == "active" and goal.target_date is None for goal in goals):
            warnings.append("存在 active goal 未设置 target_date")
        return SupervisorQAReport(
            passed=not errors,
            errors=errors,
            warnings=warnings,
            checks=checks,
            checked_goal_ids=[goal.goal_id for goal in goals],
            generated_at=supervisor_now(),
        )
