from __future__ import annotations

from pathlib import Path

from alysia.providers.analytics.base import BaseAnalyticsProvider
from alysia.schemas import VideoMetrics


class BilibiliAnalyticsProvider(BaseAnalyticsProvider):
    """Contract placeholder. alpha.6 intentionally performs no login or network access."""

    def load(self, run_id: str, source: Path | None = None) -> VideoMetrics:
        del run_id, source
        raise NotImplementedError("alpha.6 不访问 B 站账号；请使用手工 JSON/CSV 导入")

