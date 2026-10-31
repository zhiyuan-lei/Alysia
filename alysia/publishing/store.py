from __future__ import annotations

import json
from pathlib import Path

from alysia.core.io import atomic_write_json, load_json_with_recovery
from alysia.schemas import PublishJob


class PublishStore:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.jobs_dir = self.root / "jobs"
        self.jobs_dir.mkdir(parents=True, exist_ok=True)

    def save(self, job: PublishJob) -> Path:
        path = self.jobs_dir / f"{job.job_id}.json"
        return atomic_write_json(path, job.model_dump(mode="json"), backup_count=2)

    def load(self, job_id: str) -> PublishJob:
        if not job_id or Path(job_id).name != job_id:
            raise ValueError("job_id 格式无效")
        path = self.jobs_dir / f"{job_id}.json"
        if not path.is_file():
            raise FileNotFoundError(f"找不到 PublishJob：{job_id}")
        return load_json_with_recovery(path, validator=PublishJob.model_validate, backup_count=2)

    def list_for_run(self, run_id: str) -> list[PublishJob]:
        jobs: list[PublishJob] = []
        for path in sorted(self.jobs_dir.glob("job_*.json")):
            try:
                job = PublishJob.model_validate(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                continue
            if job.run_id == run_id:
                jobs.append(job)
        return jobs
