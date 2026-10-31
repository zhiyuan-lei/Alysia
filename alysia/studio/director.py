from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from alysia.core.config import AlysiaConfig
from alysia.core.orchestrator import AlysiaOrchestrator
from alysia.core.run import RunManager, RunState
from alysia.production import ProductionService
from alysia.production.service import ProductionPolicyError
from alysia.studio.agents import StudioRuntime, classify_failure, default_studio_agents
from alysia.studio.context import ContextSelector, StudioContext, StudioContextFactory
from alysia.studio.handoff import HandoffProtocol
from alysia.studio.ownership import ArtifactCatalog
from alysia.studio.protocol import (
    AgentFailure,
    AgentHandoff,
    AgentResult,
    StudioState,
    StudioTraceEvent,
    stable_studio_id,
    studio_now,
)
from alysia.studio.qa import StudioQA
from alysia.studio.registry import AgentRegistry
from alysia.studio.trace import StudioTraceStore


@dataclass(frozen=True)
class RouteDecision:
    agent_id: str | None
    reason: str
    wait_status: str | None = None


class DirectorDecisionEngine:
    """规则约束的下一角色选择；LLM 建议不能覆盖这些硬规则。"""

    def decide(
        self,
        run_state: RunState,
        studio_state: StudioState,
        artifacts: set[str],
        approvals: dict[str, Any],
        *,
        manager: RunManager,
    ) -> RouteDecision:
        if "research" not in artifacts:
            return RouteDecision("researcher", "缺少 research artifact")
        if "script" not in artifacts:
            return RouteDecision("writer", "缺少 script artifact")
        if "script_review" not in artifacts:
            return RouteDecision("critic", "Writer 输出必须先经过受控 script review")
        if "storyboard" not in artifacts:
            return RouteDecision("storyboard_director", "缺少 storyboard artifact")
        if "text_qa" not in artifacts:
            return RouteDecision("critic", "Research/Script/Storyboard 必须通过现有 Text QA")
        if "design_plan" not in artifacts or "publish_cover" not in artifacts:
            return RouteDecision("designer", "缺少 Designer-owned 视觉计划或封面")

        if _report_failed(run_state, manager, "audio_qa_report"):
            return RouteDecision("voice", "Audio QA fail，返回 artifact owner VoiceAgent")
        if not {"audio", "subtitles", "audio_qa"} <= artifacts:
            return RouteDecision("voice", "缺少音频、字幕或 Audio QA artifact")
        if _report_failed(run_state, manager, "video_qa_report"):
            return RouteDecision("editor", "Video QA fail，返回 artifact owner EditorAgent")
        if not {"composition", "final_video", "video_qa"} <= artifacts:
            return RouteDecision("editor", "缺少 composition、final_video 或 Video QA artifact")
        if "final_review" not in artifacts:
            return RouteDecision("critic", "成片必须经过跨阶段最终审查")
        if not {"publish_package", "publish_qa"} <= artifacts:
            return RouteDecision("publisher", "缺少投稿包或 Publish QA")
        if not approvals.get("publish_approved"):
            return RouteDecision(None, "等待 Human Publish Approval Gate", "waiting_for_approval")
        if "publish_validation" not in artifacts:
            return RouteDecision("publisher", "人工批准后需要重新验证 package hash 与 warnings")
        if run_state.analytics_imported and not {
            "analytics",
            "memory",
            "strategy",
            "experiment",
        } <= artifacts:
            return RouteDecision("analyst", "已有 Analytics 输入，进入 evidence-bound learning")
        if not run_state.analytics_imported:
            return RouteDecision(None, "等待发布后 Analytics/Feedback 输入", "waiting_for_approval")
        return RouteDecision(None, "Studio 所需 artifact 与分析均已完成")


class StudioDirector:
    def __init__(
        self,
        config: AlysiaConfig,
        *,
        orchestrator: AlysiaOrchestrator | None = None,
        registry: AgentRegistry | None = None,
    ) -> None:
        if config.studio.mode != "sequential":
            raise ValueError("alpha12 仅支持 sequential Studio mode")
        self.config = config
        self.manager = RunManager(config.runtime.runs_dir)
        self.orchestrator = orchestrator or AlysiaOrchestrator(config)
        self.registry = registry or AgentRegistry()
        self.selector = ContextSelector(self.registry)
        self.engine = DirectorDecisionEngine()
        self.agents = default_studio_agents()

    async def run(self, run_id: str) -> StudioState:
        if not self.config.studio.enabled:
            raise RuntimeError("Studio 已在配置中禁用")
        run_state = self.manager.load(run_id)
        store = StudioTraceStore(self.manager, run_id)
        catalog = ArtifactCatalog(store, self.registry)
        self._adopt_existing(run_state, catalog)
        studio_state = store.load_state() or StudioState(run_id=run_id)
        try:
            plan = ProductionService(self.config).ensure_plan(run_state, requested_operation="full")
            studio_state.production_plan_id = plan.plan_id
        except ProductionPolicyError as exc:
            studio_state.status = "waiting_for_approval"
            studio_state.escalation = AgentFailure(
                kind="approval_required",
                agent_id="studio_director",
                message=str(exc),
                recoverable=False,
            )
            studio_state.last_error = str(exc)
            studio_state.updated_at = studio_now()
            store.save_state(studio_state)
            self._trace(store, studio_state, "approval_required", "ProductionPolicy Gate 阻止 Studio")
            return studio_state

        context = StudioContextFactory(self.config, self.registry).build(run_id, store)
        context.decisions = store.decisions()
        for result in store.results():
            for warning in result.warnings:
                if warning not in context.warnings:
                    context.warnings.append(warning)
        context.version += 1
        store.save_context_snapshot(context, context.version)
        studio_state.status = "running"
        studio_state.escalation = None
        studio_state.last_error = None
        store.save_state(studio_state)
        self._trace(store, studio_state, "studio_started", "StudioDirector 开始或恢复串行协作")

        runtime = StudioRuntime(
            config=self.config,
            orchestrator=self.orchestrator,
            registry=self.registry,
            catalog=catalog,
            store=store,
        )
        while True:
            run_state = self.manager.load(run_id)
            self._adopt_existing(run_state, catalog)
            context.artifact_refs = store.artifacts()
            context.approvals.update(self._approval_state(run_id, run_state))

            revision_owner = self._pending_revision_owner(store)
            if revision_owner:
                decision = RouteDecision(revision_owner, "处理已登记的 artifact revision request")
            else:
                decision = self.engine.decide(
                    run_state,
                    studio_state,
                    catalog.available_kinds(),
                    context.approvals,
                    manager=self.manager,
                )
            self._trace(
                store,
                studio_state,
                "route_decision",
                decision.reason,
                metadata={"selected_agent": decision.agent_id},
            )
            if decision.agent_id is None:
                if decision.wait_status:
                    studio_state.status = "waiting_for_approval"
                    studio_state.last_error = decision.reason
                else:
                    studio_state.status = "completed"
                    studio_state.last_error = None
                studio_state.updated_at = studio_now()
                store.save_state(studio_state)
                StudioQA(self.config).run(run_id, store, studio_state)
                return studio_state

            if studio_state.agent_hops >= self.config.studio.max_agent_hops:
                return self._loop_limit(store, studio_state, "max_agent_hops")
            if (
                decision.agent_id == "voice"
                and _report_failed(run_state, self.manager, "audio_qa_report")
                and not any(
                    item.artifact_kind == "audio" and item.status in {"pending", "accepted"}
                    for item in store.revisions()
                )
            ):
                catalog.request_revision(
                    run_id=run_id,
                    artifact_kind="audio",
                    requested_by="studio_director",
                    reason="Audio QA fail，返回 VoiceAgent 定点修复",
                    acceptance_criteria=["重新生成或校验旁白", "Audio QA 必须通过"],
                )
                revision_owner = "voice"
            if (
                decision.agent_id == "editor"
                and _report_failed(run_state, self.manager, "video_qa_report")
                and not any(
                    item.artifact_kind == "final_video" and item.status in {"pending", "accepted"}
                    for item in store.revisions()
                )
            ):
                catalog.request_revision(
                    run_id=run_id,
                    artifact_kind="final_video",
                    requested_by="studio_director",
                    reason="Video QA fail，返回 EditorAgent 定点修复",
                    acceptance_criteria=["重新渲染成片", "Video QA 必须通过"],
                )
                revision_owner = "editor"
            if revision_owner:
                pending = next(
                    item
                    for item in store.revisions()
                    if item.owner_agent_id == revision_owner and item.status == "pending"
                )
                catalog.accept_revision(pending.request_id, agent_id=revision_owner)

            handoff = self._handoff(
                run_id,
                studio_state,
                decision.agent_id,
                decision.reason,
                context,
                catalog,
            )
            accepted = HandoffProtocol.accept(handoff, available_kinds=catalog.available_kinds())
            store.save_handoff(accepted)
            if accepted.status == "rejected":
                studio_state.status = "escalated"
                studio_state.last_error = accepted.status_reason
                studio_state.escalation = AgentFailure(
                    kind="artifact_invalid",
                    agent_id=decision.agent_id,
                    message=accepted.status_reason or "handoff rejected",
                    recoverable=False,
                )
                store.save_state(studio_state)
                self._trace(store, studio_state, "handoff_rejected", studio_state.last_error or "")
                StudioQA(self.config).run(run_id, store, studio_state)
                return studio_state

            studio_state.previous_agent = studio_state.current_agent
            studio_state.current_agent = decision.agent_id
            studio_state.agent_hops += 1
            studio_state.pending_handoff_id = accepted.handoff_id
            studio_state.updated_at = studio_now()
            store.save_state(studio_state)
            self._trace(
                store,
                studio_state,
                "handoff_accepted",
                f"{accepted.from_agent} -> {accepted.to_agent}",
                handoff_id=accepted.handoff_id,
            )

            agent = self.agents[decision.agent_id]
            try:
                result = await agent.run(runtime, self.selector.select(context, decision.agent_id), accepted)
            except Exception as exc:
                failure = classify_failure(decision.agent_id, exc)
                result = AgentResult(
                    agent_id=decision.agent_id,
                    task_id=accepted.handoff_id,
                    status="failed",
                    produced_artifacts=[],
                    summary=f"{decision.agent_id} 执行失败。",
                    warnings=[str(exc)],
                    confidence=1.0,
                    next_recommended_agent=failure.suggested_owner_agent,
                    failure=failure,
                )
            store.save_result(result)
            context.add_artifacts(result.produced_artifacts)
            context.add_decisions(result.decisions)
            for warning in result.warnings:
                context.add_warning(warning)
            store.save_context_snapshot(context, context.version)
            self._trace(
                store,
                studio_state,
                "agent_result",
                result.summary,
                handoff_id=accepted.handoff_id,
                task_id=result.task_id,
                artifact_ids=[item.artifact_id for item in result.produced_artifacts],
                metadata={"status": result.status, "confidence": result.confidence},
            )

            if result.status in {"completed", "skipped", "revision_required"}:
                store.save_handoff(HandoffProtocol.complete(accepted))
            elif result.status == "blocked":
                store.save_handoff(HandoffProtocol.escalate(accepted, result.failure.message if result.failure else result.summary))
            else:
                store.save_handoff(HandoffProtocol.reject(accepted, result.failure.message if result.failure else result.summary))
            studio_state.pending_handoff_id = None

            if result.status == "revision_required":
                studio_state.review_rounds += 1
                if studio_state.review_rounds > self.config.studio.max_review_rounds:
                    return self._loop_limit(store, studio_state, "max_review_rounds")
                studio_state.previous_agent = result.agent_id
                studio_state.current_agent = "studio_director"
                store.save_state(studio_state)
                continue
            if result.status in {"completed", "skipped"}:
                if result.agent_id not in studio_state.completed_agents:
                    studio_state.completed_agents.append(result.agent_id)
                studio_state.previous_agent = result.agent_id
                studio_state.current_agent = "studio_director"
                store.save_state(studio_state)
                continue
            if result.status == "blocked" or (result.failure and not result.failure.recoverable):
                studio_state.status = (
                    "waiting_for_approval"
                    if result.failure and result.failure.kind == "approval_required"
                    else "escalated"
                )
                studio_state.escalation = result.failure
                studio_state.last_error = result.failure.message if result.failure else result.summary
                studio_state.current_agent = "studio_director"
                studio_state.updated_at = studio_now()
                store.save_state(studio_state)
                StudioQA(self.config).run(run_id, store, studio_state)
                return studio_state
            if result.failure:
                if self._same_failure_count(store, result.failure) >= 2:
                    studio_state.status = "escalated"
                    studio_state.escalation = result.failure.model_copy(
                        update={"kind": "human_intervention_required", "recoverable": False}
                    )
                    studio_state.last_error = result.failure.message
                    store.save_state(studio_state)
                    StudioQA(self.config).run(run_id, store, studio_state)
                    return studio_state
                self._ensure_recovery_revision(run_id, store, catalog, result.failure)
                studio_state.current_agent = "studio_director"
                store.save_state(studio_state)

    async def resume(self, run_id: str) -> StudioState:
        return await self.run(run_id)

    def status(self, run_id: str) -> dict[str, Any]:
        store = StudioTraceStore(self.manager, run_id)
        state = store.load_state() or StudioState(run_id=run_id)
        qa_path = store.root / "studio_qa_report.json"
        return {
            "state": state.model_dump(mode="json"),
            "handoff_count": len(store.handoffs()),
            "result_count": len(store.results()),
            "artifact_count": len(store.artifacts()),
            "trace_event_count": len(store.trace_records()),
            "studio_qa": (
                __import__("json").loads(qa_path.read_text(encoding="utf-8")) if qa_path.is_file() else None
            ),
        }

    def trace(self, run_id: str) -> list[dict[str, Any]]:
        return StudioTraceStore(self.manager, run_id).trace_records()

    def _adopt_existing(self, state: RunState, catalog: ArtifactCatalog) -> None:
        mapping = {
            "research": ("researcher", "research"),
            "script": ("writer", "script"),
            "metadata": ("writer", "metadata"),
            "storyboard": ("storyboard_director", "storyboard"),
            "design_plan": ("designer", "design_plan"),
            "publish_cover": ("designer", "publish_cover"),
            "audio_manifest": ("voice", "audio"),
            "subtitles_json": ("voice", "subtitles"),
            "audio_qa_report": ("voice", "audio_qa"),
            "composition": ("editor", "composition"),
            "final_video": ("editor", "final_video"),
            "video_qa_report": ("editor", "video_qa"),
            "studio_script_review": ("critic", "script_review"),
            "text_qa_report": ("critic", "text_qa"),
            "studio_final_review": ("critic", "final_review"),
            "publish_package": ("publisher", "publish_package"),
            "publish_qa_report": ("publisher", "publish_qa"),
            "publish_validation_report": ("publisher", "publish_validation"),
            "publish_job": ("publisher", "publish_job"),
            "performance_analysis": ("analyst", "analytics"),
            "lessons": ("analyst", "memory"),
            "strategy_recommendations": ("analyst", "strategy"),
            "next_experiment": ("analyst", "experiment"),
        }
        for run_key, (owner, kind) in mapping.items():
            relative = state.artifacts.get(run_key)
            if not relative or not self.manager.artifact_exists(state, run_key):
                continue
            if catalog.latest(kind) is not None:
                continue
            catalog.register(
                run_id=state.run_id,
                agent_id=owner,
                kind=kind,
                path=relative,
                source_run_artifact=run_key,
                summary=f"adopted existing {run_key}",
                testing=bool((state.planning_provenance or {}).get("testing")),
            )

    def _handoff(
        self,
        run_id: str,
        studio_state: StudioState,
        agent_id: str,
        reason: str,
        context: StudioContext,
        catalog: ArtifactCatalog,
    ) -> AgentHandoff:
        required = self._required_inputs(agent_id, self.manager.load(run_id))
        provided = [item for item in context.artifact_refs if item.kind in set(required)]
        profile = self.registry.get(agent_id)
        handoff = HandoffProtocol.create(
            run_id=run_id,
            sequence=studio_state.agent_hops + 1,
            from_agent=(
                "studio_director"
                if studio_state.previous_agent == agent_id
                else studio_state.previous_agent or "studio_director"
            ),
            to_agent=agent_id,
            objective=reason,
            required_inputs=required,
            provided_artifacts=provided,
            acceptance_criteria=list(profile.quality_responsibilities),
            constraints=[
                "provider 必须由 ProductionPlan 选择",
                "不得绕过 Human Approval Gate",
                "默认串行执行",
                "只能修改本角色 owned artifact 或已接受 revision request 的产物",
            ],
            risks=list(profile.escalation_rules),
        )
        StudioTraceStore(self.manager, run_id).save_handoff(handoff)
        return handoff

    @staticmethod
    def _required_inputs(agent_id: str, state: RunState) -> list[str]:
        if agent_id == "researcher":
            return ["topic"]
        if agent_id == "writer":
            return ["research"]
        if agent_id == "storyboard_director":
            return ["script"]
        if agent_id == "designer":
            return ["script", "storyboard"]
        if agent_id == "voice":
            return ["storyboard"]
        if agent_id == "editor":
            return ["storyboard", "audio", "subtitles"]
        if agent_id == "critic":
            return ["final_video", "audio_qa", "video_qa"] if "final_video" in state.artifacts else ["research", "script"]
        if agent_id == "publisher":
            return ["research", "script", "final_video", "video_qa", "publish_cover"]
        return []

    def _approval_state(self, run_id: str, state: RunState) -> dict[str, bool]:
        run_dir = self.manager.run_dir(run_id)
        return {
            "topic_approved": bool(state.planning_provenance),
            "production_policy_approved": (run_dir / "production" / "policy_approval.json").is_file(),
            "publish_approved": (run_dir / "publish" / "approval_record.json").is_file(),
        }

    def _pending_revision_owner(self, store: StudioTraceStore) -> str | None:
        pending = [item for item in store.revisions() if item.status == "pending"]
        return pending[0].owner_agent_id if pending else None

    def _ensure_recovery_revision(
        self,
        run_id: str,
        store: StudioTraceStore,
        catalog: ArtifactCatalog,
        failure: AgentFailure,
    ) -> None:
        kind = failure.failed_artifact_kind
        owner = failure.suggested_owner_agent
        if not kind or not owner or kind not in {"script", "storyboard", "audio", "final_video", "publish_package"}:
            return
        existing = [
            item for item in store.revisions() if item.artifact_kind == kind and item.status in {"pending", "accepted"}
        ]
        if not existing:
            catalog.request_revision(
                run_id=run_id,
                artifact_kind=kind,
                requested_by=failure.agent_id,
                reason=failure.message,
                acceptance_criteria=["重新执行 owner stage", "相关 QA 必须通过"],
            )

    def _loop_limit(self, store: StudioTraceStore, state: StudioState, limit: str) -> StudioState:
        failure = AgentFailure(
            kind="human_intervention_required",
            agent_id="studio_director",
            message=f"Studio 达到 {limit}，已停止并升级 Human Review",
            recoverable=False,
        )
        state.status = "escalated"
        state.escalation = failure
        state.last_error = failure.message
        state.pending_handoff_id = None
        state.current_agent = "studio_director"
        state.updated_at = studio_now()
        store.save_state(state)
        self._trace(store, state, "loop_limit", failure.message)
        StudioQA(self.config).run(state.run_id, store, state)
        return state

    @staticmethod
    def _same_failure_count(store: StudioTraceStore, failure: AgentFailure) -> int:
        return sum(
            1
            for item in store.results()
            if item.failure
            and item.failure.agent_id == failure.agent_id
            and item.failure.kind == failure.kind
            and item.failure.message == failure.message
        )

    def _trace(
        self,
        store: StudioTraceStore,
        state: StudioState,
        event_type: str,
        summary: str,
        *,
        handoff_id: str | None = None,
        task_id: str | None = None,
        artifact_ids: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        now = studio_now()
        store.append_trace(
            StudioTraceEvent(
                event_id=stable_studio_id(
                    "trace", state.run_id, event_type, str(state.agent_hops), now.isoformat()
                ),
                run_id=state.run_id,
                event_type=event_type,
                actor="studio_director",
                summary=summary,
                handoff_id=handoff_id,
                task_id=task_id,
                artifact_ids=artifact_ids or [],
                metadata=metadata or {},
                created_at=now,
            )
        )


def _report_failed(state: RunState, manager: RunManager, key: str) -> bool:
    relative = state.artifacts.get(key)
    if not relative or not manager.artifact_exists(state, key):
        return False
    try:
        payload = manager.read_json(state.run_id, relative)
    except (OSError, ValueError):
        return True
    return payload.get("passed") is False
