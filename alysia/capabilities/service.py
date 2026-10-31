from __future__ import annotations

from pathlib import Path
import json

from alysia.capabilities.evaluation import EvidenceCollector, SelfEvaluationEngine
from alysia.capabilities.gaps import CapabilityGapDetector, CapabilityGapStore
from alysia.capabilities.registry import CapabilityRegistry
from alysia.capabilities.sandbox import SkillSandbox
from alysia.capabilities.skills import SkillAcquisitionService
from alysia.capabilities.store import atomic_json
from alysia.core.config import AlysiaConfig
from alysia.schemas import SkillSecurityPolicy
from alysia.security import SecurityService


class CapabilityService:
    def __init__(self, config: AlysiaConfig) -> None:
        self.config = config
        self.root = config.capability.root_dir.resolve()
        self.registry = CapabilityRegistry(self.root)
        self.gaps = CapabilityGapStore(self.root)
        self.security = SecurityService(config)
        policy = SkillSecurityPolicy(
            network_allowed=config.capability.allow_network_in_sandbox,
            credentials_allowed=config.capability.allow_credentials_in_sandbox,
            core_source_write_allowed=config.capability.allow_core_source_write,
            allowed_write_roots=[str(config.capability.sandbox_dir), "tests/fixtures"],
        )
        sandbox = SkillSandbox(Path.cwd(), config.capability.sandbox_dir, policy, security=self.security)
        self.skills = SkillAcquisitionService(self.root, sandbox, security=self.security)

    def list_capabilities(self):
        return self.registry.bootstrap()

    def evaluate(self):
        evidence = EvidenceCollector(
            self.config.capability.evidence_files,
            self.config.runtime.runs_dir,
            self.config.supervisor.root_dir,
        ).collect()
        report = SelfEvaluationEngine().evaluate(self.registry, evidence)
        atomic_json(self.root / "reports" / f"{report.report_id}.json", report.model_dump(mode="json"))
        atomic_json(self.root / "reports" / "latest.json", report.model_dump(mode="json"))
        detector = CapabilityGapDetector(minimum_evidence_count=self.config.capability.minimum_evidence_count)
        for gap in detector.detect(report):
            for proposal_path in (self.root / "skills" / "proposals").glob("*.json"):
                try:
                    proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                if gap.gap_id in proposal.get("gap_refs", []):
                    gap = gap.model_copy(update={"status": "proposed"})
                    break
            self.gaps.save(gap)
        return report

    def list_gaps(self):
        return self.gaps.list()
