from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel

from alysia.core.io import atomic_write_json, load_json_with_recovery

from alysia.schemas import (
    ContentProject,
    Goal,
    LongHorizonPlan,
    Objective,
    ReplanProposal,
    SuccessMetric,
    SupervisorQAReport,
    SupervisorReview,
    SupervisorState,
)


ModelT = TypeVar("ModelT", bound=BaseModel)


def supervisor_now() -> datetime:
    return datetime.now().astimezone()


def stable_id(prefix: str, *parts: str) -> str:
    payload = "\x1f".join(parts)
    return f"{prefix}_{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:16]}"


class SupervisorStore:
    """文件型、原子写入的长期 Supervisor 状态库。"""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        for name in ("goals", "plans", "projects", "reviews", "replans"):
            (self.root / name).mkdir(parents=True, exist_ok=True)

    def save_goal(self, goal: Goal) -> Path:
        return self._save(self.root / "goals" / f"{self._safe(goal.goal_id)}.json", goal)

    def load_goal(self, goal_id: str) -> Goal:
        return self._load(self.root / "goals" / f"{self._safe(goal_id)}.json", Goal)

    def list_goals(self) -> list[Goal]:
        return self._list(self.root / "goals", Goal)

    def save_plan(self, plan: LongHorizonPlan) -> Path:
        path = self.root / "plans" / self._safe(plan.goal_id) / f"v{plan.version:04d}.{self._safe(plan.plan_id)}.json"
        return self._save(path, plan)

    def load_plan(self, plan_id: str) -> LongHorizonPlan:
        matches = list((self.root / "plans").glob(f"*/v*.{self._safe(plan_id)}.json"))
        if not matches:
            raise FileNotFoundError(f"找不到长期计划：{plan_id}")
        return self._load(matches[-1], LongHorizonPlan)

    def latest_plan_for_goal(self, goal_id: str) -> LongHorizonPlan:
        directory = self.root / "plans" / self._safe(goal_id)
        matches = sorted(directory.glob("v*.json")) if directory.is_dir() else []
        if not matches:
            raise FileNotFoundError(f"goal 没有长期计划：{goal_id}")
        return self._load(matches[-1], LongHorizonPlan)

    def list_plans(self, goal_id: str | None = None) -> list[LongHorizonPlan]:
        directory = self.root / "plans" / self._safe(goal_id) if goal_id else self.root / "plans"
        pattern = "v*.json" if goal_id else "*/v*.json"
        return [self._load(path, LongHorizonPlan) for path in sorted(directory.glob(pattern))]

    def save_project(self, project: ContentProject) -> Path:
        return self._save(self.root / "projects" / f"{self._safe(project.project_id)}.json", project)

    def load_project(self, project_id: str) -> ContentProject:
        return self._load(self.root / "projects" / f"{self._safe(project_id)}.json", ContentProject)

    def list_projects(self, goal_id: str | None = None) -> list[ContentProject]:
        projects = self._list(self.root / "projects", ContentProject)
        return [item for item in projects if goal_id is None or item.goal_id == goal_id]

    def save_review(self, review: SupervisorReview) -> Path:
        return self._save(self.root / "reviews" / f"{self._safe(review.review_id)}.json", review)

    def list_reviews(self, goal_id: str | None = None) -> list[SupervisorReview]:
        reviews = self._list(self.root / "reviews", SupervisorReview)
        return [item for item in reviews if goal_id is None or item.goal_id == goal_id]

    def save_replan(self, proposal: ReplanProposal) -> Path:
        return self._save(self.root / "replans" / f"{self._safe(proposal.proposal_id)}.json", proposal)

    def list_replans(self, goal_id: str | None = None) -> list[ReplanProposal]:
        proposals = self._list(self.root / "replans", ReplanProposal)
        return [item for item in proposals if goal_id is None or item.goal_id == goal_id]

    @property
    def state_path(self) -> Path:
        return self.root / "supervisor_state.json"

    def save_state(self, state: SupervisorState) -> Path:
        return self._save(self.state_path, state)

    def load_state(self) -> SupervisorState | None:
        return self._load_optional(self.state_path, SupervisorState)

    def save_qa(self, report: SupervisorQAReport) -> Path:
        return self._save(self.root / "supervisor_qa_report.json", report)

    @staticmethod
    def _safe(value: str) -> str:
        if not value or Path(value).name != value or not value.replace("_", "").replace("-", "").isalnum():
            raise ValueError(f"无效标识符：{value}")
        return value

    @staticmethod
    def _save(path: Path, value: BaseModel | dict[str, Any]) -> Path:
        payload = value.model_dump(mode="json") if isinstance(value, BaseModel) else value
        return atomic_write_json(path, payload, backup_count=2 if path.name == "supervisor_state.json" else 0)

    @staticmethod
    def _load(path: Path, model: type[ModelT]) -> ModelT:
        if not path.is_file():
            raise FileNotFoundError(path)
        if path.name == "supervisor_state.json":
            return load_json_with_recovery(path, validator=model.model_validate, backup_count=2)
        return model.model_validate_json(path.read_text(encoding="utf-8"))

    @classmethod
    def _load_optional(cls, path: Path, model: type[ModelT]) -> ModelT | None:
        return cls._load(path, model) if path.is_file() else None

    @classmethod
    def _list(cls, directory: Path, model: type[ModelT]) -> list[ModelT]:
        if not directory.is_dir():
            return []
        return [cls._load(path, model) for path in sorted(directory.glob("*.json"))]


class GoalDecomposer:
    """确定性有限分解；不递归调用 LLM，也不会创建无限子目标。"""

    def __init__(self, *, max_depth: int = 3, max_children: int = 8) -> None:
        if max_depth < 1 or max_children < 1:
            raise ValueError("max_depth/max_children 必须为正数")
        self.max_depth = max_depth
        self.max_children = max_children

    def decompose(self, goal: Goal, *, depth: int = 1) -> list[Objective]:
        if depth > self.max_depth:
            raise ValueError(f"goal decomposition 超过 max_depth={self.max_depth}")
        horizon_end = goal.target_date or (goal.start_date + timedelta(days=30))
        templates = self._templates(goal)
        limited = templates[: self.max_children]
        objectives: list[Objective] = []
        for index, (title, description, owner, dependencies, metric) in enumerate(limited, start=1):
            objective_id = stable_id("objective", goal.goal_id, str(depth), str(index), title)
            resolved_dependencies = [objectives[item - 1].objective_id for item in dependencies if 0 < item <= len(objectives)]
            objectives.append(
                Objective(
                    objective_id=objective_id,
                    goal_id=goal.goal_id,
                    title=title,
                    description=description,
                    owner_component=owner,
                    priority=max(0, goal.priority - index + 1),
                    depth=depth,
                    depends_on=resolved_dependencies,
                    success_metrics=[metric],
                    deadline=horizon_end,
                )
            )
        return objectives

    @staticmethod
    def _templates(goal: Goal) -> list[tuple[str, str, str, list[int], SuccessMetric]]:
        if goal.type == "content_series":
            return [
                ("建立候选选题池", "形成覆盖系列范围的候选选题。", "creator_loop", [], SuccessMetric(name="候选选题数", target=8, measurement_source="content_plan")),
                ("完成系列内容", "按前后依赖完成计划内容。", "studio_director", [1], SuccessMetric(name="完成内容数", target=4, measurement_source="run_state")),
                ("运行核心实验", "只改变一个 hook 变量并保留审批。", "operations", [1], SuccessMetric(name="完成实验数", target=1, measurement_source="channel_experiments")),
                ("完成周期复盘", "在 review point 汇总进度、偏差与风险。", "supervisor", [2, 3], SuccessMetric(name="复盘数", target=1, measurement_source="supervisor_reviews")),
            ]
        return [
            ("建立可执行计划", "将长期目标转换为有界里程碑和项目。", "supervisor", [], SuccessMetric(name="有效计划数", target=1, measurement_source="supervisor_plans")),
            ("执行首个项目", "通过 CreatorLoop 和 StudioDirector 推进已批准内容。", "creator_loop", [1], SuccessMetric(name="完成项目数", target=1, measurement_source="supervisor_projects")),
            ("阶段复盘", "依据指标决定继续、暂停或提出重规划。", "supervisor", [2], SuccessMetric(name="复盘数", target=1, measurement_source="supervisor_reviews")),
        ]


def new_goal(
    *,
    title: str,
    description: str,
    goal_type: str,
    horizon_days: int,
    success_metrics: list[SuccessMetric],
    stop_conditions: list[str],
    priority: int = 80,
) -> Goal:
    now = supervisor_now()
    goal_id = stable_id("goal", title, now.date().isoformat())
    return Goal(
        goal_id=goal_id,
        title=title,
        description=description,
        type=goal_type,
        status="active",
        priority=priority,
        created_at=now,
        updated_at=now,
        start_date=now.date(),
        target_date=now.date() + timedelta(days=horizon_days),
        success_metrics=success_metrics,
        constraints=["保留 Human Approval Gate", "不得自动修改源码或身份使命"],
        stop_conditions=stop_conditions,
    )
