from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class BaseCoverGenerator(ABC):
    @abstractmethod
    def generate(
        self,
        output_path: Path,
        *,
        title: str,
        subtitle: str | None = None,
        background_path: Path | None = None,
        logo_text: str = "ALYSIA",
        theme_elements: list[str] | None = None,
    ) -> Path:
        """生成确定性封面并返回输出路径。"""
