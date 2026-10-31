from __future__ import annotations

from datetime import datetime
from pathlib import Path

from alysia.providers.feedback.base import BaseFeedbackProvider
from alysia.schemas import FeedbackRecord, RetentionPoint


class MockFeedbackProvider(BaseFeedbackProvider):
    name = "mock"

    def collect(self, run_id: str, external_id: str, source: Path | None = None) -> FeedbackRecord:
        del source
        return FeedbackRecord(
            run_id=run_id,
            external_id=external_id,
            collected_at=datetime.now().astimezone(),
            source="mock",
            views=420,
            likes=28,
            comments=7,
            favorites=19,
            shares=4,
            followers_gained=3,
            retention_points=[
                RetentionPoint(second=0, percentage=1.0),
                RetentionPoint(second=30, percentage=0.58),
                RetentionPoint(second=60, percentage=0.35),
            ],
            comments_summary=[
                "讲解清楚，流程图很好理解",
                "希望下一期解释长期任务为什么容易失控？",
                "字幕节奏有点快",
            ],
        )

