from __future__ import annotations

from datetime import datetime

from alysia.providers.search.base import BaseResearchProvider
from alysia.schemas.research import ResearchResult, Source


class MockResearchProvider(BaseResearchProvider):
    def __init__(self) -> None:
        self.call_count = 0

    async def research(self, topic: str, *, max_sources: int) -> ResearchResult:
        self.call_count += 1
        sources = [
            Source(
                id="source-1",
                title="Mock：Agent 与 AGI 概念说明",
                url="https://example.invalid/agent-agi-overview",
                publisher="Alysia 离线测试资料",
                domain="example.invalid",
                retrieved_at=datetime.now().astimezone(),
                note="仅用于离线演示结构，不是可用于发布的真实事实来源。",
            )
        ][:max_sources]
        return ResearchResult(
            topic=topic,
            summary=(
                "本次结果由 MockResearchProvider 生成，用于验证 Alysia 的文本创作闭环。"
                "正式发布前必须切换到可验证的真实调研来源。"
            ),
            key_points=[
                "Agent 的核心特征是围绕目标调用工具并执行多步任务。",
                "是否具备跨任务迁移、可靠验证与持续学习，是讨论 AGI 时更严格的判断维度。",
                "一次成功演示不能代表系统能够长期稳定自主运行。",
            ],
            open_questions=["如何为长期自主任务建立可重复、可量化的可靠性评测？"],
            sources=sources,
        )
