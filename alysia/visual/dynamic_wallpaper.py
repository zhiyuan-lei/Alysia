"""Alysia's local, single-image H3 workflow: 动态壁纸制作.

The 720p profile is based on the measured four-process Alpha22 H3 run. It is
explicitly separate from the legacy one-shot ComfyUI H3 provider.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
from uuid import uuid4

from PIL import Image

from alysia.core.config import AlysiaConfig
from alysia.core.io import atomic_write_json
from alysia.core.resources import ResourceManager
from alysia.reliability.resources import GpuBudgetBlocked, ResourceGuard
from alysia.workers.media import require_media_executable


WORKFLOW_ID = "dynamic_wallpaper"
WORKFLOW_NAME = "动态壁纸制作"
PHASES = ("keyframe", "encode", "sample", "decode")
PHASE_FILES = ("keyframe.pt", "conditioning.pt", "sampled.pt", "frame_089.png")
FRAMES = 90
STEPS = 20
SEED = 20261001
FPS = 24
PREFLIGHT_GPU_BUDGET_MIB = 6144
RUNTIME_VRAM_STOP_MIB = 7680  # 7.5 GiB, sampled whole-device usage
# Measured 90-frame whole-device peak 5447 MiB minus 1210 MiB baseline =
# 4237 MiB incremental; round upward for preflight (not a whole-device peak).
ESTIMATED_INCREMENTAL_MIB = 4500
# The measured system-RAM rise was ~4 GiB; leave 2 GiB of margin.
ESTIMATED_RAM_INCREMENT_MIB = 6144


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class DynamicWallpaperWorkflow:
    """Generate a review-only 1280x720 MP4 from one local reference image."""

    def __init__(self, config: AlysiaConfig, *, resources: ResourceManager | None = None) -> None:
        self.config = config
        self.resources = resources or ResourceManager(sequential_gpu=True)
        self.root = Path("workspace/dynamic_wallpaper")

    def run(self, image_path: Path, prompt: str, *, output_dir: Path | None = None) -> dict:
        image_path = image_path.expanduser().resolve()
        if not image_path.is_file():
            raise FileNotFoundError(f"参考图片不存在：{image_path}")
        if not prompt.strip() or len(prompt) > 12000:
            raise ValueError("动作提示词必须为 1–12000 个字符")
        with Image.open(image_path) as image:
            image.verify()
        self._dependencies()
        root = (output_dir or self.root).expanduser().resolve()
        self._preflight(root)
        run_dir = root / f"wallpaper_{time.strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}"
        run_dir.mkdir(parents=True, exist_ok=False)
        h3 = self.config.visual_generation.h3
        job = {
            "workflow_id": WORKFLOW_ID,
            "workflow_name": WORKFLOW_NAME,
            "profile": "h3_staged_720p_90f_20steps_loop",
            "comfyui_dir": str(h3.comfyui_dir.resolve()),
            "diffusion_model": h3.diffusion_model,
            "text_encoder": h3.text_encoder,
            "video_vae": h3.video_vae,
            "frames": FRAMES,
            "steps": STEPS,
            "seed": SEED,
            "fps": FPS,
            "source_image_sha256": _sha256(image_path),
            "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
            "source_image": str(image_path),
        }
        (run_dir / "prompt.txt").write_text(prompt, encoding="utf-8", newline="\n")
        job["prompt_sha256"] = _sha256(run_dir / "prompt.txt")
        atomic_write_json(run_dir / "job.json", job)
        summary = {"workflow_id": WORKFLOW_ID, "workflow_name": WORKFLOW_NAME,
                   "status": "RUNNING", "stages": [], "run_dir": str(run_dir),
                   "source_image_sha256": job["source_image_sha256"]}
        atomic_write_json(run_dir / "summary.json", summary)
        try:
            self._make_canvas(image_path, run_dir)
            return self._execute(run_dir, job, summary)
        except Exception as exc:
            summary.update(status="FAILED", error=f"{type(exc).__name__}: {exc}")
            atomic_write_json(run_dir / "summary.json", summary)
            raise

    def resume(self, run_dir: Path) -> dict:
        run_dir = run_dir.expanduser().resolve()
        job = json.loads((run_dir / "job.json").read_text(encoding="utf-8"))
        summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
        if job.get("workflow_id") != WORKFLOW_ID or job.get("profile") != "h3_staged_720p_90f_20steps_loop":
            raise ValueError("不是受支持的动态壁纸运行记录")
        if not (run_dir / "reference_canvas.png").is_file() or not (run_dir / "prompt.txt").is_file():
            raise ValueError("恢复所需的参考帧或提示词缺失")
        if hashlib.sha256((run_dir / "prompt.txt").read_bytes()).hexdigest() != job["prompt_sha256"]:
            raise ValueError("提示词已变化，不能安全恢复")
        if summary.get("status") == "GENERATED_PENDING_HUMAN_REVIEW":
            artifact = run_dir / "dynamic_wallpaper_720p.mp4"
            if artifact.is_file() and _sha256(artifact) == summary.get("artifact_sha256"):
                return summary
            raise ValueError("已完成视频缺失或哈希变化，不能自动覆盖")
        self._dependencies()
        (run_dir / "STOP").unlink(missing_ok=True)
        summary.pop("error", None)
        summary["status"] = "RUNNING"
        atomic_write_json(run_dir / "summary.json", summary)
        try:
            return self._execute(run_dir, job, summary)
        except Exception as exc:
            summary.update(status="FAILED", error=f"{type(exc).__name__}: {exc}")
            atomic_write_json(run_dir / "summary.json", summary)
            raise

    def _dependencies(self) -> None:
        h3 = self.config.visual_generation.h3
        if not h3.enabled or h3.comfyui_dir is None:
            raise ValueError("请启用 H3 并配置 visual_generation.h3.comfyui_dir")
        python = h3.comfyui_dir / ".venv" / "Scripts" / "python.exe"
        if not python.is_file():
            raise FileNotFoundError(f"ComfyUI Python 不存在：{python}")
        models = h3.comfyui_dir / "models"
        for path in (models / "diffusion_models" / h3.diffusion_model,
                     models / "text_encoders" / h3.text_encoder,
                     models / "vae" / h3.video_vae):
            if not path.is_file():
                raise FileNotFoundError(f"H3 模型不存在：{path}")
        require_media_executable("ffmpeg", self.config.render.ffmpeg_path)
        require_media_executable("ffprobe", self.config.render.ffprobe_path)

    def _preflight(self, target: Path) -> None:
        budget = min(self.config.production.max_local_vram_mb, PREFLIGHT_GPU_BUDGET_MIB)
        guard = ResourceGuard(self.resources, max_task_vram_mb=budget).check(
            target, gpu_heavy=True, estimated_output_mb=1024,
            estimated_peak_vram_mb=ESTIMATED_INCREMENTAL_MIB, require_vram_budget=True,
        )
        if guard.status == "blocked":
            raise GpuBudgetBlocked("; ".join(guard.reasons))
        ram = self.resources.probe_ram()
        ram_limit_mib = min(self.config.hardware_profile.ram_gb, 24) * 1024
        if ram is None or ram["used_mb"] + ESTIMATED_RAM_INCREMENT_MIB > ram_limit_mib:
            raise GpuBudgetBlocked("24 GiB RAM envelope 预检未通过，等待系统内存释放")

    def _make_canvas(self, image_path: Path, run_dir: Path) -> None:
        ffmpeg = require_media_executable("ffmpeg", self.config.render.ffmpeg_path)
        subprocess.run([
            str(ffmpeg), "-nostdin", "-y", "-v", "error", "-i", str(image_path),
            "-vf", "scale=1280:720:force_original_aspect_ratio=increase,"
                   "crop=1280:720,pad=1280:736:0:8",
            "-frames:v", "1", str(run_dir / "reference_canvas.png"),
        ], check=True, timeout=120)

    def _execute(self, run_dir: Path, job: dict, summary: dict) -> dict:
        python = Path(job["comfyui_dir"]) / ".venv" / "Scripts" / "python.exe"
        worker = Path(__file__).resolve().parent.parent / "h3_staged_wallpaper_worker.py"
        for phase, expected in zip(PHASES, PHASE_FILES, strict=True):
            if phase in {item["phase"] for item in summary["stages"] if item.get("status") == "PASS"}:
                if not (run_dir / expected).is_file():
                    raise ValueError(f"已完成阶段的产物缺失：{expected}")
                continue
            self._preflight(run_dir)
            with self.resources.phase(f"{WORKFLOW_ID}:{phase}", gpu_heavy=True, timeout_sec=0):
                result = self._phase(python, worker, run_dir, phase)
            summary["stages"].append(result)
            atomic_write_json(run_dir / "summary.json", summary)
            if result["status"] != "PASS" or not (run_dir / expected).is_file():
                raise RuntimeError(f"H3 阶段 {phase} 失败；详见 {run_dir / (phase + '_stderr.log')}")
        video = run_dir / "dynamic_wallpaper_720p.mp4"
        ffmpeg = require_media_executable("ffmpeg", self.config.render.ffmpeg_path)
        subprocess.run([
            str(ffmpeg), "-nostdin", "-y", "-v", "error", "-framerate", str(FPS),
            "-i", str(run_dir / "frame_%03d.png"), "-vf", "crop=1280:720:0:8",
            "-frames:v", str(FRAMES), "-c:v", "libx264", "-crf", "18",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(video),
        ], check=True, timeout=600)
        probe = require_media_executable("ffprobe", self.config.render.ffprobe_path)
        checked = subprocess.run([
            str(probe), "-v", "error", "-count_frames", "-show_entries",
            "stream=codec_type,width,height,nb_read_frames:format=duration", "-of", "json",
            str(video),
        ], capture_output=True, text=True, check=True, timeout=120)
        media = json.loads(checked.stdout)
        streams = [item for item in media.get("streams", []) if item.get("codec_type") == "video"]
        if not streams or (streams[0].get("width"), streams[0].get("height")) != (1280, 720):
            raise ValueError("输出视频分辨率验证失败")
        if int(streams[0].get("nb_read_frames", 0)) != FRAMES:
            raise ValueError("输出视频帧数验证失败")
        summary.update(status="GENERATED_PENDING_HUMAN_REVIEW", artifact=str(video),
                       artifact_bytes=video.stat().st_size, artifact_sha256=_sha256(video),
                       validation={"width": 1280, "height": 720, "frames": FRAMES,
                                   "duration_sec": float(media["format"]["duration"])},
                       peak_vram_mib=max(item["peak_vram_mib"] for item in summary["stages"]),
                       peak_system_ram_mib=max(item["peak_system_ram_mib"] for item in summary["stages"]))
        atomic_write_json(run_dir / "summary.json", summary)
        return summary

    def _phase(self, python: Path, worker: Path, run_dir: Path, phase: str) -> dict:
        start = time.monotonic()
        baseline_vram = self.resources.probe_vram()
        baseline_ram = self.resources.probe_ram()
        peak_vram = baseline_vram["used_mb"] if baseline_vram else 0
        peak_ram = baseline_ram["used_mb"] if baseline_ram else 0
        stop_reason = None
        stdout = run_dir / f"{phase}_stdout.log"
        stderr = run_dir / f"{phase}_stderr.log"
        with stdout.open("w", encoding="utf-8") as out, stderr.open("w", encoding="utf-8") as err:
            process = subprocess.Popen([
                str(python), str(worker), "--phase", phase, "--run-dir", str(run_dir),
            ], stdout=out, stderr=err, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            while process.poll() is None:
                vram = self.resources.probe_vram()
                ram = self.resources.probe_ram()
                if vram is None or ram is None:
                    stop_reason = "resource_probe_unavailable"
                else:
                    peak_vram = max(peak_vram, vram["used_mb"])
                    peak_ram = max(peak_ram, ram["used_mb"])
                    if vram["used_mb"] > RUNTIME_VRAM_STOP_MIB:
                        stop_reason = "gpu_budget_exceeded"
                    elif ram["used_mb"] > min(self.config.hardware_profile.ram_gb, 24) * 1024:
                        stop_reason = "ram_budget_exceeded"
                if time.monotonic() - start > self.config.visual_generation.h3.job_timeout_sec:
                    stop_reason = "timeout"
                if stop_reason:
                    (run_dir / "STOP").touch()
                time.sleep(0.5)
        after_vram = self.resources.probe_vram()
        after_ram = self.resources.probe_ram()
        return {
            "phase": phase, "status": "PASS" if process.returncode == 0 and not stop_reason else "FAILED",
            "exit_code": process.returncode, "stop_reason": stop_reason,
            "elapsed_sec": round(time.monotonic() - start, 3),
            "baseline_vram_mib": baseline_vram["used_mb"] if baseline_vram else None,
            "peak_vram_mib": peak_vram,
            "after_vram_mib": after_vram["used_mb"] if after_vram else None,
            "baseline_system_ram_mib": baseline_ram["used_mb"] if baseline_ram else None,
            "peak_system_ram_mib": peak_ram,
            "after_system_ram_mib": after_ram["used_mb"] if after_ram else None,
        }
