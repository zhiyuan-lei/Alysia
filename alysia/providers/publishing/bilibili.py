from __future__ import annotations

from pathlib import Path
from typing import Mapping

from alysia.providers.publishing.base import BasePublishingProvider, PublishingProviderError
from alysia.schemas import PublishJob, PublishPackage


class BilibiliPublishingProvider(BasePublishingProvider):
    """官方开放平台适配边界。

    alpha.8 不猜测未公开/未核验的上传 endpoint，也不使用 cookie 或网页自动登录。
    完成开发者认证、应用接入、UP 主授权并取得对应官方接口文档后，才能扩展网络提交。
    """

    name = "bilibili"
    required_environment = (
        "BILIBILI_CLIENT_ID",
        "BILIBILI_CLIENT_SECRET",
        "BILIBILI_ACCESS_TOKEN",
    )

    def __init__(self, credentials: Mapping[str, str] | None = None) -> None:
        self._credentials = dict(credentials or {})

    def missing_credentials(self) -> list[str]:
        return [name for name in self.required_environment if not self._credentials.get(name)]

    def submit(
        self,
        job: PublishJob,
        package: PublishPackage,
        *,
        video_path: Path,
        cover_path: Path,
    ) -> str:
        del job, package, video_path, cover_path
        missing = self.missing_credentials()
        if missing:
            raise PublishingProviderError(
                "Bilibili 官方开放平台凭证缺失：" + ", ".join(missing) + "；未发送任何网络请求"
            )
        raise PublishingProviderError(
            "Bilibili 官方投稿请求契约尚未由当前已授权应用文档核验；为避免伪造 endpoint，未发送任何网络请求"
        )
