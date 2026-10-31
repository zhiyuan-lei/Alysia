from __future__ import annotations

from pathlib import Path

from alysia.core.config import AlysiaConfig
from alysia.core.run import RunManager, RunState
from alysia.providers.video import BaseVideoRenderer
from alysia.schemas import (
    AudioManifest,
    Storyboard,
    SubtitleDocument,
    VideoComposition,
    VideoRenderResult,
)
from alysia.workers.composition import CompositionWorker
from alysia.workers.media import require_media_executable, run_command
from alysia.reliability.monitor import LongRunningTaskMonitor


class VideoRenderWorker:
    def __init__(
        self,
        manager: RunManager,
        config: AlysiaConfig,
        renderer: BaseVideoRenderer,
    ) -> None:
        self.manager = manager
        self.config = config
        self.renderer = renderer
        self.composition_worker = CompositionWorker(manager, config.video, config.subtitle)

    def run(
        self,
        state: RunState,
        storyboard: Storyboard,
        audio_manifest: AudioManifest,
        subtitles: SubtitleDocument,
    ) -> tuple[VideoComposition, VideoRenderResult]:
        run_dir = self.manager.run_dir(state.run_id)
        monitor = LongRunningTaskMonitor(run_dir / "reliability" / "tasks")
        with monitor.track("render", expected_timeout=2400, run_id=state.run_id) as task:
            heartbeat = lambda: monitor.heartbeat(task.task_id, renderer=self.renderer.name)
            setattr(self.renderer, "heartbeat", heartbeat)
            narration = run_dir / audio_manifest.narration_file
            if not narration.is_file():
                raise FileNotFoundError(f"旁白音频不存在：{narration}")

            composition = self.composition_worker.run(state, storyboard, audio_manifest, subtitles)
            raw_path = run_dir / self.config.render.temp_dir / "rendered.mp4"
            final_path = run_dir / self.config.render.output_dir / "final.mp4"
            raw_result = self.renderer.render(storyboard, audio_manifest, subtitles, raw_path)
            heartbeat()
            self._normalize(
                raw_result.mp4_path, final_path, audio_manifest.total_duration_sec, heartbeat=heartbeat
            )
            result = VideoRenderResult(
                mp4_path=final_path,
                duration_sec=audio_manifest.total_duration_sec,
                resolution=f"{self.config.video.width}x{self.config.video.height}",
                fps=float(self.config.video.fps),
                renderer=raw_result.renderer,
                metadata={**raw_result.metadata, "normalized_from": str(raw_result.mp4_path)},
            )
            self.manager.write_json(state.run_id, "video/render_result.json", result.model_dump(mode="json"))
            return composition, result

    def _normalize(self, source: Path, destination: Path, duration_sec: float, *, heartbeat=None) -> None:
        ffmpeg = require_media_executable("ffmpeg", self.config.render.ffmpeg_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        width = self.config.video.width
        height = self.config.video.height
        fps = self.config.video.fps
        video_filter = (
            f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,"
            f"fps={fps}"
        )
        run_command(
            [
                str(ffmpeg),
                "-y",
                "-i",
                str(source),
                "-map",
                "0:v:0",
                "-map",
                "0:a:0",
                "-vf",
                video_filter,
                "-af",
                "loudnorm=I=-16:TP=-1.5:LRA=11",
                "-c:v",
                "libx264",
                "-preset",
                "medium",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-ar",
                "48000",
                "-ac",
                "2",
                "-b:a",
                "192k",
                "-t",
                f"{duration_sec:.6f}",
                "-shortest",
                "-movflags",
                "+faststart",
                str(destination),
            ],
            timeout_sec=1200,
            heartbeat=heartbeat,
        )
