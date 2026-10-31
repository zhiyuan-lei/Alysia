from __future__ import annotations

from datetime import datetime

from alysia.schemas import (
    CandidateScoreBreakdown,
    CounterfactualComparison,
    RankedCandidate,
    SimulationResults,
)


class CounterfactualComparator:
    _METRICS = {
        "expected_quality": "expected_quality_score",
        "reliability": "reliability_score",
        "latency": "latency_score",
        "resource_use": "resource_efficiency_score",
        "monetary_cost": "monetary_cost_score",
        "approval_burden": "approval_burden_score",
        "risk": "risk_score",
        "experiment_value": "experiment_value_score",
        "novelty": "novelty_score",
    }
    _WEIGHTS = {
        "expected_quality": 0.22,
        "reliability": 0.20,
        "latency": 0.10,
        "resource_use": 0.12,
        "monetary_cost": 0.05,
        "approval_burden": 0.08,
        "risk": 0.15,
        "experiment_value": 0.04,
        "novelty": 0.04,
    }

    def compare(self, results: SimulationResults) -> CounterfactualComparison:
        breakdowns: list[CandidateScoreBreakdown] = []
        uncertainty: list[str] = []
        for result in results.candidates:
            prediction_by_metric = {item.metric: item for item in result.predictions}
            values: dict[str, float | None] = {}
            weighted = 0.0
            weight_sum = 0.0
            known = 0
            for field, metric in self._METRICS.items():
                prediction = prediction_by_metric.get(metric)
                value = prediction.point_estimate if prediction else None
                numeric = float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None
                if field == "risk" and numeric is not None:
                    score_value = 1.0 - numeric
                else:
                    score_value = numeric
                values[field] = numeric
                if score_value is not None:
                    weighted += self._WEIGHTS[field] * max(0.0, min(1.0, score_value))
                    weight_sum += self._WEIGHTS[field]
                    known += 1
                else:
                    uncertainty.append(f"{result.candidate_id}: {metric}=unknown")
            total = weighted / weight_sum if weight_sum else 0.0
            breakdowns.append(CandidateScoreBreakdown(
                candidate_id=result.candidate_id,
                expected_quality=values["expected_quality"], reliability=values["reliability"],
                latency=values["latency"], resource_use=values["resource_use"],
                monetary_cost=values["monetary_cost"], approval_burden=values["approval_burden"],
                risk=values["risk"], experiment_value=values["experiment_value"], novelty=values["novelty"],
                total_score=round(total, 4), known_fraction=round(known / len(self._METRICS), 4),
            ))
        ordered = sorted(breakdowns, key=lambda item: (-item.total_score, -item.known_fraction, item.candidate_id))
        ranked = [RankedCandidate(rank=index, candidate_id=item.candidate_id, score=item.total_score) for index, item in enumerate(ordered, 1)]
        winner = ordered[0] if ordered else None
        tied = bool(len(ordered) > 1 and winner and abs(winner.total_score - ordered[1].total_score) < 0.01)
        reasons_not_selected: dict[str, list[str]] = {}
        for item in ordered[1:]:
            reasons = [f"综合可解释分数 {item.total_score:.4f} 低于 {winner.total_score:.4f}"] if winner else []
            if item.risk is not None and winner and winner.risk is not None and item.risk > winner.risk:
                reasons.append("风险更高")
            if item.reliability is not None and winner and winner.reliability is not None and item.reliability < winner.reliability:
                reasons.append("可靠性更低")
            if item.known_fraction < (winner.known_fraction if winner else 0):
                reasons.append("可用证据比例更低")
            reasons_not_selected[item.candidate_id] = reasons or ["次优方案；应结合人工判断"]
        tradeoffs: list[str] = []
        if winner:
            tradeoffs.append(
                f"推荐 {winner.candidate_id}；quality={winner.expected_quality}, reliability={winner.reliability}, "
                f"risk={winner.risk}, known_fraction={winner.known_fraction}"
            )
        if tied:
            tradeoffs.append("领先差异小于 0.01；证据不足以支持唯一选择，保持 no_recommendation")
        tradeoffs.append("总分只聚合已知/模拟的可解释维度；unknown 不按 0 伪造，但会降低 known_fraction")
        return CounterfactualComparison(
            scenario_id=results.scenario_id, ranked_candidates=ranked,
            score_breakdown=breakdowns, dominant_tradeoffs=tradeoffs,
            uncertainty=sorted(set(uncertainty)),
            recommendation=winner.candidate_id if winner and not tied else "no_recommendation",
            reasons_not_selected=reasons_not_selected, compared_at=datetime.now().astimezone(),
        )
