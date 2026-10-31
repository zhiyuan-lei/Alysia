from __future__ import annotations

import hashlib
from datetime import datetime

from alysia.learning.memory import MemoryStore
from alysia.operations.store import ChannelStore
from alysia.schemas import (
    ContentExperiment,
    ExperimentAssignment,
    ExperimentMetric,
    ExperimentResult,
    StrategyMemory,
    VideoPerformanceSnapshot,
)


class ExperimentManagerError(RuntimeError):
    pass


class ExperimentManager:
    def __init__(self, store: ChannelStore, memory: MemoryStore, minimum_group_size: int = 2) -> None:
        self.store = store
        self.memory = memory
        self.minimum_group_size = minimum_group_size

    def create(
        self,
        channel_id: str,
        *,
        hypothesis: str,
        variable_changed: str,
        control_variables: list[str],
        success_metrics: list[ExperimentMetric],
        linked_strategy_id: str | None = None,
    ) -> ContentExperiment:
        experiment_id = self._stable_id(channel_id, hypothesis, variable_changed)
        try:
            return self.store.load_experiment(channel_id, experiment_id)
        except FileNotFoundError:
            pass
        now = datetime.now().astimezone()
        experiment = ContentExperiment(
            id=experiment_id,
            channel_id=channel_id,
            hypothesis=hypothesis,
            variable_changed=variable_changed,
            control_variables=control_variables,
            success_metrics=success_metrics,
            linked_strategy_id=linked_strategy_id,
            created_at=now,
            updated_at=now,
        )
        self.store.save_experiment(experiment)
        return experiment

    def approve(self, channel_id: str, experiment_id: str, *, approved_by: str) -> ContentExperiment:
        if not approved_by.strip() or approved_by.casefold() in {"system", "agent", "alysia", "automation"}:
            raise ExperimentManagerError("实验必须由明确的人类审核者批准")
        experiment = self.store.load_experiment(channel_id, experiment_id)
        if experiment.status in {"completed", "cancelled"}:
            raise ExperimentManagerError("已结束实验不能重新批准")
        experiment.status = "approved"
        experiment.approved_by = approved_by.strip()
        experiment.updated_at = datetime.now().astimezone()
        self.store.save_experiment(experiment)
        return experiment

    def assign(
        self,
        channel_id: str,
        experiment_id: str,
        *,
        run_id: str,
        experiment_group: str,
        source: str,
    ) -> ContentExperiment:
        experiment = self.store.load_experiment(channel_id, experiment_id)
        if experiment.status not in {"approved", "running"}:
            raise ExperimentManagerError("只有已人工批准的实验才能分配内容")
        existing = next((item for item in experiment.assignments if item.run_id == run_id), None)
        if existing:
            if existing.experiment_group != experiment_group:
                raise ExperimentManagerError("同一 run 不能被分配到不同实验组")
            return experiment
        experiment.assignments.append(
            ExperimentAssignment(
                run_id=run_id,
                experiment_group=experiment_group,
                source=source,
            )
        )
        experiment.status = "running"
        experiment.updated_at = datetime.now().astimezone()
        self.store.save_experiment(experiment)
        return experiment

    def evaluate(
        self,
        channel_id: str,
        experiment_id: str,
        snapshots: list[VideoPerformanceSnapshot],
    ) -> ContentExperiment:
        experiment = self.store.load_experiment(channel_id, experiment_id)
        if experiment.status == "completed":
            return experiment
        if experiment.status != "running":
            raise ExperimentManagerError("实验尚未运行")
        snapshot_by_run = {item.run_id: item for item in snapshots}
        groups = {
            "control": [item for item in experiment.assignments if item.experiment_group == "control"],
            "treatment": [item for item in experiment.assignments if item.experiment_group == "treatment"],
        }
        if any(len(items) < self.minimum_group_size for items in groups.values()):
            raise ExperimentManagerError(f"每个实验组至少需要 {self.minimum_group_size} 个 run")
        if any(item.run_id not in snapshot_by_run for items in groups.values() for item in items):
            raise ExperimentManagerError("部分实验 run 尚无可比较 Analytics")
        if any(
            snapshot_by_run[item.run_id].source != item.source
            for items in groups.values()
            for item in items
        ):
            raise ExperimentManagerError("实验分配的 source 与实际 Analytics source 不一致")
        if any(
            snapshot_by_run[item.run_id].channel_id != channel_id
            for items in groups.values()
            for item in items
        ):
            raise ExperimentManagerError("实验 run 不属于当前 channel")

        metric_results: dict[str, dict[str, float | int | None]] = {}
        decisions: list[bool | None] = []
        for goal in experiment.success_metrics:
            control = self._mean_metric(groups["control"], snapshot_by_run, goal.metric)
            treatment = self._mean_metric(groups["treatment"], snapshot_by_run, goal.metric)
            relative_change = None
            met: bool | None = None
            if control is not None and treatment is not None and control != 0:
                relative_change = (treatment - control) / abs(control)
                signed_change = relative_change if goal.direction == "increase" else -relative_change
                met = signed_change >= goal.minimum_relative_change
            decisions.append(met)
            metric_results[goal.metric] = {
                "control_mean": control,
                "treatment_mean": treatment,
                "relative_change": relative_change,
                "success": None if met is None else int(met),
            }
        known = [item for item in decisions if item is not None]
        if known and all(known):
            outcome = "positive"
        elif known and not any(known):
            outcome = "negative"
        else:
            outcome = "inconclusive"
        evidence_runs = sorted({item.run_id for items in groups.values() for item in items})
        experiment.result = ExperimentResult(
            outcome=outcome,
            metric_results=metric_results,
            evidence_run_ids=evidence_runs,
            evaluated_at=datetime.now().astimezone(),
        )
        experiment.conclusion = self._conclusion(experiment, outcome)
        experiment.status = "completed"
        experiment.updated_at = datetime.now().astimezone()
        self.store.save_experiment(experiment)
        self._update_linked_strategy(experiment)
        return experiment

    def _update_linked_strategy(self, experiment: ContentExperiment) -> StrategyMemory | None:
        if not experiment.linked_strategy_id or not experiment.result:
            return None
        strategy = self.memory.show_strategy(experiment.linked_strategy_id)
        completed = [
            item
            for item in self.store.list_experiments(experiment.channel_id)
            if item.linked_strategy_id == strategy.id and item.status == "completed" and item.result
        ]
        eligible = [
            item
            for item in completed
            if all(assignment.source not in {"mock", "testing"} for assignment in item.assignments)
        ]
        positive = sum(item.result is not None and item.result.outcome == "positive" for item in eligible)
        negative = sum(item.result is not None and item.result.outcome == "negative" for item in eligible)
        strategy.evidence_experiment_ids = [item.id for item in eligible]
        strategy.evidence_metrics = {
            item.id: {
                metric: values.get("relative_change")
                for metric, values in (item.result.metric_results if item.result else {}).items()
            }
            for item in eligible
        }
        strategy.confidence = min(0.9, max(0.05, round(0.3 + positive * 0.2 - negative * 0.2, 2)))
        if positive >= 2 and strategy.confidence >= 0.6:
            strategy.status = "supported"
        elif negative >= 2 and strategy.confidence <= 0.2:
            strategy.status = "deprecated"
        else:
            strategy.status = "tentative"
        strategy.updated_at = datetime.now().astimezone()
        self.memory.save_strategy(strategy)
        return strategy

    @staticmethod
    def _mean_metric(
        assignments: list[ExperimentAssignment],
        snapshots: dict[str, VideoPerformanceSnapshot],
        metric: str,
    ) -> float | None:
        values = [
            float(value)
            for assignment in assignments
            if (value := snapshots[assignment.run_id].metrics.get(metric)) is not None
        ]
        return sum(values) / len(values) if len(values) == len(assignments) else None

    @staticmethod
    def _conclusion(experiment: ContentExperiment, outcome: str) -> str:
        if outcome == "positive":
            return f"在当前受控样本中，变更“{experiment.variable_changed}”达到预设成功指标。"
        if outcome == "negative":
            return f"在当前受控样本中，变更“{experiment.variable_changed}”未达到预设成功指标。"
        return "当前指标缺失或结果方向不一致，实验结论不充分。"

    @staticmethod
    def _stable_id(channel_id: str, hypothesis: str, variable: str) -> str:
        digest = hashlib.sha256(f"{channel_id}|{hypothesis}|{variable}".encode("utf-8")).hexdigest()[:12]
        return f"experiment_{digest}"
