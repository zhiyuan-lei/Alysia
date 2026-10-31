from __future__ import annotations

from pathlib import Path

from alysia.core.config import AlysiaConfig
from alysia.knowledge.context import KnowledgeContextSelector
from alysia.knowledge.freshness import FreshnessPolicy
from alysia.knowledge.grounding import GroundingChecker
from alysia.knowledge.maintenance import KnowledgeMaintenanceService
from alysia.knowledge.pipeline import ResearchKnowledgePipeline
from alysia.knowledge.qa import KnowledgeQA
from alysia.knowledge.store import KnowledgeStore
from alysia.knowledge.tasks import KnowledgeGapDetector, ResearchTaskPlanner
from alysia.knowledge.verification import ClaimVerifier


class KnowledgeService:
    def __init__(self, config: AlysiaConfig, *, root: Path | None = None) -> None:
        self.config = config
        self.store = KnowledgeStore(root or config.knowledge.root_dir)
        self.freshness = FreshnessPolicy(
            software_days=config.freshness.software_days,
            pricing_days=config.freshness.pricing_days,
            current_roles_days=config.freshness.current_roles_days,
            stable_definition_days=config.freshness.stable_definition_days,
        )
        self.pipeline = ResearchKnowledgePipeline(self.store)
        self.verifier = ClaimVerifier(self.store)
        self.maintenance = KnowledgeMaintenanceService(self.store, self.freshness)
        self.grounding = GroundingChecker(self.store, self.freshness)
        self.qa = KnowledgeQA(self.store, self.freshness)
        self.context = KnowledgeContextSelector(self.store, self.freshness)
        self.research_tasks = ResearchTaskPlanner(
            self.store,
            max_sources=config.knowledge.max_research_sources,
            max_rounds=config.knowledge.max_research_rounds,
        )
        self.gaps = KnowledgeGapDetector(self.store)

