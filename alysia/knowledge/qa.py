from __future__ import annotations

from alysia.knowledge.freshness import FreshnessPolicy
from alysia.knowledge.models import GroundingReport, KnowledgeQAIssue, KnowledgeQAReport
from alysia.knowledge.store import KnowledgeStore


class KnowledgeQA:
    def __init__(self, store: KnowledgeStore, freshness: FreshnessPolicy) -> None:
        self.store = store
        self.freshness = freshness

    def run(self, *, grounding: GroundingReport | None = None) -> KnowledgeQAReport:
        issues: list[KnowledgeQAIssue] = []
        if grounding is None:
            for conflict in self.store.list_conflicts(open_only=True):
                issues.append(KnowledgeQAIssue(
                    code="unresolved_conflict",
                    severity="error",
                    message="存在未解决的知识冲突；相关事实不得确定性使用",
                    reference=conflict.conflict_id,
                ))
        for claim in self.store.list_claims():
            if claim.status in {"verified", "provisional"} and not claim.evidence_refs:
                issues.append(KnowledgeQAIssue(code="claim_without_source", severity="error", message="事实缺少来源", reference=claim.claim_id))
            if claim.claim_type == "opinion" and claim.status == "verified":
                issues.append(KnowledgeQAIssue(code="opinion_as_fact", severity="error", message="opinion 被错误标记为事实", reference=claim.claim_id))
            for source_id in claim.evidence_refs:
                try:
                    source = self.store.get_source(source_id)
                except FileNotFoundError:
                    issues.append(KnowledgeQAIssue(code="missing_source", severity="error", message="claim 引用不存在的 source", reference=source_id))
                    continue
                if source.evidence_origin in {"mock", "trend", "simulation", "feedback"}:
                    issues.append(KnowledgeQAIssue(code="source_boundary_violation", severity="error", message=f"{source.evidence_origin} 不得进入事实知识", reference=source_id))
            assessment = self.freshness.assess(claim)
            if claim.status in {"verified", "provisional"} and assessment.state in {"stale", "reverify_required"}:
                issues.append(KnowledgeQAIssue(code="stale_claim", severity="warning", message=assessment.reason, reference=claim.claim_id))
        if grounding:
            for section_id in grounding.unsupported_sections:
                issues.append(KnowledgeQAIssue(code="unsupported_section", severity="error", message="事实性 section 没有有效引用", reference=section_id))
            for claim_id in grounding.stale_claim_refs:
                issues.append(KnowledgeQAIssue(code="stale_claim_used", severity="error", message="正式脚本使用 stale claim", reference=claim_id))
            for claim_id in grounding.conflicted_claim_refs:
                issues.append(KnowledgeQAIssue(code="conflicted_claim_used", severity="error", message="正式脚本使用 conflicted claim", reference=claim_id))
        return KnowledgeQAReport(passed=not any(item.severity == "error" for item in issues), issues=issues)
