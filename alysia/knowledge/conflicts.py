from __future__ import annotations

from alysia.knowledge.models import KnowledgeClaim, KnowledgeConflict, knowledge_now, stable_id
from alysia.knowledge.store import KnowledgeStore


class ConflictDetector:
    def __init__(self, store: KnowledgeStore) -> None:
        self.store = store

    def detect_for(self, claim: KnowledgeClaim) -> list[KnowledgeConflict]:
        conflicts: list[KnowledgeConflict] = []
        for other in self.store.active_claims(claim.topic):
            if other.claim_id == claim.claim_id or other.normalized_key != claim.normalized_key:
                continue
            if other.statement.strip() == claim.statement.strip() or other.scope != claim.scope:
                if other.scope != claim.scope:
                    conflict_type = "scope"
                else:
                    continue
            else:
                conflict_type = "version" if other.version != claim.version or other.valid_from != claim.valid_from else "value"
            refs = sorted({other.claim_id, claim.claim_id})
            conflict = KnowledgeConflict(
                conflict_id=stable_id("conflict", *refs, conflict_type),
                claim_refs=refs,
                conflict_type=conflict_type,
                evidence_refs=sorted(set(other.evidence_refs + claim.evidence_refs)),
                resolution_status="needs_primary_source",
                recommended_action=(
                    "检查是否为版本更新；比较 published_at/valid_from，优先请求官方或一手资料。"
                    if conflict_type == "version"
                    else "暂停确定性表述并请求更高质量的一手来源。"
                ),
                updated_at=knowledge_now(),
            )
            conflicts.append(self.store.add_conflict(conflict))
            self._mark_conflicted(other)
            self._mark_conflicted(claim)
        return conflicts

    def _mark_conflicted(self, claim: KnowledgeClaim) -> None:
        if claim.status not in {"retracted", "superseded"}:
            claim.status = "conflicted"
            claim.updated_at = knowledge_now()
            self.store.add_claim(claim)

