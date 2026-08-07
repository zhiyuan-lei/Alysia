from __future__ import annotations

from typing import Any

from alysia.providers.llm.base import BaseLLMProvider, SchemaT


class CloudLLMProvider(BaseLLMProvider):
    """云端模型接口占位；alpha.2 不连接任何真实 API。"""

    async def generate_structured(
        self,
        prompt: str,
        response_model: type[SchemaT],
        *,
        context: dict[str, Any] | None = None,
    ) -> SchemaT:
        raise NotImplementedError("v0.1-alpha.2 尚未实现 cloud LLM provider")
