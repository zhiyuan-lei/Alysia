from pathlib import Path

import httpx
import pytest

from alysia.core.config import H3VisualConfig, load_config
from alysia.core.resources import ResourceManager
from alysia.creator.production import H3ProductionAdapter, ProductionFailure
from alysia.providers.visual.h3 import MiniMaxH3LocalProvider
from alysia.reliability.resources import ResourceGuard
from alysia.schemas.visual import SceneVisualPlan
from tests.test_creator_production import visual_task
from alysia.production.router import ProviderRouter
from alysia.schemas.production import ProductionConstraints, ProviderCapability


class Resources:
    def __init__(self, snapshot):
        self.snapshot = snapshot

    def probe_vram(self):
        return self.snapshot

    def probe_ram(self):
        return {"available_mb": 16384}


@pytest.mark.parametrize(
    "peak,snapshot,blocked",
    [
        (7678, {"total_mb": 8188, "used_mb": 1000, "free_mb": 7188}, True),
        (None, {"total_mb": 8188, "used_mb": 1000, "free_mb": 7188}, True),
        ("4096", {"total_mb": 8188, "used_mb": 1000, "free_mb": 7188}, True),
        (4096, None, True),
        (4096, {"free_mb": 7188}, True),
        (6144, {"total_mb": 8188, "used_mb": 1, "free_mb": 8187}, True),
        (5144, {"total_mb": 8188, "used_mb": 1000, "free_mb": 7188}, False),
        (5145, {"total_mb": 8188, "used_mb": 1000, "free_mb": 7188}, True),
        (4096, {"total_mb": 4500, "used_mb": 0, "free_mb": 4500}, True),
    ],
)
def test_gpu_admission_budget(tmp_path, peak, snapshot, blocked):
    result = ResourceGuard(Resources(snapshot), min_disk_free_gb=0).check(
        tmp_path, gpu_heavy=True, estimated_peak_vram_mb=peak, require_vram_budget=True,
    )
    assert (result.status == "blocked") is blocked


def test_budget_cannot_be_relaxed_by_legacy_override(tmp_path):
    result = ResourceGuard(
        Resources({"total_mb": 8188, "used_mb": 0, "free_mb": 8188}),
        max_task_vram_mb=7600, min_disk_free_gb=0,
    ).check(tmp_path, gpu_heavy=True, estimated_peak_vram_mb=7000, require_vram_budget=True)
    assert result.status == "blocked"
    assert result.thresholds["max_task_vram_mb"] == 6144


@pytest.mark.parametrize("peak", [7678, None])
def test_real_h3_adapter_rejects_before_network(tmp_path, monkeypatch, peak):
    monkeypatch.setattr(ResourceManager, "probe_vram", staticmethod(
        lambda: {"total_mb": 8188, "used_mb": 1000, "free_mb": 7188}
    ))
    monkeypatch.setattr(ResourceManager, "probe_ram", staticmethod(lambda: {"available_mb": 16384}))
    def unexpected_network(*args, **kwargs):
        pytest.fail("Blocked H3 must not access the ComfyUI queue or submit a prompt")
    monkeypatch.setattr(httpx, "post", unexpected_network)
    monkeypatch.setattr(httpx, "get", unexpected_network)
    adapter = H3ProductionAdapter.from_config(
        H3VisualConfig(workflow_dir=Path("workflows/comfyui/h3"), measured_peak_vram_mb=peak),
        output_dir=tmp_path,
    )
    with pytest.raises(ProductionFailure, match="GPU_BUDGET_BLOCKED") as error:
        adapter.execute(visual_task(), tmp_path)
    assert error.value.retryable is False
    assert error.value.code == "GPU_BUDGET_BLOCKED"


@pytest.mark.parametrize("queue_state,allowed", [
    ({"queue_running": [], "queue_pending": []}, True),
    ({"queue_running": [[1]], "queue_pending": []}, False),
    ({"queue_running": [], "queue_pending": [[1]]}, False),
    ({}, False),
])
def test_submit_only_to_empty_queue(tmp_path, monkeypatch, queue_state, allowed):
    monkeypatch.setattr(ResourceManager, "probe_vram", staticmethod(
        lambda: {"total_mb": 8188, "used_mb": 1000, "free_mb": 7188}
    ))
    monkeypatch.setattr(ResourceManager, "probe_ram", staticmethod(lambda: {"available_mb": 16384}))
    posts = []
    monkeypatch.setattr(httpx, "get", lambda *a, **kw: httpx.Response(
        200, json=queue_state, request=httpx.Request("GET", "http://localhost/queue"),
    ))
    def post(url, **kwargs):
        posts.append(url)
        return httpx.Response(200, json={"prompt_id": "test"}, request=httpx.Request("POST", url))
    monkeypatch.setattr(httpx, "post", post)
    provider = MiniMaxH3LocalProvider(
        H3VisualConfig(measured_peak_vram_mb=4096), output_dir=tmp_path,
    )
    job = provider.prepare_job("budget_test", SceneVisualPlan(
        scene_id="test", generation_mode="h3_t2v", requested_duration_sec=1,
        prompt={"subject": "TEST geometric shape"},
    ))
    if allowed:
        assert provider.submit(job) == "test"
        assert len(posts) == 1
    else:
        with pytest.raises(ValueError, match="GPU_BUDGET_BLOCKED"):
            provider.submit(job)
        assert posts == []


def test_current_config_retains_h3_measurement_and_ram_budget():
    config = load_config(Path("config.example.yaml"))
    assert config.production.max_local_vram_mb == 6144
    assert config.hardware_profile.ram_gb == 24
    assert config.visual_generation.h3.measured_peak_vram_mb == 7678


@pytest.mark.parametrize("peak", [None, 7000])
def test_planner_rejects_unknown_or_over_budget_local_gpu(peak):
    capability = ProviderCapability(
        provider_id="test.local.gpu", task_types=["tts"], local_or_cloud="local",
        gpu_heavy=True, estimated_vram_mb=peak, health_status="healthy",
    )
    assert ProviderRouter._exclusion_reason(
        capability, ProductionConstraints(max_local_vram_mb=7600),
    ) is not None
