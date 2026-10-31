from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path

from alysia.providers.visual.base import BaseVisualGenerationProvider
from alysia.schemas.visual import (
    SceneVisualPlan,
    VisualGenerationJob,
    VisualGenerationResult,
    VisualProviderHealth,
)


class MockVisualGenerationProvider(BaseVisualGenerationProvider):
    provider_id = "visual.mock"

    def __init__(self, runs_dir: Path) -> None:
        self.runs_dir = runs_dir.resolve()

    def prepare_job(self, run_id: str, scene_spec: SceneVisualPlan) -> VisualGenerationJob:
        payload = json.dumps(scene_spec.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
        digest = hashlib.sha256(f"{run_id}:{payload}".encode("utf-8")).hexdigest()
        now = datetime.now().astimezone()
        return VisualGenerationJob(
            job_id=f"vjob_{digest[:16]}", run_id=run_id, scene=scene_spec,
            provider=self.provider_id, workflow_id=scene_spec.generation_mode,
            cache_key=digest, created_at=now, updated_at=now,
        )

    def generate(self, job: VisualGenerationJob) -> VisualGenerationResult:
        started = time.monotonic()
        output = self.runs_dir / job.run_id / "visual" / "generated" / f"{job.scene.scene_id}.mp4"
        output.parent.mkdir(parents=True, exist_ok=True)
        ffmpeg = shutil.which("ffmpeg")
        warnings = ["Mock 视觉产物只用于离线流水线测试，不得进入 production review。"]
        if ffmpeg:
            command = [
                ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=0x16213e:s=640x360:r=24",
                "-t", f"{job.scene.requested_duration_sec:.3f}", "-an", "-c:v", "libx264",
                "-pix_fmt", "yuv420p", str(output),
            ]
            completed = subprocess.run(command, capture_output=True, text=True, timeout=60, check=False)
            if completed.returncode != 0:
                raise RuntimeError(f"Mock FFmpeg 生成失败：{completed.stderr[-500:]}")
        else:
            output = output.with_suffix(".mock.json")
            output.write_text(json.dumps({"job": job.job_id}, indent=2), encoding="utf-8")
            warnings.append("FFmpeg 不可用，生成了不可解码的 mock 描述文件。")
        return VisualGenerationResult(
            job_id=job.job_id, scene_id=job.scene.scene_id, provider=self.provider_id,
            workflow_id=job.workflow_id, workflow_version=job.workflow_version,
            output_files=[output], duration_sec=job.scene.requested_duration_sec,
            resolution="640x360", generation_time_sec=time.monotonic() - started,
            seed_config={"seed": 0, "deterministic": True}, warnings=warnings,
            status="completed", mock=True,
        )

    def health_check(self) -> VisualProviderHealth:
        return VisualProviderHealth(
            provider=self.provider_id, available=True,
            details=["离线确定性 provider；产物不可进入 production review。"],
        )
