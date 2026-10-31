from __future__ import annotations

from datetime import datetime

from alysia.knowledge.models import FreshnessAssessment, KnowledgeClaim


class FreshnessPolicy:
    def __init__(
        self,
        *,
        software_days: int = 14,
        pricing_days: int = 3,
        current_roles_days: int = 7,
        stable_definition_days: int = 365,
    ) -> None:
        self.software_days = software_days
        self.pricing_days = pricing_days
        self.current_roles_days = current_roles_days
        self.stable_definition_days = stable_definition_days

    def ttl_for(self, claim: KnowledgeClaim) -> int:
        if claim.freshness_policy_days:
            return claim.freshness_policy_days
        domain = claim.domain.lower()
        if "pricing" in domain or "price" in domain or "api_rule" in domain:
            return self.pricing_days
        if "current_role" in domain or "leadership" in domain:
            return self.current_roles_days
        if "software" in domain or "model" in domain or "api" in domain:
            return self.software_days
        if claim.claim_type == "definition":
            return self.stable_definition_days
        if claim.claim_type == "historical":
            return max(self.stable_definition_days, 3650)
        if claim.claim_type == "time_sensitive":
            return self.software_days
        return self.stable_definition_days

    def assess(self, claim: KnowledgeClaim, *, now: datetime | None = None) -> FreshnessAssessment:
        now = now or datetime.now().astimezone()
        ttl = self.ttl_for(claim)
        anchor = claim.last_verified_at or claim.created_at
        age = max(0.0, (now - anchor.astimezone()).total_seconds() / 86400)
        if claim.status in {"retracted", "conflicted"}:
            state = "reverify_required"
            reason = f"claim status={claim.status}，正式使用前必须重新验证"
        elif claim.valid_until and now > claim.valid_until.astimezone():
            state = "reverify_required"
            reason = "已超过 valid_until"
        elif age >= ttl:
            state = "stale"
            reason = f"距上次验证 {age:.1f} 天，超过 {ttl} 天策略"
        elif age >= ttl * 0.75:
            state = "aging"
            reason = f"距上次验证 {age:.1f} 天，接近 {ttl} 天策略"
        else:
            state = "fresh"
            reason = f"距上次验证 {age:.1f} 天，未超过 {ttl} 天策略"
        return FreshnessAssessment(claim_id=claim.claim_id, state=state, ttl_days=ttl, age_days=round(age, 4), reason=reason, assessed_at=now)

