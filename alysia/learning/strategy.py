from __future__ import annotations

from datetime import datetime

from alysia.learning.memory import MemoryStore
from alysia.schemas import (
    ContentFingerprint,
    LessonMemory,
    PerformanceAnalysis,
    StrategyMemory,
    StrategyRecommendation,
    VideoMetrics,
)


class StrategyEngine:
    def recommend(
        self,
        analysis: PerformanceAnalysis,
        metrics: VideoMetrics,
        fingerprint: ContentFingerprint,
        lessons: list[LessonMemory],
    ) -> list[StrategyRecommendation]:
        recommendations: list[StrategyRecommendation] = []
        retention_30 = self._retention_at(metrics, 30)
        if retention_30 is not None and retention_30 < 0.65 and (fingerprint.hook_length_sec or 0) > 8:
            recommendations.append(
                StrategyRecommendation(
                    objective="提升前 30 秒留存",
                    proposed_change="下一期将 hook 控制在 8 秒以内",
                    rationale="当前较长 hook 与较低 30 秒留存同时出现，需要受控实验验证。",
                    evidence=[f"run={metrics.run_id}: hook={fingerprint.hook_length_sec:.1f}s, retention_30={retention_30:.1%}"],
                    confidence="low",
                    risk="可能压缩必要的背景说明",
                    test_plan="未来连续 3 条同类视频只缩短 hook，其余结构尽量保持一致；比较 30 秒留存和完播率。",
                )
            )
        if metrics.completion_rate is not None and metrics.completion_rate < 0.35:
            recommendations.append(
                StrategyRecommendation(
                    objective="提升完播率",
                    proposed_change="下一期减少重复背景说明，并将每个场景限定为一个核心观点",
                    rationale="当前完播率偏低；节奏或时长是待验证因素，不视为已证实原因。",
                    evidence=[f"run={metrics.run_id}: completion_rate={metrics.completion_rate:.1%}"],
                    confidence="low",
                    risk="过度压缩可能降低解释完整性",
                    test_plan="连续 3 条视频保持题材和标题风格相近，仅减少重复叙述；比较平均观看比例与完播率。",
                )
            )
        if metrics.ctr is not None and metrics.ctr < 0.03:
            recommendations.append(
                StrategyRecommendation(
                    objective="提升点击率",
                    proposed_change=f"测试一个与当前{fingerprint.title_style}标题不同的标题包装",
                    rationale="当前 CTR 偏低，但标题与封面的单独贡献尚无法分离。",
                    evidence=[f"run={metrics.run_id}: ctr={metrics.ctr:.1%}, title_style={fingerprint.title_style}"],
                    confidence="low",
                    risk="同时改变标题和封面会造成归因困难",
                    test_plan="优先只改变标题风格，封面模板保持不变；累计至少 3 条后比较 CTR。",
                )
            )
        if not recommendations and lessons:
            lesson = lessons[0]
            recommendations.append(
                StrategyRecommendation(
                    objective="验证现有候选经验",
                    proposed_change=lesson.statement,
                    rationale="当前没有明显低值阈值，适合对 tentative lesson 做小范围验证。",
                    evidence=[f"lesson={lesson.id}; runs={','.join(lesson.evidence_run_ids)}"],
                    confidence="low",
                    risk="样本不足，效果可能无法复现",
                    test_plan="在未来 3 条同类视频中一次只改变一个变量，并记录同一组成功指标。",
                )
            )
        return recommendations

    def persist(
        self,
        store: MemoryStore,
        run_id: str,
        source: str,
        recommendations: list[StrategyRecommendation],
        applies_to: str,
        channel_id: str = "main",
    ) -> list[StrategyMemory]:
        now = datetime.now().astimezone()
        memories: list[StrategyMemory] = []
        for recommendation in recommendations:
            strategy_id = store._stable_id("strategy", channel_id, applies_to, recommendation.proposed_change)
            item = StrategyMemory(
                id=strategy_id,
                channel_id=channel_id,
                rule=recommendation.proposed_change,
                rationale=recommendation.rationale,
                evidence_run_ids=[run_id],
                confidence=0.2 if source in {"mock", "testing"} else 0.35,
                applies_to=applies_to,
                source="testing" if source in {"mock", "testing"} else source,
                created_at=now,
                updated_at=now,
            )
            store.save_strategy(item)
            memories.append(item)
        return memories

    @staticmethod
    def _retention_at(metrics: VideoMetrics, second: float) -> float | None:
        if not metrics.retention_points:
            return None
        return min(metrics.retention_points, key=lambda item: abs(item.second - second)).percentage
