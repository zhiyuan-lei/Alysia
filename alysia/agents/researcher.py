from __future__ import annotations

from alysia.prompts import load_prompt
from alysia.providers.search.base import BaseResearchProvider
from alysia.schemas.research import ResearchResult


class Researcher:
    def __init__(self, provider: BaseResearchProvider, max_sources: int) -> None:
        self.provider = provider
        self.max_sources = max_sources
        self.instructions = load_prompt("research")

    async def run(self, topic: str) -> ResearchResult:
        result = await self.provider.research(topic, max_sources=self.max_sources)
        if result.topic.strip() != topic.strip():
            raise ValueError("ResearchResult.topic 与输入 topic 不一致")
        return result
