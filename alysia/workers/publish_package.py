from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path

from alysia.agents import DescriptionAgent, TagAgent, TitleAgent
from alysia.agents.description import is_publishable_source
from alysia.core.config import AlysiaConfig
from alysia.core.run import RunManager, RunState
from alysia.providers.cover import BaseCoverGenerator
from alysia.schemas import PublishPackage, ResearchResult, Script, Storyboard
from alysia.workers.media import probe_media, require_media_executable
from alysia.workers.video_qa import parse_ffprobe


class PublishPackageWorker:
    def __init__(
        self,
        manager: RunManager,
        config: AlysiaConfig,
        cover_generator: BaseCoverGenerator,
    ) -> None:
        self.manager = manager
        self.config = config
        self.cover_generator = cover_generator
        self.title_agent = TitleAgent(config.publish.title_candidates)
        self.description_agent = DescriptionAgent()
        self.tag_agent = TagAgent(config.publish.tags.max_count)

    def run(
        self,
        state: RunState,
        research: ResearchResult,
        script: Script,
        storyboard: Storyboard,
    ) -> PublishPackage:
        run_dir = self.manager.run_dir(state.run_id)
        video_relative = state.artifacts.get("final_video")
        if not video_relative:
            raise FileNotFoundError("run 缺少 final_video 记录")
        video_path = run_dir / video_relative
        ffprobe = require_media_executable("ffprobe", self.config.render.ffprobe_path)
        video = parse_ffprobe(probe_media(video_path, ffprobe))

        title_result = self.title_agent.run(state.topic, script, storyboard)
        disclaimer = "本视频由 Alysia 辅助生成，用于知识科普；事实与链接请以原始来源为准。"
        description = self.description_agent.run(
            script,
            storyboard,
            research,
            video.duration_sec,
            disclaimer,
        )
        category = "科技"
        tags = self.tag_agent.run(state.topic, script, category)
        subtitle_title = _truncate(script.thesis, 60)

        suffix = ".jpg" if self.config.publish.cover.format == "jpeg" else ".png"
        cover_relative = Path("publish") / f"cover{suffix}"
        existing_cover = state.artifacts.get("publish_cover")
        if existing_cover and Path(existing_cover) != cover_relative:
            raise ValueError("Designer 产出的 publish_cover 路径与 PublishPackage 约定不一致")
        if not (run_dir / cover_relative).is_file():
            self.cover_generator.generate(
                run_dir / cover_relative,
                title=title_result.primary_title,
                subtitle=subtitle_title,
                theme_elements=tags[:3],
            )

        package = PublishPackage(
            title=title_result.primary_title,
            subtitle_title=subtitle_title,
            description=description,
            tags=tags,
            category=category,
            cover_path=cover_relative,
            video_path=Path(video_relative),
            duration_sec=video.duration_sec,
            language=self.config.content.language,
            disclaimer=disclaimer,
            source_links=[source.url for source in research.sources if is_publishable_source(source.url)],
            generated_at=datetime.now().astimezone(),
            qa_status="pending",
        )
        traceability = {
            "inputs": {
                key: state.artifacts[key]
                for key in ("research", "script", "storyboard", "final_video", "video_qa_report")
                if key in state.artifacts
            },
            "sha256": {
                key: _sha256(run_dir / state.artifacts[key])
                for key in ("research", "script", "storyboard", "final_video")
                if key in state.artifacts
            },
            "source_ids": [source.id for source in research.sources],
        }
        metadata = {
            "title_candidates": title_result.model_dump(mode="json")["candidates"],
            "primary_title": title_result.primary_title,
            "video": video.model_dump(mode="json"),
            "category": category,
            "language": package.language,
            "visual_identity": {
                "template_version": self.config.visual_identity.template_version,
                "cover_layout": f"left_accent_{self.config.visual_identity.template_version}",
            },
            "traceability": traceability,
        }
        self.manager.write_text(state.run_id, "publish/title.txt", package.title)
        self.manager.write_text(state.run_id, "publish/description.md", description)
        self.manager.write_json(state.run_id, "publish/tags.json", tags)
        self.manager.write_json(state.run_id, "publish/metadata.json", metadata)
        self.manager.write_json(state.run_id, "publish/publish_package.json", package.model_dump(mode="json"))
        return package


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _truncate(value: str, limit: int) -> str:
    text = " ".join(value.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip("，。；; ") + "…"
