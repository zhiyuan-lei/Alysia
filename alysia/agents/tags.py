from __future__ import annotations

import re

from alysia.schemas import Script


_MARKETING_WORDS = {"爆款", "必看", "震惊", "全网第一", "颠覆一切"}
_TECH_KEYWORDS = (
    "AI Agent",
    "AGI",
    "人工智能",
    "大模型",
    "智能体",
    "机器学习",
    "深度学习",
    "科技",
)


class TagAgent:
    def __init__(self, max_count: int = 10) -> None:
        self.max_count = max_count

    def run(self, topic: str, script: Script, category: str = "科技") -> list[str]:
        corpus = " ".join(
            [topic, script.title, script.thesis, *(section.narration for section in script.sections)]
        ).casefold()
        candidates = [keyword for keyword in _TECH_KEYWORDS if keyword.casefold() in corpus]
        subject = re.sub(r"[？?！!。.,，：:；;]", "", topic).strip()
        if 2 <= len(subject) <= 24:
            candidates.append(subject)
        candidates.append(category)

        result: list[str] = []
        seen: set[str] = set()
        for tag in candidates:
            cleaned = tag.strip().lstrip("#")
            key = cleaned.casefold()
            if not cleaned or key in seen or cleaned in _MARKETING_WORDS:
                continue
            seen.add(key)
            result.append(cleaned)
            if len(result) >= self.max_count:
                break
        return result
