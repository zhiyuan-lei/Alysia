from __future__ import annotations

from alysia.schemas import ContentFingerprint, NextExperimentProposal, StrategyRecommendation


class NextExperimentPlanner:
    def propose(
        self,
        fingerprint: ContentFingerprint,
        strategies: list[StrategyRecommendation],
    ) -> NextExperimentProposal:
        strategy = strategies[0] if strategies else None
        if "AGI" in fingerprint.topic.upper() and "Agent" in fingerprint.topic:
            topic = "AI Agent 失败时，暴露了哪些 AGI 差距？"
            angle = "用一个失败任务链作为案例，延续原主题但避免重复讲定义"
        else:
            topic = f"{fingerprint.topic}：从一个失败案例重新验证"
            angle = "保持原领域，改用案例驱动的实验角度"
        return NextExperimentProposal(
            topic=topic,
            angle=angle,
            target_audience="与当前视频相同的核心受众",
            primary_hypothesis=(strategy.rationale if strategy else "案例驱动角度可能提高内容可理解性，需实验验证。"),
            variable_to_change=(strategy.proposed_change if strategy else "叙事角度：概念讲解改为失败案例"),
            variables_to_hold_constant=["内容分类", "封面模板", "视频分辨率", "发布时段（如可控）"],
            success_metrics=["30 秒留存", "平均观看比例", "完播率", "CTR"],
        )

