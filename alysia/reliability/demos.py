from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from alysia.core.config import AlysiaConfig
from alysia.core.resources import ResourceManager
from alysia.core.run import RunManager
from alysia.core.state import Stage
from alysia.providers.tts.base import BaseTTSProvider
from alysia.providers.tts.mock import MockTTSProvider
from alysia.schemas import Scene, Storyboard, VisualType
from alysia.schemas.reliability import FailureRecord
from alysia.schemas.visual import VisualGenerationResult
from alysia.visual.qa import VisualQA
from alysia.workers.media import require_media_executable, run_command
from alysia.workers.subtitle import SubtitleWorker
from alysia.workers.voice import VoiceWorker

from .artifacts import ArtifactIntegrityChecker
from .service import ReliabilityService


class _FailOnceTTS(BaseTTSProvider):
    name = "fault_demo_tts"

    def __init__(self) -> None:
        self.delegate = MockTTSProvider()
        self.calls = 0

    async def synthesize(self, request):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("controlled TTS provider failure")
        result = await self.delegate.synthesize(request)
        return result.model_copy(update={"provider": self.name})


def run_reliability_demos(config: AlysiaConfig, evidence_root: Path | None = None) -> dict[str, Any]:
    timestamp = datetime.now().astimezone().strftime("%Y%m%dT%H%M%S")
    root = (evidence_root or Path("evaluation") / "reliability_demos" / timestamp).resolve()
    root.mkdir(parents=True, exist_ok=True)
    demo_config = config.model_copy(deep=True)
    demo_config.runtime.runs_dir = root / "runs"
    demo_config.video.width = 320
    demo_config.video.height = 180
    demo_config.video.fps = 12
    demo_config.tts.allow_test_tone = True
    demo_config.asr.provider = "none"
    outcomes = {
        "demo_a_voice": asyncio.run(_demo_voice(demo_config, root / "demo_a_voice")),
        "demo_b_h3": _demo_h3(demo_config, root / "demo_b_h3"),
        "demo_c_state": _demo_state(demo_config, root / "demo_c_state"),
        "demo_d_ffmpeg": _demo_ffmpeg(demo_config, root / "demo_d_ffmpeg"),
    }
    summary = {
        "status": "PASS" if all(item["passed"] for item in outcomes.values()) else "FAIL",
        "testing_only": True,
        "fault_injection_enabled_in_production": config.reliability.fault_injection_enabled,
        "evidence_root": str(root),
        "outcomes": outcomes,
        "generated_at": datetime.now().astimezone().isoformat(),
    }
    _write(root / "summary.json", summary)
    return summary


async def _demo_voice(config: AlysiaConfig, root: Path) -> dict[str, Any]:
    root.mkdir(parents=True, exist_ok=True)
    manager = RunManager(config.runtime.runs_dir)
    state = manager.create("Alpha19 Demo A Voice failure", config.model_dump(mode="json"))
    storyboard = Storyboard(
        title="局部恢复", target_duration_sec=30,
        scenes=[Scene(
            id="s1", section_id="body", duration_sec=30,
            narration="配音失败后，只重新生成音频、字幕和必要的编辑产物。",
            visual_type=VisualType.TEXT, screen_text="Local Recovery",
        )],
    )
    upstream = {
        "research": {"status": "preserved"},
        "script": {"status": "preserved"},
        "storyboard": storyboard.model_dump(mode="json"),
    }
    for key, payload in upstream.items():
        relative = f"{key}.json"
        manager.write_json(state.run_id, relative, payload)
        state.artifacts[key] = relative
    state.completed_stages = [Stage.RESEARCHING, Stage.WRITING, Stage.STORYBOARDING]
    state.current_stage = Stage.GENERATING_VOICE
    manager.save(state)
    hashes_before = _artifact_hashes(manager, state.run_id, upstream)
    reliability = ReliabilityService(config, manager=manager)
    provider = _FailOnceTTS()
    worker = VoiceWorker(manager, config.tts, provider, ResourceManager())
    failure: FailureRecord | None = None
    try:
        await worker.run(state, storyboard, force=True)
    except RuntimeError as exc:
        failure, decision = reliability.record_exception(
            exc, state=state, stage="voice", provider=provider.name, retry_count=0,
        )
        reliability._invalidate_owner(state, "voice")
        manager.save(state)
    else:
        raise AssertionError("Voice fault demo did not inject the expected failure")
    manifest = await worker.run(state, storyboard, force=True)
    state.artifacts.update({"audio_manifest": "audio/audio_manifest.json", "narration": "audio/narration.wav"})
    subtitle = SubtitleWorker(manager, config.subtitle, ResourceManager(), None).run(state, storyboard, manifest)
    state.artifacts.update({"subtitles_json": "subtitles/subtitles.json", "subtitles_srt": "subtitles/subtitles.srt"})
    manager.write_json(state.run_id, "video/editor_resume.json", {"resumed_from": "voice", "upstream_reused": list(upstream)})
    state.artifacts["composition"] = "video/editor_resume.json"
    manager.save(state)
    reliability.mark_recovered(state.run_id, failure.failure_id, reexecuted_stages=["voice", "subtitle", "editor"])
    hashes_after = _artifact_hashes(manager, state.run_id, upstream)
    evidence = {
        "passed": hashes_before == hashes_after and provider.calls == 2 and bool(subtitle.segments),
        "run_id": state.run_id,
        "failure_id": failure.failure_id,
        "failure_category": failure.category.value,
        "recovery_decision": decision.action,
        "provider_calls": provider.calls,
        "upstream_hashes_before": hashes_before,
        "upstream_hashes_after": hashes_after,
        "regenerated": ["voice", "subtitle", "editor"],
        "not_reexecuted": ["research", "script", "storyboard"],
        "testing_note": "Mock waveform is used only after the injected failure; production MockTTS gate remains unchanged.",
    }
    _write(root / "evidence.json", evidence)
    return evidence


def _demo_h3(config: AlysiaConfig, root: Path) -> dict[str, Any]:
    root.mkdir(parents=True, exist_ok=True)
    manager = RunManager(config.runtime.runs_dir)
    state = manager.create("Alpha19 Demo B H3 OOM", config.model_dump(mode="json"))
    state.current_stage = Stage.GENERATING_ASSETS
    manager.save(state)
    reliability = ReliabilityService(config, manager=manager)
    first, low_resource = reliability.record_exception(
        RuntimeError("CUDA out of memory during H3 generation"), state=state, stage="h3_visual",
        provider="comfyui-h3", retry_count=0, fallback_refs=["h3_low_resource", "visual.remotion"],
    )
    second, static_fallback = reliability.record_exception(
        RuntimeError("CUDA out of memory in approved low-resource profile"), state=state, stage="h3_visual",
        provider="comfyui-h3", retry_count=1, fallback_refs=["visual.remotion"],
    )
    clip = root / "fallback_static.mp4"
    ffmpeg = require_media_executable("ffmpeg", config.render.ffmpeg_path)
    run_command([
        str(ffmpeg), "-y", "-f", "lavfi", "-i", "color=c=0x1f2937:s=320x180:r=12:d=2",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(clip),
    ])
    result = VisualGenerationResult(
        job_id="demo_h3_fallback", scene_id="scene_h3", provider="visual.remotion",
        workflow_id="approved_static_fallback", workflow_version="1", output_files=[clip],
        duration_sec=2, resolution="320x180", generation_time_sec=0, status="completed", mock=False,
        warnings=["H3 OOM; quality reduced to approved static/Remotion fallback"],
    )
    qa = VisualQA().run(state.run_id, result, expected_duration_sec=2)
    reliability.mark_recovered(state.run_id, first.failure_id, reexecuted_stages=["visual"])
    reliability.mark_recovered(state.run_id, second.failure_id, reexecuted_stages=["visual"])
    evidence = {
        "passed": low_resource.fallback_ref == "h3_low_resource" and static_fallback.fallback_ref == "visual.remotion" and qa.passed,
        "run_id": state.run_id,
        "failure_ids": [first.failure_id, second.failure_id],
        "decisions": [low_resource.model_dump(mode="json"), static_fallback.model_dump(mode="json")],
        "quality_impact_recorded": bool(low_resource.quality_impact and static_fallback.quality_impact),
        "visual_qa": qa.model_dump(mode="json"),
        "fallback_clip": str(clip),
        "real_h3_loaded": False,
        "reason": "integration-safe OOM injection; local ComfyUI/H3 deployment is not loaded by the default demo",
    }
    _write(root / "evidence.json", evidence)
    return evidence


def _demo_state(config: AlysiaConfig, root: Path) -> dict[str, Any]:
    root.mkdir(parents=True, exist_ok=True)
    manager = RunManager(config.runtime.runs_dir)
    state = manager.create("Alpha19 Demo C State corruption", config.model_dump(mode="json"))
    manager.save(state)
    state_path = manager.run_dir(state.run_id) / "run_state.json"
    state_path.write_text('{"truncated":', encoding="utf-8")
    restored = manager.load(state.run_id)
    failures = ReliabilityService(config, manager=manager).failures(state.run_id).list(run_id=state.run_id)
    evidence = {
        "passed": restored.run_id == state.run_id and failures[-1].status == "recovered",
        "run_id": state.run_id,
        "restored_from_backup": True,
        "failure": failures[-1].model_dump(mode="json"),
        "current_state_valid": json.loads(state_path.read_text(encoding="utf-8"))["run_id"] == state.run_id,
    }
    _write(root / "evidence.json", evidence)
    return evidence


def _demo_ffmpeg(config: AlysiaConfig, root: Path) -> dict[str, Any]:
    root.mkdir(parents=True, exist_ok=True)
    manager = RunManager(config.runtime.runs_dir)
    state = manager.create("Alpha19 Demo D FFmpeg failure", config.model_dump(mode="json"))
    upstream = {"research": {"ok": True}, "script": {"ok": True}, "storyboard": {"ok": True}, "narration": {"ok": True}}
    for key, payload in upstream.items():
        relative = f"upstream/{key}.json"
        manager.write_json(state.run_id, relative, payload)
        state.artifacts[key] = relative
    state.current_stage = Stage.RENDERING
    manager.save(state)
    before = _artifact_hashes(manager, state.run_id, upstream)
    reliability = ReliabilityService(config, manager=manager)
    try:
        run_command(["pwsh", "-NoProfile", "-NonInteractive", "-Command", "exit 7"])
    except RuntimeError as exc:
        failure, decision = reliability.record_exception(
            exc, state=state, stage="render", provider="ffmpeg", retry_count=0,
        )
        reliability._invalidate_owner(state, "render")
    else:
        raise AssertionError("FFmpeg fault demo did not inject the expected non-zero exit")
    final_video = root / "final.mp4"
    ffmpeg = require_media_executable("ffmpeg", config.render.ffmpeg_path)
    run_command([
        str(ffmpeg), "-y", "-f", "lavfi", "-i", "color=c=0x111827:s=320x180:r=12:d=1",
        "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-shortest",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", str(final_video),
    ])
    integrity = ArtifactIntegrityChecker().check(final_video, producer="render")
    reliability.mark_recovered(state.run_id, failure.failure_id, reexecuted_stages=["render"])
    after = _artifact_hashes(manager, state.run_id, upstream)
    evidence = {
        "passed": decision.action in {"retry_with_backoff", "retry_same_step"} and integrity.validity == "valid" and before == after,
        "run_id": state.run_id,
        "failure_id": failure.failure_id,
        "decision": decision.model_dump(mode="json"),
        "final_integrity": integrity.model_dump(mode="json"),
        "upstream_hashes_before": before,
        "upstream_hashes_after": after,
        "reexecuted": ["render"],
        "not_reexecuted": list(upstream),
    }
    _write(root / "evidence.json", evidence)
    return evidence


def _artifact_hashes(manager: RunManager, run_id: str, keys: dict[str, Any]) -> dict[str, str]:
    state = manager.load(run_id)
    return {
        key: hashlib.sha256((manager.run_dir(run_id) / state.artifacts[key]).read_bytes()).hexdigest()
        for key in keys
    }


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    from alysia.core.io import atomic_write_json

    atomic_write_json(path, payload, backup_count=2)
