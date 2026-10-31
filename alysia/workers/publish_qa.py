from __future__ import annotations

import re
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from alysia.agents.title import title_risk
from alysia.core.config import AlysiaConfig
from alysia.core.run import RunManager, RunState
from alysia.schemas import PublishPackage, PublishQAReport, VideoQAReport


class PublishQAWorker:
    def __init__(self, manager: RunManager, config: AlysiaConfig) -> None:
        self.manager = manager
        self.config = config

    def run(self, state: RunState, package: PublishPackage) -> PublishQAReport:
        run_dir = self.manager.run_dir(state.run_id)
        errors: list[str] = []
        warnings: list[str] = []
        metrics: dict[str, object] = {}

        video_path = run_dir / package.video_path
        metrics["video_exists"] = video_path.is_file() and video_path.stat().st_size > 0 if video_path.exists() else False
        if not metrics["video_exists"]:
            errors.append("final.mp4 不存在或为空")
        video_qa = self._video_qa(state)
        metrics["video_qa_passed"] = bool(video_qa and video_qa.passed)
        if not video_qa or not video_qa.passed:
            errors.append("video QA 不存在或未通过")
        if package.duration_sec < self.config.content.min_duration_sec:
            warnings.append("视频短于配置的目标时长下限")
        if package.duration_sec > self.config.content.max_duration_sec:
            warnings.append("视频长于配置的目标时长上限")
        if package.duration_sec <= 0:
            errors.append("视频时长无效")
        metrics["duration_sec"] = package.duration_sec

        title_length = len(package.title)
        metrics["title_length"] = title_length
        if not 5 <= title_length <= 80:
            errors.append("标题长度应为 5 至 80 个字符")
        if not _topic_matches(state.topic, package.title):
            errors.append("标题未体现输入主题")
        risk = title_risk(package.title)
        if risk != "无":
            errors.append(f"标题存在风险表达：{risk}")

        metrics["description_length"] = len(package.description.strip())
        if not package.description.strip():
            errors.append("简介为空")
        if "## 参考资料" not in package.description:
            errors.append("简介缺少参考资料字段")
        if not package.source_links:
            warnings.append("投稿包没有可发布来源链接，人工审核时必须补充")

        normalized_tags = [tag.strip().casefold() for tag in package.tags]
        metrics["tag_count"] = len(package.tags)
        if not 1 <= len(package.tags) <= self.config.publish.tags.max_count:
            errors.append("标签数量超出配置范围")
        if len(normalized_tags) != len(set(normalized_tags)):
            errors.append("标签存在重复")

        cover_path = run_dir / package.cover_path
        metrics["cover_exists"] = cover_path.is_file()
        if not cover_path.is_file():
            errors.append("封面不存在")
        else:
            try:
                with Image.open(cover_path) as image:
                    image.verify()
                with Image.open(cover_path) as image:
                    metrics["cover_width"] = image.width
                    metrics["cover_height"] = image.height
                    if (image.width, image.height) != (
                        self.config.publish.cover.width,
                        self.config.publish.cover.height,
                    ):
                        errors.append("封面尺寸不符合配置")
            except (OSError, UnidentifiedImageError):
                errors.append("封面文件无法读取")

        passed = not errors and (not self.config.qa.strict or not warnings)
        report = PublishQAReport(passed=passed, errors=errors, warnings=warnings, metrics=metrics)
        package.qa_status = "passed" if passed else "failed"
        self.manager.write_json(
            state.run_id,
            "publish/publish_package.json",
            package.model_dump(mode="json"),
        )
        self.manager.write_json(
            state.run_id,
            "publish/publish_qa_report.json",
            report.model_dump(mode="json"),
        )
        return report

    def _video_qa(self, state: RunState) -> VideoQAReport | None:
        relative = state.artifacts.get("video_qa_report")
        if not relative or not (self.manager.run_dir(state.run_id) / relative).is_file():
            return None
        return VideoQAReport.model_validate(self.manager.read_json(state.run_id, relative))


def _topic_matches(topic: str, title: str) -> bool:
    normalized_topic = re.sub(r"\W+", "", topic, flags=re.UNICODE).casefold()
    normalized_title = re.sub(r"\W+", "", title, flags=re.UNICODE).casefold()
    if normalized_topic in normalized_title:
        return True
    ascii_terms = re.findall(r"[a-zA-Z][a-zA-Z0-9-]+", topic.casefold())
    return bool(ascii_terms) and all(term in title.casefold() for term in ascii_terms)
