from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from alysia.cli import app
from alysia.core.io import StateRecoveryError, atomic_write_json
from alysia.core.run import RunManager
from alysia.core.state import Stage
from alysia.publishing.store import PublishStore
from alysia.reliability.artifacts import ArtifactIntegrityChecker
from alysia.reliability.checkpoints import CheckpointManager
from alysia.reliability.fault_injection import FaultInjector
from alysia.reliability.monitor import LongRunningTaskMonitor
from alysia.reliability.policy import RecoveryPolicyEngine
from alysia.reliability.resources import ResourceGuard
from alysia.reliability.service import ReliabilityService
from alysia.schemas import ApprovalRecord, PublishJob
from alysia.schemas.reliability import FailureCategory, FailureRecord
from alysia.studio.protocol import AgentHandoff
from alysia.studio.trace import StudioTraceStore
from alysia.workflow.demo import failure_repair_resume_demo
from tests.helpers import make_config


def _failure(
    category: FailureCategory = FailureCategory.TIMEOUT,
    *,
    retry_count: int = 0,
    recovery_round: int = 0,
    fallbacks: list[str] | None = None,
) -> FailureRecord:
    return FailureRecord(
        failure_id="failure_test",
        run_id="run_test",
        stage="voice" if category == FailureCategory.TTS_ERROR else "test_stage",
        category=category,
        message="controlled fault",
        evidence_refs=["fixture://controlled"],
        occurred_at=datetime.now().astimezone(),
        recoverable=True,
        retryable=True,
        retry_count=retry_count,
        max_retries=2,
        suggested_action="test policy",
        fallback_refs=fallbacks or [],
        recovery_round=recovery_round,
    )


def _state(tmp_path: Path):
    config = make_config(tmp_path / "runs")
    manager = RunManager(config.runtime.runs_dir)
    state = manager.create("Alpha19 fault test", config.model_dump(mode="json"))
    return config, manager, state


def test_failure_record_schema() -> None:
    record = _failure(FailureCategory.H3_ERROR, fallbacks=["visual.remotion"])
    assert record.status == "open"
    assert record.fallback_refs == ["visual.remotion"]
    with pytest.raises(ValueError, match="run_id"):
        FailureRecord(
            failure_id="failure_invalid", stage="test", category=FailureCategory.UNKNOWN,
            message="invalid", occurred_at=datetime.now().astimezone(), recoverable=False,
            retryable=False, suggested_action="none",
        )


def test_recovery_policy_retry_limit() -> None:
    decision = RecoveryPolicyEngine(max_retries_per_stage=2).decide(
        _failure(retry_count=2), artifact_owner=None,
    )
    assert decision.action == "escalate_human"


def test_retry_backoff() -> None:
    policy = RecoveryPolicyEngine(backoff_base_sec=1, exponential_backoff=True)
    assert policy.decide(_failure(retry_count=0)).retry_after_sec == 1
    assert policy.decide(_failure(retry_count=1)).retry_after_sec == 2


def test_checkpoint_create_restore(tmp_path: Path) -> None:
    artifact = tmp_path / "script.json"
    atomic_write_json(artifact, {"text": "valid"})
    manager = CheckpointManager(tmp_path / "checkpoints")
    checkpoint = manager.create(
        run_id="run_test", stage="writing", status="succeeded",
        state_payload={"stage": "writing"}, artifact_paths=[artifact],
    )
    restored, payload = manager.restore(checkpoint.checkpoint_id)
    assert restored.valid is True
    assert payload == {"stage": "writing"}


def test_atomic_json_write(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    atomic_write_json(path, {"version": 1}, backup_count=2)
    atomic_write_json(path, {"version": 2}, backup_count=2)
    assert json.loads(path.read_text(encoding="utf-8"))["version"] == 2
    assert json.loads((tmp_path / "state.json.bak1").read_text(encoding="utf-8"))["version"] == 1
    assert not list(tmp_path.glob("*.tmp"))


def test_corrupt_state_restores_backup(tmp_path: Path) -> None:
    _, manager, state = _state(tmp_path)
    manager.save(state)
    state_path = manager.run_dir(state.run_id) / "run_state.json"
    state_path.write_text('{"broken":', encoding="utf-8")
    restored = manager.load(state.run_id)
    assert restored.run_id == state.run_id
    failures = ReliabilityService(make_config(tmp_path / "runs"), manager=manager).failures(state.run_id).list(run_id=state.run_id)
    assert failures[-1].category == FailureCategory.STATE_CORRUPT
    assert failures[-1].status == "recovered"


def test_corrupt_state_no_backup_blocks(tmp_path: Path) -> None:
    config, manager, state = _state(tmp_path)
    state_path = manager.run_dir(state.run_id) / "run_state.json"
    state_path.write_text('{"broken":', encoding="utf-8")
    for backup in state_path.parent.glob("run_state.json.bak*"):
        backup.unlink()
    with pytest.raises(StateRecoveryError):
        manager.load(state.run_id)
    failure = ReliabilityService(config, manager=manager).failures(state.run_id).list(run_id=state.run_id)[-1]
    assert failure.status == "escalated"


def test_corrupt_artifact_invalidates_cache(tmp_path: Path) -> None:
    _, manager, state = _state(tmp_path)
    manager.write_text(state.run_id, "script.json", '{"broken":')
    state.artifacts["script"] = "script.json"
    manager.save(state)
    assert manager.artifact_exists(state, "script") is False
    record = ArtifactIntegrityChecker().check(manager.run_dir(state.run_id) / "script.json", producer="writer")
    assert record.validity == "invalid"


def test_tts_failure_routes_to_voice(tmp_path: Path) -> None:
    config, manager, state = _state(tmp_path)
    record, decision = ReliabilityService(config, manager=manager).record_exception(
        RuntimeError("tts provider unavailable"), state=state, stage="voice", provider="tts.real", retry_count=2,
    )
    assert record.category == FailureCategory.TTS_ERROR
    assert decision.action == "rollback_to_artifact_owner"
    assert decision.artifact_owner == "voice"


def test_audio_repair_regenerates_subtitle_only_downstream(tmp_path: Path) -> None:
    config, manager, state = _state(tmp_path)
    state.artifacts.update({
        "research": "research.json", "script": "script.json", "storyboard": "storyboard.json",
        "narration": "audio/narration.wav", "subtitles_json": "subtitles/subtitles.json",
        "final_video": "output/final.mp4",
    })
    state.completed_stages = [Stage.RESEARCHING, Stage.WRITING, Stage.STORYBOARDING, Stage.GENERATING_VOICE, Stage.GENERATING_SUBTITLES, Stage.RENDERING]
    ReliabilityService(config, manager=manager)._invalidate_owner(state, "voice")
    assert {"research", "script", "storyboard"}.issubset(state.artifacts)
    assert "narration" not in state.artifacts and "subtitles_json" not in state.artifacts and "final_video" not in state.artifacts
    assert state.completed_stages == [Stage.RESEARCHING, Stage.WRITING, Stage.STORYBOARDING]


def test_h3_mock_oom_uses_approved_fallback() -> None:
    decision = RecoveryPolicyEngine().decide(
        _failure(FailureCategory.OOM, fallbacks=["h3_low_resource", "visual.remotion"]),
        approved_fallbacks=["h3_low_resource", "visual.remotion"],
    )
    assert decision.action == "use_approved_fallback"
    assert decision.fallback_ref == "h3_low_resource"
    assert decision.quality_impact


def test_comfyui_unavailable_recovery() -> None:
    failure = _failure(FailureCategory.COMFYUI_ERROR, fallbacks=["visual.remotion"])
    decision = RecoveryPolicyEngine().decide(failure, approved_fallbacks=["visual.remotion"])
    assert decision.action == "use_approved_fallback"
    assert decision.fallback_ref == "visual.remotion"


def test_ffmpeg_failure_render_only_retry(tmp_path: Path) -> None:
    config, manager, state = _state(tmp_path)
    state.artifacts.update({
        "script": "script.json", "storyboard": "storyboard.json", "narration": "audio/narration.wav",
        "composition": "video/composition.json", "final_video": "output/final.mp4",
    })
    ReliabilityService(config, manager=manager)._invalidate_owner(state, "render")
    assert {"script", "storyboard", "narration", "composition"}.issubset(state.artifacts)
    assert "final_video" not in state.artifacts


def test_provider_timeout_watchdog(tmp_path: Path) -> None:
    monitor = LongRunningTaskMonitor(tmp_path / "tasks")
    task = monitor.start("provider_http", expected_timeout=1, run_id="run_test")
    assert monitor.timed_out(task.task_id, now=task.last_heartbeat + timedelta(seconds=2)) is True
    assert monitor.load(task.task_id).status == "timed_out"


class _Resources:
    def __init__(self, *, ram: int = 8192, vram: int = 4096) -> None:
        self.ram = ram
        self.vram = vram

    def probe_ram(self):
        return {"available_mb": self.ram}

    def probe_vram(self):
        return {"free_mb": self.vram}


def test_disk_low_blocks_heavy_job(tmp_path: Path) -> None:
    guard = ResourceGuard(_Resources(), min_disk_free_gb=10**9)
    result = guard.check(tmp_path, gpu_heavy=True)
    assert result.status == "blocked"
    assert any("磁盘" in reason for reason in result.reasons)


def test_resource_guard_vram(tmp_path: Path) -> None:
    guard = ResourceGuard(_Resources(vram=128), min_vram_free_mb=768)
    result = guard.check(tmp_path, gpu_heavy=True)
    assert result.status == "blocked"
    assert result.observed_values["vram_free_mb"] == 128


def test_workflow_resume_after_failure(tmp_path: Path) -> None:
    result = failure_repair_resume_demo(make_config(tmp_path / "runs"))
    assert result["failed_status"] == "blocked"
    assert result["resumed_status"] == "completed"
    assert result["attempts"] == 2


def test_studio_handoff_survives_failure(tmp_path: Path) -> None:
    config, manager, state = _state(tmp_path)
    store = StudioTraceStore(manager, state.run_id)
    handoff = AgentHandoff(
        handoff_id="handoff_recovery", from_agent="voice", to_agent="editor",
        objective="继续编辑", required_inputs=["audio"], provided_artifacts=[],
        acceptance_criteria=["音频已通过 QA"], constraints=["局部恢复"], status="rejected",
        status_reason="controlled failure",
    )
    store.save_handoff(handoff)
    reloaded = StudioTraceStore(manager, state.run_id).handoffs()
    assert reloaded == [handoff]


def test_supervisor_dispatch_idempotent_after_failure(tmp_path: Path) -> None:
    from alysia.supervisor import AutonomousSupervisor
    from tests.test_supervisor import OfflineSupervisorDispatcher, _seed

    config, store, _, _, project = _seed(tmp_path, approvals=[True, False, False, False])
    dispatcher = OfflineSupervisorDispatcher({project.planned_runs[0].planned_run_id: "dispatched"})
    service = AutonomousSupervisor(config, dispatcher=dispatcher, store=store)
    asyncio.run(service.tick())
    asyncio.run(service.tick())
    assert dispatcher.calls == [project.planned_runs[0].planned_run_id]


def test_publish_job_not_duplicated_after_resume(tmp_path: Path) -> None:
    now = datetime.now().astimezone()
    approval = ApprovalRecord(run_id="run_test", approved_by="human:test", approved_at=now, package_hash="a" * 64)
    job = PublishJob(
        job_id="job_stable", run_id="run_test", provider="mock", status="submitted",
        package_path=Path("publish/publish_package.json"), package_hash="a" * 64,
        external_id="mock_bv_test", approval_record=approval, created_at=now, updated_at=now, submitted_at=now,
    )
    store = PublishStore(tmp_path / "publishing")
    store.save(job)
    resumed = store.load(job.job_id)
    store.save(resumed)
    assert len(store.list_for_run("run_test")) == 1
    assert store.load(job.job_id).external_id == "mock_bv_test"


def test_recovery_round_limit_escalates() -> None:
    decision = RecoveryPolicyEngine(max_recovery_rounds=3).decide(_failure(recovery_round=3))
    assert decision.action == "escalate_human"
    assert decision.requires_human is True


def test_fault_injection_disabled_in_production(tmp_path: Path) -> None:
    config = make_config(tmp_path / "runs")
    injector = FaultInjector(enabled=config.reliability.fault_injection_enabled, faults={"provider": RuntimeError("boom")})
    injector.trigger("provider")
    assert config.reliability.fault_injection_enabled is False


def test_reliability_cli_surface(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config, _, state = _state(tmp_path)
    monkeypatch.setattr("alysia.cli.load_config", lambda: config)
    runner = CliRunner()
    assert runner.invoke(app, ["reliability", "status", state.run_id]).exit_code == 0
    assert runner.invoke(app, ["reliability", "failures", state.run_id]).exit_code == 0
    assert runner.invoke(app, ["diagnose", state.run_id]).exit_code == 0
    assert runner.invoke(app, ["checkpoints", state.run_id]).exit_code == 0
