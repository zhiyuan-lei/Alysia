from __future__ import annotations

from urllib.parse import urlparse

from alysia.schemas import ResearchResult, Script, Storyboard


class DescriptionAgent:
    def run(
        self,
        script: Script,
        storyboard: Storyboard,
        research: ResearchResult,
        duration_sec: float,
        disclaimer: str,
    ) -> str:
        intro = script.thesis.strip()
        if len(intro) > 100:
            intro = intro[:99].rstrip("，。；; ") + "…"

        core = "\n".join(f"- {section.purpose}：{_summary(section.narration)}" for section in script.sections)
        chapters = _chapters(storyboard, duration_sec)
        references = "\n".join(
            f"- [{source.title}]({source.url}) — {source.publisher}"
            for source in research.sources
            if is_publishable_source(source.url)
        ) or "- 暂无可发布来源；正式投稿前请人工补充并核验。"

        parts = [
            intro,
            "## 视频核心内容\n\n" + core,
        ]
        if chapters:
            parts.append("## 章节时间轴\n\n" + chapters)
        parts.append("## 参考资料\n\n" + references)
        if disclaimer:
            parts.append("## 免责声明\n\n" + disclaimer)
        return "\n\n".join(parts).strip() + "\n"


def _summary(value: str, limit: int = 80) -> str:
    text = " ".join(value.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip("，。；; ") + "…"


def _chapters(storyboard: Storyboard, duration_sec: float) -> str:
    total = storyboard.total_duration_sec
    if total <= 0 or not storyboard.scenes:
        return ""
    elapsed = 0.0
    lines: list[str] = []
    for scene in storyboard.scenes:
        timestamp = max(0, round(elapsed / total * duration_sec))
        label = scene.screen_text.strip() or scene.section_id
        lines.append(f"- {_timestamp(timestamp)} {label}")
        elapsed += scene.duration_sec
    return "\n".join(lines)


def _timestamp(seconds: int) -> str:
    minutes, second = divmod(seconds, 60)
    hours, minute = divmod(minutes, 60)
    if hours:
        return f"{hours:02d}:{minute:02d}:{second:02d}"
    return f"{minute:02d}:{second:02d}"


def is_publishable_source(url: str) -> bool:
    host = (urlparse(url).hostname or "").casefold()
    return bool(host) and not (
        host == "localhost"
        or host.endswith(".invalid")
        or host.endswith(".test")
        or host.endswith(".localhost")
    )
