from __future__ import annotations

from fractions import Fraction
from pathlib import Path
from typing import Any

from alysia.core.config import AlysiaConfig
from alysia.schemas import VideoProbe, VideoQAReport
from alysia.workers.media import probe_media, require_media_executable, run_command


def parse_ffprobe(payload: dict[str, Any]) -> VideoProbe:
    streams = payload.get("streams") or []
    video = next((stream for stream in streams if stream.get("codec_type") == "video"), None)
    audio = next((stream for stream in streams if stream.get("codec_type") == "audio"), None)
    if video is None:
        raise ValueError("ffprobe 未发现视频流")
    if audio is None:
        raise ValueError("ffprobe 未发现音频流")
    rate = video.get("avg_frame_rate") or video.get("r_frame_rate") or "0/1"
    fps = float(Fraction(rate))
    duration_value = payload.get("format", {}).get("duration") or video.get("duration")
    if duration_value is None:
        raise ValueError("ffprobe 未返回视频时长")
    return VideoProbe(
        duration_sec=float(duration_value),
        width=int(video["width"]),
        height=int(video["height"]),
        fps=fps,
        video_codec=str(video.get("codec_name") or ""),
        audio_codec=str(audio.get("codec_name") or ""),
        audio_sample_rate=int(audio.get("sample_rate") or 0),
        audio_channels=int(audio.get("channels") or 0),
    )


class VideoQAWorker:
    def __init__(self, config: AlysiaConfig) -> None:
        self.config = config

    def run(self, video_path: Path, expected_duration_sec: float) -> VideoQAReport:
        errors: list[str] = []
        warnings: list[str] = []
        metrics: dict[str, float | int | str | bool] = {"file_exists": video_path.is_file()}
        if not video_path.is_file() or video_path.stat().st_size == 0:
            return VideoQAReport(passed=False, errors=["final.mp4 不存在或为空"], metrics=metrics)

        ffprobe = require_media_executable("ffprobe", self.config.render.ffprobe_path)
        try:
            probe = parse_ffprobe(probe_media(video_path, ffprobe))
        except (OSError, RuntimeError, ValueError, KeyError) as exc:
            return VideoQAReport(passed=False, errors=[f"ffprobe 验证失败：{exc}"], metrics=metrics)

        metrics.update(probe.model_dump())
        metrics["file_size_bytes"] = video_path.stat().st_size
        if probe.width != self.config.video.width or probe.height != self.config.video.height:
            errors.append("视频分辨率不符合配置")
        if abs(probe.fps - self.config.video.fps) > 0.01:
            errors.append("视频 FPS 不符合配置")
        if probe.video_codec != "h264":
            errors.append("视频编码不是 H264")
        if probe.audio_codec != "aac":
            errors.append("音频编码不是 AAC")
        if probe.audio_sample_rate != 48000:
            errors.append("成片音频采样率不是 48 kHz")
        if probe.audio_channels != 2:
            errors.append("成片音频不是立体声")
        duration_tolerance = max(0.12, 2 / self.config.video.fps)
        if abs(probe.duration_sec - expected_duration_sec) > duration_tolerance:
            errors.append("视频时长与 narration 不一致")

        ffmpeg = require_media_executable("ffmpeg", self.config.render.ffmpeg_path)
        try:
            run_command(
                [str(ffmpeg), "-v", "error", "-i", str(video_path), "-f", "null", "-"],
                timeout_sec=1200,
            )
            metrics["decodable"] = True
        except RuntimeError as exc:
            metrics["decodable"] = False
            errors.append(f"视频无法完整解码：{exc}")

        return VideoQAReport(passed=not errors, errors=errors, warnings=warnings, metrics=metrics)
