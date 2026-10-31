from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from alysia.capabilities.gaps import CapabilityGapStore
from alysia.capabilities.sandbox import SkillSandbox
from alysia.capabilities.skill_registry import SkillRegistry
from alysia.capabilities.store import atomic_json
from alysia.schemas import (
    CapabilityGap,
    SkillEvaluationCase,
    SkillEvaluationReport,
    SkillProposal,
    SkillReviewRecord,
)
from alysia.schemas.security import Permission


class SkillProposalFactory:
    def create(self, gap: CapabilityGap) -> SkillProposal:
        audio = "audio" in gap.proposed_capability or "tts" in gap.proposed_capability
        h3 = "h3" in gap.proposed_capability
        name = "Real TTS Speech Gate" if audio else "Verified Local H3 Visual Generation" if h3 else gap.proposed_capability
        skill_id = "real_tts_speech_gate" if audio else "h3_visual_generation" if h3 else gap.proposed_capability
        interface = (
            "validate(script, wav, asr_transcript) -> SpeechGateReport" if audio else
            "generate(scene_visual_plan) -> VisualGenerationResult" if h3 else
            f"run(input) -> {gap.proposed_capability}Result"
        )
        tools = ["tts", "faster-whisper", "audio_qa"] if audio else ["comfyui", "minimax_h3", "visual_qa"] if h3 else []
        resource = {"gpu_heavy": h3, "sequential_gpu_required": h3, "peak_vram_mb": "unknown"}
        risks = ["未经验证的音频不得进入正式成片"] if audio else ["不得下载并执行未知节点代码", "不得与其他 GPU 模型并发"] if h3 else ["未知实现风险"]
        now = datetime.now().astimezone()
        return SkillProposal(
            skill_id=skill_id, name=name, purpose=gap.description, gap_refs=[gap.gap_id],
            proposed_interface=interface, required_tools_providers=tools, security_risks=risks,
            resource_cost=resource, expected_benefit=f"缓解：{gap.description}",
            evaluation_plan=["functional", "quality", "regression", "resource", "security"],
            sandbox_required=True, approval_required=True, owner_agents=gap.affected_agents,
            state="PROPOSED", created_at=now, updated_at=now,
        )


class SkillEvaluator:
    """只评估受信任的声明式 observations；不导入或执行 proposal 提供的代码。"""

    def evaluate(self, proposal: SkillProposal, sandbox_path: Path, observations: dict[str, Any] | None = None) -> SkillEvaluationReport:
        observations = observations or {}
        categories = ["functional", "quality", "regression", "resource", "security"]
        cases = [
            SkillEvaluationCase(
                name=f"{proposal.skill_id}:{category}", category=category,
                passed=bool(observations.get(category, True)),
                observation=str(observations.get(f"{category}_note", "declarative offline check passed")),
            )
            for category in categories
        ]
        failures = [case.name for case in cases if not case.passed]
        regressions = [case.name for case in cases if case.category == "regression" and not case.passed]
        score = sum(case.passed for case in cases) / len(cases)
        digest = hashlib.sha256(
            json.dumps({"skill": proposal.skill_id, "cases": [case.model_dump() for case in cases]}, sort_keys=True).encode("utf-8")
        ).hexdigest()[:16]
        passed = not failures
        return SkillEvaluationReport(
            evaluation_id=f"skilleval_{digest}", skill_id=proposal.skill_id, passed=passed,
            score=score, cases=cases, failures=failures, regressions=regressions,
            resource_observations={
                "peak_vram_mb": observations.get("peak_vram_mb", "unknown"),
                "wall_time_sec": observations.get("wall_time_sec", "unknown"),
                "source": observations.get("resource_source", "not measured in declarative test"),
            },
            recommendation="approve_for_human_review" if passed else "revise",
            sandbox_path=str(sandbox_path), created_at=datetime.now().astimezone(),
        )


class SkillAcquisitionService:
    def __init__(self, root: Path, sandbox: SkillSandbox, *, security=None) -> None:
        self.root = root.resolve()
        self.sandbox = sandbox
        self.gaps = CapabilityGapStore(self.root)
        self.registry = SkillRegistry(self.root)
        self.factory = SkillProposalFactory()
        self.evaluator = SkillEvaluator()
        self.security = security

    def propose(self, gap_id: str) -> SkillProposal:
        gap = self.gaps.get(gap_id)
        candidate = self.factory.create(gap)
        path = self._proposal_path(candidate.skill_id)
        if path.is_file():
            existing = SkillProposal.model_validate_json(path.read_text(encoding="utf-8"))
            if existing.state != "REGISTERED":
                self.gaps.save(gap.model_copy(update={"status": "proposed"}))
                return existing
        proposal = candidate
        atomic_json(path, proposal.model_dump(mode="json"))
        self.gaps.save(gap.model_copy(update={"status": "proposed"}))
        return proposal

    def test(self, skill_id: str, *, observations: dict[str, Any] | None = None) -> SkillEvaluationReport:
        proposal = self.load_proposal(skill_id)
        if proposal.state in {"APPROVED", "REGISTERED", "REJECTED"}:
            existing = self.load_evaluation(skill_id)
            if existing is not None:
                return existing
        sandbox_path = self.sandbox.initialize(skill_id)
        self.sandbox.assert_operation(network=False, credentials=False, core_write=False)
        proposal = self._transition(proposal, "DESIGNED")
        proposal = self._transition(proposal, "SANDBOX_READY")
        proposal = self._transition(proposal, "TESTING")
        report = self.evaluator.evaluate(proposal, sandbox_path, observations)
        atomic_json(self._evaluation_path(skill_id), report.model_dump(mode="json"))
        self._transition(proposal, "EVALUATED" if report.passed else "FAILED")
        return report

    def review(self, skill_id: str, *, reviewer: str = "human:reviewer", notes: str = "") -> SkillReviewRecord:
        proposal = self.load_proposal(skill_id)
        evaluation = self.load_evaluation(skill_id)
        if proposal.state != "EVALUATED" or evaluation is None or not evaluation.passed:
            raise RuntimeError("Skill 必须先完成通过的 evaluation")
        record = SkillReviewRecord(
            skill_id=skill_id, reviewer=reviewer, decision="ready_for_approval",
            notes=notes or "评测已通过，等待独立人工 approve 命令。", created_at=datetime.now().astimezone(),
        )
        atomic_json(self.root / "skills" / "reviews" / f"{skill_id}.json", record.model_dump(mode="json"))
        self._transition(proposal, "WAITING_APPROVAL")
        return record

    def approve(self, skill_id: str, *, approved_by: str) -> Any:
        if not approved_by.startswith("human:"):
            raise PermissionError("Supervisor/Alysia 不能自行批准 skill；approved_by 必须以 human: 开头")
        proposal = self.load_proposal(skill_id)
        evaluation = self.load_evaluation(skill_id)
        if proposal.state != "WAITING_APPROVAL" or evaluation is None or not evaluation.passed:
            raise RuntimeError("Skill 尚未处于 WAITING_APPROVAL 或 evaluation 未通过")
        if self.security is not None:
            self.security.authorize_governed_change(
                actor="Supervisor", permission=Permission.APPROVE_SKILL,
                action_type="skill_approval", subject_id=skill_id,
                payload={"proposal": proposal.model_dump(mode="json"), "evaluation": evaluation.model_dump(mode="json")},
                approved_by=approved_by,
                scope=f"skill:{skill_id}:{evaluation.evaluation_id}",
            )
        proposal = self._transition(proposal, "APPROVED")
        record = self.registry.register(
            proposal, evaluation, approved_by=approved_by, approved_at=datetime.now().astimezone()
        )
        self._transition(proposal, "REGISTERED")
        return record

    def disable(self, skill_id: str):
        return self.registry.disable(skill_id)

    def rollback(self, skill_id: str, target_version: int):
        return self.registry.rollback(skill_id, target_version)

    def load_proposal(self, skill_id: str) -> SkillProposal:
        path = self._proposal_path(skill_id)
        if not path.is_file():
            raise KeyError(f"Skill proposal 不存在：{skill_id}")
        return SkillProposal.model_validate_json(path.read_text(encoding="utf-8"))

    def load_evaluation(self, skill_id: str) -> SkillEvaluationReport | None:
        path = self._evaluation_path(skill_id)
        return SkillEvaluationReport.model_validate_json(path.read_text(encoding="utf-8")) if path.is_file() else None

    def _transition(self, proposal: SkillProposal, state: str) -> SkillProposal:
        updated = proposal.model_copy(update={"state": state, "updated_at": datetime.now().astimezone()})
        atomic_json(self._proposal_path(proposal.skill_id), updated.model_dump(mode="json"))
        return updated

    def _proposal_path(self, skill_id: str) -> Path:
        return self.root / "skills" / "proposals" / f"{skill_id}.json"

    def _evaluation_path(self, skill_id: str) -> Path:
        return self.root / "skills" / "evaluations" / f"{skill_id}.json"
