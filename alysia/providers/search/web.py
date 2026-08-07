from __future__ import annotations

from alysia.providers.search.base import BaseResearchProvider
from alysia.schemas.research import ResearchResult


class WebResearchProvider(BaseResearchProvider):
    """联网调研接口骨架；alpha.2 不引入搜索框架或浏览器自动化。"""

    async def research(self, topic: str, *, max_sources: int) -> ResearchResult:
        del topic, max_sources
        raise NotImplementedError("v0.1-alpha.2 尚未实现 web research provider")
