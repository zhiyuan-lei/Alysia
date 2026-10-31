from __future__ import annotations

import re
from pathlib import Path

from alysia.knowledge.freshness import FreshnessPolicy
from alysia.knowledge.models import GroundingReport, SectionGrounding
from alysia.knowledge.store import KnowledgeStore
from alysia.knowledge.quality import SourceQualityEvaluator
from alysia.schemas.script import Script


class GroundingChecker:
    FACT_MARKERS = ("数据", "研究", "版本", "支持", "参数", "价格", "截至", "目前", "事实", "定义")

    def __init__(self, store: KnowledgeStore, freshness: FreshnessPolicy) -> None:
        self.store = store
        self.freshness = freshness
        self.source_quality = SourceQualityEvaluator()

    def check(
        self,
        script: Script,
        *,
        run_id: str,
        factual_section_ids: set[str] | None = None,
    ) -> GroundingReport:
        sections: list[SectionGrounding] = []
        stale_refs: set[str] = set()
        conflicted_refs: set[str] = set()
        for section in script.sections:
            factual = (
                section.id in factual_section_ids
                if factual_section_ids is not None
                else self._looks_factual(section.narration, section.claim_refs, section.source_refs)
            )
            issues: list[str] = []
            supported = not factual
            valid_claims = 0
            for claim_id in section.claim_refs:
                try:
                    claim = self.store.get_claim(claim_id)
                except FileNotFoundError:
                    issues.append(f"unknown_claim:{claim_id}")
                    continue
                assessment = self.freshness.assess(claim)
                if assessment.state in {"stale", "reverify_required"} or claim.status == "stale":
                    stale_refs.add(claim_id)
                    issues.append(f"stale_claim:{claim_id}")
                elif claim.status == "conflicted":
                    conflicted_refs.add(claim_id)
                    issues.append(f"conflicted_claim:{claim_id}")
                elif claim.status in {"verified", "provisional"}:
                    valid_claims += 1
            valid_sources = 0
            for source_id in section.source_refs:
                try:
                    source = self.store.get_source(source_id)
                except FileNotFoundError:
                    issues.append(f"unknown_source:{source_id}")
                    continue
                if source.evidence_origin in {"mock", "trend", "simulation", "feedback"}:
                    issues.append(f"inadmissible_source:{source_id}")
                elif self.source_quality.evaluate(source).score < 0.55:
                    issues.append(f"low_quality_source:{source_id}")
                else:
                    valid_sources += 1
            if factual:
                supported = (valid_claims > 0 or valid_sources > 0) and not any(
                    issue.startswith(("stale_claim", "conflicted_claim", "inadmissible_source", "low_quality_source"))
                    for issue in issues
                )
                if not section.claim_refs and not section.source_refs:
                    issues.append("unsupported_factual_section")
            sections.append(
                SectionGrounding(
                    section_id=section.id,
                    claim_refs=list(section.claim_refs),
                    source_refs=list(section.source_refs),
                    factual=factual,
                    supported=supported,
                    issues=issues,
                )
            )
        factual_sections = [item for item in sections if item.factual]
        supported_sections = [item.section_id for item in factual_sections if item.supported]
        unsupported_sections = [item.section_id for item in factual_sections if not item.supported]
        coverage = 1.0 if not factual_sections else len(supported_sections) / len(factual_sections)
        return GroundingReport(
            run_id=run_id,
            supported_sections=supported_sections,
            unsupported_sections=unsupported_sections,
            stale_claim_refs=sorted(stale_refs),
            conflicted_claim_refs=sorted(conflicted_refs),
            citation_coverage=round(coverage, 4),
            sections=sections,
            passed=not unsupported_sections and not stale_refs and not conflicted_refs,
        )

    @classmethod
    def _looks_factual(cls, narration: str, claim_refs: list[str], source_refs: list[str]) -> bool:
        return bool(claim_refs or source_refs or re.search(r"\d", narration) or any(marker in narration for marker in cls.FACT_MARKERS))

    @staticmethod
    def save(report: GroundingReport, run_dir: Path) -> Path:
        from alysia.knowledge.store import KnowledgeStore

        path = run_dir / "knowledge" / "grounding_report.json"
        KnowledgeStore._write(path, report.model_dump(mode="json"))
        return path
