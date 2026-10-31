from __future__ import annotations

import shutil
import subprocess
from abc import ABC, abstractmethod
from pathlib import Path


class BaseVideoUpscaler(ABC):
    @abstractmethod
    def upscale(self, source: Path, destination: Path, *, width: int, height: int) -> Path:
        raise NotImplementedError


class NoOpUpscaler(BaseVideoUpscaler):
    def upscale(self, source: Path, destination: Path, *, width: int, height: int) -> Path:
        del width, height
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        return destination


class FFmpegScaleUpscaler(BaseVideoUpscaler):
    def upscale(self, source: Path, destination: Path, *, width: int, height: int) -> Path:
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg is None:
            raise FileNotFoundError("FFmpeg 不可用，无法执行 scale fallback")
        destination.parent.mkdir(parents=True, exist_ok=True)
        command = [
            ffmpeg, "-y", "-i", str(source), "-an",
            "-vf", f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", str(destination),
        ]
        result = subprocess.run(command, capture_output=True, text=True, timeout=600, check=False)
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg upscale 失败：{result.stderr[-500:]}")
        return destination
