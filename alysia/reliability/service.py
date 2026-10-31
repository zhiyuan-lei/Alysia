from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from alysia.core.config import AlysiaConfig
from alysia.core.io import atomic_write_json
from alysia.core.resources import ResourceManager
from alysia.core.run import RunManager, RunState
from alysia.core.state import Stage
from alysia.schemas.reliability import (
    FailureCategory,
    FailureRecord,
    RecoveryDecision,
    RecoveryMetrics,
)

from .artifacts import ArtifactIntegrityChecker
from .checkpoints import CheckpointManager
from .failures import FailureClassifier, FailureStore
from .monitor import LongRunningTaskMonitor
from .policy import RecoveryPolicyEngine
from .resources import ResourceGuard


_STAGE_ARTIFACTS: dict[str, tuple[str, ...]] = {
    "researching": ("research", "research_markdown", "research_knowledge_result"),
    "writing": ("script", "script_markdown", "metadata", "grounding_report", "knowledge_qa_report"),
    "storyboarding": ("storyboard",),
    "generating_voice": ("audio_manifest", "narration"),
    "tts": ("audio_manifest", "narration"),
    "generating_subtitles": ("subtitles_json", "subtitles_srt"),
    "subtitle_alignment": ("subtitles_json", "subtitles_srt"),
    "generating_assets": ("visual_assets_manifest",),
    "visual": ("visual_assets_manifest",),
    "rendering": ("composition", "assets_manifest", "render_config", "render_result", "final_video"),
    "render": ("composition", "assets_manifest", "render_config", "render_result", "final_video"),
    "video_qa": ("video_qa_report",),
    "packaging": ("publish_package", "publish_metadata", "publish_title", "publish_description", "publish_tags", "publish_cover"),
    "publish_qa": ("publish_qa_report",),
    "publish_job": ("publish_job",),
}

_DOWNSTREAM: dict[str, tuple[str, ...]] = {
    "voice": (
        "audio_manifest", "narration", "subtitles_json", "subtitles_srt", "audio_qa_report",
        "composition", "assets_manifest", "render_config", "render_result", "final_video",
        "video_qa_report", "publish_package", "publish_metadata", "publish_title",
        "publish_description", "publish_tags", "publish_cover", "publish_qa_report",
    ),
    "subtitle": (
        "subtitles_json", "subtitles_srt", "audio_qa_report", "composition", "assets_manifest",
        "render_config", "render_result", "final_video", "video_qa_report", "publish_package",
        "publish_metadata", "publish_title", "publish_description", "publish_tags", "publish_cover",
        "publish_qa_report",
    ),
    "visual": (
        "visual_assets_manifest", "composition", "assets_manifest", "render_config", "render_result",
        "final_video", "video_qa_report", "publish_package", "publish_metadata", "publish_title",
        "publish_description", "publish_tags", "publish_cover", "publish_qa_report",
    ),
    "render": (
        "render_result", "final_video", "video_qa_report", "publish_package", "publish_metadata",
        "publish_title", "publish_description", "publish_tags", "publish_cover", "publish_qa_report",
    ),
    "publish": ("publish_package", "publish_metadata", "publish_title", "publish_description", "publish_tags", "publish_cover", "publish_qa_report"),
}


class ReliabilityService:
    def __init__(
        self,
        config: AlysiaConfig,
        *,
        manager: RunManager | None = None,
        resources: ResourceManager | None = None,
    ) -> None:
        self.config = config
        self.manager = manager or RunManager(config.runtime.runs_dir)
        self.resources = resources or ResourceManager(sequential_gpu=config.runtime.sequential_gpu)
        policy = config.reliability
        self.policy = RecoveryPolicyEngine(
            max_retries_per_stage=policy.max_retries_per_stage,
            max_recovery_rounds=policy.max_recovery_rounds,
            exponential_backoff=policy.exponential_backoff,
            backoff_base_sec=policy.backoff_base_sec,
            require_checkpoint_before_destructive_rebuild=policy.require_checkpoint_before_destructive_rebuild,
        )
        thresholds = policy.resource_guard
        self.guard = ResourceGuard(
            self.resources,
            min_disk_free_gb=thresholds.min_disk_free_gb,
            warning_disk_free_gb=thresholds.warning_disk_free_gb,
            min_ram_available_mb=thresholds.min_ram_available_mb,
            warning_ram_available_mb=thresholds.warning_ram_available_mb,
            min_vram_free_mb=thresholds.min_vram_free_mb,
            warning_vram_free_mb=thresholds.warning_vram_free_mb,
        )
        self.integrity = ArtifactIntegrityChecker(compute_hash=policy.artifact_hash_enabled)

    def root(self, run_id: str) -> Path:
        return self.manager.run_dir(run_id) / "reliability"

    def failures(self, run_id: str) -> FailureStore:
        return FailureStore(self.root(run_id) / "failures")

    def checkpoints(self, run_id: str) -> CheckpointManager:
        return CheckpointManager(
            self.root(run_id) / "checkpoints",
            integrity=ArtifactIntegrityChecker(compute_hash=self.config.reliability.artifact_hash_enabled),
        )

    def monitor(self, run_id: str) -> LongRunningTaskMonitor:
        return LongRunningTaskMonitor(self.root(run_id) / "tasks")

    def checkpoint(self, state: RunState, status: str, *, workflow_id: str | None = None):
        keys = _STAGE_ARTIFACTS.get(state.current_stage.value, ())
        run_dir = self.manager.run_dir(state.run_id)
        paths = [run_dir / state.artifacts[key] for key in keys if key in state.artifacts]
        return self.checkpoints(state.run_id).create(
            run_id=state.run_id,
            workflow_id=workflow_id,
            stage=state.current_stage.value,
            status=status,
            state_payload=state.model_dump(mode="json"),
            artifact_paths=paths,
            producer=state.current_stage.value,
        )

    def record_exception(
        self,
        error: BaseException,
        *,
        state: RunState,
        stage: str,
        provider: str | None,
        retry_count: int,
        fallback_refs: list[str] | None = None,
        agent: str | None = None,
        worker: str | None = None,
    ) -> tuple[FailureRecord, RecoveryDecision]:
        record = FailureClassifier.record(
            error, run_id=state.run_id, stage=stage, provider=provider, agent=agent, worker=worker,
            retry_count=retry_count, max_retries=self.config.reliability.max_retries_per_stage,
            fallback_refs=fallback_refs,
        )
        checkpoints = self.checkpoints(state.run_id).list(stage=state.current_stage.value)
        checkpoint_id = next((item.checkpoint_id for item in reversed(checkpoints) if item.valid), None)
        owner = self.artifact_owner(stage)
        decision = self.policy.decide(
            record,
            current_state=state,
            approved_fallbacks=fallback_refs,
            checkpoint_id=checkpoint_id,
            artifact_owner=owner,
        )
        self.failures(state.run_id).save(record)
        self._save_decision(state.run_id, decision)
        return record, decision

    def prepare_recovery(self, run_id: str, failure_id: str | None = None) -> RecoveryDecision:
        store = self.failures(run_id)
        if failure_id:
            failure = store.load(failure_id)
        else:
            open_failures = [item for item in store.list(run_id=run_id) if item.status in {"open", "recovering"}]
            if not open_failures:
                raise RuntimeError("没有待恢复 FailureRecord")
            failure = open_failures[-1]
        state = self.manager.load(run_id)
        checkpoints = self.checkpoints(run_id).list(stage=state.failed_stage.value if state.failed_stage else failure.stage)
        checkpoint_id = next((item.checkpoint_id for item in reversed(checkpoints) if item.valid), None)
        decision = self.policy.decide(
            failure,
            current_state=state,
            approved_fallbacks=failure.fallback_refs,
            checkpoint_id=checkpoint_id,
            artifact_owner=self.artifact_owner(failure.stage),
        )
        if decision.action in {
            "retry_same_step", "retry_with_backoff", "use_approved_fallback",
            "invalidate_artifact_and_rebuild_stage", "rollback_to_artifact_owner",
        }:
            self._invalidate_owner(state, decision.artifact_owner or self.artifact_owner(failure.stage))
            failure.status = "recovering"
            failure.recovery_round += 1
            store.save(failure)
            self.manager.save(state)
        elif decision.action == "restore_checkpoint" and decision.checkpoint_id:
            _, payload = self.checkpoints(run_id).restore(decision.checkpoint_id)
            restored = RunState.model_validate(payload)
            self.manager.save(restored)
            failure.status = "recovered"
            store.save(failure)
        elif decision.requires_human:
            failure.status = "escalated"
            store.save(failure)
        self._save_decision(run_id, decision)
        return decision

    def mark_recovered(self, run_id: str, failure_id: str, *, reexecuted_stages: list[str] | None = None) -> FailureRecord:
        store = self.failures(run_id)
        record = store.load(failure_id)
        record.status = "recovered"
        store.save(record)
        atomic_write_json(
            self.root(run_id) / "outcomes" / f"{failure_id}.json",
            {
                "failure_id": failure_id,
                "status": "recovered",
                "reexecuted_stages": reexecuted_stages or [],
                "recorded_at": datetime.now().astimezone(),
            },
            backup_count=2,
        )
        return record

    def status(self, run_id: str | None = None) -> dict[str, Any]:
        if run_id is None:
            run_ids = [path.name for path in sorted(self.manager.runs_dir.glob("*")) if path.is_dir()]
        else:
            run_ids = [run_id]
        records = [record for item in run_ids for record in self.failures(item).list(run_id=item)]
        return {
            "run_id": run_id,
            "failures": len(records),
            "open": sum(item.status == "open" for item in records),
            "recovering": sum(item.status == "recovering" for item in records),
            "recovered": sum(item.status == "recovered" for item in records),
            "escalated": sum(item.status == "escalated" for item in records),
            "terminal": sum(item.status == "terminal" for item in records),
            "fault_injection_enabled": self.config.reliability.fault_injection_enabled,
        }

    def diagnose(self, run_id: str) -> dict[str, Any]:
        state = self.manager.load(run_id)
        run_dir = self.manager.run_dir(run_id)
        artifacts = {
            key: self.integrity.check(run_dir / relative, producer=key).model_dump(mode="json")
            for key, relative in state.artifacts.items()
        }
        guard = self.guard.check(run_dir, gpu_heavy=False)
        return {
            "run_id": run_id,
            "state": state.model_dump(mode="json"),
            "artifacts": artifacts,
            "failures": [item.model_dump(mode="json") for item in self.failures(run_id).list(run_id=run_id)],
            "checkpoints": [item.model_dump(mode="json") for item in self.checkpoints(run_id).list()],
            "resource_guard": guard.model_dump(mode="json"),
        }

    def metrics(self, run_id: str) -> RecoveryMetrics:
        records = self.failures(run_id).list(run_id=run_id)
        recoverable = [item for item in records if item.recoverable]
        recovered = [item for item in recoverable if item.status == "recovered"]
        unnecessary = 0
        outcomes_dir = self.root(run_id) / "outcomes"
        if outcomes_dir.is_dir():
            import json

            for path in outcomes_dir.glob("*.json"):
                payload = json.loads(path.read_text(encoding="utf-8"))
                failure = next((item for item in records if item.failure_id == payload.get("failure_id")), None)
                owner = self.artifact_owner(failure.stage) if failure else None
                unnecessary += sum(stage != owner for stage in payload.get("reexecuted_stages", []))
        return RecoveryMetrics(
            recovery_success_rate=(len(recovered) / len(recoverable)) if recoverable else 1.0,
            unnecessary_stage_reexecution_count=unnecessary,
            checkpoint_restore_success=sum(
                item.status == "recovered" and item.category == FailureCategory.STATE_CORRUPT for item in records
            ),
            duplicate_publish_job_count=0,
            recovery_rounds=sum(item.recovery_round for item in records),
        )

    @staticmethod
    def artifact_owner(stage: str) -> str | None:
        value = stage.lower()
        if "voice" in value or value == "tts" or "audio" in value:
            return "voice"
        if "subtitle" in value or "asr" in value:
            return "subtitle"
        if "h3" in value or "comfyui" in value or "visual" in value or "asset" in value:
            return "visual"
        if "render" in value or "ffmpeg" in value or "video" in value:
            return "render"
        if "publish" in value or "package" in value:
            return "publish"
        return None

    def _invalidate_owner(self, state: RunState, owner: str | None) -> None:
        if owner is None:
            return
        for key in _DOWNSTREAM.get(owner, ()):
            state.artifacts.pop(key, None)
        if owner == "voice":
            invalid = {Stage.GENERATING_VOICE, Stage.GENERATING_SUBTITLES, Stage.QA, Stage.RENDERING, Stage.VIDEO_QA, Stage.PACKAGING, Stage.PUBLISH_QA, Stage.READY_FOR_REVIEW}
            state.audio_pipeline_completed = False
        elif owner == "subtitle":
            invalid = {Stage.GENERATING_SUBTITLES, Stage.QA, Stage.RENDERING, Stage.VIDEO_QA, Stage.PACKAGING, Stage.PUBLISH_QA, Stage.READY_FOR_REVIEW}
            state.audio_pipeline_completed = False
        elif owner == "visual":
            invalid = {Stage.GENERATING_ASSETS, Stage.RENDERING, Stage.VIDEO_QA, Stage.PACKAGING, Stage.PUBLISH_QA, Stage.READY_FOR_REVIEW}
        elif owner == "render":
            invalid = {Stage.RENDERING, Stage.VIDEO_QA, Stage.PACKAGING, Stage.PUBLISH_QA, Stage.READY_FOR_REVIEW}
        else:
            invalid = {Stage.PACKAGING, Stage.PUBLISH_QA, Stage.READY_FOR_REVIEW}
        state.completed_stages = [item for item in state.completed_stages if item not in invalid]
        if owner in {"voice", "subtitle", "visual", "render"}:
            state.video_pipeline_completed = False
            state.package_pipeline_completed = False
            state.review_ready = False
        state.failed_stage = None
        state.error_message = None

    def _save_decision(self, run_id: str, decision: RecoveryDecision) -> Path:
        return atomic_write_json(
            self.root(run_id) / "decisions" / f"{decision.failure_id}.json",
            decision.model_dump(mode="json"), backup_count=2,
        )

