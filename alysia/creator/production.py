from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Callable, Iterable, Mapping

import httpx
from pydantic import BaseModel, Field, model_validator

from alysia.core.io import atomic_write_json, load_json_with_recovery
from alysia.core.resources import ResourceManager
from alysia.creator.models import (
    CreatorJob,
    CreatorPlan,
    CreatorScriptSection,
    EvidenceStatus,
)
from alysia.creator.store import CreatorJobStore
from alysia.knowledge.models import stable_id
from alysia.providers.visual.comfyui import ComfyUIProvider
from alysia.providers.visual.h3 import MiniMaxH3LocalProvider
from alysia.reliability.artifacts import ArtifactIntegrityChecker
from alysia.reliability.resources import GpuBudgetBlocked, ResourceGuard
from alysia.schemas.visual import SceneVisualPlan
from alysia.security.redaction import Redactor


def production_now() -> datetime:
    return datetime.now().astimezone()


class ProductionTaskType(str, Enum):
    VOICE = "VOICE"
    IMAGE = "IMAGE"
    VIDEO = "VIDEO"
    COMPOSITE = "COMPOSITE"
    THUMBNAIL = "THUMBNAIL"
    METADATA = "METADATA"


class ProductionTaskStatus(str, Enum):
    PENDING = "PENDING"
    READY = "READY"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    SKIPPED = "SKIPPED"
    CANCELLED = "CANCELLED"


class ProductionStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    CANCELLED = "CANCELLED"


class ResourceClass(str, Enum):
    CPU_LIGHT = "CPU_LIGHT"
    CPU_HEAVY = "CPU_HEAVY"
    GPU_LIGHT = "GPU_LIGHT"
    GPU_HEAVY = "GPU_HEAVY"


class ArtifactStatus(str, Enum):
    VALID = "VALID"
    PARTIAL = "PARTIAL"
    INVALID = "INVALID"
    MISSING = "MISSING"


class FailureCategory(str, Enum):
    TRANSIENT = "TRANSIENT"
    PERMANENT_VALIDATION = "PERMANENT_VALIDATION"
    RESOURCE = "RESOURCE"
    CANCELLED = "CANCELLED"


class RetryPolicy(BaseModel):
    max_attempts: int = Field(default=2, ge=1, le=3)
    backoff_seconds: list[float] = Field(default_factory=lambda: [0.0, 0.25], max_length=3)


class ProductionTask(BaseModel):
    task_id: str = Field(min_length=1)
    task_type: ProductionTaskType
    status: ProductionTaskStatus = ProductionTaskStatus.PENDING
    input_refs: list[str] = Field(default_factory=list)
    output_refs: list[str] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)
    resource_class: ResourceClass = ResourceClass.CPU_LIGHT
    attempt_count: int = Field(default=0, ge=0)
    max_attempts: int = Field(default=2, ge=1, le=3)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class ProductionPlan(BaseModel):
    production_id: str = Field(min_length=1)
    job_id: str = Field(min_length=1)
    creator_plan_id: str = Field(min_length=1)
    tasks: list[ProductionTask] = Field(min_length=1)
    dependencies: dict[str, list[str]] = Field(default_factory=dict)
    resource_requirements: dict[str, object] = Field(default_factory=dict)
    artifact_targets: dict[str, str] = Field(default_factory=dict)
    status: ProductionStatus = ProductionStatus.PENDING
    created_at: datetime = Field(default_factory=production_now)
    updated_at: datetime = Field(default_factory=production_now)

    @model_validator(mode="after")
    def valid_dag(self) -> "ProductionPlan":
        task_ids = [task.task_id for task in self.tasks]
        if len(task_ids) != len(set(task_ids)):
            raise ValueError("ProductionTask task_id must be unique")
        known = set(task_ids)
        for task in self.tasks:
            unknown = set(task.depends_on).difference(known)
            if unknown:
                raise ValueError(f"unknown dependencies for {task.task_id}: {sorted(unknown)}")
            if task.task_id in task.depends_on:
                raise ValueError(f"task cannot depend on itself: {task.task_id}")
        visiting: set[str] = set()
        visited: set[str] = set()
        graph = {task.task_id: task.depends_on for task in self.tasks}

        def visit(task_id: str) -> None:
            if task_id in visiting:
                raise ValueError("ProductionPlan dependency cycle detected")
            if task_id in visited:
                return
            visiting.add(task_id)
            for dependency in graph[task_id]:
                visit(dependency)
            visiting.remove(task_id)
            visited.add(task_id)

        for task_id in task_ids:
            visit(task_id)
        expected = {task.task_id: list(task.depends_on) for task in self.tasks}
        if self.dependencies and self.dependencies != expected:
            raise ValueError("dependencies must match ProductionTask.depends_on")
        self.dependencies = expected
        return self

    def task(self, task_id: str) -> ProductionTask:
        try:
            return next(task for task in self.tasks if task.task_id == task_id)
        except StopIteration as exc:
            raise KeyError(task_id) from exc


class ProductionArtifact(BaseModel):
    artifact_id: str = Field(min_length=1)
    job_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    artifact_type: str = Field(min_length=1)
    path: Path
    created_at: datetime = Field(default_factory=production_now)
    size: int | None = Field(default=None, ge=0)
    hash: str | None = None
    status: ArtifactStatus
    metadata: dict[str, object] = Field(default_factory=dict)


class AdapterResult(BaseModel):
    output_paths: list[Path] = Field(default_factory=list)
    artifact_type: str
    metadata: dict[str, object] = Field(default_factory=dict)


class ProductionFailure(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        code: str,
        category: FailureCategory,
        retryable: bool,
        partial_paths: Iterable[Path] = (),
    ) -> None:
        super().__init__(message)
        self.code = code
        self.category = category
        self.retryable = retryable
        self.partial_paths = list(partial_paths)


class CreatorPlanBuilder:
    def create(
        self,
        job: CreatorJob,
        *,
        hook: str,
        core_message: str,
        target_audience: str,
        sections: list[CreatorScriptSection],
        visual_direction: str,
        visual_scenes: list[dict[str, object]],
        voice_direction: str,
        audio_direction: str,
        thumbnail_concept: str,
        title_candidates: list[str],
        preferred_title: str,
        description_draft: str,
        tags: list[str],
        production_requirements: Mapping[str, object] | None = None,
        estimated_cost: Mapping[str, object] | None = None,
        creative_only: bool = False,
    ) -> CreatorPlan:
        if not job.topic.strip():
            raise ValueError("CreatorPlan requires CreatorJob.topic")
        grounded = [
            claim
            for claim in job.claims
            if claim.evidence_status in {EvidenceStatus.SUPPORTED, EvidenceStatus.PARTIALLY_SUPPORTED}
        ]
        if not grounded and not creative_only:
            raise ValueError("CreatorPlan requires grounded claims or creative_only=true")
        known_claims = {claim.claim_id for claim in job.claims}
        for section in sections:
            unknown = set(section.claim_refs).difference(known_claims)
            if unknown:
                raise ValueError("script section references claims outside CreatorJob: " + ", ".join(sorted(unknown)))
        uncertain_claims = [
            claim.claim_id
            for claim in job.claims
            if claim.evidence_status in {
                EvidenceStatus.CONFLICTING,
                EvidenceStatus.INSUFFICIENT_EVIDENCE,
                EvidenceStatus.UNVERIFIED,
            }
        ]
        now = production_now()
        plan_id = stable_id("creator_plan", job.job_id, job.current_revision, job.topic)
        script = "\n\n".join(section.text for section in sections)
        return CreatorPlan(
            plan_id=plan_id,
            job_id=job.job_id,
            revision=job.current_revision,
            hook=hook,
            core_message=core_message,
            target_audience=target_audience,
            structure=[section.purpose for section in sections],
            script=script,
            script_sections=sections,
            visual_direction=visual_direction,
            visual_scenes=visual_scenes,
            voice_direction=voice_direction,
            audio_direction=audio_direction,
            thumbnail_concept=thumbnail_concept,
            title_candidates=title_candidates,
            preferred_title=preferred_title,
            title=preferred_title,
            description_draft=description_draft,
            description=description_draft,
            tags=tags,
            research_refs=[source.source_id for source in job.research_sources],
            claim_refs=[claim.claim_id for claim in job.claims],
            uncertainty_refs=list(dict.fromkeys([*job.uncertainties, *uncertain_claims])),
            production_requirements=dict(production_requirements or {}),
            estimated_cost=dict(estimated_cost or {"status": "unknown"}),
            created_at=now,
            updated_at=now,
        )


class ProductionPlanner:
    def build(
        self,
        creator_plan: CreatorPlan,
        tasks: list[ProductionTask],
        *,
        resource_requirements: Mapping[str, object] | None = None,
        artifact_targets: Mapping[str, str] | None = None,
    ) -> ProductionPlan:
        if not creator_plan.plan_id or not creator_plan.job_id:
            raise ValueError("ProductionPlan requires a bound CreatorPlan")
        return ProductionPlan(
            production_id=stable_id("production", creator_plan.job_id, creator_plan.plan_id),
            job_id=creator_plan.job_id,
            creator_plan_id=creator_plan.plan_id,
            tasks=tasks,
            resource_requirements=dict(resource_requirements or {"gpu_heavy_concurrency": 1}),
            artifact_targets=dict(artifact_targets or {}),
        )


class ProductionPlanStore:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, production_id: str) -> Path:
        if not re.fullmatch(r"production_[0-9a-f]{16}", production_id):
            raise ValueError("invalid production_id")
        return self.root / f"{production_id}.json"

    def save(self, plan: ProductionPlan) -> Path:
        plan = ProductionPlan.model_validate(plan.model_dump())
        plan.updated_at = production_now()
        return atomic_write_json(self.path_for(plan.production_id), plan.model_dump(mode="json"), backup_count=2)

    def load(self, production_id: str) -> ProductionPlan:
        path = self.path_for(production_id)
        if not path.is_file():
            raise FileNotFoundError(path)
        return load_json_with_recovery(path, validator=ProductionPlan.model_validate, backup_count=2)

    def plans(self) -> list[ProductionPlan]:
        plans: list[ProductionPlan] = []
        for path in sorted(self.root.glob("production_*.json")):
            try:
                plans.append(load_json_with_recovery(
                    path,
                    validator=ProductionPlan.model_validate,
                    backup_count=2,
                ))
            except (OSError, ValueError):
                continue
        return plans


class ProductionArtifactRegistry:
    def __init__(
        self,
        root: Path,
        redactor: Redactor | None = None,
        *,
        probe_media: bool = True,
    ) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.redactor = redactor or Redactor()
        self.checker = ArtifactIntegrityChecker(compute_hash=True, probe_media=probe_media)

    def task_dir(self, job_id: str, task_id: str) -> Path:
        for value in (job_id, task_id):
            if not re.fullmatch(r"[A-Za-z0-9_.-]+", value):
                raise ValueError("invalid artifact path identifier")
        path = (self.root / job_id / task_id).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("artifact path escapes configured root")
        path.mkdir(parents=True, exist_ok=True)
        return path

    def register(
        self,
        *,
        job_id: str,
        task_id: str,
        artifact_type: str,
        path: Path,
        metadata: Mapping[str, object] | None = None,
        forced_status: ArtifactStatus | None = None,
    ) -> ProductionArtifact:
        resolved = path.resolve()
        if not resolved.is_relative_to(self.root):
            raise ValueError("production artifact must remain inside configured artifact root")
        integrity = self.checker.check(resolved, producer=f"production:{task_id}")
        if integrity.validity == "missing":
            status = ArtifactStatus.MISSING
        elif integrity.size == 0:
            status = ArtifactStatus.PARTIAL
        elif integrity.validity == "invalid":
            status = ArtifactStatus.INVALID
        else:
            status = ArtifactStatus.VALID
        if forced_status is not None and status != ArtifactStatus.MISSING:
            status = forced_status
        artifact = ProductionArtifact(
            artifact_id=stable_id("artifact", job_id, task_id, artifact_type, resolved),
            job_id=job_id,
            task_id=task_id,
            artifact_type=artifact_type,
            path=resolved,
            size=integrity.size,
            hash=integrity.hash,
            status=status,
            metadata=self.redactor.redact_value(dict(metadata or {})),
        )
        manifest_path = self.root / "manifests" / f"{artifact.artifact_id}.json"
        atomic_write_json(manifest_path, artifact.model_dump(mode="json"))
        return artifact

    def load(self, artifact_id: str) -> ProductionArtifact:
        if not re.fullmatch(r"artifact_[0-9a-f]{16}", artifact_id):
            raise ValueError("invalid artifact_id")
        path = self.root / "manifests" / f"{artifact_id}.json"
        if not path.is_file():
            raise FileNotFoundError(path)
        return ProductionArtifact.model_validate(json.loads(path.read_text(encoding="utf-8")))

    def valid(self, artifact_ids: Iterable[str]) -> bool:
        ids = list(artifact_ids)
        if not ids:
            return False
        for artifact_id in ids:
            try:
                artifact = self.load(artifact_id)
            except (FileNotFoundError, ValueError):
                return False
            current = self.checker.check(artifact.path, producer=f"production:{artifact.task_id}")
            if artifact.status != ArtifactStatus.VALID or current.validity != "valid" or current.hash != artifact.hash:
                return False
        return True


class ProductionAdapter:
    adapter_id = "production.base"

    def execute(self, task: ProductionTask, output_dir: Path) -> AdapterResult:
        raise NotImplementedError

    def cancel(self, task: ProductionTask) -> None:
        del task

    def cleanup(self) -> None:
        return None


class ComfyUIProductionAdapter(ProductionAdapter):
    adapter_id = "production.comfyui"

    def __init__(self, provider: ComfyUIProvider) -> None:
        self.provider = provider
        self._active_jobs: dict[str, object] = {}

    @classmethod
    def from_config(
        cls,
        *,
        base_url: str,
        workflow_dir: Path,
        output_dir: Path,
        timeout_sec: float = 30.0,
        job_timeout_sec: float = 7200.0,
        security=None,
    ) -> "ComfyUIProductionAdapter":
        return cls(ComfyUIProvider(
            base_url=base_url,
            workflow_dir=workflow_dir,
            output_dir=output_dir,
            timeout_sec=timeout_sec,
            job_timeout_sec=job_timeout_sec,
            security=security,
        ))

    def execute(self, task: ProductionTask, output_dir: Path) -> AdapterResult:
        del output_dir
        scene_payload = task.metadata.get("scene")
        if not isinstance(scene_payload, dict):
            raise ProductionFailure(
                "ComfyUI task requires structured scene metadata",
                code="INVALID_REQUEST",
                category=FailureCategory.PERMANENT_VALIDATION,
                retryable=False,
            )
        try:
            scene = SceneVisualPlan.model_validate(scene_payload)
            job = self.provider.prepare_job(task.task_id, scene)
            workflow = self.provider.load_workflow(job.workflow_id)
            workflow_hash = hashlib.sha256(
                json.dumps(workflow, ensure_ascii=False, sort_keys=True).encode("utf-8")
            ).hexdigest()
            self.provider.workflow_payload(job)
            self._active_jobs[task.task_id] = job
            result = self.provider.generate(job)
            if result.status != "completed" or not result.output_files:
                raise ProductionFailure(
                    "ComfyUI returned no completed artifact",
                    code="INVALID_RESULT",
                    category=FailureCategory.PERMANENT_VALIDATION,
                    retryable=False,
                    partial_paths=result.output_files,
                )
            return AdapterResult(
                output_paths=result.output_files,
                artifact_type=task.task_type.value,
                metadata={
                    "provider": self.provider.provider_id,
                    "workflow_ref": job.workflow_id,
                    "workflow_hash": workflow_hash,
                    "scene_id": scene.scene_id,
                },
            )
        except ProductionFailure:
            raise
        except GpuBudgetBlocked as exc:
            raise ProductionFailure(
                str(exc), code="GPU_BUDGET_BLOCKED", category=FailureCategory.RESOURCE, retryable=False,
            ) from exc
        except (TimeoutError, httpx.TimeoutException) as exc:
            raise ProductionFailure(
                str(exc), code="TIMEOUT", category=FailureCategory.TRANSIENT, retryable=True
            ) from exc
        except Exception as exc:
            if ResourceManager.is_oom_error(exc):
                raise ProductionFailure(
                    str(exc), code="RESOURCE_EXHAUSTED", category=FailureCategory.RESOURCE, retryable=True
                ) from exc
            if isinstance(exc, (ValueError, KeyError, FileNotFoundError, json.JSONDecodeError)):
                raise ProductionFailure(
                    str(exc), code="INVALID_REQUEST", category=FailureCategory.PERMANENT_VALIDATION, retryable=False
                ) from exc
            raise ProductionFailure(
                str(exc), code="PROVIDER_FAILURE", category=FailureCategory.TRANSIENT, retryable=True
            ) from exc
        finally:
            self._active_jobs.pop(task.task_id, None)

    def cancel(self, task: ProductionTask) -> None:
        job = self._active_jobs.get(task.task_id)
        if job is not None:
            self.provider.cancel(job)

    def cleanup(self) -> None:
        self.provider.unload()


class H3ProductionAdapter(ComfyUIProductionAdapter):
    adapter_id = "production.comfyui-h3"

    @classmethod
    def from_config(cls, config, *, output_dir: Path, security=None) -> "H3ProductionAdapter":
        return cls(MiniMaxH3LocalProvider(config, output_dir=output_dir, security=security))


class ProductionOrchestrator:
    def __init__(
        self,
        *,
        adapters: Mapping[ProductionTaskType, ProductionAdapter],
        store: ProductionPlanStore,
        artifacts: ProductionArtifactRegistry,
        resources: ResourceManager | None = None,
        retry_policy: RetryPolicy | None = None,
        preflight: Callable[[ProductionTask], None] | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.adapters = dict(adapters)
        self.store = store
        self.artifacts = artifacts
        self.resources = resources or ResourceManager(sequential_gpu=True)
        self.retry_policy = retry_policy or RetryPolicy()
        self.preflight = preflight or self._default_preflight
        self.sleep = sleep

    def start(self, plan: ProductionPlan) -> ProductionPlan:
        if plan.status != ProductionStatus.PENDING:
            raise ValueError("start requires a PENDING ProductionPlan")
        plan.status = ProductionStatus.RUNNING
        self.store.save(plan)
        return self._run(plan)

    def resume(
        self,
        production_id: str,
        *,
        force_regenerate: Iterable[str] = (),
    ) -> ProductionPlan:
        plan = self.store.load(production_id)
        force = set(force_regenerate)
        for task in plan.tasks:
            if task.task_id in force:
                task.status = ProductionTaskStatus.PENDING
                task.attempt_count = 0
                task.output_refs = []
                task.error = None
            elif task.status == ProductionTaskStatus.SUCCEEDED and not self.artifacts.valid(task.output_refs):
                task.status = ProductionTaskStatus.PENDING
                task.output_refs = []
                task.error = "previous artifact is no longer valid"
        plan.status = ProductionStatus.RUNNING
        self.store.save(plan)
        return self._run(plan)

    def cancel(self, production_id: str) -> ProductionPlan:
        plan = self.store.load(production_id)
        for task in plan.tasks:
            if task.status in {ProductionTaskStatus.PENDING, ProductionTaskStatus.READY, ProductionTaskStatus.RUNNING}:
                adapter = self.adapters.get(task.task_type)
                if task.status == ProductionTaskStatus.RUNNING and adapter is not None:
                    adapter.cancel(task)
                task.status = ProductionTaskStatus.CANCELLED
                task.finished_at = production_now()
        plan.status = ProductionStatus.CANCELLED
        self.store.save(plan)
        return plan

    def status(self, production_id: str) -> ProductionPlan:
        return self.store.load(production_id)

    def _run(self, plan: ProductionPlan) -> ProductionPlan:
        while True:
            changed = self._resolve_dependencies(plan)
            ready = [task for task in plan.tasks if task.status == ProductionTaskStatus.READY]
            if not ready:
                if not changed:
                    break
                continue
            for task in ready:
                self._execute_task(plan, task)
                self.store.save(plan)
        statuses = {task.status for task in plan.tasks}
        if statuses <= {ProductionTaskStatus.SUCCEEDED, ProductionTaskStatus.SKIPPED}:
            plan.status = ProductionStatus.SUCCEEDED
        elif ProductionTaskStatus.FAILED in statuses:
            plan.status = ProductionStatus.FAILED
        elif ProductionTaskStatus.CANCELLED in statuses:
            plan.status = ProductionStatus.CANCELLED
        else:
            plan.status = ProductionStatus.BLOCKED
        self.store.save(plan)
        return plan

    @staticmethod
    def _resolve_dependencies(plan: ProductionPlan) -> bool:
        changed = False
        status_by_id = {task.task_id: task.status for task in plan.tasks}
        failed_upstream = {
            ProductionTaskStatus.FAILED,
            ProductionTaskStatus.BLOCKED,
            ProductionTaskStatus.CANCELLED,
        }
        for task in plan.tasks:
            if task.status != ProductionTaskStatus.PENDING:
                continue
            dependency_statuses = [status_by_id[dependency] for dependency in task.depends_on]
            if any(status in failed_upstream for status in dependency_statuses):
                task.status = ProductionTaskStatus.BLOCKED
                task.error = "upstream dependency failed"
                changed = True
            elif all(status in {ProductionTaskStatus.SUCCEEDED, ProductionTaskStatus.SKIPPED} for status in dependency_statuses):
                task.status = ProductionTaskStatus.READY
                changed = True
        return changed

    def _execute_task(self, plan: ProductionPlan, task: ProductionTask) -> None:
        if task.status == ProductionTaskStatus.SUCCEEDED and self.artifacts.valid(task.output_refs):
            return
        adapter = self.adapters.get(task.task_type)
        if adapter is None:
            task.status = ProductionTaskStatus.FAILED
            task.error = f"no adapter for {task.task_type.value}"
            task.metadata["retryable"] = False
            return
        max_attempts = min(task.max_attempts, self.retry_policy.max_attempts)
        while task.attempt_count < max_attempts:
            task.attempt_count += 1
            task.status = ProductionTaskStatus.RUNNING
            task.started_at = task.started_at or production_now()
            before = self.resources.probe_vram() if task.resource_class == ResourceClass.GPU_HEAVY else None
            try:
                self.preflight(task)
                with self.resources.phase(
                    task.task_id,
                    provider=adapter,
                    gpu_heavy=task.resource_class == ResourceClass.GPU_HEAVY,
                    timeout_sec=0,
                ):
                    result = adapter.execute(task, self.artifacts.task_dir(plan.job_id, task.task_id))
                manifests = [
                    self.artifacts.register(
                        job_id=plan.job_id,
                        task_id=task.task_id,
                        artifact_type=result.artifact_type,
                        path=path,
                        metadata=result.metadata,
                    )
                    for path in result.output_paths
                ]
                invalid = [item for item in manifests if item.status != ArtifactStatus.VALID]
                if invalid:
                    raise ProductionFailure(
                        "adapter output failed artifact validation",
                        code="INVALID_ARTIFACT",
                        category=FailureCategory.PERMANENT_VALIDATION,
                        retryable=False,
                        partial_paths=[item.path for item in invalid],
                    )
                task.output_refs = [item.artifact_id for item in manifests]
                task.status = ProductionTaskStatus.SUCCEEDED
                task.error = None
                task.finished_at = production_now()
                task.metadata.update({
                    "vram_before": before,
                    "vram_after": self.resources.probe_vram() if task.resource_class == ResourceClass.GPU_HEAVY else None,
                    "retryable": False,
                })
                return
            except Exception as raw_error:
                error = self._map_failure(raw_error)
                for path in error.partial_paths:
                    try:
                        self.artifacts.register(
                            job_id=plan.job_id,
                            task_id=task.task_id,
                            artifact_type=task.task_type.value,
                            path=path,
                            forced_status=ArtifactStatus.PARTIAL,
                            metadata={"failure_code": error.code},
                        )
                    except ValueError:
                        continue
                task.error = str(error)
                task.metadata.update({
                    "failure_code": error.code,
                    "failure_category": error.category.value,
                    "retryable": error.retryable,
                    "vram_before": before,
                    "vram_after": self.resources.probe_vram() if task.resource_class == ResourceClass.GPU_HEAVY else None,
                })
                if error.retryable and task.attempt_count < max_attempts:
                    delay_index = min(task.attempt_count - 1, len(self.retry_policy.backoff_seconds) - 1)
                    self.sleep(self.retry_policy.backoff_seconds[delay_index])
                    continue
                task.status = ProductionTaskStatus.FAILED
                task.finished_at = production_now()
                return

    def _default_preflight(self, task: ProductionTask) -> None:
        guard = ResourceGuard(self.resources).check(
            self.artifacts.root,
            gpu_heavy=task.resource_class == ResourceClass.GPU_HEAVY,
        )
        if guard.status == "blocked":
            raise ProductionFailure(
                "; ".join(guard.reasons),
                code="RESOURCE_EXHAUSTED",
                category=FailureCategory.RESOURCE,
                retryable=True,
            )

    @staticmethod
    def _map_failure(error: Exception) -> ProductionFailure:
        if isinstance(error, ProductionFailure):
            return error
        if ResourceManager.is_oom_error(error):
            return ProductionFailure(
                str(error), code="RESOURCE_EXHAUSTED", category=FailureCategory.RESOURCE, retryable=True
            )
        if isinstance(error, TimeoutError):
            return ProductionFailure(
                str(error), code="TIMEOUT", category=FailureCategory.TRANSIENT, retryable=True
            )
        return ProductionFailure(
            str(error), code="EXECUTION_FAILURE", category=FailureCategory.PERMANENT_VALIDATION, retryable=False
        )


class CreatorProductionIntegrator:
    def __init__(self, store: CreatorJobStore) -> None:
        self.store = store

    def apply(
        self,
        job_id: str,
        *,
        creator_plan: CreatorPlan,
        production_plan: ProductionPlan,
        artifacts: Iterable[ProductionArtifact],
    ) -> CreatorJob:
        if creator_plan.job_id != job_id or production_plan.job_id != job_id:
            raise ValueError("production artifacts must remain bound to CreatorJob.job_id")
        items = list(artifacts)
        if any(item.job_id != job_id or item.status != ArtifactStatus.VALID for item in items):
            raise ValueError("CreatorJob integration requires VALID artifacts for the same job")
        video = next(
            (item.path for item in reversed(items) if item.artifact_type in {"VIDEO", "COMPOSITE"}),
            None,
        )
        thumbnail = next((item.path for item in reversed(items) if item.artifact_type == "THUMBNAIL"), None)
        changes: dict[str, object] = {
            "creator_plan": creator_plan,
            "script": creator_plan.script,
            "title_candidates": creator_plan.title_candidates,
            "selected_title": creator_plan.preferred_title,
            "description": creator_plan.description_draft,
            "tags": creator_plan.tags,
            "visual_plan": {
                "direction": creator_plan.visual_direction,
                "scenes": creator_plan.visual_scenes,
                "production_id": production_plan.production_id,
            },
            "audio_plan": {
                "voice_direction": creator_plan.voice_direction,
                "audio_direction": creator_plan.audio_direction,
                "production_id": production_plan.production_id,
            },
        }
        if video is not None:
            changes["video_path"] = video
        if thumbnail is not None:
            changes["thumbnail_path"] = thumbnail
        return self.store.update(
            job_id,
            changes,
            reason="Alpha22 Step 3 production artifacts",
            updated_by="system:production_orchestrator",
        )
