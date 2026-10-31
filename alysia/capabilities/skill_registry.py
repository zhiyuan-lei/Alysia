from __future__ import annotations

from pathlib import Path

from alysia.capabilities.store import atomic_json, load_models
from alysia.schemas import SkillEvaluationReport, SkillProposal, SkillRecord


class SkillRegistry:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.directory = self.root / "skills" / "registry"

    def register(
        self,
        proposal: SkillProposal,
        evaluation: SkillEvaluationReport,
        *,
        approved_by: str,
        approved_at,
    ) -> SkillRecord:
        if proposal.state != "APPROVED":
            raise PermissionError("只有 APPROVED skill 才能注册")
        if not approved_by.startswith("human:"):
            raise PermissionError("Skill 必须由显式 human reviewer 批准")
        if not evaluation.passed:
            raise ValueError("未通过评测的 skill 不能注册")
        versions = self.versions(proposal.skill_id)
        version = max((item.version for item in versions), default=0) + 1
        for record in versions:
            if record.status == "active":
                self._save(record.model_copy(update={"status": "deprecated"}))
        record = SkillRecord(
            skill_id=proposal.skill_id, name=proposal.name, version=version, status="active",
            provenance={"source": "alpha14 controlled proposal", "sandbox": evaluation.sandbox_path},
            proposal_ref=f"proposals/{proposal.skill_id}.json",
            evaluation_ref=f"evaluations/{proposal.skill_id}.json",
            approved_by=approved_by, approved_at=approved_at, owner_agents=proposal.owner_agents,
            interface=proposal.proposed_interface, resource_requirements=proposal.resource_cost,
            rollback_target=versions[-1].version if versions else None,
            **_skill_contract(proposal.skill_id),
        )
        return self._save(record)

    def available(self, agent_id: str | None = None) -> list[SkillRecord]:
        records = [item for item in self.list() if item.status == "active"]
        return [item for item in records if agent_id is None or agent_id in item.owner_agents]

    def list(self) -> list[SkillRecord]:
        if not self.directory.is_dir():
            return []
        records = []
        for path in sorted(self.directory.glob("*/v*.json")):
            record = SkillRecord.model_validate_json(path.read_text(encoding="utf-8"))
            if not record.accepted_inputs and not record.produced_outputs:
                record = record.model_copy(update=_skill_contract(record.skill_id))
            records.append(record)
        return records

    def versions(self, skill_id: str) -> list[SkillRecord]:
        return sorted([item for item in self.list() if item.skill_id == skill_id], key=lambda item: item.version)

    def active(self, skill_id: str) -> SkillRecord:
        matches = [item for item in self.versions(skill_id) if item.status == "active"]
        if not matches:
            raise KeyError(f"没有 active skill：{skill_id}")
        return matches[-1]

    def disable(self, skill_id: str) -> SkillRecord:
        current = self.active(skill_id)
        return self._save(current.model_copy(update={"status": "disabled"}))

    def rollback(self, skill_id: str, target_version: int) -> SkillRecord:
        versions = self.versions(skill_id)
        target = next((item for item in versions if item.version == target_version), None)
        if target is None:
            raise KeyError(f"Skill rollback target 不存在：{skill_id} v{target_version}")
        for item in versions:
            if item.status == "active":
                self._save(item.model_copy(update={"status": "rolled_back", "rollback_target": target_version}))
        return self._save(target.model_copy(update={"status": "active"}))

    def _save(self, record: SkillRecord) -> SkillRecord:
        path = self.directory / record.skill_id / f"v{record.version:04d}.json"
        atomic_json(path, record.model_dump(mode="json"))
        return record


def _skill_contract(skill_id: str) -> dict:
    """受信任的 alpha14 skill contract；未知 proposal 不猜测可组合接口。"""
    if skill_id == "h3_visual_generation":
        return {
            "tags": ["visual", "h3", "video_generation"],
            "accepted_inputs": ["scene_visual_plan"],
            "produced_outputs": ["visual_clip"],
            "prerequisites": ["visual_planning"],
            "policy_restrictions": ["sequential_gpu", "no_mock_in_production"],
            "execution_layer": "production",
        }
    if skill_id == "real_tts_speech_gate":
        return {
            "tags": ["audio", "qa", "speech"],
            "accepted_inputs": ["script", "audio", "asr_transcript"],
            "produced_outputs": ["speech_gate_report"],
            "prerequisites": ["tts"],
            "policy_restrictions": ["no_mock_in_production"],
            "execution_layer": "studio",
        }
    return {
        "tags": [], "accepted_inputs": [], "produced_outputs": [], "prerequisites": [],
        "policy_restrictions": ["contract_not_declared"], "execution_layer": "workflow",
    }
