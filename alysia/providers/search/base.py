from __future__ import annotations

from abc import ABC, abstractmethod

from alysia.schemas.research import ResearchResult


class BaseResearchProvider(ABC):
    @abstractmethod
    async def research(self, topic: str, *, max_sources: int) -> ResearchResult:
        """围绕主题返回经过 schema 校验的调研结果。"""
