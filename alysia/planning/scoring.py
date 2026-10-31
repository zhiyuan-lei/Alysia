from __future__ import annotations

from alysia.core.config import PlanningConfig
from alysia.planning.novelty import find_duplicates
from alysia.schemas import CreatorProfile, TopicCandidate, TopicScore, TrendItem


class TopicScoringEngine:
    def __init__(self, config: PlanningConfig) -> None:
        self.config = config

    def score(
        self,
        candidate: TopicCandidate,
        profile: CreatorProfile,
        trends: list[TrendItem],
        history_topics: list[str],
    ) -> TopicScore:
        text = f"{candidate.topic} {candidate.angle} {candidate.category}".casefold()
        excluded = next((domain for domain in profile.excluded_domains if domain.casefold() in text), None)
        duplicates = find_duplicates(candidate.topic, history_topics)
        duplicate_value = duplicates[0].similarity if duplicates else 0.0
        trend_by_id = {trend.id: trend for trend in trends}
        linked_trends = [trend_by_id[ref] for ref in candidate.source_refs if ref in trend_by_id]
        freshness = max(
            (max(0.0, 1 - (trend.freshness_days or 0) / 30) for trend in linked_trends),
            default=0.35 if not candidate.requires_current_facts else 0.0,
        )
        audience_fit = 1.0 if candidate.target_audience == profile.target_audience else 0.75
        feasibility = {"low": 1.0, "medium": 0.75, "high": 0.4}[candidate.expected_effort]
        experiment_value = 1.0 if candidate.experiment_link else 0.45
        risk_value = min(1.0, len(candidate.risks) * 0.18)
        components = {
            "channel_relevance": candidate.relevance_score,
            "freshness": freshness,
            "audience_fit": audience_fit,
            "novelty_vs_history": min(candidate.novelty_score, 1 - duplicate_value),
            "evidence_quality": candidate.evidence_score,
            "production_feasibility": feasibility,
            "experiment_value": experiment_value,
            "duplication_penalty": duplicate_value,
            "risk_penalty": risk_value,
        }
        weights = self.config.weights
        positive_names = (
            "channel_relevance",
            "freshness",
            "audience_fit",
            "novelty_vs_history",
            "evidence_quality",
            "production_feasibility",
            "experiment_value",
        )
        positive_weight = sum(getattr(weights, name) for name in positive_names)
        positive = sum(getattr(weights, name) * components[name] for name in positive_names)
        penalties = (
            weights.duplication_penalty * components["duplication_penalty"]
            + weights.risk_penalty * components["risk_penalty"]
        )
        total = max(0.0, min(100.0, round(100 * (positive - penalties) / positive_weight, 2)))
        reason = None
        if excluded:
            reason = f"与 excluded_domains 冲突：{excluded}"
        elif duplicate_value >= self.config.duplicate_threshold:
            reason = f"与历史选题高度重复：{duplicates[0].existing_topic}"
        elif candidate.requires_current_facts and candidate.evidence_score < 0.3:
            reason = "时效性选题证据过弱"
        if reason:
            total = 0.0
        explanation = (
            f"相关性 {components['channel_relevance']:.2f}，新颖性 {components['novelty_vs_history']:.2f}，"
            f"证据 {components['evidence_quality']:.2f}，重复惩罚 {components['duplication_penalty']:.2f}。"
        )
        return TopicScore(
            candidate_id=candidate.id,
            total=total,
            components=components,
            explanation=explanation,
            disqualify_reason=reason,
            duplicate_candidates=duplicates,
        )
