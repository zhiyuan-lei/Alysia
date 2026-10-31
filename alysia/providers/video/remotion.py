from __future__ import annotations

import shutil
from pathlib import Path

from alysia.core.config import RenderConfig, VideoConfig
from alysia.providers.video.base import BaseVideoRenderer, resolve_run_dir
from alysia.schemas import AudioManifest, Storyboard, SubtitleDocument, VideoRenderResult
from alysia.workers.media import run_command


class RemotionRenderer(BaseVideoRenderer):
    name = "remotion"

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
        npm = shutil.which("npm")
        if npm is None:
            raise FileNotFoundError("找不到 npm，无法运行 Remotion")
        run_dir = resolve_run_dir(output_path, audio_manifest)
        composition_path = run_dir / "video" / "composition.json"
        narration = run_dir / audio_manifest.narration_file
        if not composition_path.is_file():
            raise FileNotFoundError(f"缺少 Remotion composition：{composition_path}")
        if not narration.is_file():
            raise FileNotFoundError(f"旁白音频不存在：{narration}")
        remotion_dir = self.render_config.remotion_dir.resolve()
        if not (remotion_dir / "node_modules" / "remotion").is_dir():
            raise FileNotFoundError("Remotion 依赖未安装；请在 video/remotion 执行 npm install")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        run_command(
            [
                npm,
                "run",
                "render",
                "--",
                "--props",
                str(composition_path),
                "--output",
                str(output_path),
                "--public-dir",
                str(run_dir),
            ],
            cwd=remotion_dir,
            timeout_sec=1200,
            heartbeat=getattr(self, "heartbeat", None),
        )
        return VideoRenderResult(
            mp4_path=output_path,
            duration_sec=audio_manifest.total_duration_sec,
            resolution=f"{self.video_config.width}x{self.video_config.height}",
            fps=float(self.video_config.fps),
            renderer=self.name,
            metadata={"composition": str(composition_path), "audio": audio_manifest.narration_file},
        )
