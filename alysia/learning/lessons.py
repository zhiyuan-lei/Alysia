from __future__ import annotations

from alysia.schemas import ContentFingerprint, LessonCandidate, PerformanceAnalysis, VideoMetrics


class LessonExtractor:
    def extract(
        self,
        analysis: PerformanceAnalysis,
        metrics: VideoMetrics,
        fingerprint: ContentFingerprint,
    ) -> list[LessonCandidate]:
        candidates: list[LessonCandidate] = []
        for hypothesis in analysis.hypotheses:
            statement = hypothesis.statement
            if "30 秒" in statement:
                candidates.append(
                    LessonCandidate(
                        statement=f"在{fingerprint.category}内容中，将 hook 控制在 8 秒以内可能有助于前 30 秒留存",
                        category="retention",
                        scope=fingerprint.category,
                        supporting_metrics={
                            "hook_length_sec": fingerprint.hook_length_sec,
                            "retention_30": self._retention_at(metrics, 30),
                        },
                        confidence=0.3,
                    )
                )
            elif "标题或封面" in statement:
                candidates.append(
                    LessonCandidate(
                        statement=f"在{fingerprint.category}内容中，{fingerprint.title_style}标题与点击率的关系值得持续验证",
                        category="packaging",
                        scope=fingerprint.category,
                        supporting_metrics={"ctr": metrics.ctr, "title_style": fingerprint.title_style},
                        confidence=0.25,
                    )
                )
            elif "节奏或时长" in statement:
                candidates.append(
                    LessonCandidate(
                        statement=f"在{fingerprint.category}内容中，控制时长和叙事密度可能有助于完播率",
                        category="completion",
                        scope=fingerprint.category,
                        supporting_metrics={
                            "completion_rate": metrics.completion_rate,
                            "duration_sec": fingerprint.duration_sec,
                            "narration_speed_chars_per_sec": fingerprint.narration_speed_chars_per_sec,
                        },
                        confidence=0.3,
                    )
                )
        retention_30 = self._retention_at(metrics, 30)
        if retention_30 is not None and retention_30 >= 0.65 and (fingerprint.hook_length_sec or 0) > 8:
            candidates.append(
                LessonCandidate(
                    statement=f"在{fingerprint.category}内容中，将 hook 控制在 8 秒以内可能有助于前 30 秒留存",
                    category="retention",
                    scope=fingerprint.category,
                    supporting_metrics={
                        "hook_length_sec": fingerprint.hook_length_sec,
                        "retention_30": retention_30,
                    },
                    confidence=0.2,
                    direction="contradicts",
                )
            )
        if metrics.completion_rate is not None and metrics.completion_rate >= 0.5 and fingerprint.duration_sec >= 60:
            candidates.append(
                LessonCandidate(
                    statement=f"在{fingerprint.category}内容中，控制时长和叙事密度可能有助于完播率",
                    category="completion",
                    scope=fingerprint.category,
                    supporting_metrics={
                        "completion_rate": metrics.completion_rate,
                        "duration_sec": fingerprint.duration_sec,
                        "narration_speed_chars_per_sec": fingerprint.narration_speed_chars_per_sec,
                    },
                    confidence=0.2,
                    direction="contradicts",
                )
            )
        return candidates

    @staticmethod
    def _retention_at(metrics: VideoMetrics, second: float) -> float | None:
        if not metrics.retention_points:
            return None
        return min(metrics.retention_points, key=lambda item: abs(item.second - second)).percentage
