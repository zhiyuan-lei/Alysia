from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest
import yaml

from alysia.core.config import AlysiaConfig, OptimizationConfig
from alysia.core.resources import ResourceManager
from alysia.core.run import RunManager
from alysia.planning import CreatorLoop
from alysia.production import (
    CostEstimator,
    ExecutionMetricsStore,
    ProductionCache,
    ProductionExecutor,
    ProductionPlanner,
    ProductionQualityGate,
    ProductionService,
    ProviderCapabilityRegistry,
    ProviderRouter,
    SystemDoctorSnapshot,
)
from alysia.schemas import (
    CostValue,
    ProductionConstraints,
    ProductionProfile,
    ProviderCapability,
    StageExecutionMetric,
)


def _capability(provider_id: str, task: str, **overrides) -> ProviderCapability:
    payload = {
        "provider_id": provider_id,
        "task_types": [task],
        "local_or_cloud": "local",
        "estimated_vram_mb": 0,
        "supports_unload": False,
        "expected_latency_class": "medium",
        "expected_quality_class": "medium",
        "monetary_cost_class": "unknown",
        "health_status": "healthy",
    }
    payload.update(overrides)
    return ProviderCapability.model_validate(payload)


def _registry() -> ProviderCapabilityRegistry:
    return ProviderCapabilityRegistry(
        [
            _capability("research.mock", "research", local_or_cloud="mock", expected_quality_class="low"),
            _capability("llm.mock", "script", local_or_cloud="mock", expected_quality_class="low"),
            ProviderCapability.model_validate(
                {
                    **_capability("llm.ollama", "script").model_dump(),
                    "task_types": ["script", "storyboard"],
                    "gpu_heavy": True,
                    "supports_unload": True,
                    "estimated_vram_mb": None,
                }
            ),
            _capability(
                "llm.cloud",
                "script",
                local_or_cloud="cloud",
                requires_network=True,
                requires_credentials=True,
                expected_quality_class="high",
                health_status="healthy",
            ),
            _capability("llm.mock.storyboard", "storyboard", local_or_cloud="mock", expected_quality_class="low"),
            _capability("deterministic.text_qa", "text_qa"),
            _capability("tts.sapi", "tts"),
            _capability(
                "tts.cosyvoice",
                "tts",
                gpu_heavy=True,
                supports_unload=True,
                estimated_vram_mb=None,
                expected_quality_class="high",
            ),
            _capability("subtitle.deterministic", "subtitle_alignment"),
            _capability(
                "asr.faster-whisper",
                "subtitle_alignment",
                gpu_heavy=True,
                supports_unload=True,
                estimated_vram_mb=None,
                expected_quality_class="high",
            ),
            _capability("deterministic.audio_qa", "audio_qa"),
            _capability("render.remotion", "render", expected_quality_class="high"),
            _capability("render.mock", "render", local_or_cloud="mock", expected_quality_class="low"),
            _capability("deterministic.video_qa", "video_qa"),
            _capability("cover.template", "cover"),
            _capability("deterministic.metadata", "metadata"),
            _capability("deterministic.publish_qa", "publish_qa"),
        ]
    )


def test_production_constraints() -> None:
    constraints = ProductionConstraints()
    assert constraints.max_local_vram_mb == 6144
    assert constraints.sequential_gpu_required is True
    with pytest.raises(ValueError, match="allowlist"):
        ProductionConstraints(provider_allowlist=["llm.mock"], provider_denylist=["llm.mock"])


def test_provider_capability_registry() -> None:
    registry = _registry()
    assert registry.get("tts.sapi").local_or_cloud == "local"
    assert registry.for_task("render")
    assert len(registry.digest()) == 64


def test_production_plan_generation() -> None:
    planner = ProductionPlanner(_registry(), OptimizationConfig())
    plan = planner.generate(run_id="run_1", profile=ProductionProfile(), requested_operation="full")
    assert plan.execution_order[0] == "research"
    assert plan.execution_order[-1] == "publish_qa"
    assert plan.selected_provider_per_stage
    assert plan.alternatives


def test_offline_mode_excludes_cloud() -> None:
    router = ProviderRouter(_registry(), OptimizationConfig())
    candidates, warnings = router.rank("script", ProductionConstraints(offline_mode=True))
    assert all(item.local_or_cloud != "cloud" for item in candidates)
    assert any("offline_mode" in warning for warning in warnings)


def test_vram_budget_rejection() -> None:
    registry = ProviderCapabilityRegistry(
        [
            _capability("local.too_large", "tts", estimated_vram_mb=8000, gpu_heavy=True),
            _capability("local.safe", "tts", estimated_vram_mb=2000, gpu_heavy=True),
        ]
    )
    candidates, warnings = ProviderRouter(registry, OptimizationConfig()).rank(
        "tts", ProductionConstraints(max_local_vram_mb=7600)
    )
    assert [item.provider_id for item in candidates] == ["local.safe"]
    assert any("超过预算" in item for item in warnings)


def test_sequential_gpu_plan() -> None:
    registry = _registry()
    # This test exercises ordering of admitted tasks; unknown peaks are now blocked.
    registry.get("tts.cosyvoice").estimated_vram_mb = 2048
    registry.get("asr.faster-whisper").estimated_vram_mb = 2048
    plan = ProductionPlanner(registry, OptimizationConfig()).generate(
        run_id="run_gpu",
        profile=ProductionProfile(quality_target="high", sequential_gpu_required=True),
        requested_operation="audio",
    )
    gpu_stages = [stage.stage_id for stage in plan.stages if stage.gpu_heavy]
    assert gpu_stages == ["tts", "subtitle_alignment"]
    assert plan.execution_order.index("tts") < plan.execution_order.index("subtitle_alignment")
    assert any("串行" in reason for reason in plan.reasons)


def test_router_quality_profiles() -> None:
    registry = ProviderCapabilityRegistry(
        [
            _capability("llm.mock", "script", local_or_cloud="mock", expected_quality_class="low"),
            _capability("llm.ollama", "script", expected_quality_class="medium"),
            _capability(
                "llm.cloud",
                "script",
                local_or_cloud="cloud",
                expected_quality_class="high",
                requires_credentials=False,
            ),
        ]
    )
    router = ProviderRouter(registry, OptimizationConfig())
    draft, _ = router.rank("script", ProductionConstraints(quality_target="draft"))
    high, _ = router.rank("script", ProductionConstraints(quality_target="high"))
    assert draft[0].provider_id == "llm.mock"
    assert high[0].provider_id == "llm.cloud"


def test_fallback_recording(tmp_path: Path) -> None:
    registry = _registry()
    plan = ProductionPlanner(registry, OptimizationConfig()).generate(
        run_id="run_fallback",
        profile=ProductionProfile(quality_target="high"),
        requested_operation="video",
    )
    metrics = ExecutionMetricsStore(tmp_path, run_id=plan.run_id, plan_id=plan.plan_id)

    def fail(_: str) -> None:
        raise RuntimeError("renderer failed")

    handlers = {"render.remotion": fail, "render.mock": lambda _: "ok", "deterministic.video_qa": lambda _: "ok"}
    result = ProductionExecutor(registry, ResourceManager(), metrics).execute(plan, handlers)
    saved = metrics.load()
    assert result["render"] == "ok"
    assert saved.fallbacks[0].original_choice == "render.remotion"
    assert saved.fallbacks[0].fallback_choice == "render.mock"


def test_cache_key_stability(tmp_path: Path) -> None:
    cache = ProductionCache(tmp_path / "cache")
    first = cache.key(
        artifact_type="script", normalized_input={"b": 2, "a": 1}, provider_id="llm.mock", provider_version="1", config={"x": True}
    )
    second = cache.key(
        artifact_type="script", normalized_input={"a": 1, "b": 2}, provider_id="llm.mock", provider_version="1", config={"x": True}
    )
    assert first == second
    artifact = tmp_path / "script.json"
    artifact.write_text("{}", encoding="utf-8")
    for artifact_type in (
        "script",
        "storyboard",
        "scene_tts",
        "subtitle_alignment",
        "render_composition",
    ):
        entry = cache.put(
            artifact_type=artifact_type,
            normalized_input={"topic": "stable"},
            provider_id="llm.mock",
            provider_version="1",
            config={"kind": artifact_type},
            artifact_path=artifact,
        )
        assert cache.get(entry.cache_key) is not None


def test_research_cache_ttl(tmp_path: Path) -> None:
    artifact = tmp_path / "research.json"
    artifact.write_text("{}", encoding="utf-8")
    cache = ProductionCache(tmp_path / "cache")
    entry = cache.put(
        artifact_type="research",
        normalized_input={"topic": "AI"},
        provider_id="research.mock",
        provider_version=None,
        config={},
        artifact_path=artifact,
        ttl_hours=24,
    )
    assert cache.get(entry.cache_key, now=entry.created_at + timedelta(hours=23)) is not None
    assert cache.get(entry.cache_key, now=entry.created_at + timedelta(hours=25)) is None


def test_execution_metrics(tmp_path: Path) -> None:
    store = ExecutionMetricsStore(tmp_path, run_id="run_metrics", plan_id="plan_metrics")
    now = datetime.now().astimezone()
    store.record_stage(
        StageExecutionMetric(
            stage_id="script",
            start_time=now,
            end_time=now,
            elapsed_sec=0,
            provider="llm.mock",
            success=True,
            peak_vram_mb=None,
        )
    )
    assert store.load().stages[0].peak_vram_mb is None


def test_unknown_cost_not_fabricated() -> None:
    value = CostEstimator().estimate(_capability("local.model", "script", estimated_vram_mb=None))
    assert value.status == "unknown"
    assert value.amount is None
    with pytest.raises(ValueError):
        CostValue(status="unknown", amount=1)


def test_production_quality_gate(tmp_path: Path) -> None:
    config = AlysiaConfig.model_validate({"runtime": {"runs_dir": str(tmp_path / "runs")}})
    manager = RunManager(config.runtime.runs_dir)
    state = manager.create("QA topic", config.model_dump(mode="json"))
    state.text_pipeline_completed = True
    manager.save(state)
    service = ProductionService(config, registry=_registry(), snapshot=SystemDoctorSnapshot())
    standard = service.plan(state.run_id, requested_operation="text", quality_target="standard")
    assert ProductionQualityGate(manager).evaluate(state.run_id, standard).passed is False
    draft = service.plan(state.run_id, requested_operation="text", quality_target="draft")
    assert ProductionQualityGate(manager).evaluate(state.run_id, draft).passed is True


def test_creator_loop_production_plan_gate(tmp_path: Path) -> None:
    profile_path = tmp_path / "creator_profile.yaml"
    profile_path.write_text(
        yaml.safe_dump(
            {
                "creator_name": "Alysia",
                "channel_goal": "解释 AI",
                "primary_domains": ["人工智能"],
                "target_audience": "技术观众",
                "preferred_formats": ["科普"],
                "excluded_domains": ["违法活动"],
                "originality_requirements": "提供独立分析",
                "source_quality_requirements": "关键结论使用可追溯来源",
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    config = AlysiaConfig.model_validate(
        {
            "runtime": {"runs_dir": str(tmp_path / "runs")},
            "learning": {"memory_dir": str(tmp_path / "memory")},
            "planning": {"plans_dir": str(tmp_path / "plans"), "selected_count": 1},
            "creator": {"profile_file": str(profile_path)},
            "trends": {"provider": "mock", "workspace_dir": str(tmp_path / "trends")},
            "creator_loop": {"candidate_count": 3, "selected_count": 1},
            "production": {"offline_mode": True},
        }
    )
    loop = CreatorLoop(config)
    content_plan = loop.tick()
    _, run = loop.approve(content_plan.plan_id, content_plan.slots[0].id)
    assert (loop.run_manager.run_dir(run.run_id) / "production" / "production_plan.json").is_file()
    assert loop.run_manager.load(run.run_id).artifacts["production_plan"]


def test_optimizer_idempotent() -> None:
    planner = ProductionPlanner(_registry(), OptimizationConfig())
    profile = ProductionProfile(quality_target="standard")
    first = planner.generate(run_id="run_stable", profile=profile, requested_operation="full")
    second = planner.generate(run_id="run_stable", profile=profile, requested_operation="full")
    assert first.plan_id == second.plan_id
    assert first.selected_provider_per_stage == second.selected_provider_per_stage
    assert first.alternatives == second.alternatives
