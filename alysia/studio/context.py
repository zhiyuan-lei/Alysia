from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from alysia.core.config import AlysiaConfig
from alysia.core.run import RunManager
from alysia.identity import IdentityService
from alysia.learning.memory import MemoryStore
from alysia.knowledge import KnowledgeService
from alysia.operations import ChannelStore
from alysia.production import ProductionService
from alysia.studio.protocol import AgentDecision, ArtifactRef, studio_now
from alysia.studio.registry import AgentRegistry
from alysia.studio.trace import StudioTraceStore


class StudioContext(BaseModel):
    run_id: str
    goal: str
    topic: str
    creator_identity_version: int | None = None
    brand_voice_version: int | None = None
    production_plan_id: str | None = None
    strategy_refs: list[dict[str, Any]] = Field(default_factory=list)
    experiment_refs: list[dict[str, Any]] = Field(default_factory=list)
    relevant_lessons: list[dict[str, Any]] = Field(default_factory=list)
    artifact_refs: list[ArtifactRef] = Field(default_factory=list)
    constraints: dict[str, Any] = Field(default_factory=dict)
    approvals: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    decisions: list[AgentDecision] = Field(default_factory=list)
    identity_summary: dict[str, Any] = Field(default_factory=dict)
    brand_voice_summary: dict[str, Any] = Field(default_factory=dict)
    knowledge_refs: list[dict[str, Any]] = Field(default_factory=list)
    knowledge_warnings: list[str] = Field(default_factory=list)
    version: int = Field(default=1, ge=1)
    updated_at: datetime = Field(default_factory=studio_now)

    def add_artifacts(self, artifacts: list[ArtifactRef]) -> None:
        by_id = {item.artifact_id: item for item in self.artifact_refs}
        by_id.update({item.artifact_id: item for item in artifacts})
        self.artifact_refs = list(by_id.values())
        self.bump()

    def add_decisions(self, decisions: list[AgentDecision]) -> None:
        by_id = {item.decision_id: item for item in self.decisions}
        by_id.update({item.decision_id: item for item in decisions})
        self.decisions = list(by_id.values())
        self.bump()

    def add_warning(self, warning: str) -> None:
        if warning not in self.warnings:
            self.warnings.append(warning)
            self.bump()

    def bump(self) -> None:
        self.version += 1
        self.updated_at = studio_now()


class StudioContextView(BaseModel):
    run_id: str
    agent_id: str
    goal: str
    topic: str
    production_plan_id: str | None
    artifact_refs: list[ArtifactRef]
    constraints: dict[str, Any]
    approvals: dict[str, Any]
    warnings: list[str]
    role_context: dict[str, Any]
    context_version: int


class ContextPolicy:
    _ROLE_KEYS: dict[str, set[str]] = {
        "researcher": {"identity_summary", "knowledge_warnings"},
        "writer": {"identity_summary", "brand_voice_summary", "strategy_refs", "experiment_refs", "relevant_lessons", "knowledge_refs", "knowledge_warnings"},
        "storyboard_director": {"identity_summary", "brand_voice_summary"},
        "designer": {"identity_summary", "brand_voice_summary"},
        "voice": set(),
        "editor": set(),
        "critic": {"identity_summary", "brand_voice_summary", "strategy_refs", "experiment_refs", "knowledge_refs", "knowledge_warnings"},
        "publisher": {"identity_summary", "brand_voice_summary"},
        "analyst": {"strategy_refs", "experiment_refs", "relevant_lessons"},
    }

    def allowed_keys(self, agent_id: str) -> set[str]:
        if agent_id not in self._ROLE_KEYS:
            raise KeyError(f"未定义 ContextPolicy：{agent_id}")
        return set(self._ROLE_KEYS[agent_id])


class ContextSelector:
    def __init__(self, registry: AgentRegistry, policy: ContextPolicy | None = None) -> None:
        self.registry = registry
        self.policy = policy or ContextPolicy()

    def select(self, context: StudioContext, agent_id: str) -> StudioContextView:
        profile = self.registry.get(agent_id)
        accepted = set(profile.accepted_inputs)
        artifact_refs = [
            item
            for item in context.artifact_refs
            if item.active and (item.kind in accepted
            or item.kind in {"text_qa", "audio_qa", "video_qa", "publish_qa", "script_review", "final_review", "revision_request"}
            )
        ]
        role_context = {
            key: getattr(context, key)
            for key in self.policy.allowed_keys(agent_id)
        }
        return StudioContextView(
            run_id=context.run_id,
            agent_id=agent_id,
            goal=context.goal,
            topic=context.topic,
            production_plan_id=context.production_plan_id,
            artifact_refs=artifact_refs,
            constraints=dict(context.constraints),
            approvals=dict(context.approvals),
            warnings=list(context.warnings),
            role_context=role_context,
            context_version=context.version,
        )


class StudioContextFactory:
    def __init__(self, config: AlysiaConfig, registry: AgentRegistry) -> None:
        self.config = config
        self.registry = registry
        self.manager = RunManager(config.runtime.runs_dir)

    def build(self, run_id: str, store: StudioTraceStore) -> StudioContext:
        state = self.manager.load(run_id)
        channel_id = (state.planning_provenance or {}).get(
            "channel_id", self.config.operations.default_channel_id
        )
        identity = IdentityService(self.config).ensure() if self.config.identity.enabled else None
        knowledge_context = (
            KnowledgeService(self.config).context.select(state.topic, role="writer")
            if self.config.knowledge.enabled
            else None
        )
        memory = MemoryStore(self.config.learning.memory_dir)
        channels = ChannelStore(self.config.learning.memory_dir)
        strategies = memory.list_strategies(channel_id)
        lessons = memory.list_lessons()
        experiments = channels.list_experiments(channel_id)
        try:
            plan = ProductionService(self.config).load_plan(run_id)
        except FileNotFoundError:
            plan = None
        approvals = {
            "topic_approved": bool(state.planning_provenance),
            "production_policy_approved": (self.manager.run_dir(run_id) / "production" / "policy_approval.json").is_file(),
            "publish_approved": (self.manager.run_dir(run_id) / "publish" / "approval_record.json").is_file(),
        }
        context = StudioContext(
            run_id=run_id,
            goal=f"为主题“{state.topic}”完成可审核的创作者工作流",
            topic=state.topic,
            creator_identity_version=identity.version if identity else None,
            brand_voice_version=identity.version if identity else None,
            production_plan_id=plan.plan_id if plan else None,
            strategy_refs=[
                {"id": item.id, "status": item.status, "rule": item.rule}
                for item in strategies[-5:]
            ],
            experiment_refs=[
                {"id": item.id, "status": item.status, "hypothesis": item.hypothesis}
                for item in experiments[-3:]
            ],
            relevant_lessons=[
                {"id": item.id, "status": item.status, "statement": item.statement, "confidence": item.confidence}
                for item in lessons[-5:]
            ],
            artifact_refs=store.artifacts(),
            constraints={
                "mode": self.config.studio.mode,
                "max_review_rounds": self.config.studio.max_review_rounds,
                "max_agent_hops": self.config.studio.max_agent_hops,
                "production_quality": self.config.production.quality_target,
                "sequential_gpu_required": self.config.production.sequential_gpu_required,
                "human_approval_required": True,
            },
            approvals=approvals,
            identity_summary=(
                {
                    "creator_name": identity.creator_name,
                    "mission_statement": identity.mission_statement,
                    "target_audience": identity.target_audience,
                    "expertise_domains": identity.expertise_domains,
                    "disclosure_policy": identity.disclosure_policy,
                }
                if identity
                else {}
            ),
            brand_voice_summary=(
                identity.communication_style.model_dump(mode="json") if identity else {}
            ),
            knowledge_refs=(
                [
                    {
                        "claim_id": item.claim_id,
                        "statement": item.statement,
                        "status": item.status,
                        "confidence": item.confidence,
                        "evidence_refs": item.evidence_refs,
                    }
                    for item in knowledge_context.claims
                ]
                if knowledge_context
                else []
            ),
            knowledge_warnings=knowledge_context.warnings if knowledge_context else [],
            version=store.latest_context_version() + 1,
        )
        store.save_context_snapshot(context, context.version)
        return context
