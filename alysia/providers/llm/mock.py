from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel

from alysia.providers.llm.base import BaseLLMProvider, SchemaT
from alysia.schemas.script import Script
from alysia.schemas.storyboard import Storyboard

MockResponse = BaseModel | dict[str, Any] | Callable[[dict[str, Any]], BaseModel | dict[str, Any]]


class MockLLMProvider(BaseLLMProvider):
    def __init__(self, responses: dict[str, MockResponse] | None = None) -> None:
        self.responses = responses or {}
        self.calls: list[str] = []

    async def generate_structured(
        self,
        prompt: str,
        response_model: type[SchemaT],
        *,
        context: dict[str, Any] | None = None,
    ) -> SchemaT:
        del prompt
        model_name = response_model.__name__
        self.calls.append(model_name)
        response = self.responses.get(model_name)
        if callable(response):
            response = response(context or {})
        if response is None:
            response = self._default_response(response_model, context or {})
        if isinstance(response, response_model):
            return response
        if isinstance(response, BaseModel):
            response = response.model_dump(mode="json")
        return response_model.model_validate(response)

    @staticmethod
    def _default_response(response_model: type[SchemaT], context: dict[str, Any]) -> dict[str, Any]:
        if response_model is Script:
            return _mock_script(context)
        if response_model is Storyboard:
            return _mock_storyboard(context)
        raise ValueError(f"MockLLMProvider 没有 {response_model.__name__} 的默认响应")


def _mock_script(context: dict[str, Any]) -> dict[str, Any]:
    topic = str(context["topic"])
    research = context["research"]
    source_ids = [source["id"] for source in research.get("sources", [])]
    refs = source_ids[:1]
    duration = int(context.get("target_duration_sec", 180))
    return {
        "title": topic,
        "hook": "Agent 能自己调用工具，但这是否已经等于 AGI？答案藏在它失败时会做什么。",
        "thesis": "现阶段 Agent 是围绕模型和工具搭建的任务系统，距离可迁移、可验证、持续学习的通用智能仍有明显差距。",
        "target_audience": "关注人工智能与智能体工程的中文观众",
        "target_duration_sec": duration,
        "sections": [
            {
                "id": "section-1",
                "purpose": "界定概念",
                "narration": "先区分两个概念。Agent 强调围绕目标调用工具并推进任务；AGI 则通常还意味着能力能够跨领域迁移，并在陌生环境中保持可靠。会执行流程，不等于理解所有新问题。",
                "key_visual_hint": "Agent 与 AGI 的对比图",
                "source_refs": refs,
            },
            {
                "id": "section-2",
                "purpose": "解释关键差距",
                "narration": "今天的 Agent 依然容易受到上下文、工具返回和错误累积的影响。它可能把一步做对，却无法稳定完成很长的任务链。更关键的是，大多数系统不会自动形成经过验证、能够安全复用的新能力。",
                "key_visual_hint": "长任务链中错误逐步放大的流程图",
                "source_refs": refs,
            },
            {
                "id": "section-3",
                "purpose": "给出判断标准",
                "narration": "因此，更有意义的判断不是它能否演示一次成功，而是能否持续规划、发现错误、验证结果，并把经验迁移到下一类任务。Agent 是通往更通用系统的重要工程形态，但不是终点。",
                "key_visual_hint": "规划、执行、验证、学习的闭环",
                "source_refs": refs,
            },
        ],
        "conclusion": "AI Agent 让模型拥有了行动能力；只有当行动、验证、迁移与持续学习形成可靠闭环时，我们才更接近 AGI。",
        "source_refs": source_ids,
    }


def _mock_storyboard(context: dict[str, Any]) -> dict[str, Any]:
    script = context["script"]
    sections = script["sections"]
    target = int(script["target_duration_sec"])
    count = len(sections)
    base, remainder = divmod(target, count)
    scenes = []
    visual_types = ["title", "diagram", "text", "chart", "quote", "code", "image"]
    for index, section in enumerate(sections):
        narration = section["narration"]
        if index == 0:
            narration = f"{script['hook']} {narration}"
        if index == count - 1:
            narration = f"{narration} {script['conclusion']}"
        scenes.append(
            {
                "id": f"scene-{index + 1}",
                "section_id": section["id"],
                "duration_sec": base + (1 if index < remainder else 0),
                "narration": narration,
                "visual_type": visual_types[index % len(visual_types)],
                "visual_prompt": section["key_visual_hint"],
                "screen_text": section["purpose"],
                "transition": "fade" if index == 0 else "slide",
                "source_refs": section.get("source_refs", []),
            }
        )
    return {"title": script["title"], "target_duration_sec": target, "scenes": scenes}
