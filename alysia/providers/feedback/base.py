from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from alysia.schemas import FeedbackRecord


class FeedbackProviderError(RuntimeError):
    pass


class BaseFeedbackProvider(ABC):
    name: str

    @abstractmethod
    def collect(self, run_id: str, external_id: str, source: Path | None = None) -> FeedbackRecord:
        """读取反馈；provider 不得自动回复评论或私信。"""

