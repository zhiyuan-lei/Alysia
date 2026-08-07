from __future__ import annotations

from alysia.prompts import load_prompt
from alysia.providers.llm.base import BaseLLMProvider
from alysia.schemas.research import ResearchResult
from alysia.schemas.script import Script


class Writer:
    def __init__(self, provider: BaseLLMProvider, target_duration_sec: int) -> None:
        self.provider = provider
        self.target_duration_sec = target_duration_sec

    async def run(self, topic: str, research: ResearchResult) -> Script:
        return await self.provider.generate_structured(
            load_prompt("writer"),
            Script,
            context={
                "topic": topic,
                "research": research.model_dump(mode="json"),
                "target_duration_sec": self.target_duration_sec,
            },
        )
