from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from alysia.schemas.visual import VisualGenerationResult, VisualQAReport


class VisualQA:
    def run(self, run_id: str, result: VisualGenerationResult, *, expected_duration_sec: float) -> VisualQAReport:
        errors: list[str] = []
        warnings: list[str] = []
        metrics: dict[str, float | int | str | bool | None] = {}
        output = result.output_files[0] if result.output_files else None
        provenance = bool(result.job_id and result.workflow_id and result.provider)
        if output is None or not output.is_file():
            errors.append("视觉输出文件不存在")
        elif output.suffix.lower() == ".mp4":
            probe = self._probe(output)
            if probe is None:
                errors.append("视觉输出无法通过 ffprobe 解码")
            else:
                metrics.update(probe)
                duration = float(probe.get("duration_sec", 0))
                if abs(duration - expected_duration_sec) > max(1.0, expected_duration_sec * 0.25):
                    errors.append("视觉 clip 时长与 scene duration 严重不符")
                freeze = self._freeze_ratio(output, duration)
                metrics["freeze_ratio"] = freeze
                if freeze is not None and freeze > 0.95:
                    warnings.append("clip 基本静止；可能不适合作为动态 B-roll")
                black = self._black_ratio(output, duration)
                metrics["black_ratio"] = black
                if black is not None and black > 0.5:
                    errors.append("clip 黑帧比例过高")
        else:
            errors.append("视觉输出不是可解码 MP4")
        if not provenance:
            errors.append("artifact provenance 不完整")
        production_eligible = not result.mock and not errors
        if result.mock:
            warnings.append("Mock artifact 已禁止进入 production review。")
        return VisualQAReport(
            run_id=run_id, scene_id=result.scene_id, passed=not errors,
            production_eligible=production_eligible, errors=errors, warnings=warnings,
            metrics=metrics, provenance_complete=provenance,
            checked_at=datetime.now().astimezone(),
        )

    @staticmethod
    def _probe(path: Path) -> dict | None:
        ffprobe = shutil.which("ffprobe")
        if ffprobe is None:
            return None
        result = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration", "-show_entries", "stream=width,height", "-of", "json", str(path)],
            capture_output=True, text=True, timeout=20, check=False,
        )
        if result.returncode != 0:
            return None
        payload = json.loads(result.stdout)
        video = next((item for item in payload.get("streams", []) if item.get("width")), {})
        return {
            "duration_sec": round(float(payload.get("format", {}).get("duration", 0)), 3),
            "width": int(video.get("width", 0)), "height": int(video.get("height", 0)),
        }

    @staticmethod
    def _black_ratio(path: Path, duration: float) -> float | None:
        if duration <= 0 or shutil.which("ffmpeg") is None:
            return None
        result = subprocess.run(
            [shutil.which("ffmpeg"), "-hide_banner", "-i", str(path), "-vf", "blackdetect=d=0.1:pic_th=0.98", "-an", "-f", "null", "-"],
            capture_output=True, text=True, timeout=60, check=False,
        )
        total = 0.0
        for line in result.stderr.splitlines():
            if "black_duration:" in line:
                try:
                    total += float(line.split("black_duration:", 1)[1].split()[0])
                except ValueError:
                    pass
        return round(min(1.0, total / duration), 4)

    @staticmethod
    def _freeze_ratio(path: Path, duration: float) -> float | None:
        if duration <= 0 or shutil.which("ffmpeg") is None:
            return None
        result = subprocess.run(
            [shutil.which("ffmpeg"), "-hide_banner", "-i", str(path), "-vf", "freezedetect=n=0.001:d=0.5", "-an", "-f", "null", "-"],
            capture_output=True, text=True, timeout=60, check=False,
        )
        total = 0.0
        for line in result.stderr.splitlines():
            if "freeze_duration:" in line:
                try:
                    total += float(line.split("freeze_duration:", 1)[1].split()[0])
                except ValueError:
                    pass
        return round(min(1.0, total / duration), 4)
