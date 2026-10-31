from alysia.providers.trends.base import BaseTrendProvider, deduplicate_trends
from alysia.providers.trends.manual import ManualTrendProvider
from alysia.providers.trends.mock import MockTrendProvider
from alysia.providers.trends.web import WebTrendProvider

__all__ = [
    "BaseTrendProvider",
    "ManualTrendProvider",
    "MockTrendProvider",
    "WebTrendProvider",
    "deduplicate_trends",
]
