from __future__ import annotations

from datetime import datetime

from alysia.knowledge.models import (
    ClaimCandidate,
    ClaimVerificationResult,
    KnowledgeClaim,
    stable_id,
)
from alysia.knowledge.quality import SourceQualityEvaluator
from alysia.knowledge.store import KnowledgeStore


class ClaimVerifier:
    def __init__(self, store: KnowledgeStore, evaluator: SourceQualityEvaluator | None = None) -> None:
        self.store = store
        self.evaluator = evaluator or SourceQualityEvaluator()

    def verify_candidate(self, candidate: ClaimCandidate, *, now: datetime | None = None) -> tuple[KnowledgeClaim | None, ClaimVerificationResult]:
        now = now or datetime.now().astimezone()
        claim_id = stable_id("claim", candidate.normalized_key, candidate.statement, now.isoformat())
        if not candidate.source_refs:
            return None, ClaimVerificationResult(
                claim_id=claim_id,
                status="unknown",
                confidence=0,
                missing_evidence=["至少一个可追溯来源"],
                reasoning_summary="候选 claim 没有 source refs，未进入知识库。",
            )

        sources = []
        missing: list[str] = []
        for source_id in candidate.source_refs:
            try:
                sources.append(self.store.get_source(source_id))
            except FileNotFoundError:
                missing.append(source_id)
        admissible = [item for item in sources if item.evidence_origin not in {"mock", "trend", "simulation", "feedback"}]
        evaluations = [
            self.evaluator.evaluate(source, topic_domain=candidate.domain, corroborating_count=max(0, len(admissible) - 1))
            for source in admissible
        ]
        authoritative = [
            evaluation for evaluation, source in zip(evaluations, admissible)
            if source.source_type in {"official", "primary"} and evaluation.score >= 0.65
        ]
        good = [evaluation for evaluation in evaluations if evaluation.score >= 0.55]

        if candidate.claim_type == "opinion":
            status = "provisional"
            confidence = min(0.6, max((item.score for item in evaluations), default=0.2))
            reasoning = "该陈述被识别为 opinion，仅保留为 provisional，不升级为事实。"
        elif authoritative:
            status = "verified"
            confidence = min(0.98, 0.78 + 0.05 * len(good))
            reasoning = "存在质量达标的官方/一手来源，可在其声明 scope 内验证。"
        elif len(good) >= 2 and len({item.domain for item in admissible}) >= 2:
            status = "verified"
            confidence = min(0.9, sum(item.score for item in good) / len(good))
            reasoning = "两个以上独立且质量达标的来源相互印证。"
        elif admissible:
            status = "provisional"
            confidence = min(0.69, max((item.score for item in evaluations), default=0.25))
            reasoning = "只有单一或质量不足的来源，保留为 provisional。"
        else:
            return None, ClaimVerificationResult(
                claim_id=claim_id,
                status="unknown",
                confidence=0,
                supporting_sources=[],
                missing_evidence=missing + ["非 mock/trend/simulation/feedback 的来源"],
                reasoning_summary="现有引用均属于不可升级为事实的来源类别，未进入知识库。",
            )

        ttl = 14 if candidate.time_sensitive else None
        claim = KnowledgeClaim(
            claim_id=claim_id,
            statement=candidate.statement,
            normalized_key=candidate.normalized_key,
            topic=candidate.topic,
            domain=candidate.domain,
            claim_type=candidate.claim_type,
            status=status,
            confidence=round(confidence, 4),
            last_verified_at=now,
            evidence_refs=[item.source_id for item in admissible],
            scope=candidate.scope,
            freshness_policy_days=ttl,
            created_at=now,
            updated_at=now,
        )
        return claim, ClaimVerificationResult(
            claim_id=claim_id,
            status=status,
            confidence=claim.confidence,
            supporting_sources=claim.evidence_refs,
            missing_evidence=missing,
            reasoning_summary=reasoning,
        )

    def verify_existing(self, claim_id: str) -> ClaimVerificationResult:
        claim = self.store.get_claim(claim_id)
        candidate = ClaimCandidate(
            statement=claim.statement,
            normalized_key=claim.normalized_key,
            topic=claim.topic,
            domain=claim.domain,
            claim_type=claim.claim_type,
            source_refs=claim.evidence_refs,
            time_sensitive=claim.claim_type == "time_sensitive",
            scope=claim.scope,
            supported=bool(claim.evidence_refs),
        )
        _, result = self.verify_candidate(candidate)
        result.claim_id = claim.claim_id
        return result

