from __future__ import annotations

import threading
from datetime import datetime
from pathlib import Path

from alysia.core.resources import ResourceManager
from alysia.core.io import atomic_write_json, load_json_with_recovery
from alysia.providers.visual import BaseVisualGenerationProvider
from alysia.schemas.visual import VisualGenerationJob, VisualGenerationResult
from alysia.reliability.artifacts import ArtifactIntegrityChecker
from alysia.reliability.monitor import LongRunningTaskMonitor


class VisualJobQueue:
    """本地持久队列。单进程内严格串行；状态文件支持恢复和缓存。"""

    def __init__(self, root: Path, resources: ResourceManager) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.resources = resources
        self._lock = threading.Lock()
        self._running_job_id: str | None = None
        self.integrity = ArtifactIntegrityChecker()
        self.monitor = LongRunningTaskMonitor(self.root / "monitor")

    def enqueue(self, job: VisualGenerationJob) -> VisualGenerationJob:
        existing = self.load(job.job_id)
        if existing is not None:
            return existing
        self._save_job(job)
        return job

    def run(self, job_id: str, provider: BaseVisualGenerationProvider) -> VisualGenerationResult:
        with self._lock:
            if self._running_job_id is not None and self._running_job_id != job_id:
                raise RuntimeError(f"已有 GPU-heavy visual job 正在运行：{self._running_job_id}")
            self._running_job_id = job_id
        try:
            job = self.load(job_id)
            if job is None:
                raise KeyError(f"visual job 不存在：{job_id}")
            cached = self._load_result(job_id)
            if job.status == "completed" and cached is not None and all(
                self.integrity.check(path, producer=job.provider).validity == "valid"
                for path in cached.output_files
            ):
                return cached
            if job.status == "cancelled":
                raise RuntimeError(f"visual job 已取消：{job_id}")
            job.status = "running"
            job.attempts += 1
            job.updated_at = datetime.now().astimezone()
            self._save_job(job)
            before = self.resources.probe_vram()
            ram_before = self.resources.probe_ram()
            task = self.monitor.start(
                "comfyui_h3", expected_timeout=float(getattr(provider, "job_timeout_sec", 7200)),
                run_id=job.run_id, job_id=job.job_id,
            )
            setattr(provider, "task_monitor", self.monitor)
            setattr(provider, "task_monitor_id", task.task_id)
            try:
                with self.resources.phase("visual:h3", provider=provider, gpu_heavy=True):
                    result = provider.generate(job)
            except Exception as exc:
                self.monitor.finish(task.task_id, status="failed", error=str(exc))
                job.status = "failed"
                job.error = str(exc)
                job.updated_at = datetime.now().astimezone()
                self._save_job(job)
                raise
            self.monitor.finish(task.task_id, status="completed")
            after = self.resources.probe_vram()
            ram_after = self.resources.probe_ram()
            result.warnings.extend(
                [
                    f"vram_before={before}",
                    f"vram_after={after}",
                    f"ram_before={ram_before}",
                    f"ram_after={ram_after}",
                ]
            )
            job.status = "completed"
            job.error = None
            job.updated_at = datetime.now().astimezone()
            self._save_job(job)
            self._save_result(result)
            return result
        finally:
            with self._lock:
                self._running_job_id = None

    def cancel(self, job_id: str, provider: BaseVisualGenerationProvider) -> VisualGenerationJob:
        job = self._require(job_id)
        provider.cancel(job)
        job.updated_at = datetime.now().astimezone()
        self._save_job(job)
        return job

    def load(self, job_id: str) -> VisualGenerationJob | None:
        path = self.root / "jobs" / f"{job_id}.json"
        return load_json_with_recovery(path, validator=VisualGenerationJob.model_validate, backup_count=2) if path.is_file() else None

    def list(self, run_id: str | None = None) -> list[VisualGenerationJob]:
        jobs = [VisualGenerationJob.model_validate_json(path.read_text(encoding="utf-8")) for path in sorted((self.root / "jobs").glob("*.json"))] if (self.root / "jobs").is_dir() else []
        return [job for job in jobs if run_id is None or job.run_id == run_id]

    def _require(self, job_id: str) -> VisualGenerationJob:
        job = self.load(job_id)
        if job is None:
            raise KeyError(job_id)
        return job

    def _save_job(self, job: VisualGenerationJob) -> None:
        path = self.root / "jobs" / f"{job.job_id}.json"
        self._write(path, job.model_dump(mode="json"))

    def _save_result(self, result: VisualGenerationResult) -> None:
        self._write(self.root / "results" / f"{result.job_id}.json", result.model_dump(mode="json"))

    def _load_result(self, job_id: str) -> VisualGenerationResult | None:
        path = self.root / "results" / f"{job_id}.json"
        return load_json_with_recovery(path, validator=VisualGenerationResult.model_validate, backup_count=2) if path.is_file() else None

    @staticmethod
    def _write(path: Path, payload: dict) -> None:
        atomic_write_json(path, payload, backup_count=2)
