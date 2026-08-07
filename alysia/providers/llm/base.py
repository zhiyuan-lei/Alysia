from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, TypeVar

from pydantic import BaseModel

SchemaT = TypeVar("SchemaT", bound=BaseModel)


class BaseLLMProvider(ABC):
    @abstractmethod
    async def generate_structured(
        self,
        prompt: str,
        response_model: type[SchemaT],
        *,
        context: dict[str, Any] | None = None,
    ) -> SchemaT:
        """生成并使用 Pydantic 模型校验结构化结果。"""
