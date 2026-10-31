from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import datetime

from alysia.schemas import (
    ContentFatigueSignal,
    MetricAggregate,
    MetricComparison,
    MultiVideoPerformanceAnalysis,
    TopicLifecycle,
    TrendChange,
    VideoPerformanceSnapshot,
)


class MultiVideoAnalyzer:
    METRICS = (
        "views",
        "ctr",
        "completion_rate",
        "avg_view_percentage",
        "likes",
        "favorites",
        "comments",
        "followers_gained",
    )
    RATE_METRICS = {"ctr", "completion_rate", "avg_view_percentage"}

    def analyze(
        self,
        channel_id: str,
        snapshots: list[VideoPerformanceSnapshot],
    ) -> MultiVideoPerformanceAnalysis:
        ordered = sorted(snapshots, key=lambda item: (item.published_at, item.run_id))
        aggregates = [self._aggregate(metric, ordered) for metric in self.METRICS]
        comparisons = [self._comparison(metric, ordered) for metric in self.METRICS]
        trends = [self._trend(item, ordered) for item in aggregates]
        categories: dict[str, list[VideoPerformanceSnapshot]] = defaultdict(list)
        for snapshot in ordered:
            categories[snapshot.category].append(snapshot)
        fatigue = [self._fatigue(category, items) for category, items in sorted(categories.items())]
        lifecycles = [self._lifecycle(category, items) for category, items in sorted(categories.items())]
        missing = [item.metric for item in aggregates if item.sample_count < len(ordered)]
        evidence = [
            f"{item.run_id}:{item.source}:{item.published_at.isoformat()}"
            for item in ordered
        ]
        digest_payload = [item.model_dump(mode="json") for item in ordered]
        digest = hashlib.sha256(
            json.dumps(digest_payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
        return MultiVideoPerformanceAnalysis(
            channel_id=channel_id,
            sample_size=len(ordered),
            non_testing_sample_size=sum(not item.is_testing for item in ordered),
            run_ids=[item.run_id for item in ordered],
            metric_aggregates=aggregates,
            comparisons=comparisons,
            trend_changes=trends,
            fatigue_signals=fatigue,
            topic_lifecycles=lifecycles,
            missing_data=missing,
            evidence=evidence,
            source_digest=digest,
            generated_at=datetime.now().astimezone(),
        )

    def _aggregate(self, metric: str, snapshots: list[VideoPerformanceSnapshot]) -> MetricAggregate:
        values = [float(value) for item in snapshots if (value := item.metrics.get(metric)) is not None]
        previous_mean: float | None = None
        recent_mean: float | None = None
        relative_change: float | None = None
        if len(values) >= 4:
            split = len(values) // 2
            previous_mean = sum(values[:split]) / split
            recent_mean = sum(values[split:]) / (len(values) - split)
            if previous_mean != 0:
                relative_change = (recent_mean - previous_mean) / abs(previous_mean)
        return MetricAggregate(
            metric=metric,
            sample_count=len(values),
            mean=(sum(values) / len(values)) if values else None,
            minimum=min(values) if values else None,
            maximum=max(values) if values else None,
            previous_mean=previous_mean,
            recent_mean=recent_mean,
            relative_change=relative_change,
        )

    def _trend(self, aggregate: MetricAggregate, snapshots: list[VideoPerformanceSnapshot]) -> TrendChange:
        change = aggregate.relative_change
        threshold = 0.05 if aggregate.metric in self.RATE_METRICS else 0.10
        if change is None:
            direction = "insufficient"
            statement = f"{aggregate.metric} 少于 4 个有效样本，不能判断趋势。"
        elif change > threshold:
            direction = "improving"
            statement = f"{aggregate.metric} 最近半段均值相对前半段上升 {change:.1%}。"
        elif change < -threshold:
            direction = "declining"
            statement = f"{aggregate.metric} 最近半段均值相对前半段下降 {abs(change):.1%}。"
        else:
            direction = "stable"
            statement = f"{aggregate.metric} 最近与此前均值变化未超过启发式阈值。"
        evidence = [item.run_id for item in snapshots if item.metrics.get(aggregate.metric) is not None]
        return TrendChange(metric=aggregate.metric, direction=direction, statement=statement, evidence_run_ids=evidence)

    @staticmethod
    def _comparison(metric: str, snapshots: list[VideoPerformanceSnapshot]) -> MetricComparison:
        values = [
            (item, float(value))
            for item in snapshots
            if (value := item.metrics.get(metric)) is not None
        ]
        if not values:
            return MetricComparison(metric=metric)
        best_item, best_value = max(values, key=lambda pair: pair[1])
        weakest_item, weakest_value = min(values, key=lambda pair: pair[1])
        return MetricComparison(
            metric=metric,
            best_run_id=best_item.run_id,
            best_value=best_value,
            weakest_run_id=weakest_item.run_id,
            weakest_value=weakest_value,
            comparable_run_ids=[item.run_id for item, _ in values],
        )

    def _fatigue(self, category: str, items: list[VideoPerformanceSnapshot]) -> ContentFatigueSignal:
        recent = items[-3:]
        values = [self._quality_score(item) for item in recent]
        usable = [(item, value) for item, value in zip(recent, values) if value is not None]
        if len(usable) < 3:
            return ContentFatigueSignal(
                dimension="category",
                value=category,
                status="insufficient",
                statement=f"{category} 少于 3 条具有可比率指标的内容，不能判断疲劳。",
                evidence_run_ids=[item.run_id for item, _ in usable],
            )
        scores = [value for _, value in usable]
        declining = scores[0] > scores[1] > scores[2] and scores[0] - scores[2] >= 0.05
        return ContentFatigueSignal(
            dimension="category",
            value=category,
            status="possible" if declining else "not_observed",
            statement=(
                f"{category} 最近 3 条的可比质量分连续下降，存在内容疲劳信号；这不是因果结论。"
                if declining
                else f"{category} 最近 3 条未出现连续下降的内容疲劳信号。"
            ),
            evidence_run_ids=[item.run_id for item, _ in usable],
        )

    def _lifecycle(self, category: str, items: list[VideoPerformanceSnapshot]) -> TopicLifecycle:
        usable = [(item, self._quality_score(item)) for item in items]
        usable = [(item, value) for item, value in usable if value is not None]
        if len(usable) < 2:
            stage = "exploring" if usable else "insufficient"
            statement = f"{category} 的有效样本不足，当前仅能视为探索阶段。"
        else:
            midpoint = len(usable) // 2
            first = sum(value for _, value in usable[:midpoint]) / midpoint
            last = sum(value for _, value in usable[midpoint:]) / (len(usable) - midpoint)
            delta = last - first
            if delta > 0.05:
                stage, statement = "growing", f"{category} 后半段可比质量分比前半段高 {delta:.1%}。"
            elif delta < -0.05:
                stage, statement = "declining", f"{category} 后半段可比质量分比前半段低 {abs(delta):.1%}。"
            else:
                stage, statement = "stable", f"{category} 前后半段可比质量分变化未超过 5%。"
        return TopicLifecycle(
            topic_key=category,
            stage=stage,
            sample_count=len(usable),
            statement=statement,
            evidence_run_ids=[item.run_id for item, _ in usable],
        )

    @staticmethod
    def _quality_score(snapshot: VideoPerformanceSnapshot) -> float | None:
        values = [
            float(value)
            for metric in ("ctr", "completion_rate", "avg_view_percentage")
            if (value := snapshot.metrics.get(metric)) is not None
        ]
        return sum(values) / len(values) if values else None
