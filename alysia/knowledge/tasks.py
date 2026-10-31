from __future__ import annotations

from datetime import datetime

from alysia.knowledge.models import KnowledgeGap, ResearchTask, stable_id
from alysia.knowledge.store import KnowledgeStore


class ResearchTaskPlanner:
    def __init__(self, store: KnowledgeStore, *, max_sources: int = 8, max_rounds: int = 2) -> None:
        self.store = store
        self.max_sources = max_sources
        self.max_rounds = max_rounds

    def create(
        self,
        question: str,
        *,
        required_evidence_quality: str = "medium",
        freshness_requirement_days: int | None = None,
        deadline: datetime | None = None,
    ) -> ResearchTask:
        task = ResearchTask(
            task_id=stable_id("research", question, required_evidence_quality, freshness_requirement_days),
            question=question,
            required_evidence_quality=required_evidence_quality,  # type: ignore[arg-type]
            freshness_requirement_days=freshness_requirement_days,
            max_sources=self.max_sources,
            max_rounds=self.max_rounds,
            deadline=deadline,
        )
        return self.store.add_task(task)  # type: ignore[return-value]

    @staticmethod
    def finish(task: ResearchTask, *, answered: bool, sufficient: bool) -> ResearchTask:
        if answered and sufficient:
            task.result_status = "answered"
        elif answered:
            task.result_status = "partially_answered"
        else:
            task.result_status = "unresolved"
        task.updated_at = datetime.now().astimezone()
        return task


class KnowledgeGapDetector:
    def __init__(self, store: KnowledgeStore) -> None:
        self.store = store

    def create(
        self,
        question: str,
        *,
        affected_topics: list[str] | None = None,
        affected_runs: list[str] | None = None,
        urgency: str = "medium",
        required_source_types: list[str] | None = None,
        current_evidence: list[str] | None = None,
    ) -> KnowledgeGap:
        gap = KnowledgeGap(
            gap_id=stable_id("kgap", question, *(affected_runs or [])),
            question=question,
            affected_topics=affected_topics or [],
            affected_runs=affected_runs or [],
            urgency=urgency,  # type: ignore[arg-type]
            required_source_types=required_source_types or [],  # type: ignore[arg-type]
            current_evidence=current_evidence or [],
        )
        return self.store.add_gap(gap)

