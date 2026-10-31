from __future__ import annotations

from alysia.knowledge.freshness import FreshnessPolicy
from alysia.knowledge.models import KnowledgeContext
from alysia.knowledge.store import KnowledgeStore


class KnowledgeContextSelector:
    def __init__(self, store: KnowledgeStore, freshness: FreshnessPolicy) -> None:
        self.store = store
        self.freshness = freshness

    def select(self, topic: str, *, role: str, limit: int = 12) -> KnowledgeContext:
        terms = {item.lower() for item in topic.replace("/", " ").replace("-", " ").split() if item}
        candidates = []
        warnings: list[str] = []
        for claim in self.store.active_claims():
            haystack = f"{claim.topic} {claim.domain} {claim.statement}".lower()
            relevant = claim.topic == topic or not terms or any(term in haystack for term in terms)
            if not relevant:
                continue
            freshness = self.freshness.assess(claim)
            if freshness.state in {"stale", "reverify_required"} or claim.status in {"conflicted", "stale"}:
                warnings.append(f"{claim.claim_id}:{claim.status}/{freshness.state}")
                continue
            if claim.status in {"verified", "provisional"}:
                candidates.append(claim)
        candidates.sort(key=lambda item: (item.status == "verified", item.last_verified_at or item.created_at, item.confidence), reverse=True)
        selected = candidates[:limit]
        source_ids = sorted({ref for claim in selected for ref in claim.evidence_refs})
        sources = [self.store.get_source(ref) for ref in source_ids]
        selected_ids = {item.claim_id for item in selected}
        conflicts = [item for item in self.store.list_conflicts(open_only=True) if selected_ids.intersection(item.claim_refs)]
        return KnowledgeContext(topic=topic, role=role, claims=selected, sources=sources, conflicts=conflicts, warnings=warnings)

