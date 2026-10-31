from __future__ import annotations

from datetime import datetime

from alysia.knowledge.models import EvidenceSource, SourceQualityBreakdown, SourceQualityEvaluation


class SourceQualityEvaluator:
    """完全透明的规则评分；输出每个维度和固定权重。"""

    WEIGHTS = {
        "primary_official_proximity": 0.25,
        "publication_recency": 0.15,
        "domain_relevance": 0.15,
        "corroboration": 0.15,
        "identifiable_authorship": 0.10,
        "citation_quality": 0.10,
        "conflict_history": 0.10,
    }

    TYPE_PROXIMITY = {
        "official": 1.0, "primary": 0.95, "academic": 0.85,
        "documentation": 0.8, "news": 0.6, "community": 0.4,
        "social": 0.2, "unknown": 0.25,
    }

    def evaluate(
        self,
        source: EvidenceSource,
        *,
        topic_domain: str | None = None,
        corroborating_count: int = 0,
        conflict_count: int = 0,
        now: datetime | None = None,
    ) -> SourceQualityEvaluation:
        now = now or datetime.now().astimezone()
        if source.published_at is None:
            recency = 0.45
        else:
            age_days = max(0.0, (now - source.published_at.astimezone()).total_seconds() / 86400)
            recency = max(0.1, 1.0 - min(age_days, 730) / 730)
        relevance = 1.0 if not topic_domain or topic_domain.lower() in {source.domain.lower(), source.publisher.lower()} else 0.65
        corroboration = min(1.0, 0.35 + 0.25 * corroborating_count)
        authorship = 1.0 if source.author else (0.75 if source.source_type in {"official", "documentation"} else 0.35)
        citation_quality = 0.85 if source.citation_note else (0.7 if source.source_type in {"official", "primary", "academic", "documentation"} else 0.4)
        conflict_history = max(0.0, 1.0 - 0.25 * conflict_count)
        breakdown = SourceQualityBreakdown(
            primary_official_proximity=self.TYPE_PROXIMITY[source.source_type],
            publication_recency=recency,
            domain_relevance=relevance,
            corroboration=corroboration,
            identifiable_authorship=authorship,
            citation_quality=citation_quality,
            conflict_history=conflict_history,
        )
        data = breakdown.model_dump()
        score = round(sum(data[key] * weight for key, weight in self.WEIGHTS.items()), 4)
        notes: list[str] = []
        if source.evidence_origin in {"mock", "trend", "simulation", "feedback"}:
            score = 0.0
            notes.append(f"{source.evidence_origin} 只能作为线索/测试数据，不能支撑事实")
        if source.source_type in {"community", "social"}:
            notes.append("社区/社交来源可作为体验证据或线索，不能单独支撑高风险事实")
        return SourceQualityEvaluation(
            source_id=source.source_id,
            score=score,
            breakdown=breakdown,
            weights=dict(self.WEIGHTS),
            notes=notes,
        )

