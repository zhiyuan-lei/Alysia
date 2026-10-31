from __future__ import annotations

from typing import Protocol

from alysia.core.config import AlysiaConfig
from alysia.planning import CreatorLoop
from alysia.schemas import DispatchResult, PlannedRun
from alysia.studio.director import StudioDirector


class SupervisorDispatcher(Protocol):
    async def dispatch(self, goal_id: str, planned_run: PlannedRun) -> DispatchResult: ...


class CreatorLoopStudioDispatcher:
    """唯一真实派发路径：Supervisor → CreatorLoop → StudioDirector。"""

    def __init__(self, config: AlysiaConfig) -> None:
        self.config = config
        self.loop = CreatorLoop(config)

    async def dispatch(self, goal_id: str, planned_run: PlannedRun) -> DispatchResult:
        if planned_run.approval_status != "approved" or not planned_run.approved_by:
            return DispatchResult(
                accepted=False,
                status="waiting_approval",
                reason="planned run 尚未获得显式人工批准",
            )
        plan, run = self.loop.create_supervised_run(
            topic=planned_run.topic,
            goal_id=goal_id,
            project_id=planned_run.project_id,
            planned_run_id=planned_run.planned_run_id,
            approved_by=planned_run.approved_by,
            testing=planned_run.testing,
        )
        studio = await StudioDirector(self.config).run(run.run_id)
        mapped = {
            "completed": "completed",
            "waiting_for_approval": "waiting_approval",
            "escalated": "blocked",
        }.get(studio.status, "dispatched")
        return DispatchResult(
            accepted=True,
            status=mapped,
            run_id=run.run_id,
            creator_plan_id=plan.plan_id,
            reason=f"CreatorLoop 已创建 run；StudioDirector 状态={studio.status}",
        )


class OfflineSupervisorDispatcher:
    """只用于离线测试/demo；不创建真实发布或外部通信。"""

    def __init__(self, outcomes: dict[str, str] | None = None) -> None:
        self.outcomes = outcomes or {}
        self.calls: list[str] = []

    async def dispatch(self, goal_id: str, planned_run: PlannedRun) -> DispatchResult:
        self.calls.append(planned_run.planned_run_id)
        if planned_run.approval_status != "approved" or not planned_run.approved_by:
            return DispatchResult(accepted=False, status="waiting_approval", reason="离线派发也不允许绕过人工批准")
        outcome = self.outcomes.get(planned_run.planned_run_id, "dispatched")
        if outcome not in {"dispatched", "completed", "blocked", "failed"}:
            outcome = "dispatched"
        return DispatchResult(
            accepted=True,
            status=outcome,
            run_id=f"mock_{planned_run.planned_run_id}",
            creator_plan_id=f"mock_plan_{planned_run.planned_run_id}",
            reason="offline mock dispatcher；未联网、未发布",
        )

