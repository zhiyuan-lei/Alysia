from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from alysia.schemas import (
    ContentProject,
    DependencyEdge,
    Goal,
    LongHorizonPlan,
    Milestone,
    PlannedRun,
    PriorityAlternative,
    PriorityCandidate,
    PriorityDecision,
    ResourceBudget,
    ReviewPoint,
    RiskRegisterItem,
)
from alysia.supervisor.goals import GoalDecomposer, stable_id, supervisor_now


class DependencyGraph:
    def __init__(self, edges: list[DependencyEdge] | None = None) -> None:
        self.edges = list(edges or [])

    def add(self, edge: DependencyEdge) -> None:
        candidate = self.edges + [edge]
        graph = DependencyGraph(candidate)
        cycle = graph.find_cycle()
        if cycle:
            raise ValueError("检测到循环依赖：" + " -> ".join(cycle))
        self.edges.append(edge)

    def find_cycle(self) -> list[str]:
        dependencies: dict[str, list[str]] = defaultdict(list)
        nodes: set[str] = set()
        for edge in self.edges:
            dependencies[edge.source_id].append(edge.depends_on_id)
            nodes.update((edge.source_id, edge.depends_on_id))
        visiting: set[str] = set()
        visited: set[str] = set()
        path: list[str] = []

        def visit(node: str) -> list[str] | None:
            if node in visiting:
                start = path.index(node)
                return path[start:] + [node]
            if node in visited:
                return None
            visiting.add(node)
            path.append(node)
            for dependency in dependencies[node]:
                found = visit(dependency)
                if found:
                    return found
            path.pop()
            visiting.remove(node)
            visited.add(node)
            return None

        for node in sorted(nodes):
            found = visit(node)
            if found:
                return found
        return []

    def blockers(self, item_id: str, statuses: dict[str, str]) -> list[str]:
        blockers = []
        for edge in self.edges:
            if edge.source_id != item_id:
                continue
            status = statuses.get(edge.depends_on_id, "missing")
            if status != "completed":
                blockers.append(f"{edge.depends_on_id}={status}：{edge.reason}")
        return blockers


class LongHorizonPlanner:
    def __init__(self, *, max_depth: int = 3, max_children: int = 8) -> None:
        self.decomposer = GoalDecomposer(max_depth=max_depth, max_children=max_children)

    def create(self, goal: Goal, *, topics: list[str] | None = None, testing: bool = False) -> tuple[LongHorizonPlan, ContentProject]:
        now = supervisor_now()
        objectives = self.decomposer.decompose(goal)
        horizon = max(1, ((goal.target_date or goal.start_date) - goal.start_date).days)
        topics = topics or self._default_topics(goal)
        project_id = stable_id("project", goal.goal_id, goal.title)
        experiment_id = stable_id("experiment", goal.goal_id, "hook-8s")
        planned_runs: list[PlannedRun] = []
        for index, topic in enumerate(topics[: self.decomposer.max_children], start=1):
            run_id = stable_id("plannedrun", project_id, str(index), topic)
            planned_runs.append(
                PlannedRun(
                    planned_run_id=run_id,
                    project_id=project_id,
                    topic=topic,
                    sequence=index,
                    depends_on=[planned_runs[-1].planned_run_id] if planned_runs else [],
                    linked_experiment_id=experiment_id,
                    approval_status="pending",
                    expected_value=max(0.4, 0.9 - ((index - 1) * 0.05)),
                    resource_cost=0.45,
                    risk=0.2,
                    deadline=goal.start_date + timedelta(days=min(horizon, index * max(1, horizon // max(1, len(topics))))),
                    testing=testing,
                )
            )
        project = ContentProject(
            project_id=project_id,
            goal_id=goal.goal_id,
            name=goal.title.replace("30天内完成一个", "").strip("。 ") or "内容系列",
            theme=goal.description,
            planned_runs=planned_runs,
            experiment_refs=[experiment_id],
            status="active" if goal.status == "active" else "planned",
            deadline=goal.target_date,
            created_at=now,
            updated_at=now,
        )
        milestones = [
            Milestone(
                milestone_id=stable_id("milestone", objective.objective_id),
                goal_id=goal.goal_id,
                title=objective.title,
                owner_component=objective.owner_component,
                depends_on=[stable_id("milestone", item) for item in objective.depends_on],
                objective_ids=[objective.objective_id],
                planned_date=objective.deadline,
                expected_value=0.8,
                resource_cost=0.35,
                risk=0.15,
            )
            for objective in objectives
        ]
        dependencies: list[DependencyEdge] = []
        for run in planned_runs:
            for dependency in run.depends_on:
                dependencies.append(
                    DependencyEdge(
                        source_id=run.planned_run_id,
                        depends_on_id=dependency,
                        kind="run",
                        reason="系列内容按顺序发布，前一集需先完成。",
                    )
                )
        for milestone in milestones:
            for dependency in milestone.depends_on:
                dependencies.append(
                    DependencyEdge(
                        source_id=milestone.milestone_id,
                        depends_on_id=dependency,
                        kind="milestone",
                        reason="上游里程碑未完成。",
                    )
                )
        graph = DependencyGraph(dependencies)
        if graph.find_cycle():
            raise ValueError("长期计划存在循环依赖")
        plan_id = stable_id("lhplan", goal.goal_id, "v1")
        plan = LongHorizonPlan(
            plan_id=plan_id,
            goal_id=goal.goal_id,
            horizon_days=horizon,
            milestones=milestones,
            projects=[project_id],
            dependencies=dependencies,
            review_points=[
                ReviewPoint(review_id=stable_id("reviewpoint", plan_id, "runs-3"), trigger_type="runs_completed", threshold=3),
                ReviewPoint(review_id=stable_id("reviewpoint", plan_id, "days-7"), trigger_type="days_elapsed", threshold=7),
                ReviewPoint(review_id=stable_id("reviewpoint", plan_id, "experiment"), trigger_type="experiment_completed", threshold=1),
                ReviewPoint(review_id=stable_id("reviewpoint", plan_id, "budget-80"), trigger_type="budget_ratio", threshold=0.8),
            ],
            resource_budget=ResourceBudget(
                max_runs=goal.budget_policy.max_runs or len(planned_runs),
                max_cloud_cost=goal.budget_policy.max_cloud_cost,
                currency=goal.budget_policy.currency,
            ),
            risk_register=[
                RiskRegisterItem(
                    risk_id=stable_id("risk", plan_id, "provider"),
                    description="关键 provider 不可用导致计划延期",
                    probability=0.35,
                    impact=0.6,
                    mitigation="暂停受影响 run，保留已完成产物并提交重规划提案。",
                ),
                RiskRegisterItem(
                    risk_id=stable_id("risk", plan_id, "quality"),
                    description="系列节奏压缩导致质量下降",
                    probability=0.3,
                    impact=0.7,
                    mitigation="在 review point 检查 QA 与预算，不以突破审批换取进度。",
                ),
            ],
            status="active" if goal.status == "active" else "draft",
            created_at=now,
            updated_at=now,
        )
        return plan, project

    @staticmethod
    def _default_topics(goal: Goal) -> list[str]:
        if "AI Agent" in goal.title or goal.type == "content_series":
            return [
                "EP1：Agent 是什么",
                "EP2：Memory 为什么重要",
                "EP3：Multi-Agent 的协作问题",
                "EP4：从 Agent 到可靠自主系统",
            ]
        return [f"{goal.title}：第一阶段", f"{goal.title}：验证", f"{goal.title}：复盘"]


class PriorityEngine:
    """透明加权规则；依赖未就绪的候选不会入选。"""

    weights = {
        "goal_priority": 0.25,
        "deadline_urgency": 0.20,
        "dependency_readiness": 0.20,
        "expected_value": 0.18,
        "experiment_importance": 0.10,
        "resource_cost": -0.04,
        "risk": -0.03,
    }

    def decide(self, candidates: list[PriorityCandidate], *, today: date | None = None) -> PriorityDecision:
        today = today or supervisor_now().date()
        scored: list[tuple[PriorityCandidate, float, dict[str, float]]] = []
        alternatives: list[PriorityAlternative] = []
        for candidate in candidates:
            urgency = self._urgency(candidate.deadline, today)
            raw = {
                "goal_priority": (candidate.goal_priority / 100) * self.weights["goal_priority"],
                "deadline_urgency": urgency * self.weights["deadline_urgency"],
                "dependency_readiness": (1.0 if candidate.dependency_ready else 0.0) * self.weights["dependency_readiness"],
                "expected_value": candidate.expected_value * self.weights["expected_value"],
                "experiment_importance": candidate.experiment_importance * self.weights["experiment_importance"],
                "resource_cost": candidate.resource_cost * self.weights["resource_cost"],
                "risk": candidate.risk * self.weights["risk"],
            }
            score = round(sum(raw.values()) * 100, 4)
            alternatives.append(PriorityAlternative(item_id=candidate.item_id, score=score, blocked=not candidate.dependency_ready))
            if candidate.dependency_ready:
                scored.append((candidate, score, raw))
        alternatives.sort(key=lambda item: (-item.score, item.item_id))
        if not scored:
            return PriorityDecision(selected_item=None, alternatives=alternatives, rationale="所有候选均被依赖阻塞或没有可执行候选。")
        selected, score, breakdown = sorted(scored, key=lambda item: (-item[1], item[0].item_id))[0]
        return PriorityDecision(
            selected_item=selected.item_id,
            score=score,
            score_breakdown={key: round(value * 100, 4) for key, value in breakdown.items()},
            alternatives=alternatives,
            rationale=f"选择 {selected.item_id}：依赖已就绪，透明加权总分 {score:.2f}。",
        )

    @staticmethod
    def _urgency(deadline: date | None, today: date) -> float:
        if deadline is None:
            return 0.25
        days = (deadline - today).days
        if days <= 0:
            return 1.0
        return max(0.0, min(1.0, 1 - (days / 30)))

