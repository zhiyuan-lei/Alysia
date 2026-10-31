from __future__ import annotations

from alysia.planning.novelty import find_duplicates
from alysia.schemas import ContentPlan, CreatorProfile, PlanningQAReport, RankedTopic, TrendItem


class PlanningQA:
    def run(
        self,
        plan: ContentPlan,
        selected: list[RankedTopic],
        profile: CreatorProfile,
        trends: list[TrendItem],
        history_topics: list[str],
        *,
        duplicate_threshold: float,
    ) -> PlanningQAReport:
        errors: list[str] = []
        warnings: list[str] = []
        trend_ids = {trend.id for trend in trends}
        profile_ok = True
        duplicate_ok = True
        sources_ok = True
        excluded_ok = True
        clickbait_ok = True
        strategy_ok = True
        clickbait_terms = ("震惊", "必看", "不看后悔", "100%", "彻底颠覆")

        for item in selected:
            candidate = item.candidate
            text = f"{candidate.topic} {candidate.angle} {candidate.category}".casefold()
            if candidate.category not in profile.primary_domains:
                profile_ok = False
                errors.append(f"候选不属于 primary_domains：{candidate.topic}")
            excluded = [domain for domain in profile.excluded_domains if domain.casefold() in text]
            if excluded:
                excluded_ok = False
                errors.append(f"候选命中 excluded_domains {excluded}：{candidate.topic}")
            duplicates = find_duplicates(candidate.topic, history_topics)
            if duplicates and duplicates[0].similarity >= duplicate_threshold:
                duplicate_ok = False
                errors.append(f"候选与历史主题严重重复：{candidate.topic}")
            if candidate.requires_current_facts and not any(ref in trend_ids for ref in candidate.source_refs):
                sources_ok = False
                errors.append(f"时效性候选缺少趋势来源：{candidate.topic}")
            if any(term in candidate.topic for term in clickbait_terms):
                clickbait_ok = False
                errors.append(f"候选包含过度标题党表达：{candidate.topic}")
            if candidate.experiment_link and not candidate.experiment_link.strip():
                strategy_ok = False
                errors.append(f"实验关联为空：{candidate.topic}")

        mock_isolated = not (plan.source in {"mock", "testing"} and not plan.testing)
        if not mock_isolated:
            errors.append("Mock trend 计划未标记 testing")
        if plan.testing:
            warnings.append("本计划来自 mock/testing trend，只能用于离线演示，不代表真实平台趋势。")
        warnings.append("Trend 只解释为什么现在做；正式脚本事实必须重新经过 Research。")
        checks = {
            "creator_profile_match": profile_ok,
            "no_severe_duplicate": duplicate_ok,
            "minimum_trend_sources": sources_ok,
            "mock_isolation": mock_isolated,
            "excluded_domains_clear": excluded_ok,
            "no_excessive_clickbait": clickbait_ok,
            "strategy_experiment_consistent": strategy_ok,
        }
        return PlanningQAReport(passed=all(checks.values()) and not errors, errors=errors, warnings=warnings, checks=checks)
