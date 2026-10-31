from __future__ import annotations

import hashlib
from pathlib import Path

from alysia.providers.publishing.base import BasePublishingProvider
from alysia.schemas import PublishJob, PublishPackage


class MockPublishingProvider(BasePublishingProvider):
    name = "mock"

    def submit(
        self,
        job: PublishJob,
        package: PublishPackage,
        *,
        video_path: Path,
        cover_path: Path,
    ) -> str:
        del package
        if not video_path.is_file() or not cover_path.is_file():
            raise FileNotFoundError("Mock 投稿所需视频或封面不存在")
        digest = hashlib.sha256(f"{job.run_id}|{job.package_hash}".encode("utf-8")).hexdigest()[:16]
        return f"mock_bv_{digest}"

