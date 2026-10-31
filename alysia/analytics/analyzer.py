from __future__ import annotations

from datetime import datetime

from alysia.schemas import (
    AnalysisHypothesis,
    ContentFingerprint,
    DerivedMetrics,
    Evidence,
    PerformanceAnalysis,
    VideoMetrics,
)


class PerformanceAnalyzer:
    OPTIONAL_FIELDS = (
        "impressions",
        "views",
        "likes",
        "comments",
        "favorites",
        "shares",
        "followers_gained",
        "avg_view_duration_sec",
        "avg_view_percentage",
        "completion_rate",
        "ctr",
    )

    def analyze(
        self,
        metrics: VideoMetrics,
        derived: DerivedMetrics,
        fingerprint: ContentFingerprint,
        qa_reports: dict[str, dict],
    ) -> PerformanceAnalysis:
        facts: list[str] = []
        strengths: list[str] = []
        weaknesses: list[str] = []
        anomalies: list[str] = []
        hypotheses: list[AnalysisHypothesis] = []
        evidence: list[Evidence] = []
        missing = [name for name in self.OPTIONAL_FIELDS if getattr(metrics, name) is None]

        for name in ("impressions", "views", "ctr", "avg_view_percentage", "completion_rate"):
            value = getattr(metrics, name)
            if value is not None:
                facts.append(f"{name}={value}")
                evidence.append(Evidence(kind="fact", statement=f"导入指标 {name}", fields={name: value}))

        if metrics.ctr is not None:
            (strengths if metrics.ctr >= 0.05 else weaknesses if metrics.ctr < 0.03 else facts).append(
                f"CTR 为 {metrics.ctr:.1%}。"
            )
        if metrics.completion_rate is not None:
            (strengths if metrics.completion_rate >= 0.5 else weaknesses if metrics.completion_rate < 0.35 else facts).append(
                f"完播率为 {metrics.completion_rate:.1%}。"
            )
        engagement = derived.engagement_rate.value
        if engagement is not None:
            facts.append(f"按显式公式计算的互动率为 {engagement:.1%}。")
            if engagement >= 0.05:
                strengths.append(f"互动率为 {engagement:.1%}，达到启发式高互动阈值。")

        retention_30 = self._retention_at(metrics, 30)
        if retention_30 is not None:
            facts.append(f"最接近 30 秒的留存为 {retention_30:.1%}。")
        if len(metrics.retention_points) >= 2:
            for previous, current in zip(metrics.retention_points, metrics.retention_points[1:]):
                if current.percentage > previous.percentage + 0.05:
                    anomalies.append(
                        f"留存从 {previous.second:g}s 的 {previous.percentage:.1%} 上升到 "
                        f"{current.second:g}s 的 {current.percentage:.1%}，需核对数据口径。"
                    )

        if retention_30 is not None and retention_30 < 0.65 and (fingerprint.hook_length_sec or 0) > 8:
            item = Evidence(
                kind="artifact",
                statement="较长 hook 与较低 30 秒留存同时出现",
                fields={"hook_length_sec": fingerprint.hook_length_sec, "retention_30": retention_30},
            )
            hypotheses.append(
                AnalysisHypothesis(
                    statement="开头进入主题较慢可能与前 30 秒流失相关。",
                    confidence="low",
                    evidence=[item],
                )
            )
            evidence.append(item)
        if metrics.ctr is not None and metrics.ctr < 0.03:
            item = Evidence(
                kind="artifact",
                statement="低 CTR 与当前标题/封面包装同时出现",
                fields={"ctr": metrics.ctr, "title_style": fingerprint.title_style, "cover": fingerprint.cover_template},
            )
            hypotheses.append(
                AnalysisHypothesis(
                    statement="当前标题或封面包装可能与较低点击率相关。",
                    confidence="low",
                    evidence=[item],
                )
            )
            evidence.append(item)
        if metrics.completion_rate is not None and metrics.completion_rate < 0.35:
            item = Evidence(
                kind="artifact",
                statement="较低完播率与当前时长和叙事速度同时出现",
                fields={
                    "completion_rate": metrics.completion_rate,
                    "duration_sec": fingerprint.duration_sec,
                    "narration_speed_chars_per_sec": fingerprint.narration_speed_chars_per_sec,
                },
            )
            hypotheses.append(
                AnalysisHypothesis(
                    statement="内容节奏或时长可能与较低完播率相关。",
                    confidence="low",
                    evidence=[item],
                )
            )
            evidence.append(item)

        for name, report in qa_reports.items():
            if report and report.get("passed") is False:
                anomalies.append(f"{name} 未通过，平台表现分析可能受产物质量影响。")
                evidence.append(Evidence(kind="qa", statement=f"{name} 未通过", fields={"passed": False}))

        observed = len(self.OPTIONAL_FIELDS) - len(missing)
        summary = (
            f"已分析 {observed}/{len(self.OPTIONAL_FIELDS)} 个可选平台指标。"
            f"本报告包含 {len(hypotheses)} 个低强度假设；单条视频不能证明因果关系。"
        )
        return PerformanceAnalysis(
            run_id=metrics.run_id,
            summary=summary,
            facts=facts,
            strengths=strengths,
            weaknesses=weaknesses,
            anomalies=anomalies,
            hypotheses=hypotheses,
            evidence=evidence,
            missing_data=missing,
            generated_at=datetime.now().astimezone(),
        )

    @staticmethod
    def _retention_at(metrics: VideoMetrics, second: float) -> float | None:
        if not metrics.retention_points:
            return None
        point = min(metrics.retention_points, key=lambda item: abs(item.second - second))
        return point.percentage

