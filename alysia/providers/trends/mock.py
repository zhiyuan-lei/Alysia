from __future__ import annotations

import hashlib
from datetime import datetime

from alysia.providers.trends.base import BaseTrendProvider
from alysia.schemas import TrendItem


class MockTrendProvider(BaseTrendProvider):
    source_kind = "mock"

    _ITEMS = (
        ("AI Agent 为什么仍会在长任务中失控", "自主智能体", ["AI Agent", "可靠性", "长任务"]),
        ("本地小模型如何成为个人 AI 的执行层", "人工智能", ["本地模型", "Agent", "工具调用"]),
        ("程序化视频为什么适合 AI 创作者", "软件工程", ["程序化视频", "Remotion", "自动化"]),
        ("从一次失败任务看 Agent 的自我检查", "自主智能体", ["Agent", "QA", "失败恢复"]),
        ("RAG 与长期记忆到底有什么区别", "人工智能", ["RAG", "长期记忆", "知识库"]),
        ("结构化输出如何减少大模型工作流事故", "软件工程", ["结构化输出", "Pydantic", "可靠性"]),
        ("8GB 显存如何串行调度多个 AI 工具", "人工智能", ["显存", "本地部署", "调度"]),
        ("Human Approval Gate 为什么不是落后设计", "自主智能体", ["人工审核", "安全", "Agent"]),
        ("从脚本到成片：AI 视频流水线的可测试设计", "软件工程", ["视频自动化", "测试", "流水线"]),
        ("AI 创作者如何用实验而不是直觉改进内容", "自主智能体", ["内容实验", "Analytics", "学习闭环"]),
        ("为什么单条爆款不能证明内容策略有效", "人工智能", ["数据分析", "因果", "内容策略"]),
        ("可恢复状态机如何支撑无人值守工作流", "软件工程", ["状态机", "恢复", "自动化"]),
    )

    def gather(self, *, max_items: int, freshness_days: int) -> list[TrendItem]:
        observed_at = datetime.now().astimezone()
        result: list[TrendItem] = []
        for topic, category, keywords in self._ITEMS[:max_items]:
            digest = hashlib.sha256(topic.encode("utf-8")).hexdigest()[:12]
            result.append(
                TrendItem(
                    id=f"mock_{digest}",
                    topic=topic,
                    source="Alysia MockTrendProvider",
                    source_kind="mock",
                    url=f"mock://trend/{digest}",
                    published_at=None,
                    observed_at=observed_at,
                    popularity_hint=None,
                    summary="离线测试趋势，仅用于验证选题与排期逻辑。",
                    keywords=keywords,
                    category=category,
                    confidence=0.6,
                    freshness_days=0,
                )
            )
        return result
