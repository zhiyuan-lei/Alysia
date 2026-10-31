from __future__ import annotations

from datetime import datetime
from pathlib import Path

from alysia.providers.analytics.base import BaseAnalyticsProvider
from alysia.schemas import RetentionPoint, VideoMetrics


class MockAnalyticsProvider(BaseAnalyticsProvider):
    def load(self, run_id: str, source: Path | None = None) -> VideoMetrics:
        del source
        return VideoMetrics(
            run_id=run_id,
            platform="bilibili",
            collected_at=datetime.now().astimezone(),
            source="mock",
            impressions=10000,
            views=420,
            likes=28,
            comments=7,
            favorites=19,
            shares=4,
            followers_gained=3,
            avg_view_duration_sec=31.2,
            avg_view_percentage=0.38,
            completion_rate=0.31,
            ctr=0.042,
            retention_points=[
                RetentionPoint(second=0, percentage=1.0),
                RetentionPoint(second=10, percentage=0.72),
                RetentionPoint(second=30, percentage=0.58),
                RetentionPoint(second=60, percentage=0.35),
            ],
        )

