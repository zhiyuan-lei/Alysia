from __future__ import annotations

import re

from alysia.schemas import Script, Storyboard, TitleCandidate, TitleResult


_RISK_PATTERNS = (
    "100%",
    "绝对",
    "保证",
    "必然",
    "史上最",
    "震惊",
    "颠覆一切",
    "人人都",
)


class TitleAgent:
    """从已验证脚本派生可解释、非标题党的候选标题。"""

    def __init__(self, candidate_count: int = 5) -> None:
        self.candidate_count = candidate_count

    def run(self, topic: str, script: Script, storyboard: Storyboard) -> TitleResult:
        subject = topic.strip().rstrip("？?！!。.")
        section_count = len(script.sections)
        thesis = _compact(script.thesis, 28)
        raw = [
            (f"{subject}：一次讲清核心逻辑", "科普型", "直接说明科普范围，不承诺超出脚本的结论。"),
            (f"{subject}？关键差距在哪里", "问题型", "延续主题问题，并指向脚本的分析主线。"),
            (f"{subject}：能力与目标之间还差什么", "冲突型", "使用能力与目标的真实张力，不制造对立。"),
            (f"{section_count}个关键点，看懂{subject}", "数字型", f"数字来自脚本现有的 {section_count} 个结构化章节。"),
            (f"{subject}，真正需要关注的是：{thesis}", "悬念型", "悬念内容直接来自脚本核心论点。"),
        ]
        candidates: list[TitleCandidate] = []
        for title, style, reason in raw[: self.candidate_count]:
            title = _compact(title, 80)
            risk = title_risk(title)
            candidates.append(TitleCandidate(title=title, style=style, reason=reason, risk=risk))
        primary = next((item.title for item in candidates if item.risk == "无"), candidates[0].title)
        return TitleResult(primary_title=primary, candidates=candidates)


def title_risk(title: str) -> str:
    found = [pattern for pattern in _RISK_PATTERNS if pattern.casefold() in title.casefold()]
    unsupported_number = re.search(r"\d+", title) and not re.match(r"^\d+个关键点", title)
    if unsupported_number:
        found.append("可能含无依据数字")
    return "；".join(found) if found else "无"


def _compact(value: str, limit: int) -> str:
    compact = re.sub(r"\s+", " ", value).strip()
    return compact if len(compact) <= limit else compact[: limit - 1].rstrip("，：:；;。") + "…"
