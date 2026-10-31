from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from pydantic import BaseModel, Field


class ASRSegment(BaseModel):
    start_sec: float = Field(ge=0)
    end_sec: float = Field(gt=0)
    text: str = ""


class BaseASRProvider(ABC):
    name: str

    @classmethod
    def is_available(cls) -> bool:
        return True

    @abstractmethod
    def transcribe(self, wav_path: Path, *, language: str = "zh") -> list[ASRSegment]:
        """返回校准用时间段；默认字幕文字仍来自脚本。"""

    def unload(self) -> None:
        """释放可选 ASR 模型资源。"""
