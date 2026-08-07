from __future__ import annotations

import json
from typing import Any

import httpx

from alysia.providers.llm.base import BaseLLMProvider, SchemaT


class OllamaProvider(BaseLLMProvider):
    def __init__(self, model: str, base_url: str, timeout_sec: float = 120.0) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_sec = timeout_sec

    async def generate_structured(
        self,
        prompt: str,
        response_model: type[SchemaT],
        *,
        context: dict[str, Any] | None = None,
    ) -> SchemaT:
        context_json = json.dumps(context or {}, ensure_ascii=False, default=str)
        request = {
            "model": self.model,
            "stream": False,
            "format": response_model.model_json_schema(),
            "messages": [
                {
                    "role": "user",
                    "content": f"{prompt}\n\n输入上下文：\n{context_json}",
                }
            ],
            "options": {"temperature": 0.2},
        }
        async with httpx.AsyncClient(timeout=self.timeout_sec) as client:
            response = await client.post(f"{self.base_url}/api/chat", json=request)
            response.raise_for_status()
        content = response.json()["message"]["content"]
        return response_model.model_validate_json(content)
