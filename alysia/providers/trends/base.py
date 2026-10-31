from __future__ import annotations

import re
from abc import ABC, abstractmethod

from alysia.schemas import TrendItem


def normalize_topic(value: str) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", value.casefold())


def deduplicate_trends(items: list[TrendItem]) -> list[TrendItem]:
    """按规范化主题与 URL 去重，保留置信度更高的记录。"""
    selected: dict[str, TrendItem] = {}
    for item in items:
        key = item.url or normalize_topic(item.topic)
        current = selected.get(key)
        if current is None or item.confidence > current.confidence:
            selected[key] = item
    return sorted(selected.values(), key=lambda item: (-item.confidence, item.topic))


class BaseTrendProvider(ABC):
    source_kind: str

    @abstractmethod
    def gather(self, *, max_items: int, freshness_days: int) -> list[TrendItem]:
        raise NotImplementedError
