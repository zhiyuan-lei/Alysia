from __future__ import annotations

from pathlib import Path
import hashlib
import json
from types import SimpleNamespace
import wave

import pytest
from fastapi.testclient import TestClient

from alysia.control import ControlCenterService, create_control_app
from alysia.local_creator import LocalCreationSpec, LocalCreatorService
from alysia.providers.visual.comfyui import ComfyUIProvider
from alysia.reliability.resources import GpuBudgetBlocked
from alysia.schemas.visual import H3VisualPrompt, SceneVisualPlan
from alysia.visual.jobs import build_visual_job
from alysia.schemas.audio import TTSResult
from tests.helpers import make_config


def spec(reference: Path) -> dict:
    return {"title": "自写提示词测试", "scenes": [{
        "scene_id": "scene_1", "backend": "h3_staged_i2v",
        "prompt": "人物眨眼", "narration": "大家好。", "reference_image": str(reference),
    }]}


def test_scene_requires_real_input_and_unique_id(tmp_path: Path):
    reference = tmp_path / "reference.png"
    reference.write_bytes(b"fixture")
    LocalCreationSpec.model_validate(spec(reference))
    with pytest.raises(ValueError, match="scene_id 必须唯一"):
        LocalCreationSpec.model_validate({"title": "test", "scenes": [spec(reference)["scenes"][0]] * 2})
    with pytest.raises(ValueError, match="reference_image"):
        LocalCreationSpec.model_validate(spec(tmp_path / "missing.png"))


def test_custom_comfyui_requires_measured_budget_and_video_output():
    scene = {"scene_id": "shot", "backend": "comfyui_api", "prompt": "make a clip",
             "narration": "hello", "workflow": {"_alysia": {"api_format": True,
             "bindings": {"prompt": "2.inputs.text"}},
             "prompt": {"1": {"class_type": "SaveVideo", "inputs": {}},
                        "2": {"class_type": "TextNode", "inputs": {"text": "placeholder"}}}}}
    with pytest.raises(ValueError, match="实测显存峰值"):
        LocalCreationSpec.model_validate({"title": "test", "scenes": [scene]})
    scene["workflow"]["_alysia"]["measured_peak_vram_mb"] = 6145
    with pytest.raises(ValueError, match="实测显存峰值"):
        LocalCreationSpec.model_validate({"title": "test", "scenes": [scene]})
    scene["workflow"]["_alysia"]["measured_peak_vram_mb"] = 500
    LocalCreationSpec.model_validate({"title": "test", "scenes": [scene]})
    scene["workflow"]["_alysia"]["bindings"]["prompt"] = "2.inputs.missing"
    with pytest.raises(ValueError, match="绑定"):
        LocalCreationSpec.model_validate({"title": "test", "scenes": [scene]})
    scene["workflow"]["_alysia"]["bindings"]["prompt"] = "2.inputs.text"
    scene["workflow"]["prompt"]["1"]["class_type"] = "SaveImage"
    with pytest.raises(ValueError, match="SaveVideo"):
        LocalCreationSpec.model_validate({"title": "test", "scenes": [scene]})


def test_comfyui_runtime_monitor_requests_interrupt_before_poll(tmp_path: Path, monkeypatch):
    provider = ComfyUIProvider(base_url="http://127.0.0.1:8188", workflow_dir=tmp_path,
                               output_dir=tmp_path, runtime_vram_stop_mib=7680,
                               runtime_ram_stop_mib=24576)
    job = SimpleNamespace(job_id="test", status="running")
    interrupted = []
    monkeypatch.setattr(provider, "submit", lambda _: "prompt-id")
    monkeypatch.setattr(provider, "cancel", lambda _: interrupted.append(True))
    monkeypatch.setattr("alysia.providers.visual.comfyui.ResourceManager.probe_vram",
                        lambda: {"used_mb": 7800})
    monkeypatch.setattr("alysia.providers.visual.comfyui.ResourceManager.probe_ram",
                        lambda: {"used_mb": 10000})
    with pytest.raises(GpuBudgetBlocked, match="已请求中断"):
        provider.generate(job)
    assert interrupted == [True]


def test_comfyui_binding_preserves_user_prompt(tmp_path: Path):
    workflow = {"_alysia": {"api_format": True, "bindings": {"prompt": "2.inputs.text"}},
                "prompt": {"2": {"class_type": "TextNode", "inputs": {"text": "placeholder"}}}}
    (tmp_path / "shot.json").write_text(json.dumps(workflow), encoding="utf-8")
    provider = ComfyUIProvider(base_url="http://127.0.0.1:8188", workflow_dir=tmp_path, output_dir=tmp_path)
    scene = SceneVisualPlan(scene_id="shot", generation_mode="h3_t2v", requested_duration_sec=1,
                            prompt=H3VisualPrompt(subject="user authored prompt", camera=""))
    job = build_visual_job("local_test", scene, provider.provider_id, "shot")
    assert provider.workflow_payload(job)["2"]["inputs"]["text"] == "user authored prompt"


def test_matching_h3_run_uses_unchanged_prompt_and_reference(tmp_path: Path):
    reference = tmp_path / "reference.png"
    reference.write_bytes(b"reference")
    scene = LocalCreationSpec.model_validate(spec(reference)).scenes[0]
    candidate = tmp_path / "wallpaper_20261002_000000_abcdef12"
    candidate.mkdir()
    (candidate / "job.json").write_text(json.dumps({
        "workflow_id": "dynamic_wallpaper",
        "prompt_sha256": hashlib.sha256(scene.prompt.encode("utf-8")).hexdigest(),
        "source_image_sha256": hashlib.sha256(reference.read_bytes()).hexdigest(),
    }), encoding="utf-8")
    assert LocalCreatorService._matching_h3_run(tmp_path, scene) == candidate
    reference.write_bytes(b"changed")
    assert LocalCreatorService._matching_h3_run(tmp_path, scene) is None


def test_local_creator_preserves_finished_clip_and_voice_on_resume(tmp_path: Path, monkeypatch):
    reference = tmp_path / "reference.png"
    reference.write_bytes(b"fixture")
    config = make_config(tmp_path / "runs")
    config.tts.provider = "sapi"
    service = LocalCreatorService(config, root=tmp_path / "local")
    job = service.submit(spec(reference))
    run_id = job["run_id"]
    calls = []

    def fake_h3(self, _image, _prompt, *, output_dir):
        calls.append("clip")
        source = output_dir / "h3.mp4"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(b"real-clip-fixture")
        return {"artifact": str(source), "run_dir": str(output_dir)}

    async def fake_sapi(self, request):
        calls.append("voice")
        with wave.open(str(request.output_path), "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(24000)
            output.writeframes(b"\0" * 4800)
        return TTSResult(wav_path=request.output_path, duration_sec=.1,
                         sample_rate=24000, channels=1, provider="sapi")

    def fake_edit(self, _run_id, _spec, _state):
        calls.append("edit")
        if len([item for item in calls if item == "edit"]) == 1:
            raise RuntimeError("simulated editor crash")
        video = self.final_video(run_id)
        video.parent.mkdir(parents=True, exist_ok=True)
        video.write_bytes(b"final-fixture")
        return 1.0

    monkeypatch.setattr("alysia.local_creator.DynamicWallpaperWorkflow.run", fake_h3)
    monkeypatch.setattr("alysia.local_creator.SapiTTSProvider.synthesize", fake_sapi)
    monkeypatch.setattr(LocalCreatorService, "_video_duration", lambda *_: 1.0)
    monkeypatch.setattr(LocalCreatorService, "_edit", fake_edit)
    monkeypatch.setattr("alysia.local_creator.VideoQAWorker.run", lambda *_: type("Q", (), {
        "passed": True, "model_dump": lambda self, **_: {"passed": True, "errors": []},
    })())
    assert service.run(run_id)["status"] == "FAILED"
    assert service.run(run_id)["status"] == "COMPLETE"
    assert calls == ["clip", "voice", "edit", "edit"]


def test_control_center_local_create_requires_csrf(tmp_path: Path, monkeypatch):
    reference = tmp_path / "reference.png"
    reference.write_bytes(b"fixture")
    config = make_config(tmp_path / "runs")
    control = ControlCenterService(config)
    client = TestClient(create_control_app(config, service=control, static_dir=tmp_path / "none"))
    token = client.get("/api/health").json()["csrf_token"]
    monkeypatch.setattr(control.local_creator, "start_background", control.local_creator.status)
    body = {"confirmed": True, "spec": spec(reference)}
    assert client.post("/api/local-create/jobs", json=body).status_code == 403
    created = client.post("/api/local-create/jobs", json=body, headers={"X-Alysia-CSRF": token})
    assert created.status_code == 200
    assert created.json()["status"] == "PENDING"
    run_id = created.json()["run_id"]
    assert client.get(f"/api/local-create/jobs/{run_id}").status_code == 200
    assert client.get(f"/api/local-create/jobs/{run_id}/video").status_code == 404
    video = control.local_creator.final_video(run_id)
    video.parent.mkdir(parents=True)
    video.write_bytes(b"tampered-video")
    state = control.local_creator.status(run_id)
    state["status"] = "COMPLETE"
    state["final_video"] = {"sha256": "0" * 64}
    control.local_creator._save(state)
    assert client.get(f"/api/local-create/jobs/{run_id}/video").status_code == 404
