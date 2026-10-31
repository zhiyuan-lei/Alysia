from __future__ import annotations

from abc import ABC, abstractmethod

from alysia.schemas.audio import TTSRequest, TTSResult


class BaseTTSProvider(ABC):
    name: str

    @classmethod
    def is_available(cls) -> bool:
        return True

    @abstractmethod
    async def synthesize(self, request: TTSRequest) -> TTSResult:
        """将单个 scene 的旁白合成为有效 WAV。"""

    def unload(self) -> None:
        """释放 provider 持有的模型资源；无常驻资源时无需操作。"""
