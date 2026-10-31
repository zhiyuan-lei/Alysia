from __future__ import annotations

import os
from pathlib import Path

from alysia.providers.feedback.base import BaseFeedbackProvider, FeedbackProviderError
from alysia.schemas import FeedbackRecord


class BilibiliFeedbackProvider(BaseFeedbackProvider):
    name = "bilibili"

    def collect(self, run_id: str, external_id: str, source: Path | None = None) -> FeedbackRecord:
        del run_id, external_id, source
        if not os.environ.get("BILIBILI_ACCESS_TOKEN"):
            raise FeedbackProviderError("BILIBILI_ACCESS_TOKEN 缺失；未发送任何网络请求")
        raise FeedbackProviderError(
            "Bilibili 官方稿件数据接口契约尚未由当前已授权应用文档核验；未发送任何网络请求"
        )

