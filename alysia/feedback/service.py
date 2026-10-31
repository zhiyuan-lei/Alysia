from __future__ import annotations

from pathlib import Path

from alysia.core.config import AlysiaConfig
from alysia.core.run import RunManager, RunState
from alysia.feedback.mapper import FeedbackMapper
from alysia.providers.feedback import (
    BilibiliFeedbackProvider,
    ManualFeedbackProvider,
    MockFeedbackProvider,
)


class FeedbackService:
    def __init__(self, config: AlysiaConfig) -> None:
        self.config = config
        self.manager = RunManager(config.runtime.runs_dir)
        self.mapper = FeedbackMapper(
            self.manager,
            config.learning.memory_dir,
            plans_dir=config.planning.plans_dir,
        )

    def import_feedback(
        self,
        run_id: str,
        *,
        provider: str | None = None,
        source: Path | None = None,
    ) -> RunState:
        state = self.manager.load(run_id)
        if not state.external_id:
            raise RuntimeError("run 尚未完成发布提交，缺少 external_id")
        selected = provider or self.config.feedback.provider
        provider_impl = self._provider(selected)
        feedback = provider_impl.collect(run_id, state.external_id, source)
        return self.mapper.apply(feedback)

    @staticmethod
    def _provider(name: str):
        if name == "manual":
            return ManualFeedbackProvider()
        if name == "mock":
            return MockFeedbackProvider()
        if name == "bilibili":
            return BilibiliFeedbackProvider()
        raise ValueError(f"不支持的 feedback provider：{name}")

