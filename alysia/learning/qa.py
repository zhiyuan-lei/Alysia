from __future__ import annotations

from alysia.schemas import LearningQAReport, LessonMemory, PerformanceAnalysis, StrategyRecommendation, VideoMetrics


class LearningQA:
    def run(
        self,
        metrics: VideoMetrics,
        analysis: PerformanceAnalysis,
        lessons: list[LessonMemory],
        recommendations: list[StrategyRecommendation],
    ) -> LearningQAReport:
        errors: list[str] = []
        warnings: list[str] = []
        missing_not_facts = all(
            not any(fact.startswith(f"{field}=") for fact in analysis.facts)
            for field in analysis.missing_data
        )
        single_run_not_supported = all(
            lesson.status != "supported" or len(set(lesson.evidence_run_ids)) >= 2 for lesson in lessons
        )
        mock_not_supported = all(
            lesson.source not in {"mock", "testing"} or lesson.status != "supported" for lesson in lessons
        )
        recommendations_traceable = all(
            bool(item.evidence) and item.confidence in {"low", "medium", "high"} for item in recommendations
        )
        checks = {
            "missing_data_not_used_as_fact": missing_not_facts,
            "single_run_not_supported": single_run_not_supported,
            "mock_not_promoted": mock_not_supported,
            "recommendations_have_evidence_and_confidence": recommendations_traceable,
        }
        for name, passed in checks.items():
            if not passed:
                errors.append(f"Learning QA 失败：{name}")
        if metrics.is_mock:
            warnings.append("本次指标来自 mock/testing，仅可形成测试记忆和 tentative lesson。")
        if len(set(run_id for lesson in lessons for run_id in lesson.evidence_run_ids)) < 2:
            warnings.append("独立 run 样本不足，不应形成强因果结论。")
        return LearningQAReport(passed=not errors, errors=errors, warnings=warnings, checks=checks)

