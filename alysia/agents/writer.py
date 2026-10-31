from __future__ import annotations

from alysia.prompts import load_prompt
from alysia.providers.llm.base import BaseLLMProvider
from typing import Any

from alysia.schemas.research import ResearchResult
from alysia.schemas.script import Script


class Writer:
    def __init__(self, provider: BaseLLMProvider, target_duration_sec: int) -> None:
        self.provider = provider
        self.target_duration_sec = target_duration_sec

    async def run(
        self,
        topic: str,
        research: ResearchResult,
        *,
        assembled_prompt: str | None = None,
        knowledge_context: dict[str, Any] | None = None,
    ) -> Script:
        return await self.provider.generate_structured(
            assembled_prompt or load_prompt("writer"),
            Script,
            context={
                "topic": topic,
                "research": research.model_dump(mode="json"),
                "knowledge_context": knowledge_context or {},
                "target_duration_sec": self.target_duration_sec,
            },
        )
