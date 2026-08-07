from __future__ import annotations

from alysia.prompts import load_prompt
from alysia.providers.llm.base import BaseLLMProvider
from alysia.schemas.script import Script
from alysia.schemas.storyboard import Storyboard


class Director:
    def __init__(self, provider: BaseLLMProvider) -> None:
        self.provider = provider

    async def run(self, script: Script) -> Storyboard:
        return await self.provider.generate_structured(
            load_prompt("director"),
            Storyboard,
            context={"script": script.model_dump(mode="json")},
        )
