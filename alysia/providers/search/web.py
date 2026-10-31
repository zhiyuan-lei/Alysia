from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any, Protocol
from urllib.parse import urlparse

from alysia.providers.search.base import BaseResearchProvider
from alysia.schemas.research import ResearchResult, Source


class WebSearchAdapter(Protocol):
    async def search(self, question: str, *, max_results: int) -> list[dict[str, Any]]: ...


class WebResearchProvider(BaseResearchProvider):
    """无登录搜索适配层；实际联网由显式注入的合规 adapter 提供。"""

    def __init__(self, adapter: WebSearchAdapter | None = None, *, security=None) -> None:
        self.adapter = adapter
        self.security = security

    async def research(self, topic: str, *, max_sources: int) -> ResearchResult:
        if self.adapter is None:
            raise RuntimeError("WebResearchProvider 尚未配置公开 WebSearchAdapter；不会自动登录或绕过访问限制")
        if self.security is not None:
            from alysia.schemas.security import Permission
            self.security.policy.enforce(
                actor="ResearcherAgent", permission=Permission.NETWORK_PUBLIC,
                resource="public-web-research", action="research.network",
            )
        records = (await self.adapter.search(topic, max_results=max_sources))[:max_sources]
        if not records:
            raise RuntimeError("WebSearchAdapter 没有返回可验证来源")
        now = datetime.now().astimezone()
        sources: list[Source] = []
        points: list[str] = []
        for index, record in enumerate(records, start=1):
            url = str(record["url"])
            if self.security is not None:
                decision = self.security.policy.authorize_network(
                    actor="ResearcherAgent", url=url, action="research.source",
                )
                if decision.decision != "allow":
                    raise PermissionError(f"research URL 被网络策略拒绝：{url}")
            domain = urlparse(url).netloc.lower()
            snippet = str(record.get("snippet") or "").strip()
            published = record.get("published_at")
            if isinstance(published, str):
                published = datetime.fromisoformat(published.replace("Z", "+00:00"))
            source_type = record.get("source_type") or self._classify(domain, url)
            content_hash = hashlib.sha256(
                f"{record.get('title', '')}\x1f{url}\x1f{snippet}".encode("utf-8")
            ).hexdigest()
            sources.append(
                Source(
                    id=str(record.get("source_id") or f"web-{index}"),
                    title=str(record.get("title") or url),
                    url=url,
                    publisher=str(record.get("publisher") or domain),
                    domain=domain,
                    author=record.get("author"),
                    published_at=published,
                    retrieved_at=now,
                    source_type=source_type,
                    content_hash=content_hash,
                    access_note=str(record.get("access_note") or "公开网页；未使用登录、付费墙绕过或受限访问"),
                    citation_note=record.get("citation_note"),
                    evidence_origin="web",
                    note=snippet,
                )
            )
            if snippet:
                points.append(snippet)
        if not points:
            points = ["来源已捕获，但没有可直接抽取的摘要；需要进一步人工/Provider 验证。"]
        return ResearchResult(
            topic=topic,
            summary=f"从 {len(sources)} 个公开来源捕获元数据；正式事实仍需 claim verification。",
            key_points=points,
            open_questions=[],
            sources=sources,
        )

    @staticmethod
    def _classify(domain: str, url: str) -> str:
        if domain.endswith(".gov") or domain.endswith(".gov.cn"):
            return "official"
        if "docs" in domain or "/docs" in url:
            return "documentation"
        if "arxiv.org" in domain or domain.endswith(".edu"):
            return "academic"
        return "unknown"
