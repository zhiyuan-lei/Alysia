from __future__ import annotations

from alysia.knowledge.freshness import FreshnessPolicy
from alysia.knowledge.models import KnowledgeMaintenanceReport, ReverificationTask, knowledge_now, stable_id
from alysia.knowledge.store import KnowledgeStore


class KnowledgeMaintenanceService:
    def __init__(self, store: KnowledgeStore, freshness: FreshnessPolicy) -> None:
        self.store = store
        self.freshness = freshness

    def tick(self, *, priority_topics: list[str] | None = None) -> KnowledgeMaintenanceReport:
        priority_topics = priority_topics or []
        report = KnowledgeMaintenanceReport()
        existing_tasks = {item.task_id for item in self.store.list_tasks()}
        for claim in self.store.active_claims():
            report.scanned_claims += 1
            assessment = self.freshness.assess(claim)
            setattr(report, assessment.state, getattr(report, assessment.state) + 1)
            if assessment.state in {"stale", "reverify_required"}:
                if claim.status not in {"conflicted", "retracted", "stale"}:
                    claim.status = "stale"
                    claim.updated_at = knowledge_now()
                    self.store.add_claim(claim)
                task_id = stable_id("reverify", claim.claim_id, claim.last_verified_at or claim.created_at)
                if task_id not in existing_tasks:
                    priority = "critical" if claim.topic in priority_topics else "high"
                    task = ReverificationTask(
                        task_id=task_id,
                        claim_id=claim.claim_id,
                        question=f"重新验证：{claim.statement}",
                        priority=priority,
                        required_source_types=["official", "primary"],
                        reason=assessment.reason,
                    )
                    self.store.add_task(task)
                    existing_tasks.add(task_id)
                report.task_ids.append(task_id)
        report.conflict_ids = [item.conflict_id for item in self.store.list_conflicts(open_only=True)]
        return report
