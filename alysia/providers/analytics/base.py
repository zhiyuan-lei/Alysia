from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from alysia.schemas import VideoMetrics


class BaseAnalyticsProvider(ABC):
    @abstractmethod
    def load(self, run_id: str, source: Path | None = None) -> VideoMetrics:
        """Load one video's metrics without mutating external systems."""

