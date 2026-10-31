from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from alysia.core.config import AlysiaConfig
from alysia.core.orchestrator import AlysiaOrchestrator, AudioPipelineError
from alysia.core.run import RunManager, RunState
from alysia.core.state import Stage
from alysia.identity import IdentityService
from alysia.learning import LearningPipeline
from alysia.operations import OperationsService
from alysia.publishing import PublishingService
from alysia.schemas import AudioManifest, ResearchResult, Script, Storyboard, SubtitleDocument
from alysia.studio.context import StudioContextView
from alysia.studio.ownership import ArtifactCatalog
from alysia.studio.protocol import (
    AgentDecision,
    AgentFailure,
    AgentHandoff,
    AgentResult,
    ArtifactRef,
    RevisionRequest,
    stable_studio_id,
)
from alysia.studio.registry import AgentRegistry
from alysia.studio.trace import StudioTraceStore
from alysia.workers import DesignWorker
from alysia.visual import VisualGenerationService


@dataclass
class StudioRuntime:
    config: AlysiaConfig
    orchestrator: AlysiaOrchestrator
    registry: AgentRegistry
    catalog: ArtifactCatalog
    store: StudioTraceStore

    @property
    def manager(self) -> RunManager:
        return self.orchestrator.manager

    def state(self, run_id: str) -> RunState:
        return self.manager.load(run_id)

    def provider_for(self, run_id: str, production_stage: str, agent_id: str) -> str:
        plan = self.orchestrator.production.load_plan(run_id)
        provider_id = plan.selected_provider_per_stage.get(
            production_stage, f"deterministic.{production_stage}"
        )
        self.registry.assert_provider_allowed(agent_id, provider_id)
        return provider_id

    def accepted_revision(self, kind: str, owner_agent_id: str) -> RevisionRequest | None:
        matches = [
            item
            for item in self.store.revisions()
            if item.artifact_kind == kind
            and item.owner_agent_id == owner_agent_id
            and item.status == "accepted"
        ]
        return matches[-1] if matches else None

    def register(
        self,
        run_id: str,
        agent_id: str,
        kind: str,
        run_artifact_key: str,
        *,
        summary: str,
        revision: RevisionRequest | None = None,
    ) -> ArtifactRef:
        state = self.state(run_id)
        path = state.artifacts.get(run_artifact_key)
        if not path or not self.manager.artifact_exists(state, run_artifact_key):
            raise FileNotFoundError(f"run 缺少 artifact：{run_artifact_key}")
        testing = _is_testing(state)
        return self.catalog.register(
            run_id=run_id,
            agent_id=agent_id,
            kind=kind,
            path=path,
            source_run_artifact=run_artifact_key,
            summary=summary,
            testing=testing,
            revision_request=revision,
        )


class BaseStudioAgent(ABC):
    agent_id: str

    @abstractmethod
    async def run(
        self,
        runtime: StudioRuntime,
        context: StudioContextView,
        handoff: AgentHandoff,
    ) -> AgentResult:
        raise NotImplementedError

    def result(
        self,
        handoff: AgentHandoff,
        *,
        status: str = "completed",
        artifacts: list[ArtifactRef] | None = None,
        summary: str,
        decisions: list[AgentDecision] | None = None,
        warnings: list[str] | None = None,
        unresolved_questions: list[str] | None = None,
        confidence: float = 0.9,
        next_agent: str | None = None,
        failure: AgentFailure | None = None,
    ) -> AgentResult:
        return AgentResult(
            agent_id=self.agent_id,
            task_id=handoff.handoff_id,
            status=status,
            produced_artifacts=artifacts or [],
            summary=summary,
            decisions=decisions or [],
            assumptions=[],
            warnings=warnings or [],
            unresolved_questions=unresolved_questions or [],
            confidence=confidence,
            next_recommended_agent=next_agent,
            failure=failure,
        )

    def decision(
        self,
        handoff: AgentHandoff,
        summary: str,
        rationale: str,
        artifact_ids: list[str] | None = None,
    ) -> AgentDecision:
        return AgentDecision(
            decision_id=stable_studio_id("decision", handoff.handoff_id, self.agent_id, summary),
            agent_id=self.agent_id,
            summary=summary,
            rationale=rationale,
            input_artifact_ids=artifact_ids or [],
        )


class ResearcherStudioAgent(BaseStudioAgent):
    agent_id = "researcher"

    async def run(self, runtime: StudioRuntime, context: StudioContextView, handoff: AgentHandoff) -> AgentResult:
        provider = runtime.provider_for(context.run_id, "research", self.agent_id)
        state = runtime.state(context.run_id)
        await runtime.orchestrator._research(state, force=False)
        artifact = runtime.register(
            context.run_id, self.agent_id, "research", "research", summary="可追溯调研资料与事实摘要"
        )
        decision = self.decision(handoff, f"使用 {provider} 完成调研", "provider 由 ProductionPlan 选择")
        return self.result(
            handoff,
            artifacts=[artifact],
            summary="Researcher 完成资料与来源交接。",
            decisions=[decision],
            next_agent="writer",
        )


class WriterStudioAgent(BaseStudioAgent):
    agent_id = "writer"

    async def run(self, runtime: StudioRuntime, context: StudioContextView, handoff: AgentHandoff) -> AgentResult:
        provider = runtime.provider_for(context.run_id, "script", self.agent_id)
        state = runtime.state(context.run_id)
        research = ResearchResult.model_validate(
            runtime.manager.read_json(context.run_id, state.artifacts["research"])
        )
        revision = runtime.accepted_revision("script", self.agent_id)
        if revision is not None:
            runtime.catalog.invalidate(
                [
                    "script_review",
                    "text_qa",
                    "storyboard",
                    "design_plan",
                    "publish_cover",
                    "audio",
                    "subtitles",
                    "audio_qa",
                    "composition",
                    "final_video",
                    "video_qa",
                    "final_review",
                    "publish_package",
                    "publish_qa",
                    "publish_validation",
                    "publish_job",
                ]
            )
            downstream_keys = {
                "storyboard",
                "design_plan",
                "publish_cover",
                "audio_manifest",
                "narration",
                "subtitles_json",
                "subtitles_srt",
                "audio_qa_report",
                "composition",
                "assets_manifest",
                "render_config",
                "render_result",
                "final_video",
                "video_qa_report",
                "studio_script_review",
                "studio_final_review",
                "publish_package",
                "publish_metadata",
                "publish_title",
                "publish_description",
                "publish_tags",
                "publish_qa_report",
                "publish_validation_report",
                "publish_job",
            }
            for key in downstream_keys:
                state.artifacts.pop(key, None)
            state.completed_stages = [
                item
                for item in state.completed_stages
                if item
                not in {
                    Stage.STORYBOARDING,
                    Stage.GENERATING_ASSETS,
                    Stage.GENERATING_VOICE,
                    Stage.GENERATING_SUBTITLES,
                    Stage.QA,
                    Stage.RENDERING,
                    Stage.VIDEO_QA,
                    Stage.PACKAGING,
                    Stage.PUBLISH_QA,
                    Stage.READY_FOR_REVIEW,
                }
            ]
            state.text_pipeline_completed = False
            state.audio_pipeline_completed = False
            state.video_pipeline_completed = False
            state.package_pipeline_completed = False
            state.review_ready = False
            runtime.manager.save(state)
        await runtime.orchestrator._write(state, research, force=revision is not None)
        artifacts = [
            runtime.register(
                context.run_id,
                self.agent_id,
                "script",
                "script",
                summary="结构化视频脚本",
                revision=revision,
            ),
            runtime.register(
                context.run_id, self.agent_id, "metadata", "metadata", summary="脚本基础 metadata"
            ),
        ]
        decision = self.decision(
            handoff,
            f"使用 {provider} 生成脚本" + ("修订版" if revision else ""),
            "模型选择来自 ProductionPlan；Writer 不裁决最终事实",
        )
        return self.result(
            handoff,
            artifacts=artifacts,
            summary="Writer 完成脚本" + ("修订" if revision else "初稿") + "。",
            decisions=[decision],
            next_agent="critic",
        )


class StoryboardStudioAgent(BaseStudioAgent):
    agent_id = "storyboard_director"

    async def run(self, runtime: StudioRuntime, context: StudioContextView, handoff: AgentHandoff) -> AgentResult:
        provider = runtime.provider_for(context.run_id, "storyboard", self.agent_id)
        state = runtime.state(context.run_id)
        script = Script.model_validate(runtime.manager.read_json(context.run_id, state.artifacts["script"]))
        await runtime.orchestrator._storyboard(state, script, force=False)
        artifact = runtime.register(
            context.run_id,
            self.agent_id,
            "storyboard",
            "storyboard",
            summary="结构化分镜与叙事节奏",
        )
        return self.result(
            handoff,
            artifacts=[artifact],
            summary="StoryboardDirector 完成分镜。",
            decisions=[self.decision(handoff, f"使用 {provider} 生成分镜", "provider 由 ProductionPlan 选择")],
            next_agent="designer",
        )


class DesignerStudioAgent(BaseStudioAgent):
    agent_id = "designer"

    async def run(self, runtime: StudioRuntime, context: StudioContextView, handoff: AgentHandoff) -> AgentResult:
        provider = runtime.provider_for(context.run_id, "cover", self.agent_id)
        runtime.orchestrator._configure_provider("cover", provider)
        state = runtime.state(context.run_id)
        script = Script.model_validate(runtime.manager.read_json(context.run_id, state.artifacts["script"]))
        storyboard = Storyboard.model_validate(
            runtime.manager.read_json(context.run_id, state.artifacts["storyboard"])
        )
        DesignWorker(
            runtime.manager, runtime.config, runtime.orchestrator.cover_generator
        ).run(state, script, storyboard)
        VisualGenerationService(runtime.config, resources=runtime.orchestrator.resources).plan(context.run_id)
        artifacts = [
            runtime.register(
                context.run_id, self.agent_id, "design_plan", "design_plan", summary="低成本视觉与资产计划"
            ),
            runtime.register(
                context.run_id, self.agent_id, "publish_cover", "publish_cover", summary="确定性模板封面"
            ),
            runtime.register(
                context.run_id, self.agent_id, "visual_plan", "visual_plan", summary="受预算约束的混合视觉路由计划"
            ),
        ]
        return self.result(
            handoff,
            artifacts=artifacts,
            summary="Designer 完成视觉计划和模板封面，未触发高成本图像生成。",
            decisions=[self.decision(handoff, f"使用 {provider}", "遵循 ProductionPlan 与低成本模板边界")],
            next_agent="voice",
        )


class VoiceStudioAgent(BaseStudioAgent):
    agent_id = "voice"

    async def run(self, runtime: StudioRuntime, context: StudioContextView, handoff: AgentHandoff) -> AgentResult:
        tts_provider = runtime.provider_for(context.run_id, "tts", self.agent_id)
        runtime.provider_for(context.run_id, "subtitle_alignment", self.agent_id)
        state = runtime.state(context.run_id)
        storyboard = Storyboard.model_validate(
            runtime.manager.read_json(context.run_id, state.artifacts["storyboard"])
        )
        revision = runtime.accepted_revision("audio", self.agent_id)
        if revision is not None:
            runtime.catalog.invalidate(
                [
                    "subtitles",
                    "audio_qa",
                    "composition",
                    "final_video",
                    "video_qa",
                    "final_review",
                    "publish_package",
                    "publish_qa",
                    "publish_validation",
                    "publish_job",
                ]
            )
        manifest = await runtime.orchestrator._voice(state, storyboard, force=revision is not None)
        if revision is not None:
            state.artifacts.pop("studio_final_review", None)
            runtime.manager.save(state)
        subtitles = await runtime.orchestrator._subtitle(
            state, storyboard, manifest, force=revision is not None
        )
        report = await runtime.orchestrator._audio_qa(
            state, storyboard, manifest, subtitles, force=revision is not None
        )
        if not report.passed:
            raise AudioPipelineError("音频 QA 未通过")
        runtime.orchestrator._mark_audio_ready(state)
        artifacts = [
            runtime.register(
                context.run_id,
                self.agent_id,
                "audio",
                "audio_manifest",
                summary="旁白音频 manifest",
                revision=revision,
            ),
            runtime.register(
                context.run_id, self.agent_id, "subtitles", "subtitles_json", summary="字幕时间轴"
            ),
            runtime.register(
                context.run_id, self.agent_id, "audio_qa", "audio_qa_report", summary="音频与字幕 QA"
            ),
        ]
        return self.result(
            handoff,
            artifacts=artifacts,
            summary="Voice 完成旁白、字幕和 Audio QA。",
            decisions=[self.decision(handoff, f"使用 {tts_provider} 生成旁白", "TTS provider 由 ProductionPlan 选择")],
            next_agent="editor",
        )


class EditorStudioAgent(BaseStudioAgent):
    agent_id = "editor"

    async def run(self, runtime: StudioRuntime, context: StudioContextView, handoff: AgentHandoff) -> AgentResult:
        provider = runtime.provider_for(context.run_id, "render", self.agent_id)
        state = runtime.state(context.run_id)
        revision = runtime.accepted_revision("final_video", self.agent_id)
        if revision is not None:
            runtime.catalog.invalidate(
                ["composition", "final_video", "video_qa", "final_review", "publish_package", "publish_qa", "publish_validation", "publish_job"]
            )
            state.artifacts.pop("studio_final_review", None)
            runtime.manager.save(state)
        await runtime.orchestrator._run_video_pipeline(state, force=revision is not None)
        artifacts = [
            runtime.register(
                context.run_id, self.agent_id, "composition", "composition", summary="程序化视频 composition"
            ),
            runtime.register(
                context.run_id,
                self.agent_id,
                "final_video",
                "final_video",
                summary="规范化 final.mp4",
                revision=revision,
            ),
            runtime.register(
                context.run_id, self.agent_id, "video_qa", "video_qa_report", summary="可解码性与格式 QA"
            ),
        ]
        return self.result(
            handoff,
            artifacts=artifacts,
            summary="Editor 完成合成、渲染和 Video QA。",
            decisions=[self.decision(handoff, f"使用 {provider} 渲染", "renderer 由 ProductionPlan 选择")],
            next_agent="critic",
        )


class CriticStudioAgent(BaseStudioAgent):
    agent_id = "critic"

    async def run(self, runtime: StudioRuntime, context: StudioContextView, handoff: AgentHandoff) -> AgentResult:
        state = runtime.state(context.run_id)
        final_review = "final_video" in state.artifacts
        if final_review:
            return await self._final_review(runtime, context, handoff, state)
        if "storyboard" in state.artifacts:
            return await self._text_qa(runtime, context, handoff, state)
        return await self._script_review(runtime, context, handoff, state)

    async def _text_qa(
        self,
        runtime: StudioRuntime,
        context: StudioContextView,
        handoff: AgentHandoff,
        state: RunState,
    ) -> AgentResult:
        research = ResearchResult.model_validate(
            runtime.manager.read_json(context.run_id, state.artifacts["research"])
        )
        script = Script.model_validate(runtime.manager.read_json(context.run_id, state.artifacts["script"]))
        storyboard = Storyboard.model_validate(
            runtime.manager.read_json(context.run_id, state.artifacts["storyboard"])
        )
        report = await runtime.orchestrator._qa(
            state, research, script, storyboard, force=False
        )
        artifact = runtime.register(
            context.run_id,
            self.agent_id,
            "text_qa",
            "text_qa_report",
            summary="现有 TextCritic 的跨 Research/Script/Storyboard QA",
        )
        if not report.passed:
            failure = AgentFailure(
                kind="qa_failure",
                agent_id=self.agent_id,
                message="Text QA 未通过",
                recoverable=True,
                failed_artifact_kind="script",
                suggested_owner_agent="writer",
            )
            return self.result(
                handoff,
                status="failed",
                artifacts=[artifact],
                summary="Critic 的 Text QA 未通过。",
                warnings=[item.message for item in report.issues],
                confidence=0.95,
                next_agent="writer",
                failure=failure,
            )
        return self.result(
            handoff,
            artifacts=[artifact],
            summary="Critic 的 Text QA 通过。",
            next_agent="designer",
        )

    async def _script_review(
        self,
        runtime: StudioRuntime,
        context: StudioContextView,
        handoff: AgentHandoff,
        state: RunState,
    ) -> AgentResult:
        research = ResearchResult.model_validate(
            runtime.manager.read_json(context.run_id, state.artifacts["research"])
        )
        script = Script.model_validate(runtime.manager.read_json(context.run_id, state.artifacts["script"]))
        known_refs = {item.id for item in research.sources}
        used_refs = set(script.source_refs)
        used_refs.update(ref for section in script.sections for ref in section.source_refs)
        errors = []
        if not script.hook.strip():
            errors.append("脚本缺少 hook")
        if not script.conclusion.strip():
            errors.append("脚本缺少结论")
        if used_refs - known_refs:
            errors.append("脚本包含未知来源引用")
        payload = {
            "phase": "script",
            "passed": not errors,
            "errors": errors,
            "checks": {
                "has_hook": bool(script.hook.strip()),
                "has_conclusion": bool(script.conclusion.strip()),
                "source_refs_known": not bool(used_refs - known_refs),
            },
        }
        runtime.manager.write_json(context.run_id, "studio/reviews/script_review.json", payload)
        state.artifacts["studio_script_review"] = "studio/reviews/script_review.json"
        runtime.manager.save(state)
        artifact = runtime.catalog.register(
            run_id=context.run_id,
            agent_id=self.agent_id,
            kind="script_review",
            path="studio/reviews/script_review.json",
            source_run_artifact="studio_script_review",
            summary="脚本事实、逻辑与结构审查",
            testing=_is_testing(state),
        )
        if errors:
            request = runtime.catalog.request_revision(
                run_id=context.run_id,
                artifact_kind="script",
                requested_by=self.agent_id,
                reason="；".join(errors),
                acceptance_criteria=["修复所有 script review error", "保持可追溯来源引用"],
            )
            revision_ref = runtime.catalog.register(
                run_id=context.run_id,
                agent_id=self.agent_id,
                kind="revision_request",
                path=f"studio/revision_requests.json#{request.request_id}",
                summary="Writer 修订请求",
                testing=_is_testing(state),
            )
            return self.result(
                handoff,
                status="revision_required",
                artifacts=[artifact, revision_ref],
                summary="Critic 要求 Writer 修订脚本。",
                warnings=errors,
                confidence=0.95,
                next_agent="writer",
            )
        return self.result(
            handoff,
            artifacts=[artifact],
            summary="Critic 完成脚本审查，未发现硬错误。",
            next_agent="storyboard_director",
        )

    async def _final_review(
        self,
        runtime: StudioRuntime,
        context: StudioContextView,
        handoff: AgentHandoff,
        state: RunState,
    ) -> AgentResult:
        required = ["text_qa_report", "audio_qa_report", "video_qa_report"]
        reports: dict[str, Any] = {}
        errors = []
        for key in required:
            relative = state.artifacts.get(key)
            if not relative or not runtime.manager.artifact_exists(state, key):
                errors.append(f"缺少 {key}")
                continue
            reports[key] = runtime.manager.read_json(context.run_id, relative)
            if reports[key].get("passed") is False:
                errors.append(f"{key} 未通过")
        style = None
        if runtime.config.identity.enabled:
            try:
                style = IdentityService(runtime.config).style_check(context.run_id).model_dump(mode="json")
            except (FileNotFoundError, ValueError) as exc:
                errors.append(f"Style QA 无法完成：{exc}")
        payload = {"phase": "final", "passed": not errors, "errors": errors, "qa": reports, "style": style}
        runtime.manager.write_json(context.run_id, "studio/reviews/final_review.json", payload)
        state.artifacts["studio_final_review"] = "studio/reviews/final_review.json"
        runtime.manager.save(state)
        artifact = runtime.catalog.register(
            run_id=context.run_id,
            agent_id=self.agent_id,
            kind="final_review",
            path="studio/reviews/final_review.json",
            source_run_artifact="studio_final_review",
            summary="跨阶段最终审查",
            testing=_is_testing(state),
        )
        if errors:
            owner = "voice" if any("audio_qa" in item for item in errors) else "editor"
            failure = AgentFailure(
                kind="qa_failure",
                agent_id=self.agent_id,
                message="；".join(errors),
                recoverable=True,
                failed_artifact_kind="audio" if owner == "voice" else "final_video",
                suggested_owner_agent=owner,
            )
            return self.result(
                handoff,
                status="failed",
                artifacts=[artifact],
                summary="Critic 最终审查未通过。",
                warnings=errors,
                confidence=0.95,
                next_agent=owner,
                failure=failure,
            )
        return self.result(
            handoff,
            artifacts=[artifact],
            summary="Critic 最终审查通过。",
            next_agent="publisher",
        )


class PublisherStudioAgent(BaseStudioAgent):
    agent_id = "publisher"

    async def run(self, runtime: StudioRuntime, context: StudioContextView, handoff: AgentHandoff) -> AgentResult:
        state = runtime.state(context.run_id)
        if not state.package_pipeline_completed:
            state = await runtime.orchestrator._run_package_pipeline(state, force=False)
        if not state.review_ready:
            state = await runtime.orchestrator._run_publish_qa_pipeline(state, force=False)
        artifacts = [
            runtime.register(
                context.run_id, self.agent_id, "publish_package", "publish_package", summary="投稿包"
            ),
            runtime.register(
                context.run_id, self.agent_id, "publish_qa", "publish_qa_report", summary="发布前 QA"
            ),
        ]
        review = PublishingService(runtime.config).review(context.run_id)
        if runtime.config.publishing.require_approval and not context.approvals.get("publish_approved"):
            failure = AgentFailure(
                kind="approval_required",
                agent_id=self.agent_id,
                message="投稿包已就绪，等待 Human Approval Gate",
                recoverable=False,
                suggested_owner_agent="publisher",
                details={"warnings": review.get("risk_warnings", [])},
            )
            return self.result(
                handoff,
                status="blocked",
                artifacts=artifacts,
                summary="Publisher 已准备投稿包，但不会绕过人工审批。",
                warnings=list(review.get("risk_warnings", [])),
                unresolved_questions=["是否由人工批准当前投稿包？"],
                confidence=1.0,
                failure=failure,
            )
        validation = PublishingService(runtime.config).validate(context.run_id)
        state = runtime.state(context.run_id)
        validation_ref = runtime.register(
            context.run_id,
            self.agent_id,
            "publish_validation",
            "publish_validation_report",
            summary="发布验证",
        )
        artifacts.append(validation_ref)
        if not validation.passed:
            failure = AgentFailure(
                kind="artifact_invalid",
                agent_id=self.agent_id,
                message="；".join(validation.errors),
                recoverable=True,
                suggested_owner_agent="publisher",
            )
            return self.result(
                handoff,
                status="failed",
                artifacts=artifacts,
                summary="Publisher 验证未通过。",
                warnings=validation.errors,
                confidence=0.95,
                failure=failure,
            )
        return self.result(
            handoff,
            artifacts=artifacts,
            summary="Publisher 验证通过；未自动提交。",
            next_agent="analyst",
        )


class AnalystStudioAgent(BaseStudioAgent):
    agent_id = "analyst"

    async def run(self, runtime: StudioRuntime, context: StudioContextView, handoff: AgentHandoff) -> AgentResult:
        state = runtime.state(context.run_id)
        if not state.analytics_imported:
            failure = AgentFailure(
                kind="human_intervention_required",
                agent_id=self.agent_id,
                message="尚无真实或显式 mock Analytics 输入；不得补造数据",
                recoverable=False,
                suggested_owner_agent="analyst",
            )
            return self.result(
                handoff,
                status="blocked",
                summary="Analyst 等待可追溯 Analytics/Feedback 输入。",
                unresolved_questions=["何时导入平台 Analytics 或显式 testing 数据？"],
                confidence=1.0,
                failure=failure,
            )
        pipeline = LearningPipeline(runtime.manager, runtime.config.learning.memory_dir)
        pipeline.analyze(context.run_id)
        pipeline.learn(context.run_id)
        pipeline.strategy(context.run_id)
        OperationsService(runtime.config).refresh(
            (state.planning_provenance or {}).get(
                "channel_id", runtime.config.operations.default_channel_id
            )
        )
        artifacts = [
            runtime.register(
                context.run_id, self.agent_id, "analytics", "performance_analysis", summary="表现分析"
            ),
            runtime.register(
                context.run_id, self.agent_id, "memory", "lessons", summary="证据约束的 lessons"
            ),
            runtime.register(
                context.run_id,
                self.agent_id,
                "strategy",
                "strategy_recommendations",
                summary="待验证策略建议",
            ),
            runtime.register(
                context.run_id, self.agent_id, "experiment", "next_experiment", summary="下一实验提案"
            ),
        ]
        return self.result(
            handoff,
            artifacts=artifacts,
            summary="Analyst 完成 Analytics、Memory、Strategy 与 Experiment 更新。",
            next_agent=None,
        )


def default_studio_agents() -> dict[str, BaseStudioAgent]:
    agents: list[BaseStudioAgent] = [
        ResearcherStudioAgent(),
        WriterStudioAgent(),
        StoryboardStudioAgent(),
        DesignerStudioAgent(),
        VoiceStudioAgent(),
        EditorStudioAgent(),
        CriticStudioAgent(),
        PublisherStudioAgent(),
        AnalystStudioAgent(),
    ]
    return {agent.agent_id: agent for agent in agents}


def classify_failure(agent_id: str, exc: Exception) -> AgentFailure:
    message = str(exc)
    lowered = message.casefold()
    if "approval" in lowered or "人工" in message or "策略阻止" in message:
        kind = "approval_required"
        recoverable = False
    elif "qa" in lowered or "未通过" in message:
        kind = "qa_failure"
        recoverable = True
    elif "provider" in lowered or "ollama" in lowered or "tts" in lowered:
        kind = "provider_failure"
        recoverable = True
    elif isinstance(exc, (FileNotFoundError, ValueError)):
        kind = "artifact_invalid"
        recoverable = True
    else:
        kind = "recoverable"
        recoverable = True
    suggested = agent_id
    if "audio" in lowered or "音频" in message or "旁白" in message or "subtitle" in lowered:
        suggested = "voice"
    elif "video" in lowered or "视频" in message or "render" in lowered:
        suggested = "editor"
    return AgentFailure(
        kind=kind,
        agent_id=agent_id,
        message=message,
        recoverable=recoverable,
        suggested_owner_agent=suggested,
    )


def _is_testing(state: RunState) -> bool:
    snapshot = state.config_snapshot
    values = [
        (snapshot.get("llm") or {}).get("provider"),
        (snapshot.get("research") or {}).get("provider"),
        (snapshot.get("tts") or {}).get("provider"),
        (snapshot.get("video") or {}).get("renderer"),
    ]
    return bool(
        any(item in {"mock", "testing"} for item in values)
        or (state.planning_provenance or {}).get("testing")
    )
