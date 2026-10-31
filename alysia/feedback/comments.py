from __future__ import annotations

import re
from collections import Counter

from alysia.schemas import CommentInsight


def analyze_comments(summary: str | list[str] | None) -> CommentInsight:
    if summary is None:
        return CommentInsight()
    entries = summary if isinstance(summary, list) else [item for item in re.split(r"[\r\n]+", summary) if item]
    topic_terms = ("AI Agent", "AGI", "字幕", "配音", "流程图", "长期任务", "工具调用")
    counts = Counter(term for entry in entries for term in topic_terms if term.casefold() in entry.casefold())
    positives = [entry for entry in entries if any(term in entry for term in ("清楚", "好理解", "喜欢", "有帮助"))]
    negatives = [entry for entry in entries if any(term in entry for term in ("太快", "噪音", "不清楚", "错误", "看不懂"))]
    questions = [entry for entry in entries if "?" in entry or "？" in entry or any(term in entry for term in ("为什么", "怎么", "如何"))]
    requests = [entry for entry in entries if any(term in entry for term in ("希望", "下一期", "想看", "能否"))]
    return CommentInsight(
        frequent_topics=[term for term, _ in counts.most_common()],
        positive_signals=positives,
        negative_signals=negatives,
        questions=questions,
        possible_content_requests=requests,
    )

