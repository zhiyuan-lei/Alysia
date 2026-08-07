from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from pydantic import BaseModel

from alysia.agents import Director, Researcher, TextCritic, Writer
from alysia.core.config import AlysiaConfig
from alysia.core.run import RunManager, RunState
from alysia.core.state import Stage
from alysia.providers.llm import BaseLLMProvider, CloudLLMProvider, MockLLMProvider, OllamaProvider
from alysia.providers.search import BaseResearchProvider, MockResearchProvider, WebResearchProvider
from alysia.schemas import ResearchResult, Script, Storyboard, TextQAReport

ResultT = TypeVar("ResultT", bound=BaseModel)


class TextPipelineError(RuntimeError):
    pass


class AlysiaOrchestrator:
    def __init__(
        self,
        config: AlysiaConfig,
        *,
        llm_provider: BaseLLMProvider | None = None,
        research_provider: BaseResearchProvider | None = None,
    ) -> None:
        self.config = config
        self.manager = RunManager(config.runtime.runs_dir)
        self.llm_provider = llm_provider or build_llm_provider(config)
        self.research_provider = research_provider or build_research_provider(config)
        self.researcher = Researcher(self.research_provider, config.research.max_sources)
        self.writer = Writer(self.llm_provider, config.content.default_duration_sec)
        self.director = Director(self.llm_provider)
        self.critic = TextCritic(config.content)

    async def create(self, topic: str) -> RunState:
        cleaned_topic = topic.strip()
        if not cleaned_topic:
            raise ValueError("主题不能为空")
        state = self.manager.create(cleaned_topic, self.config.model_dump(mode="json"))
        return await self._run_text_pipeline(state, force=False)

    async def resume(self, run_id: str, *, force: bool = False) -> RunState:
        state = self.manager.load(run_id)
        return await self._run_text_pipeline(state, force=force)

    async def _run_text_pipeline(self, state: RunState, *, force: bool) -> RunState:
        research = await self._research(state, force=force)
        script = await self._write(state, research, force=force)
        storyboard = await self._storyboard(state, script, force=force)
        report = await self._qa(state, research, script, storyboard, force=force)
        if not report.passed:
            raise TextPipelineError("文本 QA 存在硬错误，任务已标记为 failed")

        state.text_pipeline_completed = True
        state.milestone = "text_ready"
        state.pipeline_phase = "text"
        self.manager.save(state)
        self.manager.append_event(state.run_id, "text_pipeline_completed", stage=Stage.QA)
        return state

    async def _research(self, state: RunState, *, force: bool) -> ResearchResult:
        if self._can_skip(state, Stage.RESEARCHING, ("research", "research_markdown"), force):
            return ResearchResult.model_validate(self.manager.read_json(state.run_id, state.artifacts["research"]))

        async def action() -> ResearchResult:
            result = await self.researcher.run(state.topic)
            self.manager.write_json(state.run_id, "sources.json", result.model_dump(mode="json"))
            self.manager.write_text(state.run_id, "research.md", result.to_markdown())
            state.artifacts.update({"research": "sources.json", "research_markdown": "research.md"})
            return result

        return await self._execute(state, Stage.RESEARCHING, action)

    async def _write(self, state: RunState, research: ResearchResult, *, force: bool) -> Script:
        if self._can_skip(state, Stage.WRITING, ("script", "script_markdown", "metadata"), force):
            return Script.model_validate(self.manager.read_json(state.run_id, state.artifacts["script"]))

        async def action() -> Script:
            result = await self.writer.run(state.topic, research)
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
            return result

        return await self._execute(state, Stage.WRITING, action)

    async def _storyboard(self, state: RunState, script: Script, *, force: bool) -> Storyboard:
        if self._can_skip(state, Stage.STORYBOARDING, ("storyboard",), force):
            return Storyboard.model_validate(self.manager.read_json(state.run_id, state.artifacts["storyboard"]))

        async def action() -> Storyboard:
            result = await self.director.run(script)
            self.manager.write_json(state.run_id, "storyboard.json", result.model_dump(mode="json"))
            state.artifacts["storyboard"] = "storyboard.json"
            return result

        return await self._execute(state, Stage.STORYBOARDING, action)

    async def _qa(
        self,
        state: RunState,
        research: ResearchResult,
        script: Script,
        storyboard: Storyboard,
        *,
        force: bool,
    ) -> TextQAReport:
        if self._can_skip(state, Stage.QA, ("text_qa_report",), force):
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

        return await self._execute(state, Stage.QA, action)

    def _can_skip(self, state: RunState, stage: Stage, artifacts: tuple[str, ...], force: bool) -> bool:
        return (
            not force
            and stage in state.completed_stages
            and all(self.manager.artifact_exists(state, artifact) for artifact in artifacts)
        )

    async def _execute(
        self,
        state: RunState,
        stage: Stage,
        action: Callable[[], Awaitable[ResultT]],
    ) -> ResultT:
        state.start_stage(stage)
        self.manager.save(state)
        self.manager.append_event(state.run_id, "stage_started", stage=stage)
        last_error: Exception | None = None
        for attempt in range(self.config.runtime.retries + 1):
            try:
                result = await action()
                state.complete_stage(stage)
                self.manager.save(state)
                self.manager.append_event(state.run_id, "stage_completed", stage=stage)
                return result
            except Exception as exc:  # 边界层负责记录任意 provider/schema 错误
                last_error = exc
                if attempt < self.config.runtime.retries:
                    self.manager.append_event(state.run_id, "stage_retry", stage=stage)

        assert last_error is not None
        state.fail_stage(stage, last_error)
        self.manager.save(state)
        self.manager.append_event(state.run_id, "stage_failed", stage=stage)
        raise last_error


def build_llm_provider(config: AlysiaConfig) -> BaseLLMProvider:
    if config.llm.provider == "mock":
        return MockLLMProvider()
    if config.llm.provider == "ollama":
        return OllamaProvider(config.llm.model, config.llm.base_url, config.llm.timeout_sec)
    if config.llm.provider == "cloud":
        return CloudLLMProvider()
    raise ValueError(f"不支持的 LLM provider：{config.llm.provider}")


def build_research_provider(config: AlysiaConfig) -> BaseResearchProvider:
    if config.research.provider == "mock":
        return MockResearchProvider()
    if config.research.provider == "web":
        return WebResearchProvider()
    raise ValueError(f"不支持的 Research provider：{config.research.provider}")
