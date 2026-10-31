from __future__ import annotations

import json
from pathlib import Path

from alysia.providers.search.base import BaseResearchProvider
from alysia.schemas.research import ResearchResult


class ManualResearchProvider(BaseResearchProvider):
    def __init__(self, source_file: Path) -> None:
        self.source_file = source_file

    async def research(self, topic: str, *, max_sources: int) -> ResearchResult:
        payload = json.loads(self.source_file.read_text(encoding="utf-8"))
        result = ResearchResult.model_validate(payload)
        if result.topic != topic:
            raise ValueError("ManualResearchProvider topic 与请求不一致")
        result.sources = result.sources[:max_sources]
        for source in result.sources:
            source.evidence_origin = "manual"
        return result

