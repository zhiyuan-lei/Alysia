from __future__ import annotations

import json
import threading
import time
from datetime import datetime
from pathlib import Path

import pytest

from alysia.core.resources import ResourceManager
from alysia.core.run import RunManager
from alysia.production import ProductionService
from alysia.production.registry import ProviderCapabilityRegistry, SystemDoctorSnapshot
from alysia.providers.visual import (
    ComfyUIProvider,
    MockVisualGenerationProvider,
    VisualProviderRegistry,
)
from alysia.schemas import (
    AudioManifest,
    AudioScene,
    Scene,
    Storyboard,
    SubtitleDocument,
    SubtitleSegment,
    VisualIdentity,
    VisualType,
)
from alysia.schemas.visual import SceneVisualPlan, VisualAssetsManifest
from alysia.visual import H3VisualPromptBuilder, VisualGenerationService, VisualJobQueue, VisualPlanner, VisualQA
from alysia.workers.composition import CompositionWorker
from tests.helpers import make_config


@pytest.fixture(autouse=True)
def _stable_resource_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    """固定显存/内存快照，避免本机 GPU 占用让 H3 路由与 QA 断言随环境漂移。"""
    monkeypatch.setattr(
        ResourceManager, "probe_vram",
        staticmethod(lambda: {"total_mb": 8188, "used_mb": 512, "free_mb": 7676}),
    )
    monkeypatch.setattr(
        ResourceManager, "probe_ram",
        staticmethod(lambda: {"available_mb": 16384}),
    )


def _storyboard(dynamic: bool = True) -> Storyboard:
    return Storyboard(
        title="视觉测试", target_duration_sec=30,
        scenes=[
            Scene(id="s1", section_id="intro", duration_sec=10, narration="概念标题", visual_type=VisualType.TITLE),
            Scene(
                id="s2", section_id="body", duration_sec=10,
                narration="镜头缓慢推进，数据流动态穿过城市", visual_type=VisualType.IMAGE,
                visual_prompt="cinematic motion" if dynamic else "静态芯片插图",
            ),
            Scene(id="s3", section_id="end", duration_sec=10, narration="结论", visual_type=VisualType.DIAGRAM),
        ],
    )


def _identity() -> VisualIdentity:
    return VisualIdentity(
        color_theme={"accent": "#5BECFF"}, typography={"body": "Microsoft YaHei"},
        cover_layout="left", scene_preferences=["clean", "technology"],
    )


def _run_with_storyboard(tmp_path: Path):
    config = make_config(tmp_path / "runs")
    config.video.width = 320
    config.video.height = 240
    config.visual_generation.upscale = "none"
    config.visual_generation.queue_dir = tmp_path / "queue"
    manager = RunManager(config.runtime.runs_dir)
    state = manager.create("视觉测试", config.model_dump(mode="json"))
    manager.write_json(state.run_id, "storyboard.json", _storyboard().model_dump(mode="json"))
    state.artifacts["storyboard"] = "storyboard.json"
    manager.save(state)
    ProductionService(config).plan(state.run_id, requested_operation="full")
    return config, manager, state


def test_visual_provider_registry(tmp_path: Path) -> None:
    registry = VisualProviderRegistry([MockVisualGenerationProvider(tmp_path)])
    assert registry.get("visual.mock").provider_id == "visual.mock"
    with pytest.raises(ValueError):
        registry.register(MockVisualGenerationProvider(tmp_path))


def test_visual_scene_routing(tmp_path: Path) -> None:
    config = make_config(tmp_path / "runs")
    plan = VisualPlanner(config).plan("run", _storyboard(), None, _identity())
    assert [scene.generation_mode for scene in plan.scenes] == ["remotion", "h3_t2v", "remotion"]


def test_h3_budget_limit(tmp_path: Path) -> None:
    config = make_config(tmp_path / "runs")
    config.visual_generation.h3.max_clips_per_video = 0
    plan = VisualPlanner(config).plan("run", _storyboard(), None, _identity())
    assert plan.used_h3_clips == 0
    assert not any(scene.generation_mode.startswith("h3_") for scene in plan.scenes)


def test_h3_machine_budget_defaults(tmp_path: Path) -> None:
    config = make_config(tmp_path / "runs")
    assert config.hardware_profile.ram_gb == 24
    assert config.hardware_profile.vram_mb == 8192
    assert config.visual_generation.h3.standard_max_clips == 3
    assert config.visual_generation.h3.standard_max_generated_seconds == 18


def test_h3_job_queue_serial(tmp_path: Path) -> None:
    provider = MockVisualGenerationProvider(tmp_path / "runs")
    scene = VisualPlanner(make_config(tmp_path / "config-runs")).plan("run", _storyboard(), None, _identity()).scenes[1]
    first = provider.prepare_job("run", scene)
    second = first.model_copy(update={"job_id": "vjob_second", "cache_key": "second"})
    queue = VisualJobQueue(tmp_path / "queue", ResourceManager())
    queue.enqueue(first)
    queue.enqueue(second)
    queue._running_job_id = first.job_id
    with pytest.raises(RuntimeError, match="正在运行"):
        queue.run(second.job_id, provider)


def test_comfyui_workflow_injection_mock() -> None:
    template = {"_alysia": {"scene_id": "", "prompt": {}}}
    result = ComfyUIProvider.inject_parameters(template, {"_alysia.scene_id": "s1", "_alysia.prompt": {"subject": "AI"}})
    assert result["_alysia"]["scene_id"] == "s1"
    assert template["_alysia"]["scene_id"] == ""


def test_comfyui_api_workflow_binding(tmp_path: Path) -> None:
    workflow = {
        "_alysia": {
            "api_format": True,
            "defaults": {"width": 608, "height": 352, "steps": 6},
            "bindings": {
                "prompt": "4.inputs.prompt",
                "seed": "6.inputs.noise_seed",
                "length": "4.inputs.length",
            },
        },
        "prompt": {
            "4": {"class_type": "MiniMaxH3ImageToVideo", "inputs": {"prompt": "", "length": 73}},
            "6": {"class_type": "RandomNoise", "inputs": {"noise_seed": 0}},
        },
    }
    (tmp_path / "t2v.json").write_text(json.dumps(workflow), encoding="utf-8")
    provider = ComfyUIProvider(
        base_url="http://127.0.0.1:1",
        workflow_dir=tmp_path,
        output_dir=tmp_path,
    )
    scene = VisualPlanner(make_config(tmp_path / "runs")).plan(
        "run", _storyboard(), None, _identity()
    ).scenes[1]
    job = provider.prepare_job("run", scene)
    payload = provider.workflow_payload(job)
    assert "_alysia" not in payload
    assert payload["4"]["inputs"]["prompt"]
    assert payload["4"]["inputs"]["length"] == 192
    assert payload["6"]["inputs"]["noise_seed"] > 0


def test_visual_prompt_schema() -> None:
    prompt = H3VisualPromptBuilder().build(_storyboard().scenes[1], _identity())
    assert prompt.subject
    assert "no embedded captions" in prompt.negative_constraints


def test_visual_cache(tmp_path: Path) -> None:
    config, _, state = _run_with_storyboard(tmp_path)
    service = VisualGenerationService(config)
    first = service.generate(state.run_id, provider="mock")
    attempts = [job.attempts for job in service.queue.list(state.run_id)]
    second = service.generate(state.run_id, provider="mock")
    assert first == second
    assert [job.attempts for job in service.queue.list(state.run_id)] == attempts


def test_visual_qa(tmp_path: Path) -> None:
    config, _, state = _run_with_storyboard(tmp_path)
    service = VisualGenerationService(config)
    manifest = service.generate(state.run_id, provider="mock")
    generated = next(item for item in manifest.assets if item.generation_mode.startswith("h3_"))
    qa = json.loads((service.manager.run_dir(state.run_id) / "visual" / "qa" / f"{generated.scene_id}.json").read_text(encoding="utf-8"))
    assert qa["passed"] is True


def test_mock_visual_not_promoted(tmp_path: Path) -> None:
    config, _, state = _run_with_storyboard(tmp_path)
    manifest = VisualGenerationService(config).generate(state.run_id, provider="mock")
    assert manifest.production_review_eligible is False
    assert any(asset.mock and not asset.review_eligible for asset in manifest.assets)


def test_resource_manager_h3_exclusive() -> None:
    manager = ResourceManager()
    manager.acquire("visual:h3", gpu_heavy=True)
    with pytest.raises(RuntimeError, match="资源阶段冲突"):
        manager.acquire("tts", gpu_heavy=True)
    manager.release("visual:h3", gpu_heavy=True)


def test_editor_mixed_assets(tmp_path: Path) -> None:
    config, manager, state = _run_with_storyboard(tmp_path)
    service = VisualGenerationService(config)
    service.generate(state.run_id, provider="mock")
    audio = AudioManifest(
        sample_rate=24000, channels=1, sample_width_bytes=2,
        narration_file="audio/narration.wav", total_duration_sec=30,
        scenes=[
            AudioScene(index=1, scene_id="s1", original_text="概念", normalized_text="概念", file="a.wav", start_sec=0, end_sec=10, duration_sec=10, provider="mock", input_hash="12345678"),
            AudioScene(index=2, scene_id="s2", original_text="动态", normalized_text="动态", file="b.wav", start_sec=10, end_sec=20, duration_sec=10, provider="mock", input_hash="12345679"),
            AudioScene(index=3, scene_id="s3", original_text="结论", normalized_text="结论", file="c.wav", start_sec=20, end_sec=30, duration_sec=10, provider="mock", input_hash="12345670"),
        ],
    )
    composition = CompositionWorker(manager, config.video, config.subtitle).run(
        state, _storyboard(), audio, SubtitleDocument(
            total_duration_sec=30, source="deterministic",
            segments=[SubtitleSegment(id=1, scene_id="s1", start_sec=0, end_sec=2, text="概念")],
        )
    )
    mixed = next(scene for scene in composition.scenes if scene.id == "s2")
    assert mixed.visual["video_asset_path"].endswith(".mp4")
    assert mixed.visual["discard_source_audio"] is True


def test_production_plan_h3_constraints(tmp_path: Path) -> None:
    config = make_config(tmp_path / "runs")
    config.visual_generation.h3.comfyui_dir = tmp_path / "missing-comfy"
    config.visual_generation.h3.model_path = tmp_path / "missing-model"
    registry = ProviderCapabilityRegistry.default(config, SystemDoctorSnapshot())
    assert registry.get("visual.comfyui-h3").gpu_heavy is True
    assert registry.get("visual.comfyui-h3").expected_latency_class == "high"
    assert registry.get("visual.comfyui-h3").health_status == "unavailable"


def test_visual_resume_idempotent(tmp_path: Path) -> None:
    config, _, state = _run_with_storyboard(tmp_path)
    first_service = VisualGenerationService(config)
    first = first_service.generate(state.run_id, provider="mock")
    second = VisualGenerationService(config).generate(state.run_id, provider="mock")
    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert len(first_service.queue.list(state.run_id)) == 1
