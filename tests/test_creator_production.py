from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from PIL import Image
from pydantic import ValidationError

from alysia.core.config import H3VisualConfig
from alysia.core.resources import ResourceManager
from alysia.creator import (
    AdapterResult,
    ApprovalStatus,
    ArtifactStatus,
    ClaimClassification,
    ComfyUIProductionAdapter,
    CreatorClaimTrace,
    CreatorJob,
    CreatorJobStore,
    CreatorPlanBuilder,
    CreatorProductionIntegrator,
    CreatorScriptSection,
    EvidenceStatus,
    FailureCategory,
    H3ProductionAdapter,
    ProductionAdapter,
    ProductionArtifactRegistry,
    ProductionFailure,
    ProductionOrchestrator,
    ProductionPlanner,
    ProductionPlanStore,
    ProductionStatus,
    ProductionTask,
    ProductionTaskStatus,
    ProductionTaskType,
    PublishStatus,
    ResearchSourceTrace,
    ResourceClass,
    RetryPolicy,
)
from alysia.schemas.visual import SceneVisualPlan, VisualGenerationJob, VisualGenerationResult


def make_job(*, grounded: bool = True, uncertain: bool = False) -> CreatorJob:
    now = datetime.now().astimezone()
    claims = []
    if grounded:
        claims.append(
            CreatorClaimTrace(
                claim_id="claim_grounded",
                claim="A grounded fact.",
                classification=ClaimClassification.VERIFIED_FACT,
                confidence=0.8,
                source_refs=["source_grounded"],
                evidence_status=EvidenceStatus.SUPPORTED,
            )
        )
    if uncertain:
        claims.append(
            CreatorClaimTrace(
                claim_id="claim_uncertain",
                claim="A disputed result.",
                classification=ClaimClassification.UNKNOWN,
                confidence=0.3,
                source_refs=["source_grounded"],
                evidence_status=EvidenceStatus.CONFLICTING,
            )
        )
    return CreatorJob.new(
        created_at=now,
        updated_at=now,
        topic="Grounded production orchestration",
        topic_source="research",
        topic_score=80,
        research_sources=[
            ResearchSourceTrace(
                source_id="source_grounded",
                source="https://example.com/source",
                retrieved_at=now,
                claim="Grounded evidence",
                confidence=0.9,
                source_type="web",
            )
        ],
        claims=claims,
        uncertainties=["measurement scope remains uncertain"] if uncertain else [],
    )


def make_creator_plan(job: CreatorJob):
    section = CreatorScriptSection(
        section_id="section_1",
        purpose="Explain the grounded fact",
        text="The source documents the behavior.",
        factual=True,
        claim_refs=["claim_grounded"],
    )
    return CreatorPlanBuilder().create(
        job,
        hook="Start with the failure mode.",
        core_message="Production must be recoverable.",
        target_audience="AI builders",
        sections=[section],
        visual_direction="Clear technical diagrams",
        visual_scenes=[{"scene_id": "scene_1", "claim_refs": ["claim_grounded"]}],
        voice_direction="Calm narration",
        audio_direction="No generated ambience",
        thumbnail_concept="TEST production DAG",
        title_candidates=["Recoverable production"],
        preferred_title="Recoverable production",
        description_draft="Grounded production test.",
        tags=["Alysia", "Production"],
        production_requirements={"gpu_heavy_concurrency": 1},
    )


def make_tasks() -> list[ProductionTask]:
    return [
        ProductionTask(
            task_id="voice",
            task_type=ProductionTaskType.VOICE,
            resource_class=ResourceClass.CPU_LIGHT,
        ),
        ProductionTask(
            task_id="visual",
            task_type=ProductionTaskType.IMAGE,
            resource_class=ResourceClass.GPU_HEAVY,
        ),
        ProductionTask(
            task_id="composite",
            task_type=ProductionTaskType.COMPOSITE,
            depends_on=["voice", "visual"],
            resource_class=ResourceClass.CPU_HEAVY,
        ),
    ]


class FakeAdapter(ProductionAdapter):
    adapter_id = "fake"

    def __init__(self, events: list[str], failures: list[ProductionFailure] | None = None) -> None:
        self.events = events
        self.failures = list(failures or [])
        self.calls = 0
        self.cleanup_calls = 0

    def execute(self, task: ProductionTask, output_dir: Path) -> AdapterResult:
        self.calls += 1
        self.events.append(task.task_id)
        if self.failures:
            raise self.failures.pop(0)
        path = output_dir / f"{task.task_id}.txt"
        path.write_text(f"TEST artifact call={self.calls}", encoding="utf-8")
        return AdapterResult(output_paths=[path], artifact_type=task.task_type.value)

    def cleanup(self) -> None:
        self.cleanup_calls += 1


def make_orchestrator(
    tmp_path: Path,
    adapters: dict[ProductionTaskType, ProductionAdapter],
    *,
    resources: ResourceManager | None = None,
) -> tuple[ProductionOrchestrator, ProductionPlanStore, ProductionArtifactRegistry]:
    plan_store = ProductionPlanStore(tmp_path / "production_plans")
    artifacts = ProductionArtifactRegistry(tmp_path / "production_artifacts")
    orchestrator = ProductionOrchestrator(
        adapters=adapters,
        store=plan_store,
        artifacts=artifacts,
        resources=resources,
        retry_policy=RetryPolicy(max_attempts=3, backoff_seconds=[0, 0, 0]),
        preflight=lambda task: None,
        sleep=lambda seconds: None,
    )
    return orchestrator, plan_store, artifacts


def test_creator_plan_is_bound_and_retains_grounding_and_uncertainties() -> None:
    job = make_job(uncertain=True)
    plan = make_creator_plan(job)

    assert plan.job_id == job.job_id
    assert plan.revision == job.current_revision
    assert plan.research_refs == ["source_grounded"]
    assert plan.claim_refs == ["claim_grounded", "claim_uncertain"]
    assert "claim_uncertain" in plan.uncertainty_refs
    assert "measurement scope remains uncertain" in plan.uncertainty_refs
    assert plan.script_sections[0].claim_refs == ["claim_grounded"]


def test_creator_plan_requires_grounding_or_explicit_creative_only() -> None:
    job = make_job(grounded=False)

    with pytest.raises(ValueError, match="grounded claims"):
        make_creator_plan(job)

    creative = CreatorPlanBuilder().create(
        job,
        hook="Imagine a fictional scene.",
        core_message="Creative-only test.",
        target_audience="Viewers",
        sections=[CreatorScriptSection(
            section_id="creative",
            purpose="Fiction",
            text="Imagine a machine dreaming.",
        )],
        visual_direction="Abstract",
        visual_scenes=[],
        voice_direction="Narrative",
        audio_direction="Quiet",
        thumbnail_concept="TEST",
        title_candidates=["A machine dreams"],
        preferred_title="A machine dreams",
        description_draft="Creative-only.",
        tags=["fiction"],
        creative_only=True,
    )
    assert creative.job_id == job.job_id


def test_factual_script_section_requires_claim_refs() -> None:
    with pytest.raises(ValidationError, match="requires claim_refs"):
        CreatorScriptSection(
            section_id="fact",
            purpose="State a fact",
            text="A factual sentence.",
            factual=True,
        )


def test_production_plan_validates_dag_and_dependency_order(tmp_path: Path) -> None:
    creator_plan = make_creator_plan(make_job())
    plan = ProductionPlanner().build(creator_plan, make_tasks())
    events: list[str] = []
    fake = FakeAdapter(events)
    orchestrator, plan_store, _ = make_orchestrator(
        tmp_path,
        {task_type: fake for task_type in ProductionTaskType},
    )

    completed = orchestrator.start(plan)

    assert completed.status == ProductionStatus.SUCCEEDED
    assert events.index("composite") > events.index("voice")
    assert events.index("composite") > events.index("visual")
    assert plan_store.load(plan.production_id).status == ProductionStatus.SUCCEEDED
    assert all(task.output_refs for task in completed.tasks)


def test_dependency_cycle_is_rejected() -> None:
    creator_plan = make_creator_plan(make_job())
    tasks = [
        ProductionTask(task_id="a", task_type=ProductionTaskType.VOICE, depends_on=["b"]),
        ProductionTask(task_id="b", task_type=ProductionTaskType.IMAGE, depends_on=["a"]),
    ]

    with pytest.raises(ValidationError, match="cycle"):
        ProductionPlanner().build(creator_plan, tasks)


def test_failed_upstream_blocks_downstream(tmp_path: Path) -> None:
    creator_plan = make_creator_plan(make_job())
    plan = ProductionPlanner().build(creator_plan, [
        ProductionTask(task_id="voice", task_type=ProductionTaskType.VOICE, max_attempts=3),
        ProductionTask(
            task_id="composite",
            task_type=ProductionTaskType.COMPOSITE,
            depends_on=["voice"],
        ),
    ])
    permanent = ProductionFailure(
        "invalid voice request",
        code="INVALID_REQUEST",
        category=FailureCategory.PERMANENT_VALIDATION,
        retryable=False,
    )
    failing = FakeAdapter([], [permanent])
    downstream = FakeAdapter([])
    orchestrator, _, _ = make_orchestrator(
        tmp_path,
        {ProductionTaskType.VOICE: failing, ProductionTaskType.COMPOSITE: downstream},
    )

    completed = orchestrator.start(plan)

    assert completed.task("voice").status == ProductionTaskStatus.FAILED
    assert completed.task("voice").attempt_count == 1
    assert completed.task("composite").status == ProductionTaskStatus.BLOCKED
    assert downstream.calls == 0


def test_resume_skips_valid_success_and_force_regenerate_reruns(tmp_path: Path) -> None:
    job = make_job()
    creator_plan = make_creator_plan(job)
    plan = ProductionPlanner().build(creator_plan, [
        ProductionTask(task_id="voice", task_type=ProductionTaskType.VOICE),
    ])
    fake = FakeAdapter([])
    orchestrator, _, _ = make_orchestrator(tmp_path, {ProductionTaskType.VOICE: fake})

    first = orchestrator.start(plan)
    resumed = orchestrator.resume(first.production_id)
    forced = orchestrator.resume(first.production_id, force_regenerate=["voice"])

    assert resumed.status == ProductionStatus.SUCCEEDED
    assert fake.calls == 2
    assert forced.task("voice").attempt_count == 1


def test_retryable_failure_retries_within_budget(tmp_path: Path) -> None:
    plan = ProductionPlanner().build(make_creator_plan(make_job()), [
        ProductionTask(task_id="voice", task_type=ProductionTaskType.VOICE, max_attempts=3),
    ])
    transient = ProductionFailure(
        "temporary timeout",
        code="TIMEOUT",
        category=FailureCategory.TRANSIENT,
        retryable=True,
    )
    fake = FakeAdapter([], [transient])
    orchestrator, _, _ = make_orchestrator(tmp_path, {ProductionTaskType.VOICE: fake})

    completed = orchestrator.start(plan)

    assert completed.status == ProductionStatus.SUCCEEDED
    assert completed.task("voice").attempt_count == 2
    assert fake.calls == 2


def test_cancel_persists_cancelled_state(tmp_path: Path) -> None:
    plan = ProductionPlanner().build(make_creator_plan(make_job()), [
        ProductionTask(task_id="voice", task_type=ProductionTaskType.VOICE),
    ])
    fake = FakeAdapter([])
    orchestrator, plan_store, _ = make_orchestrator(tmp_path, {ProductionTaskType.VOICE: fake})
    plan_store.save(plan)

    cancelled = orchestrator.cancel(plan.production_id)

    assert cancelled.status == ProductionStatus.CANCELLED
    assert cancelled.task("voice").status == ProductionTaskStatus.CANCELLED
    assert orchestrator.status(plan.production_id).status == ProductionStatus.CANCELLED


def test_artifact_validation_and_path_safety(tmp_path: Path) -> None:
    registry = ProductionArtifactRegistry(tmp_path / "artifacts")
    task_dir = registry.task_dir("creator_1234", "task")
    valid = task_dir / "valid.txt"
    empty = task_dir / "empty.txt"
    invalid = task_dir / "invalid.json"
    missing = task_dir / "missing.txt"
    valid.write_text("TEST artifact", encoding="utf-8")
    empty.write_bytes(b"")
    invalid.write_text("{not json", encoding="utf-8")

    assert registry.register(job_id="creator_1234", task_id="task", artifact_type="TEXT", path=valid).status == ArtifactStatus.VALID
    assert registry.register(job_id="creator_1234", task_id="task", artifact_type="TEXT", path=empty).status == ArtifactStatus.PARTIAL
    assert registry.register(job_id="creator_1234", task_id="task", artifact_type="JSON", path=invalid).status == ArtifactStatus.INVALID
    assert registry.register(job_id="creator_1234", task_id="task", artifact_type="TEXT", path=missing).status == ArtifactStatus.MISSING
    with pytest.raises(ValueError, match="artifact root"):
        registry.register(
            job_id="creator_1234",
            task_id="task",
            artifact_type="TEXT",
            path=tmp_path / "outside.txt",
        )


def test_gpu_heavy_lock_is_deterministic_and_released() -> None:
    resources = ResourceManager(sequential_gpu=True)
    resources.acquire("h3", gpu_heavy=True, timeout_sec=0)
    with pytest.raises(RuntimeError, match="资源阶段冲突"):
        resources.acquire("comfyui", gpu_heavy=True, timeout_sec=0)
    resources.release("h3", gpu_heavy=True)

    resources.acquire("comfyui", gpu_heavy=True, timeout_sec=0)
    resources.release("comfyui", gpu_heavy=True)
    assert resources.current_gpu_phase is None


@pytest.mark.parametrize("should_fail", [False, True])
def test_gpu_lock_releases_after_success_or_failure(tmp_path: Path, should_fail: bool) -> None:
    resources = ResourceManager(sequential_gpu=True)
    failures = []
    if should_fail:
        failures.append(ProductionFailure(
            "CUDA out of memory",
            code="RESOURCE_EXHAUSTED",
            category=FailureCategory.RESOURCE,
            retryable=True,
        ))
    fake = FakeAdapter([], failures)
    task = ProductionTask(
        task_id="visual",
        task_type=ProductionTaskType.IMAGE,
        resource_class=ResourceClass.GPU_HEAVY,
        max_attempts=1,
    )
    plan = ProductionPlanner().build(make_creator_plan(make_job()), [task])
    orchestrator, _, _ = make_orchestrator(
        tmp_path,
        {ProductionTaskType.IMAGE: fake},
        resources=resources,
    )

    completed = orchestrator.start(plan)

    assert resources.current_gpu_phase is None
    resources.acquire("after", gpu_heavy=True, timeout_sec=0)
    resources.release("after", gpu_heavy=True)
    if should_fail:
        assert completed.status == ProductionStatus.FAILED
        assert completed.task("visual").metadata["failure_code"] == "RESOURCE_EXHAUSTED"
        assert ProductionPlanStore(tmp_path / "production_plans").load(plan.production_id).status == ProductionStatus.FAILED
    else:
        assert completed.status == ProductionStatus.SUCCEEDED


class ContractProvider:
    provider_id = "visual.contract"

    def __init__(self, output_root: Path, behavior: str = "success") -> None:
        self.output_root = output_root
        self.behavior = behavior
        self.cancelled = False
        self.unloaded = False

    def prepare_job(self, run_id: str, scene: SceneVisualPlan) -> VisualGenerationJob:
        now = datetime.now().astimezone()
        return VisualGenerationJob(
            job_id=f"visual_{run_id}",
            run_id=run_id,
            scene=scene,
            provider=self.provider_id,
            workflow_id="t2v",
            cache_key=f"cache_{run_id}",
            created_at=now,
            updated_at=now,
        )

    def load_workflow(self, workflow_id: str):
        return {
            "_alysia": {"api_format": True, "bindings": {}},
            "prompt": {"1": {"class_type": "TEST"}},
            "workflow_id": workflow_id,
        }

    def workflow_payload(self, job: VisualGenerationJob):
        return self.load_workflow(job.workflow_id)["prompt"]

    def generate(self, job: VisualGenerationJob) -> VisualGenerationResult:
        if self.behavior == "timeout":
            raise TimeoutError("provider timeout")
        if self.behavior == "oom":
            raise RuntimeError("CUDA out of memory")
        output = self.output_root / "contract.mp4"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"TEST-video")
        return VisualGenerationResult(
            job_id=job.job_id,
            scene_id=job.scene.scene_id,
            provider=self.provider_id,
            workflow_id=job.workflow_id,
            workflow_version="1",
            output_files=[output],
            duration_sec=job.scene.requested_duration_sec,
            resolution="TEST",
            generation_time_sec=0,
            status="completed",
            mock=True,
        )

    def cancel(self, job: VisualGenerationJob) -> None:
        self.cancelled = True

    def unload(self) -> None:
        self.unloaded = True


def visual_task() -> ProductionTask:
    return ProductionTask(
        task_id="visual_contract",
        task_type=ProductionTaskType.VIDEO,
        resource_class=ResourceClass.GPU_HEAVY,
        metadata={
            "scene": {
                "scene_id": "scene_contract",
                "generation_mode": "h3_t2v",
                "requested_duration_sec": 1,
                "prompt": {"subject": "TEST geometric shape"},
            }
        },
    )


def test_comfyui_and_h3_configuration_load_without_service_start(tmp_path: Path) -> None:
    workflow_dir = tmp_path / "workflows"
    workflow_dir.mkdir()
    comfy = ComfyUIProductionAdapter.from_config(
        base_url="http://127.0.0.1:8188",
        workflow_dir=workflow_dir,
        output_dir=tmp_path / "outputs",
        timeout_sec=1,
        job_timeout_sec=2,
    )
    h3_config = H3VisualConfig(
        enabled=True,
        workflow_dir=workflow_dir,
        comfyui_base_url="http://127.0.0.1:8188",
    )
    h3 = H3ProductionAdapter.from_config(h3_config, output_dir=tmp_path / "h3_outputs")

    assert comfy.provider.workflow_dir == workflow_dir.resolve()
    assert comfy.provider.timeout_sec == 1
    assert h3.provider.config is h3_config
    assert h3.provider.base_url == "http://127.0.0.1:8188"


def test_visual_adapter_validates_request_and_maps_timeout_and_oom(tmp_path: Path) -> None:
    missing = ComfyUIProductionAdapter(ContractProvider(tmp_path))
    with pytest.raises(ProductionFailure) as invalid:
        missing.execute(ProductionTask(task_id="bad", task_type=ProductionTaskType.VIDEO), tmp_path)
    assert invalid.value.category == FailureCategory.PERMANENT_VALIDATION

    for behavior, code, category in [
        ("timeout", "TIMEOUT", FailureCategory.TRANSIENT),
        ("oom", "RESOURCE_EXHAUSTED", FailureCategory.RESOURCE),
    ]:
        adapter = ComfyUIProductionAdapter(ContractProvider(tmp_path, behavior))
        with pytest.raises(ProductionFailure) as failure:
            adapter.execute(visual_task(), tmp_path)
        assert failure.value.code == code
        assert failure.value.category == category
        assert failure.value.retryable


def test_visual_adapter_parses_artifact_without_persisting_workflow_json(tmp_path: Path) -> None:
    adapter = ComfyUIProductionAdapter(ContractProvider(tmp_path))

    result = adapter.execute(visual_task(), tmp_path)

    assert result.output_paths[0].is_file()
    assert result.metadata["workflow_ref"] == "t2v"
    assert len(result.metadata["workflow_hash"]) == 64
    assert "prompt" not in result.metadata


def test_creator_job_integration_updates_revision_without_approval(tmp_path: Path) -> None:
    job_store = CreatorJobStore(tmp_path / "creator_jobs")
    job = make_job()
    job_store.create(job)
    creator_plan = make_creator_plan(job)
    production_plan = ProductionPlanner().build(creator_plan, [
        ProductionTask(task_id="video", task_type=ProductionTaskType.VIDEO),
        ProductionTask(task_id="thumbnail", task_type=ProductionTaskType.THUMBNAIL),
    ])
    registry = ProductionArtifactRegistry(tmp_path / "artifacts", probe_media=False)
    video = registry.task_dir(job.job_id, "video") / "video.mp4"
    thumbnail = registry.task_dir(job.job_id, "thumbnail") / "thumbnail.png"
    video.write_bytes(b"TEST-video")
    Image.new("RGB", (2, 2), "white").save(thumbnail)
    manifests = [
        registry.register(job_id=job.job_id, task_id="video", artifact_type="VIDEO", path=video),
        registry.register(job_id=job.job_id, task_id="thumbnail", artifact_type="THUMBNAIL", path=thumbnail),
    ]

    updated = CreatorProductionIntegrator(job_store).apply(
        job.job_id,
        creator_plan=creator_plan,
        production_plan=production_plan,
        artifacts=manifests,
    )

    assert updated.current_revision == 2
    assert updated.video_path == video.resolve()
    assert updated.thumbnail_path == thumbnail.resolve()
    assert updated.script == creator_plan.script
    assert updated.approval_status == ApprovalStatus.DRAFT
    assert updated.publish_status == PublishStatus.NOT_READY
    assert job_store.revision_path(job.job_id, 1).is_file()
