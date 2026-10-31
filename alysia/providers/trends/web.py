from __future__ import annotations

from datetime import datetime

import httpx

from alysia.providers.trends.base import BaseTrendProvider, deduplicate_trends
from alysia.schemas import TrendItem


class WebTrendProvider(BaseTrendProvider):
    """读取显式配置的公共 JSON feed；不登录平台，也不推断缺失热度。"""

    source_kind = "web"

    def __init__(self, source_urls: list[str], *, timeout_sec: float = 15.0, security=None) -> None:
        self.source_urls = source_urls
        self.timeout_sec = timeout_sec
        self.security = security

    def gather(self, *, max_items: int, freshness_days: int) -> list[TrendItem]:
        if not self.source_urls:
            raise RuntimeError("WebTrendProvider 未配置公共 JSON feed URL")
        rows: list[TrendItem] = []
        now = datetime.now().astimezone()
        with httpx.Client(timeout=self.timeout_sec, follow_redirects=True) as client:
            for source_url in self.source_urls:
                if self.security is not None:
                    decision = self.security.policy.authorize_network(
                        actor="ResearcherAgent", url=source_url, action="trends.network",
                    )
                    if decision.decision != "allow":
                        raise PermissionError(f"trend URL 被网络策略拒绝：{source_url}")
                response = client.get(source_url)
                response.raise_for_status()
                payload = response.json()
                raw_items = payload.get("items", []) if isinstance(payload, dict) else payload
                for raw in raw_items:
                    item = TrendItem.model_validate(
                        {
                            **raw,
                            "source": raw.get("source") or source_url,
                            "source_kind": "web",
                            "observed_at": raw.get("observed_at") or now,
                            "popularity_hint": raw.get("popularity_hint"),
                        }
                    )
                    if item.freshness_days is None or item.freshness_days <= freshness_days:
                        rows.append(item)
        return deduplicate_trends(rows)[:max_items]
