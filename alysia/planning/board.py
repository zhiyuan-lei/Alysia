from __future__ import annotations

from alysia.schemas import EditorialDecision, RankedTopic, TopicCandidate, TopicScore


class EditorialBoard:
    """Scout/Editor/Critic 的确定性单进程编排，不启动并发 Agent。"""

    def decide(
        self,
        candidates: list[TopicCandidate],
        scores: list[TopicScore],
        *,
        selected_count: int,
    ) -> tuple[EditorialDecision, list[RankedTopic]]:
        score_by_id = {score.candidate_id: score for score in scores}
        ranked = sorted(
            (
                RankedTopic(candidate=candidate, score=score_by_id[candidate.id])
                for candidate in candidates
                if candidate.id in score_by_id and score_by_id[candidate.id].disqualify_reason is None
            ),
            key=lambda item: (-item.score.total, item.candidate.topic),
        )
        if not ranked:
            raise ValueError("没有通过 Critic 硬规则的候选选题")
        chosen = self._diversify(ranked, selected_count)
        primary = chosen[0]
        decision = EditorialDecision(
            selected_topic=primary,
            alternates=chosen[1:],
            rationale="Editor 按显式权重排序，Critic 已排除禁区、强重复与证据不足候选。",
            evidence=primary.candidate.source_refs,
            linked_strategy=primary.candidate.experiment_link,
            confidence=min(0.9, 0.45 + primary.score.total / 200),
        )
        return decision, chosen

    @staticmethod
    def _diversify(ranked: list[RankedTopic], count: int) -> list[RankedTopic]:
        selected: list[RankedTopic] = []
        remaining = list(ranked)
        while remaining and len(selected) < count:
            used_categories = {item.candidate.category for item in selected}
            choice = next(
                (item for item in remaining if item.candidate.category not in used_categories),
                remaining[0],
            )
            selected.append(choice)
            remaining.remove(choice)
        return selected
