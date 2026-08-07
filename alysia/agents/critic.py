from __future__ import annotations

import re
from difflib import SequenceMatcher

from alysia.core.config import ContentConfig
from alysia.prompts import load_prompt
from alysia.schemas.qa import QAIssue, TextQAReport
from alysia.schemas.research import ResearchResult
from alysia.schemas.script import Script
from alysia.schemas.storyboard import Storyboard


class TextCritic:
    def __init__(self, content_config: ContentConfig) -> None:
        self.content_config = content_config
        self.instructions = load_prompt("critic")

    def run(
        self,
        topic: str,
        research: ResearchResult,
        script: Script,
        storyboard: Storyboard,
    ) -> TextQAReport:
        issues: list[QAIssue] = []
        topic_consistent = research.topic.strip() == topic.strip() and (
            _normalise(topic) in _normalise(script.title)
            or _normalise(script.title) in _normalise(topic)
        )
        if not topic_consistent:
            issues.append(QAIssue(code="topic_mismatch", severity="error", message="调研或脚本标题与输入主题不一致。"))

        has_hook = bool(script.hook.strip())
        if not has_hook:
            issues.append(QAIssue(code="missing_hook", severity="error", message="脚本缺少 hook。"))

        has_conclusion = bool(script.conclusion.strip())
        if not has_conclusion:
            issues.append(QAIssue(code="missing_conclusion", severity="error", message="脚本缺少明确结论。"))

        section_ids = {section.id for section in script.sections}
        covered_ids = {scene.section_id for scene in storyboard.scenes}
        storyboard_covers_sections = section_ids <= covered_ids
        if not storyboard_covers_sections:
            missing = ", ".join(sorted(section_ids - covered_ids))
            issues.append(QAIssue(code="missing_scenes", severity="error", message=f"分镜未覆盖脚本段落：{missing}"))

        duration = storyboard.total_duration_sec
        duration_in_range = (
            self.content_config.min_duration_sec <= duration <= self.content_config.max_duration_sec
            and self.content_config.min_duration_sec <= script.target_duration_sec <= self.content_config.max_duration_sec
        )
        if not duration_in_range:
            issues.append(QAIssue(code="duration_out_of_range", severity="error", message="脚本或分镜总时长超出配置范围。"))

        known_refs = {source.id for source in research.sources}
        used_refs = set(script.source_refs)
        used_refs.update(ref for section in script.sections for ref in section.source_refs)
        used_refs.update(ref for scene in storyboard.scenes for ref in scene.source_refs)
        unknown_refs = used_refs - known_refs
        if unknown_refs:
            issues.append(QAIssue(code="unknown_source_refs", severity="error", message=f"发现未知来源引用：{', '.join(sorted(unknown_refs))}"))

        if not research.sources:
            issues.append(QAIssue(code="no_sources", severity="warning", message="调研没有来源，正式发布前必须补充。"))

        narrations = [section.narration.strip() for section in script.sections]
        if _has_repetition(narrations):
            issues.append(QAIssue(code="repeated_sections", severity="warning", message="脚本段落存在明显重复。"))

        factual_markers = re.compile(r"(?:\d+(?:\.\d+)?%|\d{4}年|研究表明|数据显示)")
        for section in script.sections:
            if factual_markers.search(section.narration) and not section.source_refs:
                issues.append(QAIssue(code="unsupported_factual_claim", severity="warning", message=f"{section.id} 可能含有无来源支撑的事实性表达。"))

        return TextQAReport(
            passed=not any(issue.severity == "error" for issue in issues),
            topic_consistent=topic_consistent,
            has_hook=has_hook,
            has_conclusion=has_conclusion,
            storyboard_covers_sections=storyboard_covers_sections,
            duration_in_range=duration_in_range,
            issues=issues,
        )


def _normalise(value: str) -> str:
    return re.sub(r"\W+", "", value, flags=re.UNICODE).lower()


def _has_repetition(narrations: list[str]) -> bool:
    for index, left in enumerate(narrations):
        for right in narrations[index + 1 :]:
            if left and right and SequenceMatcher(None, left, right).ratio() >= 0.9:
                return True
    return False
