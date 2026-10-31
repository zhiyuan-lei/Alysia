from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime
from time import monotonic
from typing import Any, TypeVar

from pydantic import BaseModel

from alysia.agents import Director, Researcher, TextCritic, Writer
from alysia.core.config import AlysiaConfig
from alysia.core.resources import ResourceManager
from alysia.core.run import RunManager, RunState
from alysia.core.state import Stage
from alysia.identity import IdentityService
from alysia.knowledge import KnowledgeService
from alysia.production import CostEstimator, ProductionService
from alysia.reliability import ReliabilityService
from alysia.prompts import load_prompt
from alysia.providers.asr import BaseASRProvider, FasterWhisperProvider, MockASRProvider
from alysia.providers.llm import BaseLLMProvider, CloudLLMProvider, MockLLMProvider, OllamaProvider
from alysia.providers.cover import BaseCoverGenerator, TemplateCoverGenerator
from alysia.providers.search import BaseResearchProvider, ManualResearchProvider, MockResearchProvider, WebResearchProvider
from alysia.providers.tts import BaseTTSProvider, CosyVoiceProvider, MockTTSProvider, SapiTTSProvider
from alysia.providers.video import BaseVideoRenderer, MockVideoRenderer, RemotionRenderer
from alysia.schemas import (
    AudioManifest,
    AudioQAReport,
    PublishPackage,
    PublishQAReport,
    ResearchResult,
    Script,
    Storyboard,
    SubtitleDocument,
    TextQAReport,
    VideoQAReport,
    VideoRenderResult,
    FallbackRecord,
    StageExecutionMetric,
)
from alysia.workers import (
    AudioQAWorker,
    PublishPackageWorker,
    PublishQAWorker,
    SubtitleWorker,
    VideoQAWorker,
    VideoRenderWorker,
    VoiceWorker,
)

ResultT = TypeVar("ResultT", bound=BaseModel)


class TextPipelineError(RuntimeError):
    pass


class AudioPipelineError(RuntimeError):
    pass


class VideoPipelineError(RuntimeError):
    pass


class PublishPipelineError(RuntimeError):
    pass


class AlysiaOrchestrator:
    def __init__(
        self,
        config: AlysiaConfig,
        *,
        llm_provider: BaseLLMProvider | None = None,
        research_provider: BaseResearchProvider | None = None,
        tts_provider: BaseTTSProvider | None = None,
        asr_provider: BaseASRProvider | None = None,
        video_renderer: BaseVideoRenderer | None = None,
        cover_generator: BaseCoverGenerator | None = None,
        resources: ResourceManager | None = None,
    ) -> None:
        self.config = config
        self.manager = RunManager(config.runtime.runs_dir)
        self.identity_service = IdentityService(config) if config.identity.enabled else None
        self.llm_provider = llm_provider or build_llm_provider(config)
        self.research_provider = research_provider or build_research_provider(config)
        self.tts_provider = tts_provider or build_tts_provider(config)
        self.asr_provider = asr_provider if asr_provider is not None else build_asr_provider(config)
        self.resources = resources or ResourceManager(sequential_gpu=config.runtime.sequential_gpu)
        self.researcher = Researcher(self.research_provider, config.research.max_sources)
        self.writer = Writer(self.llm_provider, config.content.default_duration_sec)
        self.director = Director(self.llm_provider)
        self.critic = TextCritic(config.content)
        self.voice_worker = VoiceWorker(self.manager, config.tts, self.tts_provider, self.resources)
        self.subtitle_worker = SubtitleWorker(
            self.manager,
            config.subtitle,
            self.resources,
            self.asr_provider,
        )
        self.audio_qa_worker = AudioQAWorker(self.manager, allow_test_tone=config.tts.allow_test_tone)
        self.video_renderer = video_renderer or build_video_renderer(config)
        self.video_worker = VideoRenderWorker(self.manager, config, self.video_renderer)
        self.video_qa_worker = VideoQAWorker(config)
        self.cover_generator = cover_generator or TemplateCoverGenerator(
            config.publish.cover,
            config.visual_identity.template_version,
        )
        self.publish_worker = PublishPackageWorker(self.manager, config, self.cover_generator)
        self.publish_qa_worker = PublishQAWorker(self.manager, config)
        self.production = ProductionService(config)
        self.cost_estimator = CostEstimator()
        self.reliability = ReliabilityService(config, manager=self.manager, resources=self.resources)

    async def create(self, topic: str) -> RunState:
        cleaned_topic = topic.strip()
        if not cleaned_topic:
            raise ValueError("主题不能为空")
        state = self.manager.create(cleaned_topic, self.config.model_dump(mode="json"))
        self.production.ensure_plan(state, requested_operation="full")
        state = self.manager.load(state.run_id)
        return await self._run_text_pipeline(state, force=False)

    async def start_planned(self, run_id: str) -> RunState:
        """显式启动已通过人工审批的规划 run，并只推进现有文本创作阶段。"""
        state = self.manager.load(run_id)
        if not state.planning_provenance:
            raise ValueError("run 不包含 planning provenance，不能通过 creator-loop 启动")
        self.production.ensure_plan(state, requested_operation="full")
        state = self.manager.load(run_id)
        if state.text_pipeline_completed:
            return state
        return await self._run_text_pipeline(state, force=False)

    async def resume(self, run_id: str, *, force: bool = False) -> RunState:
        state = self.manager.load(run_id)
        self.production.ensure_plan(state, requested_operation="full")
        state = self.manager.load(run_id)
        if state.review_ready and self.manager.artifact_exists(state, "publish_qa_report") and not force:
            return state
        if state.package_pipeline_completed and self.manager.artifact_exists(state, "publish_package"):
            return await self._run_publish_qa_pipeline(state, force=force)
        if state.video_pipeline_completed and all(
            self.manager.artifact_exists(state, key) for key in ("final_video", "video_qa_report")
        ):
            return await self._run_package_pipeline(state, force=force)
        if state.audio_pipeline_completed and all(
            self.manager.artifact_exists(state, key)
            for key in ("storyboard", "audio_manifest", "narration", "subtitles_json", "audio_qa_report")
        ):
            return await self._run_video_pipeline(state, force=force)
        state = await self._run_text_pipeline(state, force=force)
        return await self._run_audio_pipeline(state, force=force)

    async def render(self, run_id: str, *, force: bool = False) -> RunState:
        state = self.manager.load(run_id)
        self.production.ensure_plan(state, requested_operation="full")
        state = self.manager.load(run_id)
        if not state.audio_pipeline_completed:
            raise VideoPipelineError("run 尚未达到 audio_ready，不能渲染视频")
        return await self._run_video_pipeline(state, force=force)

    async def package(self, run_id: str, *, force: bool = False) -> RunState:
        state = self.manager.load(run_id)
        self.production.ensure_plan(state, requested_operation="full")
        state = self.manager.load(run_id)
        if not state.video_pipeline_completed:
            raise PublishPipelineError("run 尚未达到 video_ready，不能生成投稿包")
        return await self._run_package_pipeline(state, force=force)

    async def publish_check(self, run_id: str, *, force: bool = False) -> RunState:
        state = self.manager.load(run_id)
        self.production.ensure_plan(state, requested_operation="full")
        state = self.manager.load(run_id)
        if not state.package_pipeline_completed:
            raise PublishPipelineError("run 尚未达到 package_ready，不能执行发布前 QA")
        return await self._run_publish_qa_pipeline(state, force=force)

    async def voice(self, run_id: str, *, force: bool = False) -> RunState:
        state = self.manager.load(run_id)
        state.config_snapshot["tts"] = self.config.tts.model_dump(mode="json")
        self.manager.save(state)
        storyboard = self._load_text_artifact(state, "storyboard", Storyboard)
        await self._voice(state, storyboard, force=force)
        state.audio_pipeline_completed = False
        state.pipeline_phase = "voice_ready"
        state.milestone = "voice_ready"
        self.manager.save(state)
        return state

    async def subtitle(self, run_id: str, *, force: bool = False) -> RunState:
        state = self.manager.load(run_id)
        state.config_snapshot["subtitle"] = self.config.subtitle.model_dump(mode="json")
        state.config_snapshot["asr"] = self.config.asr.model_dump(mode="json")
        self.manager.save(state)
        storyboard = self._load_text_artifact(state, "storyboard", Storyboard)
        manifest = self._load_text_artifact(state, "audio_manifest", AudioManifest)
        subtitles = await self._subtitle(state, storyboard, manifest, force=force)
        report = await self._audio_qa(state, storyboard, manifest, subtitles, force=force)
        if not report.passed:
            raise AudioPipelineError("音频 QA 存在硬错误，任务已标记为 failed")
        return self._mark_audio_ready(state)

    async def _run_text_pipeline(self, state: RunState, *, force: bool) -> RunState:
        research = await self._research(state, force=force)
        script = await self._write(state, research, force=force)
        storyboard = await self._storyboard(state, script, force=force)
        report = await self._qa(state, research, script, storyboard, force=force)
        if not report.passed:
            raise TextPipelineError("文本 QA 存在硬错误，任务已标记为 failed")

        state.text_pipeline_completed = True
        state.milestone = "text_ready"
        state.pipeline_phase = "text_ready"
        self.manager.save(state)
        self.manager.append_event(state.run_id, "text_pipeline_completed", stage=Stage.QA)
        return state

    async def _run_audio_pipeline(self, state: RunState, *, force: bool) -> RunState:
        storyboard = self._load_text_artifact(state, "storyboard", Storyboard)
        manifest = await self._voice(state, storyboard, force=force)
        subtitles = await self._subtitle(state, storyboard, manifest, force=force)
        report = await self._audio_qa(state, storyboard, manifest, subtitles, force=force)
        if not report.passed:
            raise AudioPipelineError("音频 QA 存在硬错误，任务已标记为 failed")
        return self._mark_audio_ready(state)

    async def _voice(self, state: RunState, storyboard: Storyboard, *, force: bool) -> AudioManifest:
        if self._can_skip(
            state, Stage.GENERATING_VOICE, ("audio_manifest", "narration"), force, "tts"
        ):
            return self._load_text_artifact(state, "audio_manifest", AudioManifest)

        async def action() -> AudioManifest:
            result = await self.voice_worker.run(state, storyboard, force=force)
            self._invalidate_stages(
                state,
                (
                    Stage.GENERATING_SUBTITLES,
                    Stage.QA,
                    Stage.RENDERING,
                    Stage.VIDEO_QA,
                    Stage.PACKAGING,
                    Stage.PUBLISH_QA,
                    Stage.READY_FOR_REVIEW,
                ),
                (
                    "subtitles_json",
                    "subtitles_srt",
                    "audio_qa_report",
                    "composition",
                    "assets_manifest",
                    "render_config",
                    "render_result",
                    "final_video",
                    "video_qa_report",
                    "publish_package",
                    "publish_metadata",
                    "publish_title",
                    "publish_description",
                    "publish_tags",
                    "publish_cover",
                    "publish_qa_report",
                ),
            )
            state.audio_pipeline_completed = False
            state.video_pipeline_completed = False
            state.package_pipeline_completed = False
            state.review_ready = False
            state.artifacts.update(
                {
                    "audio_manifest": "audio/audio_manifest.json",
                    "narration": "audio/narration.wav",
                }
            )
            return result

        return await self._execute(state, Stage.GENERATING_VOICE, action, production_stage="tts")

    async def _subtitle(
        self,
        state: RunState,
        storyboard: Storyboard,
        manifest: AudioManifest,
        *,
        force: bool,
    ) -> SubtitleDocument:
        if self._can_skip(
            state,
            Stage.GENERATING_SUBTITLES,
            ("subtitles_json", "subtitles_srt"),
            force,
            "subtitle_alignment",
        ):
            return self._load_text_artifact(state, "subtitles_json", SubtitleDocument)

        async def action() -> SubtitleDocument:
            result = self.subtitle_worker.run(state, storyboard, manifest)
            self._invalidate_stages(
                state,
                (
                    Stage.QA,
                    Stage.RENDERING,
                    Stage.VIDEO_QA,
                    Stage.PACKAGING,
                    Stage.PUBLISH_QA,
                    Stage.READY_FOR_REVIEW,
                ),
                (
                    "audio_qa_report",
                    "composition",
                    "assets_manifest",
                    "render_config",
                    "render_result",
                    "final_video",
                    "video_qa_report",
                    "publish_package",
                    "publish_metadata",
                    "publish_title",
                    "publish_description",
                    "publish_tags",
                    "publish_cover",
                    "publish_qa_report",
                ),
            )
            state.audio_pipeline_completed = False
            state.video_pipeline_completed = False
            state.package_pipeline_completed = False
            state.review_ready = False
            state.artifacts.update(
                {
                    "subtitles_json": "subtitles/subtitles.json",
                    "subtitles_srt": "subtitles/subtitles.srt",
                }
            )
            return result

        return await self._execute(
            state, Stage.GENERATING_SUBTITLES, action, production_stage="subtitle_alignment"
        )

    async def _audio_qa(
        self,
        state: RunState,
        storyboard: Storyboard,
        manifest: AudioManifest,
        subtitles: SubtitleDocument,
        *,
        force: bool,
    ) -> AudioQAReport:
        if self._can_skip(state, Stage.QA, ("audio_qa_report",), force, "audio_qa"):
            return self._load_text_artifact(state, "audio_qa_report", AudioQAReport)

        async def action() -> AudioQAReport:
            result = self.audio_qa_worker.run(state, storyboard, manifest, subtitles)
            self.manager.write_json(state.run_id, "audio_qa_report.json", result.model_dump(mode="json"))
            state.artifacts["audio_qa_report"] = "audio_qa_report.json"
            if not result.passed:
                raise AudioPipelineError("音频 QA 未通过")
            return result

        return await self._execute(state, Stage.QA, action, production_stage="audio_qa")

    def _mark_audio_ready(self, state: RunState) -> RunState:
        state.audio_pipeline_completed = True
        state.pipeline_phase = "audio_ready"
        state.milestone = "audio_ready"
        self.manager.save(state)
        self.manager.append_event(state.run_id, "audio_pipeline_completed", stage=Stage.QA)
        return state

    async def _run_video_pipeline(self, state: RunState, *, force: bool) -> RunState:
        storyboard = self._load_text_artifact(state, "storyboard", Storyboard)
        manifest = self._load_text_artifact(state, "audio_manifest", AudioManifest)
        subtitles = self._load_text_artifact(state, "subtitles_json", SubtitleDocument)
        result = await self._video_render(state, storyboard, manifest, subtitles, force=force)
        report = await self._video_qa(state, result, manifest, force=force)
        if not report.passed:
            raise VideoPipelineError("视频 QA 存在硬错误，任务已标记为 failed")
        return self._mark_video_ready(state)

    async def _video_render(
        self,
        state: RunState,
        storyboard: Storyboard,
        manifest: AudioManifest,
        subtitles: SubtitleDocument,
        *,
        force: bool,
    ) -> VideoRenderResult:
        artifacts = ("composition", "assets_manifest", "render_config", "render_result", "final_video")
        if self._can_skip(state, Stage.RENDERING, artifacts, force, "render"):
            return self._load_text_artifact(state, "render_result", VideoRenderResult)

        async def action() -> VideoRenderResult:
            _, result = self.video_worker.run(state, storyboard, manifest, subtitles)
            self._invalidate_stages(
                state,
                (Stage.VIDEO_QA, Stage.PACKAGING, Stage.PUBLISH_QA, Stage.READY_FOR_REVIEW),
                (
                    "video_qa_report",
                    "publish_package",
                    "publish_metadata",
                    "publish_title",
                    "publish_description",
                    "publish_tags",
                    "publish_cover",
                    "publish_qa_report",
                ),
            )
            state.video_pipeline_completed = False
            state.package_pipeline_completed = False
            state.review_ready = False
            state.artifacts.update(
                {
                    "composition": "video/composition.json",
                    "assets_manifest": "video/assets_manifest.json",
                    "render_config": "video/render_config.json",
                    "render_result": "video/render_result.json",
                    "final_video": self.config.render.output_dir.joinpath("final.mp4").as_posix(),
                }
            )
            return result

        return await self._execute(state, Stage.RENDERING, action, production_stage="render")

    async def _video_qa(
        self,
        state: RunState,
        result: VideoRenderResult,
        manifest: AudioManifest,
        *,
        force: bool,
    ) -> VideoQAReport:
        if self._can_skip(state, Stage.VIDEO_QA, ("video_qa_report",), force, "video_qa"):
            return self._load_text_artifact(state, "video_qa_report", VideoQAReport)

        async def action() -> VideoQAReport:
            report = self.video_qa_worker.run(result.mp4_path, manifest.total_duration_sec)
            self.manager.write_json(
                state.run_id,
                "qa/video_qa_report.json",
                report.model_dump(mode="json"),
            )
            state.artifacts["video_qa_report"] = "qa/video_qa_report.json"
            if not report.passed:
                raise VideoPipelineError("视频 QA 未通过")
            return report

        return await self._execute(state, Stage.VIDEO_QA, action, production_stage="video_qa")

    def _mark_video_ready(self, state: RunState) -> RunState:
        state.video_pipeline_completed = True
        state.pipeline_phase = "video_ready"
        state.milestone = "video_ready"
        self.manager.save(state)
        self.manager.append_event(state.run_id, "video_pipeline_completed", stage=Stage.VIDEO_QA)
        return state

    async def _run_package_pipeline(self, state: RunState, *, force: bool) -> RunState:
        research = self._load_text_artifact(state, "research", ResearchResult)
        script = self._load_text_artifact(state, "script", Script)
        storyboard = self._load_text_artifact(state, "storyboard", Storyboard)
        await self._publish_package(state, research, script, storyboard, force=force)
        state.package_pipeline_completed = True
        state.review_ready = False
        state.pipeline_phase = "package_ready"
        state.milestone = "package_ready"
        self.manager.save(state)
        self.manager.append_event(state.run_id, "package_pipeline_completed", stage=Stage.PACKAGING)
        return state

    async def _publish_package(
        self,
        state: RunState,
        research: ResearchResult,
        script: Script,
        storyboard: Storyboard,
        *,
        force: bool,
    ) -> PublishPackage:
        artifacts = (
            "publish_package",
            "publish_metadata",
            "publish_title",
            "publish_description",
            "publish_tags",
            "publish_cover",
        )
        if self._can_skip(state, Stage.PACKAGING, artifacts, force, "cover"):
            return self._load_text_artifact(state, "publish_package", PublishPackage)

        async def action() -> PublishPackage:
            package = self.publish_worker.run(state, research, script, storyboard)
            self._invalidate_stages(
                state,
                (Stage.PUBLISH_QA, Stage.READY_FOR_REVIEW),
                ("publish_qa_report",),
            )
            state.review_ready = False
            state.artifacts.update(
                {
                    "publish_package": "publish/publish_package.json",
                    "publish_metadata": "publish/metadata.json",
                    "publish_title": "publish/title.txt",
                    "publish_description": "publish/description.md",
                    "publish_tags": "publish/tags.json",
                    "publish_cover": package.cover_path.as_posix(),
                }
            )
            return package

        return await self._execute(state, Stage.PACKAGING, action, production_stage="cover")

    async def _run_publish_qa_pipeline(self, state: RunState, *, force: bool) -> RunState:
        package = self._load_text_artifact(state, "publish_package", PublishPackage)
        report = await self._publish_qa(state, package, force=force)
        if not report.passed:
            raise PublishPipelineError("发布前 QA 存在硬错误，任务已标记为 failed")
        state.complete_stage(Stage.READY_FOR_REVIEW)
        state.review_ready = True
        state.pipeline_phase = "review_ready"
        state.milestone = "review_ready"
        self.manager.save(state)
        self.manager.append_event(state.run_id, "ready_for_review", stage=Stage.READY_FOR_REVIEW)
        if state.creator_job_id:
            from alysia.creator import CreatorRunBridge

            CreatorRunBridge(self.config).sync_review_ready(state)
        return state

    async def _publish_qa(
        self,
        state: RunState,
        package: PublishPackage,
        *,
        force: bool,
    ) -> PublishQAReport:
        if self._can_skip(state, Stage.PUBLISH_QA, ("publish_qa_report",), force, "publish_qa"):
            return self._load_text_artifact(state, "publish_qa_report", PublishQAReport)

        async def action() -> PublishQAReport:
            report = self.publish_qa_worker.run(state, package)
            state.artifacts["publish_qa_report"] = "publish/publish_qa_report.json"
            if not report.passed:
                raise PublishPipelineError("发布前 QA 未通过")
            return report

        return await self._execute(state, Stage.PUBLISH_QA, action, production_stage="publish_qa")

    def _load_text_artifact(self, state: RunState, key: str, model: type[ResultT]) -> ResultT:
        relative = state.artifacts.get(key)
        if not relative or not self.manager.artifact_exists(state, key):
            raise FileNotFoundError(f"run 缺少必需产物：{key}")
        return model.model_validate(self.manager.read_json(state.run_id, relative))

    @staticmethod
    def _invalidate_stages(state: RunState, stages: tuple[Stage, ...], artifacts: tuple[str, ...]) -> None:
        state.completed_stages = [stage for stage in state.completed_stages if stage not in stages]
        for artifact in artifacts:
            state.artifacts.pop(artifact, None)

    async def _research(self, state: RunState, *, force: bool) -> ResearchResult:
        if self._can_skip(
            state, Stage.RESEARCHING, ("research", "research_markdown"), force, "research"
        ):
            return ResearchResult.model_validate(self.manager.read_json(state.run_id, state.artifacts["research"]))

        async def action() -> ResearchResult:
            result = await self.researcher.run(state.topic)
            self.manager.write_json(state.run_id, "sources.json", result.model_dump(mode="json"))
            self.manager.write_text(state.run_id, "research.md", result.to_markdown())
            state.artifacts.update({"research": "sources.json", "research_markdown": "research.md"})
            if self.config.knowledge.enabled:
                knowledge = KnowledgeService(self.config)
                ingestion = knowledge.pipeline.ingest(result, domain="general")
                self.manager.write_json(
                    state.run_id,
                    "knowledge/research_knowledge_result.json",
                    ingestion.model_dump(mode="json"),
                )
                state.artifacts["research_knowledge_result"] = "knowledge/research_knowledge_result.json"
            return result

        return await self._execute(state, Stage.RESEARCHING, action, production_stage="research")

    async def _write(self, state: RunState, research: ResearchResult, *, force: bool) -> Script:
        if self._can_skip(
            state, Stage.WRITING, ("script", "script_markdown", "metadata"), force, "script"
        ):
            return Script.model_validate(self.manager.read_json(state.run_id, state.artifacts["script"]))

        async def action() -> Script:
            prompt = None
            if self.identity_service is not None:
                prompt = self.identity_service.build_prompt_context(
                    state,
                    role="writer",
                    base_task_prompt=load_prompt("writer"),
                ).rendered_context
            knowledge = KnowledgeService(self.config) if self.config.knowledge.enabled else None
            knowledge_context = (
                knowledge.context.select(state.topic, role="writer").model_dump(mode="json")
                if knowledge is not None
                else None
            )
            result = await self.writer.run(
                state.topic,
                research,
                assembled_prompt=prompt,
                knowledge_context=knowledge_context,
            )
            self.manager.write_json(state.run_id, "script.json", result.model_dump(mode="json"))
            self.manager.write_text(state.run_id, "script.md", result.to_markdown())
            metadata = {
                "topic": state.topic,
                "title": result.title,
                "description": result.thesis,
                "tags": ["AI Agent", "AGI", "人工智能"],
                "language": self.config.content.language,
                "target_duration_sec": result.target_duration_sec,
            }
            self.manager.write_json(state.run_id, "metadata.json", metadata)
            state.artifacts.update(
                {"script": "script.json", "script_markdown": "script.md", "metadata": "metadata.json"}
            )
            if knowledge is not None:
                grounding = knowledge.grounding.check(result, run_id=state.run_id)
                knowledge.grounding.save(grounding, self.manager.run_dir(state.run_id))
                qa = knowledge.qa.run(grounding=grounding)
                self.manager.write_json(
                    state.run_id,
                    "knowledge/knowledge_qa_report.json",
                    qa.model_dump(mode="json"),
                )
                selected_claims = knowledge.context.select(state.topic, role="writer").claims
                knowledge.store.snapshot_run(self.manager.run_dir(state.run_id), selected_claims)
                state.artifacts.update(
                    {
                        "grounding_report": "knowledge/grounding_report.json",
                        "knowledge_qa_report": "knowledge/knowledge_qa_report.json",
                        "claims_used": "knowledge/claims_used.json",
                        "source_snapshot": "knowledge/source_snapshot.json",
                    }
                )
                strict_grounding = self.config.qa.strict or self.config.research.provider != "mock"
                if strict_grounding and (not grounding.passed or not qa.passed):
                    raise TextPipelineError("知识 Grounding/QA 未通过；需要重新调研后 resume")
            return result

        return await self._execute(state, Stage.WRITING, action, production_stage="script")

    async def _storyboard(self, state: RunState, script: Script, *, force: bool) -> Storyboard:
        if self._can_skip(state, Stage.STORYBOARDING, ("storyboard",), force, "storyboard"):
            return Storyboard.model_validate(self.manager.read_json(state.run_id, state.artifacts["storyboard"]))

        async def action() -> Storyboard:
            prompt = None
            if self.identity_service is not None:
                prompt = self.identity_service.build_prompt_context(
                    state,
                    role="director",
                    base_task_prompt=load_prompt("director"),
                ).rendered_context
            result = await self.director.run(script, assembled_prompt=prompt)
            self.manager.write_json(state.run_id, "storyboard.json", result.model_dump(mode="json"))
            state.artifacts["storyboard"] = "storyboard.json"
            return result

        return await self._execute(state, Stage.STORYBOARDING, action, production_stage="storyboard")

    async def _qa(
        self,
        state: RunState,
        research: ResearchResult,
        script: Script,
        storyboard: Storyboard,
        *,
        force: bool,
    ) -> TextQAReport:
        if self._can_skip(state, Stage.QA, ("text_qa_report",), force, "text_qa"):
            return TextQAReport.model_validate(
                self.manager.read_json(state.run_id, state.artifacts["text_qa_report"])
            )

        async def action() -> TextQAReport:
            result = self.critic.run(state.topic, research, script, storyboard)
            self.manager.write_json(state.run_id, "text_qa_report.json", result.model_dump(mode="json"))
            state.artifacts["text_qa_report"] = "text_qa_report.json"
            if not result.passed:
                raise TextPipelineError("文本 QA 未通过")
            return result

        return await self._execute(state, Stage.QA, action, production_stage="text_qa")

    def _can_skip(
        self,
        state: RunState,
        stage: Stage,
        artifacts: tuple[str, ...],
        force: bool,
        production_stage: str,
    ) -> bool:
        can_skip = (
            not force
            and stage in state.completed_stages
            and all(self.manager.artifact_exists(state, artifact) for artifact in artifacts)
        )
        if can_skip:
            try:
                plan = self.production.load_plan(state.run_id)
                provider_id = plan.selected_provider_per_stage.get(
                    production_stage, f"deterministic.{production_stage}"
                )
                capability = self.production.registry.get(provider_id)
                now = datetime.now().astimezone()
                self.production.metrics_store(state.run_id, plan.plan_id).record_stage(
                    StageExecutionMetric(
                        stage_id=production_stage,
                        start_time=now,
                        end_time=now,
                        elapsed_sec=0,
                        provider=provider_id,
                        success=True,
                        cache_hit=True,
                        estimated_cost=self.cost_estimator.estimate(capability),
                        actual_cost=self.cost_estimator.estimate(capability),
                    )
                )
            except (FileNotFoundError, KeyError, ValueError):
                pass
        return can_skip

    async def _execute(
        self,
        state: RunState,
        stage: Stage,
        action: Callable[[], Awaitable[ResultT]],
        *,
        production_stage: str,
    ) -> ResultT:
        state.start_stage(stage)
        self.manager.save(state)
        self.reliability.checkpoint(state, "started")
        self.manager.append_event(state.run_id, "stage_started", stage=stage)
        plan = self.production.load_plan(state.run_id)
        planned = next((item for item in plan.stages if item.stage_id == production_stage), None)
        choices = [planned.selected_provider, *planned.fallback_chain] if planned else []
        if not choices:
            choices = [f"deterministic.{production_stage}"]
        max_attempts = min(len(choices), plan.profile.max_retries_per_stage + 1)
        choices = choices[:max_attempts]
        metrics = self.production.metrics_store(state.run_id, plan.plan_id)
        last_error: Exception | None = None
        attempt_failures: list[str] = []
        original_choice = choices[0]
        for attempt, provider_id in enumerate(choices):
            self._configure_provider(production_stage, provider_id)
            started_at = datetime.now().astimezone()
            started = monotonic()
            try:
                fallback_count_before = len(metrics.load().fallbacks)
                result = await action()
                capability = self.production.registry.get(provider_id)
                ended_at = datetime.now().astimezone()
                internal_fallback = len(metrics.load().fallbacks) > fallback_count_before
                metrics.record_stage(
                    StageExecutionMetric(
                        stage_id=production_stage,
                        start_time=started_at,
                        end_time=ended_at,
                        elapsed_sec=monotonic() - started,
                        provider=provider_id,
                        success=True,
                        retry_count=attempt,
                        fallback_used=attempt > 0 or internal_fallback,
                        estimated_cost=self.cost_estimator.estimate(capability),
                        actual_cost=self.cost_estimator.estimate(capability),
                    )
                )
                state.complete_stage(stage)
                self.manager.save(state)
                self.reliability.checkpoint(state, "succeeded")
                for failure_id in attempt_failures:
                    self.reliability.mark_recovered(
                        state.run_id,
                        failure_id,
                        reexecuted_stages=[self.reliability.artifact_owner(production_stage) or production_stage],
                    )
                self.manager.append_event(state.run_id, "stage_completed", stage=stage)
                return result
            except Exception as exc:  # 边界层负责记录任意 provider/schema 错误
                last_error = exc
                failure, decision = self.reliability.record_exception(
                    exc,
                    state=state,
                    stage=production_stage,
                    provider=provider_id,
                    retry_count=attempt,
                    fallback_refs=choices[attempt + 1 :],
                )
                attempt_failures.append(failure.failure_id)
                capability = self.production.registry.get(provider_id)
                ended_at = datetime.now().astimezone()
                metrics.record_stage(
                    StageExecutionMetric(
                        stage_id=production_stage,
                        start_time=started_at,
                        end_time=ended_at,
                        elapsed_sec=monotonic() - started,
                        provider=provider_id,
                        success=False,
                        failure_reason=str(exc),
                        retry_count=attempt,
                        fallback_used=attempt > 0,
                        estimated_cost=self.cost_estimator.estimate(capability),
                        actual_cost=self.cost_estimator.estimate(capability),
                    )
                )
                if attempt + 1 < len(choices):
                    failure.status = "recovering"
                    self.reliability.failures(state.run_id).save(failure)
                    if decision.action == "retry_with_backoff" and decision.retry_after_sec > 0:
                        self.manager.append_event(
                            state.run_id,
                            "stage_retry_backoff",
                            stage=stage,
                            seconds=decision.retry_after_sec,
                        )
                        await asyncio.sleep(decision.retry_after_sec)
                    fallback_id = choices[attempt + 1]
                    fallback_capability = self.production.registry.get(fallback_id)
                    metrics.record_fallback(
                        FallbackRecord(
                            stage_id=production_stage,
                            original_choice=provider_id,
                            failure_reason=str(exc),
                            fallback_choice=fallback_id,
                            quality_impact=(
                                f"quality {capability.expected_quality_class} → "
                                f"{fallback_capability.expected_quality_class}"
                            ),
                            occurred_at=ended_at,
                        )
                    )
                    self.manager.append_event(state.run_id, "stage_retry", stage=stage)

        assert last_error is not None
        state.fail_stage(stage, last_error)
        self.manager.save(state)
        self.reliability.checkpoint(state, "failed")
        self.manager.append_event(state.run_id, "stage_failed", stage=stage)
        raise last_error

    def _configure_provider(self, stage_id: str, provider_id: str) -> None:
        if self._current_provider_id(stage_id) == provider_id:
            return
        if provider_id.startswith("deterministic."):
            return
        if stage_id == "research":
            self.research_provider = build_research_provider_id(self.config, provider_id)
            self.researcher = Researcher(self.research_provider, self.config.research.max_sources)
        elif stage_id == "script":
            provider = build_llm_provider_id(self.config, provider_id)
            self.writer = Writer(provider, self.config.content.default_duration_sec)
        elif stage_id == "storyboard":
            provider = build_llm_provider_id(self.config, provider_id)
            self.director = Director(provider)
        elif stage_id == "tts":
            self.tts_provider = build_tts_provider_id(self.config, provider_id)
            self.voice_worker = VoiceWorker(self.manager, self.config.tts, self.tts_provider, self.resources)
        elif stage_id == "subtitle_alignment":
            self.asr_provider = build_asr_provider_id(self.config, provider_id)
            self.subtitle_worker = SubtitleWorker(
                self.manager,
                self.config.subtitle,
                self.resources,
                self.asr_provider,
            )
        elif stage_id == "render":
            self.video_renderer = build_video_renderer_id(self.config, provider_id)
            self.video_worker = VideoRenderWorker(self.manager, self.config, self.video_renderer)
        elif stage_id == "cover":
            self.cover_generator = TemplateCoverGenerator(
                self.config.publish.cover,
                self.config.visual_identity.template_version,
            )
            self.publish_worker = PublishPackageWorker(
                self.manager, self.config, self.cover_generator
            )

    def _current_provider_id(self, stage_id: str) -> str | None:
        if stage_id == "research":
            if isinstance(self.research_provider, MockResearchProvider):
                return "research.mock"
            if isinstance(self.research_provider, ManualResearchProvider):
                return "research.manual"
            if isinstance(self.research_provider, WebResearchProvider):
                return "research.web"
        if stage_id in {"script", "storyboard"}:
            agent = self.writer if stage_id == "script" else self.director
            provider = getattr(agent, "provider", None)
            if isinstance(provider, MockLLMProvider):
                return "llm.mock"
            if isinstance(provider, OllamaProvider):
                return "llm.ollama"
            if isinstance(provider, CloudLLMProvider):
                return "llm.cloud"
        if stage_id == "tts":
            return f"tts.{getattr(self.tts_provider, 'name', '')}".rstrip(".")
        if stage_id == "subtitle_alignment":
            return (
                f"asr.{getattr(self.asr_provider, 'name', '')}".rstrip(".")
                if self.asr_provider is not None
                else "subtitle.deterministic"
            )
        if stage_id == "render":
            return f"render.{getattr(self.video_renderer, 'name', '')}".rstrip(".")
        if stage_id == "cover" and isinstance(self.cover_generator, TemplateCoverGenerator):
            return "cover.template"
        return None


def build_llm_provider(config: AlysiaConfig) -> BaseLLMProvider:
    if config.llm.provider == "mock":
        return MockLLMProvider()
    if config.llm.provider == "ollama":
        from alysia.security import SecurityService
        return OllamaProvider(
            config.llm.model, config.llm.base_url, config.llm.timeout_sec,
            security=SecurityService(config),
        )
    if config.llm.provider == "cloud":
        return CloudLLMProvider()
    raise ValueError(f"不支持的 LLM provider：{config.llm.provider}")


def build_research_provider(config: AlysiaConfig) -> BaseResearchProvider:
    if config.research.provider == "mock":
        return MockResearchProvider()
    if config.research.provider == "manual":
        if config.research.manual_source_file is None:
            raise ValueError("research.provider=manual 需要 research.manual_source_file")
        return ManualResearchProvider(config.research.manual_source_file)
    if config.research.provider == "web":
        from alysia.security import SecurityService
        return WebResearchProvider(security=SecurityService(config))
    raise ValueError(f"不支持的 Research provider：{config.research.provider}")


def build_tts_provider(config: AlysiaConfig) -> BaseTTSProvider:
    if config.tts.provider == "mock":
        return MockTTSProvider()
    if config.tts.provider == "sapi":
        return SapiTTSProvider()
    if config.tts.provider == "cosyvoice":
        return CosyVoiceProvider(config.tts.model_dir)
    raise ValueError(f"不支持的 TTS provider：{config.tts.provider}")


def build_asr_provider(config: AlysiaConfig) -> BaseASRProvider | None:
    if not config.asr.enabled:
        return None
    if config.asr.provider == "mock":
        return MockASRProvider()
    if config.asr.provider == "faster-whisper":
        return FasterWhisperProvider(
            config.asr.model,
            config.asr.device,
            config.asr.compute_type,
            local_files_only=config.asr.local_files_only,
        )
    raise ValueError(f"不支持的 ASR provider：{config.asr.provider}")


def build_video_renderer(config: AlysiaConfig) -> BaseVideoRenderer:
    if config.video.renderer == "mock":
        return MockVideoRenderer(config.video, config.render)
    if config.video.renderer == "remotion":
        return RemotionRenderer(config.video, config.render)
    raise ValueError(f"不支持的 Video renderer：{config.video.renderer}")


def build_llm_provider_id(config: AlysiaConfig, provider_id: str) -> BaseLLMProvider:
    if provider_id == "llm.mock":
        return MockLLMProvider()
    if provider_id == "llm.ollama":
        from alysia.security import SecurityService
        return OllamaProvider(
            config.llm.model, config.llm.base_url, config.llm.timeout_sec,
            security=SecurityService(config),
        )
    if provider_id == "llm.cloud":
        return CloudLLMProvider()
    raise ValueError(f"ProductionPlan 指定了不支持的 LLM provider：{provider_id}")


def build_research_provider_id(config: AlysiaConfig, provider_id: str) -> BaseResearchProvider:
    if provider_id == "research.mock":
        return MockResearchProvider()
    if provider_id == "research.manual":
        if config.research.manual_source_file is None:
            raise ValueError("research.manual 需要 research.manual_source_file")
        return ManualResearchProvider(config.research.manual_source_file)
    if provider_id == "research.web":
        from alysia.security import SecurityService
        return WebResearchProvider(security=SecurityService(config))
    raise ValueError(f"ProductionPlan 指定了不支持的 Research provider：{provider_id}")


def build_tts_provider_id(config: AlysiaConfig, provider_id: str) -> BaseTTSProvider:
    if provider_id == "tts.mock":
        return MockTTSProvider()
    if provider_id == "tts.sapi":
        return SapiTTSProvider()
    if provider_id == "tts.cosyvoice":
        return CosyVoiceProvider(config.tts.model_dir)
    raise ValueError(f"ProductionPlan 指定了不支持的 TTS provider：{provider_id}")


def build_asr_provider_id(config: AlysiaConfig, provider_id: str) -> BaseASRProvider | None:
    if provider_id == "subtitle.deterministic":
        return None
    if provider_id == "asr.mock":
        return MockASRProvider()
    if provider_id == "asr.faster-whisper":
        return FasterWhisperProvider(
            config.asr.model,
            config.asr.device,
            config.asr.compute_type,
            local_files_only=config.asr.local_files_only,
        )
    raise ValueError(f"ProductionPlan 指定了不支持的 ASR provider：{provider_id}")


def build_video_renderer_id(config: AlysiaConfig, provider_id: str) -> BaseVideoRenderer:
    if provider_id == "render.mock":
        return MockVideoRenderer(config.video, config.render)
    if provider_id == "render.remotion":
        return RemotionRenderer(config.video, config.render)
    raise ValueError(f"ProductionPlan 指定了不支持的 Video renderer：{provider_id}")
