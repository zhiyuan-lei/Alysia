from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from alysia.schemas.visual import (
    SceneVisualPlan,
    VisualGenerationJob,
    VisualGenerationResult,
    VisualProviderHealth,
)


class BaseVisualGenerationProvider(ABC):
    provider_id: str

    @abstractmethod
    def prepare_job(self, run_id: str, scene_spec: SceneVisualPlan) -> VisualGenerationJob:
        raise NotImplementedError

    @abstractmethod
    def generate(self, job: VisualGenerationJob) -> VisualGenerationResult:
        raise NotImplementedError

    def submit(self, job: VisualGenerationJob) -> str:
        return job.job_id

    def poll(self, job: VisualGenerationJob) -> str:
        return job.status

    def collect_artifacts(self, job: VisualGenerationJob) -> list[str]:
        del job
        return []

    def cancel(self, job: VisualGenerationJob) -> None:
        job.status = "cancelled"

    @abstractmethod
    def health_check(self) -> VisualProviderHealth:
        raise NotImplementedError

    def unload(self) -> None:
        return None

    def workflow_payload(self, job: VisualGenerationJob) -> dict[str, Any]:
        del job
        return {}
