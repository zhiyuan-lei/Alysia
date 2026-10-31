from __future__ import annotations

from pathlib import Path

from alysia.core.config import RenderConfig, VideoConfig
from alysia.providers.video.base import BaseVideoRenderer, resolve_run_dir
from alysia.schemas import AudioManifest, Storyboard, SubtitleDocument, VideoRenderResult
from alysia.workers.media import require_media_executable, run_command


class MockVideoRenderer(BaseVideoRenderer):
    name = "mock"

    def __init__(self, video_config: VideoConfig, render_config: RenderConfig) -> None:
        self.video_config = video_config
        self.render_config = render_config

    def render(
        self,
        storyboard: Storyboard,
        audio_manifest: AudioManifest,
        subtitles: SubtitleDocument,
        output_path: Path,
    ) -> VideoRenderResult:
        del storyboard, subtitles
        ffmpeg = require_media_executable("ffmpeg", self.render_config.ffmpeg_path)
        run_dir = resolve_run_dir(output_path, audio_manifest)
        narration = run_dir / audio_manifest.narration_file
        if not narration.is_file():
            raise FileNotFoundError(f"旁白音频不存在：{narration}")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        duration = audio_manifest.total_duration_sec
        run_command(
            [
                str(ffmpeg),
                "-y",
                "-f",
                "lavfi",
                "-i",
                f"color=c=0x111827:s={self.video_config.width}x{self.video_config.height}:r={self.video_config.fps}:d={duration:.6f}",
                "-i",
                str(narration),
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
                "-c:v",
                "libx264",
                "-preset",
                "ultrafast",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-shortest",
                str(output_path),
            ]
        )
        return VideoRenderResult(
            mp4_path=output_path,
            duration_sec=duration,
            resolution=f"{self.video_config.width}x{self.video_config.height}",
            fps=float(self.video_config.fps),
            renderer=self.name,
            metadata={"kind": "deterministic_color_video", "audio": audio_manifest.narration_file},
        )
