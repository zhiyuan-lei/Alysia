from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from typing import Any

from alysia.core.config import AlysiaConfig
from alysia.schemas import (
    BudgetUsage,
    Goal,
    LongHorizonPlan,
    PlannedRun,
    PriorityCandidate,
    PriorityDecision,
    ReplanProposal,
    SupervisorQAReport,
    SupervisorReview,
    SupervisorState,
    SupervisorTraceEvent,
)
from alysia.supervisor.goals import SupervisorStore, stable_id, supervisor_now
from alysia.supervisor.monitor import CrossRunContextSelector, Replanner, SupervisorMonitor, SupervisorQA
from alysia.supervisor.planner import DependencyGraph, PriorityEngine
from alysia.supervisor.policy import GovernancePolicy
from alysia.supervisor.scheduler import CreatorLoopStudioDispatcher, SupervisorDispatcher
from alysia.supervisor.trace import SupervisorTraceStore


class AutonomousSupervisor:
    """长期目标总控；不直接调用 Research/Writer/Render/Publisher。"""

    def __init__(
        self,
        config: AlysiaConfig,
        *,
        dispatcher: SupervisorDispatcher | None = None,
        store: SupervisorStore | None = None,
    ) -> None:
        self.config = config
        self.store = store or SupervisorStore(config.supervisor.root_dir)
        self.trace_store = SupervisorTraceStore(self.store.root)
        self.dispatcher = dispatcher or CreatorLoopStudioDispatcher(config)
        self.priority = PriorityEngine()
        self.policy = GovernancePolicy(config.governance, config.supervisor)
        self.monitor = SupervisorMonitor()

    def knowledge_readiness(self, topic: str, *, run_id: str | None = None) -> dict[str, Any]:
        """只评估/登记知识阻塞；Supervisor 不直接执行 ResearchAgent。"""
        from alysia.knowledge import KnowledgeService

        service = KnowledgeService(self.config)
        context = service.context.select(topic, role="supervisor")
        open_gaps = [
            item for item in service.store.list_gaps()
            if item.status in {"open", "researching"}
            and (topic in item.affected_topics or (run_id and run_id in item.affected_runs))
        ]
        blocked = bool(open_gaps) or not context.claims
        gap_id = None
        if blocked and not open_gaps:
            gap = service.gaps.create(
                f"为主题“{topic}”补充可验证且足够新鲜的事实依据",
                affected_topics=[topic],
                affected_runs=[run_id] if run_id else [],
                urgency="high",
                required_source_types=["official", "primary", "academic"],
            )
            gap_id = gap.gap_id
        return {
            "topic": topic,
            "ready": not blocked,
            "blocked": blocked,
            "claim_refs": [item.claim_id for item in context.claims],
            "warnings": context.warnings,
            "knowledge_gap_ids": [item.gap_id for item in open_gaps] + ([gap_id] if gap_id else []),
            "dispatch": False,
        }

    async def tick(self, *, usage: BudgetUsage | None = None) -> SupervisorState:
        now = supervisor_now()
        state = self.store.load_state() or SupervisorState(updated_at=now)
        state.actions_this_tick = 0
        state.dispatches_this_tick = 0
        if not self.config.supervisor.enabled:
            state.stage = "paused"
            state.waiting_reason = "supervisor.enabled=false"
            state.updated_at = now
            return self.store_and_return(state)

        goals = [item for item in self.store.list_goals() if item.status == "active"]
        digest = self._input_digest(goals, self.store.list_plans(), self.store.list_projects(), usage)
        tick_id = stable_id("tick", now.isoformat(), digest)
        if state.last_input_digest == digest and state.stage in {"idle", "waiting_approval", "paused"}:
            state.last_tick_id = tick_id
            state.updated_at = now
            return self.store_and_return(state)

        state.last_tick_id = tick_id
        state.last_input_digest = digest
        if not self._advance(state, "evaluate_goals"):
            return self.store_and_return(state)
        if not goals:
            state.stage = "idle"
            state.waiting_reason = "没有 active goal"
            self._trace(state, "no_active_goal", "没有可评估的 active goal")
            return self.store_and_return(state)

        goal_decision = self._select_goal(goals)
        selected_goal = next(item for item in goals if item.goal_id == goal_decision.selected_item)
        state.active_goal_id = selected_goal.goal_id
        if not self._advance(state, "select_priority"):
            return self.store_and_return(state)
        self._trace(
            state,
            "goal_selected",
            f"选择 goal {selected_goal.goal_id}",
            rationale=goal_decision.rationale,
            metadata={"score_breakdown": goal_decision.score_breakdown},
        )
        try:
            plan = self.store.latest_plan_for_goal(selected_goal.goal_id)
        except FileNotFoundError:
            selected_goal.status = "blocked"
            selected_goal.updated_at = now
            self.store.save_goal(selected_goal)
            state.stage = "paused"
            state.waiting_reason = "active goal 缺少 LongHorizonPlan"
            self._trace(state, "plan_missing", state.waiting_reason)
            return self.store_and_return(state)
        state.active_plan_id = plan.plan_id
        projects = self.store.list_projects(selected_goal.goal_id)
        effective_usage = usage or self._usage(projects)
        budget = self.policy.evaluate_budget(effective_usage)
        plan_budget = self.policy.evaluate_plan_budget(plan, effective_usage)
        if not budget.allowed or not plan_budget.allowed:
            state.stage = "waiting_approval"
            state.waiting_reason = "; ".join(budget.reasons + plan_budget.reasons)
            self._trace(
                state,
                "budget_pause",
                "预算或配额限制触发暂停并要求人工批准",
                metadata={
                    "governance": budget.model_dump(mode="json"),
                    "plan": plan_budget.model_dump(mode="json"),
                },
            )
            return self.store_and_return(state)

        state.stage = "check_dependencies"
        state.updated_at = supervisor_now()
        self.store.save_state(state)
        triggered = self.monitor.triggered_review_points(selected_goal, plan, projects, effective_usage)
        if triggered:
            review = self.review(selected_goal.goal_id, usage=effective_usage)
            completed_at = supervisor_now()
            for point in plan.review_points:
                if point.review_id in triggered:
                    point.triggered = True
                    point.triggered_at = point.triggered_at or completed_at
                    point.completed_at = completed_at
            plan.updated_at = completed_at
            self.store.save_plan(plan)
            self._trace(
                state,
                "review_triggered",
                f"触发 review points：{', '.join(triggered)}",
                metadata={"review_id": review.review_id, "recommendation": review.recommendation},
            )
            if review.recommendation in {"pause", "replan"}:
                state.stage = "waiting_approval" if review.recommendation == "replan" else "paused"
                state.waiting_reason = f"review recommendation={review.recommendation}"
                return self.store_and_return(state)

        candidates, blocker_map = self._run_candidates(selected_goal, plan, projects)
        decision = self.priority.decide(candidates)
        self._trace(
            state,
            "priority_decision",
            decision.rationale,
            selected_item_id=decision.selected_item,
            metadata={
                "score_breakdown": decision.score_breakdown,
                "alternatives": [item.model_dump(mode="json") for item in decision.alternatives],
                "blockers": blocker_map,
            },
        )
        if decision.selected_item is None:
            state.stage = "idle"
            state.waiting_reason = "没有依赖就绪的 planned run"
            return self.store_and_return(state)

        state.selected_item_id = decision.selected_item
        state.stage = "plan_action"
        state.updated_at = supervisor_now()
        self.store.save_state(state)
        project, planned_run = self._find_run(projects, decision.selected_item)
        if planned_run.approval_status != "approved" or not planned_run.approved_by:
            state.stage = "waiting_approval"
            state.waiting_reason = f"{planned_run.planned_run_id} 需要人工内容批准"
            self._trace(state, "approval_required", state.waiting_reason, project_id=project.project_id)
            return self.store_and_return(state)
        if state.dispatches_this_tick >= self.config.supervisor.max_dispatches_per_tick:
            state.stage = "idle"
            state.waiting_reason = "达到 max_dispatches_per_tick"
            return self.store_and_return(state)

        if not self._advance(state, "dispatch"):
            return self.store_and_return(state)
        result = await self.dispatcher.dispatch(selected_goal.goal_id, planned_run)
        state.dispatches_this_tick += 1 if result.accepted else 0
        planned_run.run_id = result.run_id
        planned_run.creator_plan_id = result.creator_plan_id
        if result.status == "completed":
            planned_run.status = "completed"
        elif result.status == "dispatched":
            planned_run.status = "dispatched"
        elif result.status in {"blocked", "failed"}:
            planned_run.status = "blocked"
            planned_run.blocked_reason = result.reason
        elif result.status == "waiting_approval":
            state.stage = "waiting_approval"
            state.waiting_reason = result.reason
        project.progress = self._project_progress(project)
        project.updated_at = supervisor_now()
        self.store.save_project(project)
        self._trace(
            state,
            "dispatch_result",
            result.reason,
            project_id=project.project_id,
            run_id=result.run_id,
            selected_item_id=planned_run.planned_run_id,
            metadata={"status": result.status, "creator_plan_id": result.creator_plan_id},
        )
        if state.stage != "waiting_approval":
            state.stage = "monitor"
            state.stage = "idle"
            state.waiting_reason = None
        return self.store_and_return(state)

    def status(self) -> dict[str, Any]:
        state = self.store.load_state() or SupervisorState(updated_at=supervisor_now())
        return {
            "state": state.model_dump(mode="json"),
            "active_goals": len([item for item in self.store.list_goals() if item.status == "active"]),
            "plans": len(self.store.list_plans()),
            "projects": len(self.store.list_projects()),
            "trace_events": len(self.trace_store.records()),
        }

    def set_goal_status(self, goal_id: str, status: str) -> Goal:
        if status not in {"draft", "active", "paused", "completed", "cancelled", "blocked"}:
            raise ValueError(f"不支持的 goal status：{status}")
        goal = self.store.load_goal(goal_id)
        goal.status = status
        goal.updated_at = supervisor_now()
        self.store.save_goal(goal)
        return goal

    def approve_planned_run(self, planned_run_id: str, *, approved_by: str) -> PlannedRun:
        if not approved_by.strip() or approved_by.lower().startswith(("alysia", "supervisor", "system", "agent")):
            raise ValueError("planned run 必须由可识别的人工审核者批准")
        for project in self.store.list_projects():
            for run in project.planned_runs:
                if run.planned_run_id != planned_run_id:
                    continue
                run.approval_status = "approved"
                run.approved_by = approved_by
                project.updated_at = supervisor_now()
                self.store.save_project(project)
                return run
        raise KeyError(planned_run_id)

    def blockers(self, goal_id: str | None = None) -> dict[str, list[str]]:
        goals = [item for item in self.store.list_goals() if goal_id is None or item.goal_id == goal_id]
        result: dict[str, list[str]] = {}
        for goal in goals:
            try:
                plan = self.store.latest_plan_for_goal(goal.goal_id)
            except FileNotFoundError:
                result[goal.goal_id] = ["缺少 LongHorizonPlan"]
                continue
            projects = self.store.list_projects(goal.goal_id)
            statuses = self._statuses(plan, projects)
            graph = DependencyGraph(plan.dependencies)
            for project in projects:
                for run in project.planned_runs:
                    reasons = graph.blockers(run.planned_run_id, statuses)
                    if run.status == "blocked" and run.blocked_reason:
                        reasons.append(run.blocked_reason)
                    if run.approval_status != "approved":
                        reasons.append("缺少人工内容批准")
                    if reasons:
                        result[run.planned_run_id] = reasons
        return result

    def review(self, goal_id: str, *, usage: BudgetUsage | None = None) -> SupervisorReview:
        goal = self.store.load_goal(goal_id)
        plan = self.store.latest_plan_for_goal(goal_id)
        projects = self.store.list_projects(goal_id)
        review = self.monitor.review(goal, plan, projects, usage or self._usage(projects))
        self.store.save_review(review)
        return review

    def propose_replan(
        self,
        goal_id: str,
        *,
        what_changed: list[str],
        why: list[str],
        impact: list[str],
        risks: list[str],
    ) -> ReplanProposal:
        goal = self.store.load_goal(goal_id)
        plan = self.store.latest_plan_for_goal(goal_id)
        proposal = Replanner().propose(
            goal,
            plan,
            what_changed=what_changed,
            why=why,
            impact=impact,
            risks=risks,
        )
        self.store.save_replan(proposal)
        return proposal

    def qa(self) -> SupervisorQAReport:
        report = SupervisorQA(self.config).run(
            self.store.list_goals(),
            self.store.list_plans(),
            self.store.list_projects(),
        )
        self.store.save_qa(report)
        return report

    def context(self) -> dict[str, Any]:
        return CrossRunContextSelector(self.config).select().model_dump(mode="json")

    def simulation_recommendation(self, scenario_id: str, *, service=None) -> dict[str, Any]:
        """重大 action 前的可选决策辅助；永远不直接 dispatch 模拟步骤。"""
        if service is None:
            from alysia.simulation import SimulationService

            service = SimulationService(self.config)
        payload = service.supervisor_recommendation(scenario_id)
        return {
            "comparison": payload["comparison"].model_dump(mode="json"),
            "decision": payload["decision"].model_dump(mode="json"),
            "agent_steps_executed": False,
            "dispatch_performed": False,
        }

    def _select_goal(self, goals: list[Goal]) -> PriorityDecision:
        return self.priority.decide(
            [
                PriorityCandidate(
                    item_id=goal.goal_id,
                    item_type="goal",
                    goal_priority=goal.priority,
                    deadline=goal.target_date,
                    expected_value=0.8,
                    resource_cost=0.2,
                    risk=0.2,
                )
                for goal in goals
            ]
        )

    def _run_candidates(self, goal: Goal, plan: LongHorizonPlan, projects: list) -> tuple[list[PriorityCandidate], dict[str, list[str]]]:
        statuses = self._statuses(plan, projects)
        graph = DependencyGraph(plan.dependencies)
        candidates: list[PriorityCandidate] = []
        blockers: dict[str, list[str]] = {}
        for project in projects:
            if project.status not in {"planned", "active"}:
                continue
            for run in project.planned_runs:
                if run.status not in {"planned", "ready"}:
                    continue
                reasons = graph.blockers(run.planned_run_id, statuses)
                if reasons:
                    blockers[run.planned_run_id] = reasons
                candidates.append(
                    PriorityCandidate(
                        item_id=run.planned_run_id,
                        item_type="run",
                        goal_priority=goal.priority,
                        deadline=run.deadline,
                        dependency_ready=not reasons,
                        expected_value=run.expected_value,
                        experiment_importance=0.8 if run.linked_experiment_id else 0,
                        resource_cost=run.resource_cost,
                        risk=run.risk,
                    )
                )
        return candidates, blockers

    @staticmethod
    def _statuses(plan: LongHorizonPlan, projects: list) -> dict[str, str]:
        statuses = {item.milestone_id: item.status for item in plan.milestones}
        for project in projects:
            statuses[project.project_id] = project.status
            statuses.update({run.planned_run_id: run.status for run in project.planned_runs})
        return statuses

    @staticmethod
    def _find_run(projects: list, planned_run_id: str):
        for project in projects:
            for run in project.planned_runs:
                if run.planned_run_id == planned_run_id:
                    return project, run
        raise KeyError(planned_run_id)

    @staticmethod
    def _project_progress(project) -> float:
        if not project.planned_runs:
            return 0
        return sum(1 for item in project.planned_runs if item.status == "completed") / len(project.planned_runs)

    @staticmethod
    def _usage(projects: list) -> BudgetUsage:
        dispatched = sum(
            1 for project in projects for run in project.planned_runs if run.status in {"dispatched", "completed", "blocked"}
        )
        failed = sum(
            1 for project in projects for run in project.planned_runs if run.status == "blocked" and run.blocked_reason
        )
        active = sum(1 for project in projects if project.status == "active")
        return BudgetUsage(
            runs_today=dispatched,
            runs_this_week=dispatched,
            failed_runs=failed,
            active_projects=active,
        )

    def _advance(self, state: SupervisorState, stage: str) -> bool:
        if state.actions_this_tick >= self.config.supervisor.max_actions_per_tick:
            state.stage = "idle"
            state.waiting_reason = "达到 max_actions_per_tick"
            return False
        state.stage = stage
        state.actions_this_tick += 1
        state.updated_at = supervisor_now()
        self.store.save_state(state)
        return True

    def _trace(
        self,
        state: SupervisorState,
        event_type: str,
        summary: str,
        *,
        rationale: str | None = None,
        project_id: str | None = None,
        run_id: str | None = None,
        selected_item_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        now = supervisor_now()
        self.trace_store.append(
            SupervisorTraceEvent(
                event_id=stable_id("supervisortrace", state.last_tick_id or "none", event_type, now.isoformat()),
                tick_id=state.last_tick_id or "none",
                event_type=event_type,
                goal_id=state.active_goal_id,
                plan_id=state.active_plan_id,
                project_id=project_id,
                run_id=run_id,
                selected_item_id=selected_item_id or state.selected_item_id,
                summary=summary,
                rationale=rationale,
                metadata=metadata or {},
                created_at=now,
            )
        )

    def store_and_return(self, state: SupervisorState) -> SupervisorState:
        state.updated_at = supervisor_now()
        self.store.save_state(state)
        return state

    @staticmethod
    def _input_digest(goals: list, plans: list, projects: list, usage: BudgetUsage | None) -> str:
        payload = {
            "goals": [item.model_dump(mode="json") for item in goals],
            "plans": [item.model_dump(mode="json") for item in plans],
            "projects": [item.model_dump(mode="json") for item in projects],
            "usage": usage.model_dump(mode="json") if usage else None,
        }
        return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()
