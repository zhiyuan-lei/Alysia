from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from alysia.schemas import PublishJob, PublishPackage


class PublishingProviderError(RuntimeError):
    pass


class BasePublishingProvider(ABC):
    name: str

    @abstractmethod
    def submit(
        self,
        job: PublishJob,
        package: PublishPackage,
        *,
        video_path: Path,
        cover_path: Path,
    ) -> str:
        """提交并返回平台稿件 ID。实现不得持久化认证信息。"""

