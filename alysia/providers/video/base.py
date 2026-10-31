from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from alysia.schemas import AudioManifest, Storyboard, SubtitleDocument, VideoRenderResult


def resolve_run_dir(output_path: Path, audio_manifest: AudioManifest) -> Path:
    for candidate in (output_path.parent, *output_path.parents):
        if (candidate / audio_manifest.narration_file).is_file():
            return candidate
    raise FileNotFoundError(f"无法从输出路径定位 run 目录：{output_path}")


class BaseVideoRenderer(ABC):
    name: str

    @abstractmethod
    def render(
        self,
        storyboard: Storyboard,
        audio_manifest: AudioManifest,
        subtitles: SubtitleDocument,
        output_path: Path,
    ) -> VideoRenderResult:
        """渲染中间 MP4；最终规范化由 FFmpeg 后处理完成。"""
