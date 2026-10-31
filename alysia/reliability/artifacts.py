from __future__ import annotations

import hashlib
import json
import subprocess
import wave
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from alysia.schemas.reliability import ArtifactIntegrityRecord
from alysia.workers.media import find_media_executable


class ArtifactIntegrityChecker:
    def __init__(self, *, compute_hash: bool = False, probe_media: bool = True, min_size_bytes: int = 1) -> None:
        self.compute_hash = compute_hash
        self.probe_media = probe_media
        self.min_size_bytes = min_size_bytes

    def check(self, path: Path, *, producer: str = "unknown") -> ArtifactIntegrityRecord:
        path = path.resolve()
        now = datetime.now().astimezone()
        if not path.is_file():
            return ArtifactIntegrityRecord(
                path=path, created_at=now, producer=producer, validity="missing",
                errors=["artifact 不存在"],
            )
        size = path.stat().st_size
        errors: list[str] = []
        media_probe: dict[str, Any] | None = None
        if size < self.min_size_bytes:
            errors.append(f"artifact size={size} 小于下限 {self.min_size_bytes}")
        suffix = path.suffix.lower()
        try:
            if suffix == ".json":
                json.loads(path.read_text(encoding="utf-8"))
            elif suffix in {".yaml", ".yml"}:
                yaml.safe_load(path.read_text(encoding="utf-8"))
            elif suffix == ".wav":
                with wave.open(str(path), "rb") as audio:
                    if audio.getnframes() <= 0 or audio.getframerate() <= 0:
                        errors.append("WAV 没有有效采样帧")
                    media_probe = {
                        "channels": audio.getnchannels(), "sample_rate": audio.getframerate(),
                        "frames": audio.getnframes(),
                    }
            elif suffix in {".mp4", ".mov", ".mkv", ".webm"} and self.probe_media:
                media_probe = self._ffprobe(path)
                if not media_probe.get("streams"):
                    errors.append("媒体没有可解码 stream")
            elif suffix in {".png", ".jpg", ".jpeg", ".webp"}:
                from PIL import Image

                with Image.open(path) as image:
                    image.verify()
                    media_probe = {"format": image.format, "width": image.width, "height": image.height}
        except (OSError, ValueError, json.JSONDecodeError, yaml.YAMLError, wave.Error) as exc:
            errors.append(f"artifact 无法解析/解码：{exc}")
        digest = self._sha256(path) if self.compute_hash and not errors else None
        return ArtifactIntegrityRecord(
            path=path, size=size, hash=digest, media_probe=media_probe, created_at=now,
            producer=producer, validity="invalid" if errors else "valid", errors=errors,
        )

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _ffprobe(path: Path) -> dict[str, Any]:
        executable = find_media_executable("ffprobe")
        if executable is None:
            raise OSError("ffprobe 不可用")
        result = subprocess.run(
            [str(executable), "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30, check=False,
        )
        if result.returncode != 0:
            raise OSError(result.stderr.strip() or f"ffprobe exit={result.returncode}")
        return json.loads(result.stdout)

