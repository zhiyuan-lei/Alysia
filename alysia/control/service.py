from __future__ import annotations

import asyncio
import hashlib
import json
import mimetypes
from datetime import datetime
from pathlib import Path
from typing import Any

from alysia.capabilities import CapabilityService
from alysia.core.config import AlysiaConfig
from alysia.core.orchestrator import AlysiaOrchestrator
from alysia.core.run import RunManager, RunState
from alysia.core.state import Stage
from alysia.creator import (
    BilibiliPublicationReceipt,
    ContentObservation,
    CreatorJob,
    CreatorMemoryIntegrator,
    CreatorReflection,
)
from alysia.creator.evidence import BetaEvidenceLedger
from alysia.creator.service import CreatorJobService
from alysia.creator.store import CreatorJobStore
from alysia.evaluation import EvaluationService
from alysia.identity import IdentityService
from alysia.knowledge import KnowledgeService
from alysia.local_creator import LocalCreationSpec, LocalCreatorService, _hash_file
from alysia.operations.store import ChannelStore
from alysia.production import ProductionService
from alysia.publishing import PublishingService
from alysia.reliability import ReliabilityService
from alysia.schemas.security import Permission
from alysia.security import SecurityService
from alysia.studio import AgentRegistry
from alysia.studio.trace import StudioTraceStore
from alysia.supervisor import AutonomousSupervisor
from alysia.supervisor.goals import SupervisorStore
from alysia.visual import VisualGenerationService
from alysia.workflow.recipes import WorkflowRecipeStore


_TIMELINE: tuple[tuple[str, tuple[Stage, ...]], ...] = (
    ("Topic", (Stage.CREATED,)),
    ("Research", (Stage.RESEARCHING,)),
    ("Script", (Stage.WRITING,)),
    ("Storyboard", (Stage.STORYBOARDING,)),
    ("Voice", (Stage.GENERATING_VOICE,)),
    ("Subtitle", (Stage.GENERATING_SUBTITLES, Stage.QA)),
    ("Visual", (Stage.GENERATING_ASSETS,)),
    ("Render", (Stage.RENDERING, Stage.VIDEO_QA)),
    ("Packaging", (Stage.PACKAGING, Stage.PUBLISH_QA)),
    ("Review", (Stage.READY_FOR_REVIEW, Stage.PUBLISH_APPROVAL)),
    ("Publish / Feedback", (Stage.PUBLISH_JOB, Stage.FEEDBACK_WAITING)),
)

_PREVIEW_EXTENSIONS = {
    ".json", ".jsonl", ".md", ".txt", ".srt", ".yaml", ".yml",
    ".png", ".jpg", ".jpeg", ".webp", ".gif", ".mp4", ".webm", ".wav",
}


class ControlCenterError(RuntimeError):
    """A controlled adapter failure that is safe to redact and return locally."""


class ControlCenterService:
    """Thin local adapter over Alpha1-20 services and their validated artifacts."""

    baseline_id = "baseline_alpha17_75261fe47f27"
    alpha20_evaluation_id = "eval_879a6ab4d0ede96b5905"

    def __init__(self, config: AlysiaConfig) -> None:
        self.config = config
        self.project_root = Path.cwd().resolve()
        self.manager = RunManager(config.runtime.runs_dir)
        self.security = SecurityService(config)
        self.reliability = ReliabilityService(config, manager=self.manager)
        self.evaluation = EvaluationService(config, project_root=self.project_root)
        creator_jobs_dir = config.creator_loop.jobs_dir or (config.runtime.runs_dir.parent / "creator_jobs")
        self.creator_jobs = CreatorJobStore(creator_jobs_dir)
        self.creator_job_service = CreatorJobService(self.creator_jobs)
        self.local_creator = LocalCreatorService(config)

    def local_creation_jobs(self) -> list[dict[str, Any]]:
        return self.local_creator.list()

    def local_creation_job(self, run_id: str) -> dict[str, Any]:
        return self.local_creator.status(run_id)

    def submit_local_creation(self, spec: LocalCreationSpec) -> dict[str, Any]:
        self._authorize_write("local_create.submit", spec.title)
        job = self.local_creator.submit(spec)
        return self.local_creator.start_background(job["run_id"])

    def resume_local_creation(self, run_id: str) -> dict[str, Any]:
        self._authorize_write("local_create.resume", run_id)
        return self.local_creator.start_background(run_id)

    def local_creation_video(self, run_id: str) -> Path:
        state = self.local_creator.status(run_id)
        path = self.local_creator.final_video(run_id)
        if (state["status"] != "COMPLETE" or not path.is_file()
                or (state.get("final_video") or {}).get("sha256") != _hash_file(path)):
            raise FileNotFoundError("本地创作成片尚未通过 QA")
        return path

    @staticmethod
    def _model(value: Any) -> Any:
        if hasattr(value, "model_dump"):
            return value.model_dump(mode="json")
        return value

    @staticmethod
    def _safe_id(value: str, *, label: str = "identifier") -> str:
        if not value or Path(value).name != value or not value.replace("_", "").replace("-", "").replace(":", "").isalnum():
            raise ValueError(f"{label} 格式无效")
        return value

    def health(self) -> dict[str, Any]:
        security = self.security.status().model_dump(mode="json")
        reliability = self.reliability.status()
        gate = self.evaluation.gate(self.alpha20_evaluation_id, baseline_id=self.baseline_id)
        visual = VisualGenerationService(self.config).doctor()
        return {
            "status": "healthy" if gate.status != "BLOCKED" and security["enabled"] else "degraded",
            "version": "0.1-alpha.21",
            "local_only": True,
            "alpha18": gate.model_dump(mode="json"),
            "alpha19": reliability,
            "alpha20": security,
            "visual": visual,
            "checked_at": datetime.now().astimezone().isoformat(),
        }

    def resources(self) -> dict[str, Any]:
        guard = self.reliability.guard.check(self.project_root, gpu_heavy=True)
        vram = self.reliability.resources.probe_vram()
        ram = self.reliability.resources.probe_ram()
        return {
            "gpu": {"name": "NVIDIA GeForce RTX 4060 Ti", "budget_mb": 8192, **(vram or {})},
            "ram": {"budget_mb": 24 * 1024, **(ram or {})},
            "disk": {"free_gb": guard.observed_values.get("disk_free_gb")},
            "guard": guard.model_dump(mode="json"),
        }

    def providers(self) -> list[dict[str, Any]]:
        registry = ProductionService(self.config).registry
        visual = VisualGenerationService(self.config).doctor()
        output = [item.model_dump(mode="json") for item in registry.list()]
        for item in output:
            if item["provider_id"] == "visual.comfyui-h3":
                item["runtime_health"] = visual
        return output

    def list_runs(self) -> list[dict[str, Any]]:
        runs: list[dict[str, Any]] = []
        for directory in sorted(self.manager.runs_dir.iterdir(), reverse=True):
            if not directory.is_dir() or not (directory / "run_state.json").is_file():
                continue
            try:
                state = self.manager.load(directory.name)
                runs.append(self.run_summary(state))
            except Exception as exc:
                runs.append({"run_id": directory.name, "status": "blocked", "error": str(exc)})
        return runs

    def run_summary(self, state: RunState) -> dict[str, Any]:
        status = "failed" if state.failed_stage or state.current_stage == Stage.FAILED else "waiting_approval" if state.current_stage in {Stage.READY_FOR_REVIEW, Stage.PUBLISH_APPROVAL} else "completed" if state.current_stage in {Stage.COMPLETED, Stage.FEEDBACK_WAITING} else "running"
        return {
            "run_id": state.run_id, "topic": state.topic, "stage": state.current_stage.value,
            "status": status, "milestone": state.milestone, "updated_at": state.updated_at,
            "review_ready": state.review_ready, "testing": self._run_testing(state),
        }

    def run_detail(self, run_id: str) -> dict[str, Any]:
        state = self.manager.load(self._safe_id(run_id, label="run_id"))
        return {
            "summary": self.run_summary(state),
            "state": state.model_dump(mode="json"),
            "timeline": self._timeline(state),
            "qa": self._qa_reports(state),
            "failures": [item.model_dump(mode="json") for item in self.reliability.failures(run_id).list(run_id=run_id)],
        }

    def run_artifacts(self, run_id: str) -> list[dict[str, Any]]:
        state = self.manager.load(self._safe_id(run_id, label="run_id"))
        root = self.manager.run_dir(run_id).resolve()
        artifacts: list[dict[str, Any]] = []
        for key, relative in sorted(state.artifacts.items()):
            path = self._artifact_path(state, key)
            suffix = path.suffix.lower()
            artifacts.append({
                "key": key, "name": path.name, "relative": Path(relative).as_posix(),
                "exists": path.is_file(), "size": path.stat().st_size if path.is_file() else 0,
                "previewable": suffix in _PREVIEW_EXTENSIONS,
                "kind": self._artifact_kind(suffix),
                "url": f"/api/runs/{state.run_id}/artifacts/{key}" if path.is_file() else None,
                "root_guarded": path.is_relative_to(root),
            })
        return artifacts

    def artifact(self, run_id: str, key: str) -> tuple[Path, str]:
        state = self.manager.load(self._safe_id(run_id, label="run_id"))
        path = self._artifact_path(state, self._safe_id(key, label="artifact key"))
        if not path.is_file() or path.suffix.lower() not in _PREVIEW_EXTENSIONS:
            raise FileNotFoundError("artifact 不存在或不可预览")
        return path, mimetypes.guess_type(path.name)[0] or "application/octet-stream"

    async def resume(self, run_id: str) -> dict[str, Any]:
        self._authorize_write("run.resume", run_id)
        safe_run_id = self._safe_id(run_id, label="run_id")
        self.reliability.diagnose(safe_run_id)
        state = await AlysiaOrchestrator(self.config).resume(safe_run_id)
        return state.model_dump(mode="json")

    async def recover(self, run_id: str, failure_id: str | None = None) -> dict[str, Any]:
        self._authorize_write("run.recover", run_id)
        decision = self.reliability.prepare_recovery(self._safe_id(run_id, label="run_id"), failure_id)
        payload: dict[str, Any] = {"decision": decision.model_dump(mode="json"), "resume_executed": False}
        if decision.action in {"retry_same_step", "retry_with_backoff", "use_approved_fallback", "invalidate_artifact_and_rebuild_stage", "rollback_to_artifact_owner"}:
            payload["state"] = (await AlysiaOrchestrator(self.config).resume(run_id)).model_dump(mode="json")
            payload["resume_executed"] = True
        return payload

    def diagnose(self, run_id: str) -> dict[str, Any]:
        return self.reliability.diagnose(self._safe_id(run_id, label="run_id"))

    def supervisor(self, kind: str) -> Any:
        store = SupervisorStore(self.config.supervisor.root_dir)
        if kind == "goals":
            return [self._model(item) for item in store.list_goals()]
        if kind == "plans":
            return [self._model(item) for item in store.list_plans()]
        if kind == "blockers":
            return AutonomousSupervisor(self.config).blockers()
        raise KeyError(kind)

    def studio(self, run_id: str, kind: str) -> Any:
        self._safe_id(run_id, label="run_id")
        if kind == "agents":
            return [self._model(item) for item in AgentRegistry.default_profiles()]
        store = StudioTraceStore(self.manager, run_id)
        if kind == "trace":
            return store.trace_records()
        raise KeyError(kind)

    def production(self, run_id: str, kind: str) -> Any:
        service = ProductionService(self.config)
        if kind == "plan":
            return service.status(self._safe_id(run_id, label="run_id"))
        if kind == "resources":
            return {"system": self.resources(), "plan": service.status(run_id)}
        raise KeyError(kind)

    def visual_jobs(self) -> list[dict[str, Any]]:
        return [item.model_dump(mode="json") for item in VisualGenerationService(self.config).queue.list()]

    def visual_job(self, job_id: str) -> dict[str, Any]:
        self._safe_id(job_id, label="job_id")
        for item in VisualGenerationService(self.config).queue.list():
            if item.job_id == job_id:
                return item.model_dump(mode="json")
        raise FileNotFoundError(job_id)

    def visual_plan(self, run_id: str) -> dict[str, Any]:
        return VisualGenerationService(self.config).status(self._safe_id(run_id, label="run_id"))

    def knowledge(self, kind: str) -> Any:
        service = KnowledgeService(self.config)
        if kind == "status":
            return service.store.status()
        if kind == "claims":
            return [self._model(item) for item in service.store.list_claims()]
        if kind == "conflicts":
            return [self._model(item) for item in service.store.list_conflicts(open_only=True)]
        if kind == "stale":
            return [self._model(item) for item in service.store.list_claims() if item.status == "stale"]
        raise KeyError(kind)

    def analytics(self, run_id: str) -> dict[str, Any]:
        state = self.manager.load(self._safe_id(run_id, label="run_id"))
        keys = [key for key in state.artifacts if key.startswith("analytics") or key in {"metrics", "derived_metrics", "performance_analysis"}]
        return {key: self.manager.read_json(run_id, state.artifacts[key]) for key in keys if self.manager.artifact_exists(state, key)}

    def lessons(self) -> list[Any]:
        return self._json_files(self.config.learning.memory_dir / "lessons")

    def experiments(self) -> list[Any]:
        return [self._model(item) for item in ChannelStore(self.config.learning.memory_dir).list_experiments(self.config.operations.default_channel_id)]

    def approvals(self) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for summary in self.list_runs():
            if not summary.get("review_ready"):
                continue
            run_id = summary["run_id"]
            state = self.manager.load(run_id)
            if state.creator_job_id:
                try:
                    creator_job = self.creator_jobs.load(state.creator_job_id)
                except FileNotFoundError:
                    continue
                if creator_job.status != "REVIEW" or not creator_job.qa_report or not creator_job.qa_report.passed:
                    continue
            if "approval_record" in state.artifacts or (self.manager.run_dir(run_id) / "publish" / "approval_record.json").is_file() or (self.manager.run_dir(run_id) / "publish" / "rejection_record.json").is_file():
                continue
            try:
                review = PublishingService(self.config).review(run_id)
                validation = PublishingService(self.config).validate(run_id, require_approval=False)
            except Exception:
                continue
            records.append({
                "id": f"publish:{run_id}", "kind": "publish", "action": "Publish",
                "subject": review["title"], "subject_id": run_id, "scope": f"publish:{self.config.publishing.provider}",
                "hash": validation.package_hash, "version": "publish-package-v1", "state": "pending",
                "risk": "high", "context": "MOCK" if validation.mock_artifacts else "REAL",
                "requested_at": state.updated_at, "expires_at": None, "warnings": validation.warnings,
                "creator_job_id": state.creator_job_id,
            })
        identity_root = self.config.identity.directory / "proposals"
        for payload in self._json_files(identity_root):
            if payload.get("status") != "pending":
                continue
            identifier = payload.get("id")
            records.append(self._generic_approval("identity", identifier, f"identity:{identifier}:v{payload.get('identity_version')}", payload))
        proposal_root = self.config.capability.root_dir / "skills" / "proposals"
        for payload in self._json_files(proposal_root):
            if payload.get("state") != "WAITING_APPROVAL":
                continue
            identifier = payload.get("skill_id")
            evaluation = CapabilityService(self.config).skills.load_evaluation(identifier)
            scope = f"skill:{identifier}:{evaluation.evaluation_id if evaluation else 'missing'}"
            records.append(self._generic_approval("skill", identifier, scope, payload))
        return sorted(records, key=lambda item: str(item.get("requested_at") or ""), reverse=True)

    def approval(self, approval_id: str) -> dict[str, Any]:
        for item in self.approvals():
            if item["id"] == approval_id:
                return item
        raise FileNotFoundError(approval_id)

    def approve(self, approval_id: str, *, expected_hash: str, expected_scope: str, expected_version: str, approved_by: str) -> dict[str, Any]:
        current = self.approval(approval_id)
        self._validate_approval_request(current, expected_hash, expected_scope, expected_version)
        kind, subject_id = approval_id.split(":", 1)
        if kind == "publish":
            result = PublishingService(self.config).approve(subject_id, approved_by=approved_by)
            creator_result = self._approve_creator_job(subject_id, result, approved_by)
        elif kind == "identity":
            result = IdentityService(self.config).evolution().approve(subject_id, approved_by=approved_by)
        elif kind == "skill":
            result = CapabilityService(self.config).skills.approve(subject_id, approved_by=approved_by)
        else:
            raise ControlCenterError(f"不支持的 approval kind: {kind}")
        self.security.audit.record(
            actor=approved_by,
            action="control.approval.approve",
            resource=approval_id,
            permission=Permission.WRITE_ARTIFACT,
            decision="allow",
            result="approved",
            approval_ref=approval_id,
            run_id=subject_id if kind == "publish" else None,
            context={
                "scope": expected_scope,
                "package_hash": expected_hash,
                "version": expected_version,
            },
        )
        payload = {"status": "approved", "approval_id": approval_id, "result": self._model(result)}
        if kind == "publish" and creator_result is not None:
            payload["creator_job"] = self._model(creator_result)
        return payload

    def reject(self, approval_id: str, *, expected_hash: str, expected_scope: str, expected_version: str, rejected_by: str, reason: str) -> dict[str, Any]:
        current = self.approval(approval_id)
        self._validate_approval_request(current, expected_hash, expected_scope, expected_version)
        if not rejected_by.startswith("human:"):
            raise PermissionError("rejected_by 必须以 human: 开头")
        self._authorize_write("approval.reject", approval_id)
        kind, subject_id = approval_id.split(":", 1)
        record = {"approval_id": approval_id, "kind": kind, "subject_id": subject_id, "scope": expected_scope, "hash": expected_hash, "version": expected_version, "rejected_by": rejected_by, "reason": reason, "rejected_at": datetime.now().astimezone().isoformat()}
        if kind == "publish":
            self.manager.write_json(subject_id, "publish/rejection_record.json", record)
            state = self.manager.load(subject_id)
            if state.creator_job_id:
                creator = self.creator_jobs.load(state.creator_job_id)
                if creator.status == "REVIEW":
                    self.creator_job_service.reject(
                        creator.job_id, reason=reason, rejected_by=rejected_by,
                    )
        else:
            target = self.project_root / "workspace" / "control_center" / "rejections" / f"{hashlib.sha256(approval_id.encode()).hexdigest()[:16]}.json"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        self.security.audit.record(
            actor=rejected_by,
            action="control.approval.reject",
            resource=approval_id,
            permission=Permission.WRITE_ARTIFACT,
            decision="allow",
            result="rejected",
            approval_ref=approval_id,
            run_id=subject_id if kind == "publish" else None,
            context={"scope": expected_scope, "package_hash": expected_hash, "version": expected_version, "reason": reason},
        )
        return {"status": "rejected", **record}

    def list_creator_jobs(self) -> list[dict[str, Any]]:
        return [self._creator_job_payload(job) for job in self.creator_jobs.list()]

    def creator_job(self, job_id: str) -> dict[str, Any]:
        return self._creator_job_payload(
            self.creator_jobs.load(self._safe_id(job_id, label="creator job_id"))
        )

    @staticmethod
    def _creator_job_payload(job: CreatorJob) -> dict[str, Any]:
        payload = job.model_dump(mode="json")
        if payload.get("approval_status") == "REVISION_REQUIRED":
            payload["approval_status"] = "REVISION_REQUESTED"
        return payload

    def request_creator_revision(self, job_id: str, *, actor: str, reason: str) -> dict[str, Any]:
        if not actor.startswith("human:"):
            raise PermissionError("REQUEST_REVISION requires a human actor")
        if not reason.strip():
            raise ValueError("REQUEST_REVISION requires a reason")
        self._authorize_write("creator.request_revision", job_id)
        job = self.creator_job_service.request_revision(job_id, reason=reason, requested_by=actor)
        if job.run_id:
            self.manager.write_json(
                job.run_id,
                f"publish/revision_request_{job.current_revision:04d}.json",
                job.revisions[-1].model_dump(mode="json"),
            )
        self.security.audit.record(
            actor=actor, action="control.creator.request_revision", resource=f"creator-job:{job_id}",
            permission=Permission.WRITE_ARTIFACT, decision="allow", result="revision_requested",
            run_id=job.run_id, correlation_id=job_id, context={"reason": reason, "revision": job.current_revision},
        )
        return self._creator_job_payload(job)

    def record_creator_publication(
        self,
        job_id: str,
        *,
        content_id: str,
        publication_url: str,
        published_at: datetime,
        recorded_at: datetime,
        actor: str,
        evidence_path: Path,
    ) -> dict[str, Any]:
        job = self.creator_jobs.load(self._safe_id(job_id, label="creator job_id"))
        self._authorize_write("creator.record_publication", job_id)
        resolved_evidence = evidence_path.resolve()
        if job.run_id:
            run_root = self.manager.run_dir(job.run_id).resolve()
            if not resolved_evidence.is_relative_to(run_root):
                raise PermissionError("publication evidence must remain inside the bound run directory")
        receipt = BilibiliPublicationReceipt(
            content_id=content_id,
            publication_url=publication_url,
            published_at=published_at,
            recorded_at=recorded_at,
            recorded_by=actor,
            source="manual_handoff",
            evidence_path=resolved_evidence,
        )
        updated = self.creator_job_service.record_publication(job_id, receipt)
        self.security.audit.record(
            actor=actor, action="control.creator.record_publication", resource=f"creator-job:{job_id}",
            permission=Permission.PUBLISH, decision="allow", result="published_receipt_recorded",
            approval_ref=job.approval_ref, correlation_id=job_id, run_id=job.run_id,
            context={"platform": "bilibili", "content_id": content_id},
        )
        return updated.model_dump(mode="json")

    def record_creator_observation(
        self,
        job_id: str,
        *,
        observed_at: datetime,
        values: dict[str, int | None],
        availability: dict[str, str],
        evidence_path: Path,
        actor: str,
    ) -> dict[str, Any]:
        job = self.creator_jobs.load(self._safe_id(job_id, label="creator job_id"))
        self._authorize_write("creator.record_observation", job_id)
        resolved_evidence = self._guard_creator_evidence(job, evidence_path)
        observation = ContentObservation(
            content_id=job.platform_content_id or "",
            observed_at=observed_at,
            source="manual_real",
            views=values.get("views"), likes=values.get("likes"), comments=values.get("comments"),
            favorites=values.get("favorites"), shares=values.get("shares"),
            followers_delta=values.get("followers_delta"),
            availability=availability,
            evidence_path=resolved_evidence,
        )
        updated = self.creator_job_service.add_observation(job_id, observation)
        self.security.audit.record(
            actor=actor, action="control.creator.record_observation", resource=f"creator-job:{job_id}",
            permission=Permission.WRITE_ARTIFACT, decision="allow", result="observation_recorded",
            run_id=job.run_id, correlation_id=job_id,
            context={"observed_at": observed_at.isoformat(), "availability": availability},
        )
        return updated.model_dump(mode="json")

    def record_creator_reflection(self, job_id: str, *, actor: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not actor.startswith("human:"):
            raise PermissionError("reflection recording requires a human actor")
        self._authorize_write("creator.record_reflection", job_id)
        reflection = CreatorReflection.model_validate(payload)
        updated = self.creator_job_service.set_reflection(job_id, reflection)
        self.security.audit.record(
            actor=actor, action="control.creator.record_reflection", resource=f"creator-job:{job_id}",
            permission=Permission.WRITE_ARTIFACT, decision="allow", result="reflection_recorded",
            run_id=updated.run_id, correlation_id=job_id,
            context={"facts": len(reflection.facts), "interpretations": len(reflection.interpretations)},
        )
        return updated.model_dump(mode="json")

    def integrate_creator_memory(self, job_id: str, *, actor: str) -> dict[str, Any]:
        self._authorize_write("creator.memory.integrate", job_id)
        job = self.creator_jobs.load(self._safe_id(job_id, label="creator job_id"))
        updated = CreatorMemoryIntegrator(self.config.learning.memory_dir).record(job, self.creator_jobs)
        self.security.audit.record(
            actor=actor, action="control.creator.memory_integrate", resource=f"creator-job:{job_id}",
            permission=Permission.WRITE_ARTIFACT, decision="allow", result="episodic_memory_written",
            run_id=job.run_id, correlation_id=job_id, context={"memory_refs": len(updated.memory_refs)},
        )
        return updated.model_dump(mode="json")

    def upsert_creator_beta_evidence(self, job_id: str, *, evidence_path: Path, actor: str) -> dict[str, Any]:
        job = self.creator_jobs.load(self._safe_id(job_id, label="creator job_id"))
        self._authorize_write("creator.beta_evidence", job_id)
        resolved_evidence = self._guard_creator_evidence(job, evidence_path)
        ledger = BetaEvidenceLedger(self.config.creator_loop.beta_evidence_file)
        ledger.upsert(job, evidence_path=resolved_evidence)
        self.security.audit.record(
            actor=actor, action="control.creator.beta_evidence", resource=f"creator-job:{job_id}",
            permission=Permission.WRITE_ARTIFACT, decision="allow", result="beta_evidence_upserted",
            run_id=job.run_id, correlation_id=job_id,
            context={"qualified_count": ledger.qualified_count()},
        )
        return {"job_id": job_id, "qualified_count": ledger.qualified_count(), "ledger": str(ledger.path)}

    def _guard_creator_evidence(self, job: Any, evidence_path: Path) -> Path:
        resolved = evidence_path.resolve()
        if job.run_id:
            run_root = self.manager.run_dir(job.run_id).resolve()
            if not resolved.is_relative_to(run_root):
                raise PermissionError("creator evidence must remain inside the bound run directory")
        if not resolved.is_file() or resolved.stat().st_size == 0:
            raise FileNotFoundError(f"creator evidence is missing: {resolved}")
        return resolved

    def _approve_creator_job(self, run_id: str, publish_job: Any, approved_by: str):
        try:
            state = self.manager.load(run_id)
        except FileNotFoundError:
            return None
        if not state.creator_job_id:
            return None
        creator = self.creator_jobs.load(state.creator_job_id)
        if creator.status == "PUBLISH_READY":
            return creator
        if creator.status != "REVIEW":
            raise ControlCenterError(f"CreatorJob is not REVIEW: {creator.status}")
        package_hash = getattr(publish_job, "package_hash", None)
        approval = getattr(publish_job, "approval_record", None)
        if not package_hash:
            raise ControlCenterError("PublishJob did not return package_hash")
        creator = self.creator_job_service.approve(
            creator.job_id,
            approved_by=approved_by,
            package_hash=package_hash,
            approval_ref=getattr(approval, "approval_id", None),
        )
        return self.creator_job_service.mark_publish_ready(
            creator.job_id,
            package_path=self.manager.run_dir(run_id) / "publish" / "bilibili_handoff.json",
        )

    def capabilities(self) -> list[Any]:
        return [self._model(item) for item in CapabilityService(self.config).list_capabilities()]

    def skills(self) -> list[Any]:
        return [self._model(item) for item in CapabilityService(self.config).skills.registry.list()]

    def workflows(self) -> list[Any]:
        output: list[Any] = []
        for directory in sorted(self.manager.runs_dir.glob("workflow_*")):
            path = directory / "workflow" / "workflow_plan.json"
            if path.is_file():
                output.append(json.loads(path.read_text(encoding="utf-8")))
        return output

    def workflow_recipes(self) -> list[Any]:
        store = WorkflowRecipeStore(self.config.workflow.recipe_dir, validation_successes=self.config.workflow.recipe_validation_successes)
        return [self._model(item) for item in store.list()]

    def audit(self) -> list[Any]:
        return [item.model_dump(mode="json") for item in self.security.audit.list()][-500:]

    def errors(self) -> list[Any]:
        return [item for run in self.list_runs() for item in self.run_detail(run["run_id"]).get("failures", [])][-500:]

    def _artifact_path(self, state: RunState, key: str) -> Path:
        relative = state.artifacts.get(key)
        if not relative:
            raise FileNotFoundError(f"artifact key 不存在：{key}")
        root = self.manager.run_dir(state.run_id).resolve()
        path = (root / relative).resolve()
        if not path.is_relative_to(root):
            raise PermissionError("artifact 路径越界")
        return path

    def _timeline(self, state: RunState) -> list[dict[str, Any]]:
        completed = set(state.completed_stages)
        result: list[dict[str, Any]] = []
        for label, stages in _TIMELINE:
            status = "completed" if any(stage in completed for stage in stages) else "pending"
            if state.failed_stage in stages or (state.current_stage == Stage.FAILED and state.failed_stage in stages):
                status = "failed"
            elif state.current_stage in stages and status != "completed":
                status = "waiting_approval" if state.current_stage in {Stage.READY_FOR_REVIEW, Stage.PUBLISH_APPROVAL} else "running"
            failures = self.reliability.failures(state.run_id).list(run_id=state.run_id)
            if any(item.stage in {stage.value for stage in stages} and item.status == "recovering" for item in failures):
                status = "recovering"
            result.append({"label": label, "status": status, "stages": [stage.value for stage in stages]})
        return result

    def _qa_reports(self, state: RunState) -> list[dict[str, Any]]:
        reports = []
        for key, relative in state.artifacts.items():
            if "qa" not in key:
                continue
            path = self.manager.run_dir(state.run_id) / relative
            if path.is_file() and path.suffix.lower() == ".json":
                reports.append({"key": key, "report": self.security.redactor.redact_value(json.loads(path.read_text(encoding="utf-8")))})
        return reports

    def _authorize_write(self, action: str, resource: str) -> None:
        self.security.policy.enforce(actor="ControlCenterAdapter", permission=Permission.WRITE_ARTIFACT, resource=resource, action=action, correlation_id=resource)

    @staticmethod
    def _artifact_kind(suffix: str) -> str:
        if suffix in {".mp4", ".webm"}:
            return "video"
        if suffix in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
            return "image"
        if suffix in {".wav"}:
            return "audio"
        if suffix in {".json", ".jsonl"}:
            return "json"
        return "text"

    @staticmethod
    def _run_testing(state: RunState) -> bool:
        snapshot = state.config_snapshot
        values = [((snapshot.get("llm") or {}).get("provider")), ((snapshot.get("research") or {}).get("provider")), ((snapshot.get("tts") or {}).get("provider")), ((snapshot.get("video") or {}).get("renderer"))]
        return (
            bool(snapshot.get("testing"))
            or str(snapshot.get("environment", "")).lower() in {"mock", "testing", "simulation"}
            or any(value in {"mock", "testing"} for value in values)
            or bool(state.planning_provenance and state.planning_provenance.get("testing"))
        )

    def _generic_approval(self, kind: str, identifier: str, scope: str, payload: dict[str, Any]) -> dict[str, Any]:
        digest = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()
        return {"id": f"{kind}:{identifier}", "kind": kind, "action": kind.title(), "subject": identifier, "subject_id": identifier, "scope": scope, "hash": digest, "version": str(payload.get("version") or payload.get("identity_version") or payload.get("updated_at") or "1"), "state": "pending", "risk": payload.get("risk", "medium"), "context": "REAL", "requested_at": payload.get("created_at") or payload.get("updated_at"), "expires_at": None, "warnings": []}

    @staticmethod
    def _validate_approval_request(current: dict[str, Any], expected_hash: str, expected_scope: str, expected_version: str) -> None:
        errors = []
        if current["hash"] != expected_hash:
            errors.append("approval_artifact_hash_mismatch")
        if current["scope"] != expected_scope:
            errors.append("approval_scope_mismatch")
        if current["version"] != expected_version:
            errors.append("approval_version_mismatch")
        if errors:
            raise PermissionError("approval_invalid: " + ",".join(errors))

    @staticmethod
    def _json_files(directory: Path) -> list[dict[str, Any]]:
        if not directory.is_dir():
            return []
        output = []
        for path in sorted(directory.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(payload, dict):
                output.append(payload)
        return output
