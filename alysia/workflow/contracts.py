from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from alysia.capabilities import CapabilityRegistry, SkillRegistry
from alysia.schemas import Capability, SkillRecord


@dataclass(frozen=True)
class RegisteredContract:
    implementation_id: str
    source_type: str
    version: int | None
    status: str
    owner_agent: str
    accepted_inputs: tuple[str, ...]
    produced_outputs: tuple[str, ...]
    prerequisites: tuple[str, ...]
    tags: tuple[str, ...]
    resource_requirements: dict
    policy_restrictions: tuple[str, ...]
    execution_layer: str
    maturity: str


class RegistryView:
    """将 alpha14 capability/skill registries 投影成只读 composition contracts。"""

    def __init__(self, capabilities: CapabilityRegistry, skills: SkillRegistry) -> None:
        self.capabilities = capabilities
        self.skills = skills

    def all(self) -> list[RegisteredContract]:
        return [self._capability(item) for item in self.capabilities.bootstrap()] + [
            self._skill(item) for item in self.skills.list()
        ]

    def eligible(self) -> list[RegisteredContract]:
        return [
            item for item in self.all()
            if (item.source_type == "capability" and item.status != "deprecated")
            or (item.source_type == "skill" and item.status == "active")
        ]

    def get(self, implementation_id: str, *, source_type: str | None = None) -> RegisteredContract:
        matches = [
            item for item in self.all()
            if item.implementation_id == implementation_id
            and (source_type is None or item.source_type == source_type)
        ]
        if not matches:
            raise KeyError(f"Registry 中不存在能力：{implementation_id}")
        active = [item for item in matches if item.status == "active"]
        return (active or matches)[-1]

    @staticmethod
    def _capability(item: Capability) -> RegisteredContract:
        return RegisteredContract(
            implementation_id=item.capability_id, source_type="capability", version=None,
            status=item.maturity, owner_agent=item.owner_agent,
            accepted_inputs=tuple(item.accepted_inputs), produced_outputs=tuple(item.produced_outputs),
            prerequisites=tuple(item.prerequisites), tags=tuple(item.tags),
            resource_requirements=dict(item.resource_requirements),
            policy_restrictions=tuple(item.policy_restrictions), execution_layer=item.execution_layer,
            maturity=item.maturity,
        )

    @staticmethod
    def _skill(item: SkillRecord) -> RegisteredContract:
        return RegisteredContract(
            implementation_id=item.skill_id, source_type="skill", version=item.version,
            status=item.status, owner_agent=item.owner_agents[0] if item.owner_agents else "unknown",
            accepted_inputs=tuple(item.accepted_inputs), produced_outputs=tuple(item.produced_outputs),
            prerequisites=tuple(item.prerequisites), tags=tuple(item.tags),
            resource_requirements=dict(item.resource_requirements),
            policy_restrictions=tuple(item.policy_restrictions), execution_layer=item.execution_layer,
            maturity="stable" if item.status == "active" else "deprecated",
        )

    def versions(self) -> dict[str, str]:
        versions: dict[str, str] = {}
        for item in self.eligible():
            versions[item.implementation_id] = (
                f"skill:v{item.version}" if item.source_type == "skill" else f"capability:{item.maturity}"
            )
        return versions


def contracts_producing(contracts: Iterable[RegisteredContract], artifact: str) -> list[RegisteredContract]:
    return [item for item in contracts if artifact in item.produced_outputs]
