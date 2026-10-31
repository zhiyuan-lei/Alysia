from __future__ import annotations

from alysia.core.config import GovernanceConfig, SupervisorConfig
from alysia.schemas import BudgetDecision, BudgetUsage, Goal, LongHorizonPlan


class GovernancePolicy:
    def __init__(self, governance: GovernanceConfig, supervisor: SupervisorConfig) -> None:
        self.governance = governance
        self.supervisor = supervisor

    def evaluate_budget(self, usage: BudgetUsage) -> BudgetDecision:
        hard: list[str] = []
        warnings: list[str] = []
        checks = [
            ("daily runs", usage.runs_today, self.governance.max_runs_per_day),
            ("weekly runs", usage.runs_this_week, self.governance.max_runs_per_week),
            ("active projects", usage.active_projects, self.supervisor.max_active_projects),
        ]
        for label, current, maximum in checks:
            if current >= maximum:
                hard.append(f"{label} 达到限制 {current}/{maximum}")
            elif maximum and current / maximum >= self.governance.budget_warning_ratio:
                warnings.append(f"{label} 达到预警比例 {current}/{maximum}")
        self._check_cost(
            "daily cloud cost",
            usage.cloud_cost_today,
            self.governance.max_cloud_cost_per_day,
            hard,
            warnings,
        )
        self._check_cost(
            "weekly cloud cost",
            usage.cloud_cost_this_week,
            self.governance.max_cloud_cost_per_week,
            hard,
            warnings,
        )
        if usage.failed_runs >= self.governance.max_failed_runs_before_pause:
            hard.append(
                f"failed runs 达到暂停阈值 {usage.failed_runs}/{self.governance.max_failed_runs_before_pause}"
            )
        return BudgetDecision(
            allowed=not hard,
            warning=bool(warnings),
            approval_required=bool(hard),
            reasons=hard + warnings,
            usage=usage,
        )

    def approval_reasons(self, goal: Goal, plan: LongHorizonPlan, *, major_replan: bool = False) -> list[str]:
        reasons: list[str] = []
        if goal.status != "active" or plan.status != "active":
            reasons.append(f"goal/plan 当前不可执行：{goal.status}/{plan.status}")
        if major_replan and (
            self.supervisor.require_approval_for_major_replan
            or goal.approval_policy.require_major_replan_approval
        ):
            reasons.append("重大 replan 必须人工批准")
        return reasons

    def evaluate_plan_budget(self, plan: LongHorizonPlan, usage: BudgetUsage) -> BudgetDecision:
        hard: list[str] = []
        warnings: list[str] = []
        maximum_runs = plan.resource_budget.max_runs
        if maximum_runs is not None:
            if usage.runs_this_week >= maximum_runs:
                hard.append(f"plan runs 达到限制 {usage.runs_this_week}/{maximum_runs}")
            elif maximum_runs and usage.runs_this_week / maximum_runs >= self.governance.budget_warning_ratio:
                warnings.append(f"plan runs 达到预警比例 {usage.runs_this_week}/{maximum_runs}")
        self._check_cost(
            "plan cloud cost",
            usage.cloud_cost_this_week,
            plan.resource_budget.max_cloud_cost,
            hard,
            warnings,
        )
        return BudgetDecision(
            allowed=not hard,
            warning=bool(warnings),
            approval_required=bool(hard),
            reasons=hard + warnings,
            usage=usage,
        )

    def _check_cost(
        self,
        label: str,
        current: float | None,
        maximum: float | None,
        hard: list[str],
        warnings: list[str],
    ) -> None:
        if maximum is None:
            return
        if current is None:
            warnings.append(f"{label} 未知，不能按 0 处理")
            return
        if current > maximum:
            hard.append(f"{label} 超过限制 {current:.2f}/{maximum:.2f}")
        elif maximum and current / maximum >= self.governance.budget_warning_ratio:
            warnings.append(f"{label} 达到预警比例 {current:.2f}/{maximum:.2f}")
