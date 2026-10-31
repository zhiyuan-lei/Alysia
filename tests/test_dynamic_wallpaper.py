from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
from types import SimpleNamespace

from PIL import Image
import pytest

from alysia.core.config import AlysiaConfig
from alysia.reliability.resources import GpuBudgetBlocked
from alysia.visual import dynamic_wallpaper as wallpaper


class FakeResources:
    def __init__(self, used_vram: int = 1200, used_ram: int = 9000) -> None:
        self.used_vram = used_vram
        self.used_ram = used_ram

    def probe_vram(self) -> dict[str, int]:
        return {"total_mb": 8188, "used_mb": self.used_vram,
                "free_mb": 8188 - self.used_vram}

    def probe_ram(self) -> dict[str, int]:
        return {"total_mb": 32610, "used_mb": self.used_ram,
                "available_mb": 32610 - self.used_ram}

    @contextmanager
    def phase(self, *_args, **_kwargs):
        yield


def workflow(tmp_path: Path, *, used_vram: int = 1200, used_ram: int = 9000):
    config = AlysiaConfig()
    config.visual_generation.h3.comfyui_dir = tmp_path / "ComfyUI"
    return wallpaper.DynamicWallpaperWorkflow(
        config, resources=FakeResources(used_vram, used_ram),
    )


def test_preflight_rejects_projected_vram_and_ram(tmp_path: Path) -> None:
    high_vram = workflow(tmp_path, used_vram=1800)
    with pytest.raises(GpuBudgetBlocked, match="显存预算|保留空间"):
        high_vram._preflight(tmp_path)

    high_ram = workflow(tmp_path, used_ram=19000)
    with pytest.raises(GpuBudgetBlocked, match="24 GiB RAM"):
        high_ram._preflight(tmp_path)


def test_input_validation_happens_before_gpu_submission(tmp_path: Path, monkeypatch) -> None:
    service = workflow(tmp_path)
    monkeypatch.setattr(service, "_dependencies", lambda: pytest.fail("must not load H3"))
    with pytest.raises(FileNotFoundError):
        service.run(tmp_path / "missing.png", "blink")
    image = tmp_path / "source.png"
    Image.new("RGB", (32, 32)).save(image)
    with pytest.raises(ValueError, match="动作提示词"):
        service.run(image, " ")


def test_workflow_generates_validated_review_only_artifact(tmp_path: Path, monkeypatch) -> None:
    service = workflow(tmp_path)
    image = tmp_path / "source.png"
    Image.new("RGB", (32, 32)).save(image)
    monkeypatch.setattr(service, "_dependencies", lambda: None)
    monkeypatch.setattr(service, "_make_canvas", lambda _image, run: (run / "reference_canvas.png").write_bytes(b"png"))

    def fake_phase(_python, _worker, run: Path, phase: str) -> dict:
        (run / wallpaper.PHASE_FILES[wallpaper.PHASES.index(phase)]).write_bytes(b"stage")
        return {"phase": phase, "status": "PASS", "peak_vram_mib": 5400,
                "peak_system_ram_mib": 13000}

    monkeypatch.setattr(service, "_phase", fake_phase)
    monkeypatch.setattr(wallpaper, "require_media_executable", lambda name, _configured: Path(name))

    def fake_run(command, **_kwargs):
        if str(command[0]) == "ffmpeg":
            Path(command[-1]).write_bytes(b"video")
            return SimpleNamespace(returncode=0)
        return SimpleNamespace(stdout=json.dumps({
            "streams": [{"codec_type": "video", "width": 1280, "height": 720,
                         "nb_read_frames": "90"}],
            "format": {"duration": "3.750000"},
        }), returncode=0)

    monkeypatch.setattr(wallpaper.subprocess, "run", fake_run)
    result = service.run(image, "A subtle blink.\nHair moves gently.", output_dir=tmp_path)
    assert result["workflow_name"] == "动态壁纸制作"
    assert result["status"] == "GENERATED_PENDING_HUMAN_REVIEW"
    assert result["validation"] == {"width": 1280, "height": 720,
                                    "frames": 90, "duration_sec": 3.75}
    assert len(result["stages"]) == 4
    assert Path(result["artifact"]).is_file()
    assert service.resume(Path(result["run_dir"]))["artifact_sha256"] == result["artifact_sha256"]


def test_failed_phase_keeps_evidence_and_does_not_publish(tmp_path: Path, monkeypatch) -> None:
    service = workflow(tmp_path)
    image = tmp_path / "source.png"
    Image.new("RGB", (32, 32)).save(image)
    monkeypatch.setattr(service, "_dependencies", lambda: None)
    monkeypatch.setattr(service, "_make_canvas", lambda _image, run: (run / "reference_canvas.png").write_bytes(b"png"))
    monkeypatch.setattr(service, "_phase", lambda *_args: {
        "phase": "keyframe", "status": "FAILED", "peak_vram_mib": 6200,
        "peak_system_ram_mib": 13000,
    })
    with pytest.raises(RuntimeError, match="keyframe"):
        service.run(image, "blink", output_dir=tmp_path)
    run_dir = next(tmp_path.glob("wallpaper_*"))
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["status"] == "FAILED"
    assert summary["stages"][0]["status"] == "FAILED"
    assert not (run_dir / "dynamic_wallpaper_720p.mp4").exists()


@pytest.mark.parametrize("observed_mib,should_stop", [(6200, False), (7680, False), (7681, True)])
def test_phase_requests_cooperative_stop_when_gpu_exceeds_boundary(
    tmp_path: Path, monkeypatch, observed_mib: int, should_stop: bool,
) -> None:
    service = workflow(tmp_path)
    resources = service.resources

    class FakeProcess:
        returncode = 0

        def __init__(self, *_args, **_kwargs) -> None:
            self.polls = 0

        def poll(self):
            self.polls += 1
            if self.polls == 1:
                resources.used_vram = observed_mib
                return None
            resources.used_vram = 1200
            return 0

    monkeypatch.setattr(wallpaper.subprocess, "Popen", FakeProcess)
    monkeypatch.setattr(wallpaper.time, "sleep", lambda _seconds: None)
    result = service._phase(Path("python.exe"), Path("worker.py"), tmp_path, "sample")
    assert result["status"] == ("FAILED" if should_stop else "PASS")
    assert result["stop_reason"] == ("gpu_budget_exceeded" if should_stop else None)
    assert result["peak_vram_mib"] == observed_mib
    assert (tmp_path / "STOP").is_file() is should_stop
