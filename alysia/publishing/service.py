from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path

from alysia.core.config import AlysiaConfig
from alysia.core.run import RunManager, RunState
from alysia.core.state import Stage
from alysia.planning import PlanStore
from alysia.providers.publishing import (
    BilibiliPublishingProvider,
    MockPublishingProvider,
    PublishingProviderError,
)
from alysia.publishing.security import redact_credentials
from alysia.publishing.store import PublishStore
from alysia.security import SecurityService
from alysia.schemas import (
    ApprovalBoundAction,
    ApprovalRecord,
    PublishJob,
    PublishPackage,
    PublishQAReport,
    PublishValidationReport,
    VideoQAReport,
)
from alysia.schemas.security import Permission


class PublishingValidationError(RuntimeError):
    pass


class PublishingService:
    def __init__(self, config: AlysiaConfig) -> None:
        if config.publishing.save_credentials:
            raise ValueError("publishing.save_credentials 必须保持 false")
        self.config = config
        self.manager = RunManager(config.runtime.runs_dir)
        self.store = PublishStore(config.publishing.workspace_dir)
        self.security = SecurityService(config)

    def review(self, run_id: str) -> dict[str, object]:
        state, package = self._load_ready_package(run_id)
        publish_qa = self._load_model(state, "publish_qa_report", PublishQAReport)
        self._sync_creator_loop(state, "publish_approval")
        return {
            "run_id": run_id,
            "video": str(self.manager.run_dir(run_id) / package.video_path),
            "cover": str(self.manager.run_dir(run_id) / package.cover_path),
            "title": package.title,
            "description": package.description,
            "tags": package.tags,
            "qa": publish_qa.model_dump(mode="json"),
            "risk_warnings": list(publish_qa.warnings),
            "approval_required": self.config.publishing.require_approval,
        }

    def approve(self, run_id: str, *, approved_by: str = "human", note: str | None = None) -> PublishJob:
        provider = self.config.publishing.provider
        preflight = self.validate(run_id, provider=provider, require_approval=False)
        if preflight.errors:
            raise PublishingValidationError("发布包存在硬错误：" + "; ".join(preflight.errors))
        approval = ApprovalRecord(
            action_type="publish",
            subject_id=run_id,
            run_id=run_id,
            approved_by=approved_by,
            approved_at=datetime.now().astimezone(),
            package_hash=preflight.package_hash,
            scope=[f"publish:{provider}"],
            accepted_warnings=preflight.warnings,
            note=note,
        )
        self.manager.write_json(run_id, "publish/approval_record.json", approval.model_dump(mode="json"))
        state = self.manager.load(run_id)
        state.artifacts["approval_record"] = "publish/approval_record.json"
        state.complete_stage(Stage.PUBLISH_APPROVAL)
        state.pipeline_phase = "publish_approved"
        state.milestone = "publish_approved"
        self.manager.save(state)
        job = self._ensure_job(state, provider, preflight.package_hash, approval)
        job.status = "approved"
        job.updated_at = datetime.now().astimezone()
        self.store.save(job)
        state.publish_job_id = job.job_id
        self.manager.save(state)
        self._sync_creator_loop(state, "publish_job")
        return job

    def validate(
        self,
        run_id: str,
        *,
        provider: str | None = None,
        require_approval: bool | None = None,
    ) -> PublishValidationReport:
        selected_provider = provider or self.config.publishing.provider
        if selected_provider not in {"mock", "bilibili"}:
            raise ValueError(f"不支持的 publishing provider：{selected_provider}")
        state, package = self._load_ready_package(run_id)
        errors: list[str] = []
        checks: dict[str, bool] = {}
        run_dir = self.manager.run_dir(run_id)
        package_hash = self._package_hash(state, package)

        checks["review_ready"] = state.review_ready
        checks["package_exists"] = self.manager.artifact_exists(state, "publish_package")
        checks["cover_exists"] = (run_dir / package.cover_path).is_file()
        checks["video_exists"] = (run_dir / package.video_path).is_file()
        checks["metadata_exists"] = self.manager.artifact_exists(state, "publish_metadata")
        for label, passed in checks.copy().items():
            if not passed:
                errors.append(f"发布检查失败：{label}")

        video_qa = self._load_model(state, "video_qa_report", VideoQAReport)
        publish_qa = self._load_model(state, "publish_qa_report", PublishQAReport)
        checks["video_qa_passed"] = video_qa.passed
        checks["publish_qa_passed"] = publish_qa.passed
        if not video_qa.passed:
            errors.append("video QA 未通过")
        if not publish_qa.passed:
            errors.append("publish QA 未通过")

        mock_artifacts = self._mock_artifacts(state)
        checks["mock_artifacts_allowed"] = not mock_artifacts or selected_provider == "mock"
        if mock_artifacts and selected_provider != "mock":
            errors.append("真实发布禁止包含 mock/testing 产物：" + ", ".join(mock_artifacts))

        warnings = list(dict.fromkeys(publish_qa.warnings + (["当前包包含 mock/testing 产物"] if mock_artifacts else [])))
        approval = self._load_approval(state)
        approval_required = self.config.publishing.require_approval if require_approval is None else require_approval
        checks["approval_present"] = approval is not None
        checks["package_hash_matches_approval"] = bool(approval and approval.package_hash == package_hash)
        approval_action = ApprovalBoundAction(
            action_type="publish", subject_id=run_id, artifact_hash=package_hash,
            required_scope=f"publish:{selected_provider}",
            consumption_ref=self._job_id(run_id, selected_provider, package_hash),
        )
        approval_validation = self.security.policy.approvals.validate(approval, approval_action)
        checks["approval_action_scope_valid"] = approval_validation.valid
        unresolved = warnings if approval is None else [item for item in warnings if item not in approval.accepted_warnings]
        checks["warnings_resolved"] = not unresolved
        if approval_required and approval is None:
            errors.append("缺少人工 ApprovalRecord")
        if approval_required and approval and approval.package_hash != package_hash:
            errors.append("投稿包已在审批后变化，ApprovalRecord 失效")
        if approval_required and approval and not approval_validation.valid:
            errors.append("ApprovalRecord action/scope/expiry 无效：" + ", ".join(approval_validation.errors))
        if approval_required and unresolved:
            errors.append("存在未由人工接受的 warning：" + "; ".join(unresolved))

        report = PublishValidationReport(
            run_id=run_id,
            provider=selected_provider,
            passed=not errors,
            package_hash=package_hash,
            approval_required=approval_required,
            approval_present=approval is not None,
            checks=checks,
            errors=errors,
            warnings=warnings,
            mock_artifacts=mock_artifacts,
            generated_at=datetime.now().astimezone(),
        )
        self.manager.write_json(
            run_id,
            "publish/publish_validation_report.json",
            report.model_dump(mode="json"),
        )
        state.artifacts["publish_validation_report"] = "publish/publish_validation_report.json"
        self.manager.save(state)
        return report

    def submit(self, run_id: str, *, provider: str | None = None) -> PublishJob:
        selected_provider = provider or self.config.publishing.provider
        report = self.validate(run_id, provider=selected_provider)
        if not report.passed:
            self.security.audit.record(
                actor="PublisherAgent", action="publish.submit", resource=f"run:{run_id}",
                permission=Permission.PUBLISH, decision="deny", result="publish_validation_failed",
                run_id=run_id, context={"errors": report.errors, "provider": selected_provider},
            )
            raise PublishingValidationError("发布验证未通过：" + "; ".join(report.errors))
        state, package = self._load_ready_package(run_id)
        approval = self._load_approval(state)
        if approval is None:
            raise PublishingValidationError("所有提交都必须包含 ApprovalRecord")
        job = self._ensure_job(state, selected_provider, report.package_hash, approval)
        approval_action = ApprovalBoundAction(
            action_type="publish", subject_id=run_id, artifact_hash=report.package_hash,
            required_scope=f"publish:{selected_provider}", consumption_ref=job.job_id,
        )
        self.security.policy.enforce(
            actor="PublisherAgent", permission=Permission.PUBLISH,
            resource=f"publish-job:{job.job_id}", action="publish.submit",
            approval=approval, approval_action=approval_action,
            correlation_id=job.job_id, run_id=run_id,
            context={"provider": selected_provider, "package_hash": report.package_hash},
        )
        if job.status == "submitted":
            return job
        approval = self.security.policy.approvals.consume(approval, approval_action)
        self.manager.write_json(run_id, "publish/approval_record.json", approval.model_dump(mode="json"))
        job.approval_record = approval
        job.status = "submitting"
        job.error = None
        job.updated_at = datetime.now().astimezone()
        self.store.save(job)
        try:
            provider_impl = self._provider(selected_provider, job_id=job.job_id)
            external_id = provider_impl.submit(
                job,
                package,
                video_path=self.manager.run_dir(run_id) / package.video_path,
                cover_path=self.manager.run_dir(run_id) / package.cover_path,
            )
        except Exception as exc:
            job.status = "failed"
            job.error = self.security.redactor.redact(str(exc)) if self.config.security.redact_credentials else redact_credentials(str(exc))
            job.updated_at = datetime.now().astimezone()
            self.store.save(job)
            self.security.audit.record(
                actor="PublisherAgent", action="publish.provider", resource=f"publish-job:{job.job_id}",
                permission=Permission.PUBLISH, decision="deny", result="provider_failed",
                approval_ref=approval.approval_id, correlation_id=job.job_id, run_id=run_id,
                context={"provider": selected_provider, "error": job.error},
            )
            raise PublishingProviderError(job.error) from exc
        now = datetime.now().astimezone()
        job.status = "submitted"
        job.external_id = external_id
        job.submitted_at = now
        job.updated_at = now
        self.store.save(job)
        state = self.manager.load(run_id)
        state.publish_job_id = job.job_id
        state.external_id = external_id
        self.manager.write_json(run_id, "publish/publish_job.json", job.model_dump(mode="json"))
        state.artifacts["publish_job"] = "publish/publish_job.json"
        state.complete_stage(Stage.PUBLISH_JOB)
        state.complete_stage(Stage.FEEDBACK_WAITING)
        state.pipeline_phase = "feedback_waiting"
        state.milestone = "feedback_waiting"
        self.manager.save(state)
        self.security.audit.record(
            actor="PublisherAgent", action="publish.provider", resource=f"publish-job:{job.job_id}",
            permission=Permission.PUBLISH, decision="allow", result="submitted",
            approval_ref=approval.approval_id, correlation_id=job.job_id, run_id=run_id,
            context={"provider": selected_provider, "external_id": external_id},
        )
        self._sync_creator_loop(state, "feedback_waiting")
        return job

    def status(self, job_id: str) -> PublishJob:
        return self.store.load(job_id)

    def _load_ready_package(self, run_id: str) -> tuple[RunState, PublishPackage]:
        state = self.manager.load(run_id)
        if not state.review_ready:
            raise PublishingValidationError("run 尚未达到 REVIEW_READY")
        return state, self._load_model(state, "publish_package", PublishPackage)

    def _ensure_job(
        self,
        state: RunState,
        provider: str,
        package_hash: str,
        approval: ApprovalRecord,
    ) -> PublishJob:
        job_id = self._job_id(state.run_id, provider, package_hash)
        try:
            job = self.store.load(job_id)
        except FileNotFoundError:
            now = datetime.now().astimezone()
            job = PublishJob(
                job_id=job_id,
                run_id=state.run_id,
                provider=provider,
                status="approved",
                package_path=Path(state.artifacts["publish_package"]),
                package_hash=package_hash,
                approval_record=approval,
                created_at=now,
                updated_at=now,
            )
        else:
            job.approval_record = approval
            if job.status not in {"submitted", "cancelled"}:
                job.status = "approved"
            job.updated_at = datetime.now().astimezone()
        self.store.save(job)
        return job

    @staticmethod
    def _job_id(run_id: str, provider: str, package_hash: str) -> str:
        digest = hashlib.sha256(f"{run_id}|{provider}|{package_hash}".encode("utf-8")).hexdigest()[:16]
        return f"job_{digest}"

    def _load_approval(self, state: RunState) -> ApprovalRecord | None:
        relative = state.artifacts.get("approval_record", "publish/approval_record.json")
        path = self.manager.run_dir(state.run_id) / relative
        if not path.is_file():
            return None
        return ApprovalRecord.model_validate(self.manager.read_json(state.run_id, relative))

    def _package_hash(self, state: RunState, package: PublishPackage) -> str:
        run_dir = self.manager.run_dir(state.run_id).resolve()
        relatives = [
            Path(state.artifacts["publish_package"]),
            package.video_path,
            package.cover_path,
            Path(state.artifacts["publish_metadata"]),
            Path(state.artifacts["publish_title"]),
            Path(state.artifacts["publish_description"]),
            Path(state.artifacts["publish_tags"]),
        ]
        digest = hashlib.sha256()
        for relative in sorted({item.as_posix() for item in relatives}):
            path = (run_dir / relative).resolve()
            if not path.is_relative_to(run_dir) or not path.is_file():
                raise FileNotFoundError(f"投稿包文件不存在或越界：{relative}")
            digest.update(relative.encode("utf-8"))
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
        return digest.hexdigest()

    def _mock_artifacts(self, state: RunState) -> list[str]:
        snapshot = state.config_snapshot
        checks = {
            "llm": ((snapshot.get("llm") or {}).get("provider")),
            "research": ((snapshot.get("research") or {}).get("provider")),
            "tts": ((snapshot.get("tts") or {}).get("provider")),
            "video": ((snapshot.get("video") or {}).get("renderer")),
        }
        artifacts = [name for name, value in checks.items() if value in {"mock", "testing"}]
        if state.planning_provenance and state.planning_provenance.get("testing"):
            artifacts.append("planning")
        return artifacts

    def _load_model(self, state: RunState, key: str, model: type):
        relative = state.artifacts.get(key)
        if not relative or not self.manager.artifact_exists(state, key):
            raise FileNotFoundError(f"run 缺少必需产物：{key}")
        return model.model_validate(self.manager.read_json(state.run_id, relative))

    def _provider(self, name: str, *, job_id: str):
        if name == "mock":
            return MockPublishingProvider()
        if name == "bilibili":
            credentials = self.security.credentials.resolve(
                "bilibili.official", actor="PublisherAgent", correlation_id=job_id,
            )
            return BilibiliPublishingProvider(credentials=credentials)
        raise ValueError(f"不支持的 publishing provider：{name}")

    def _sync_creator_loop(self, state: RunState, stage: str) -> None:
        if not state.planning_provenance:
            return
        channel_id = state.planning_provenance.get("channel_id") or self.config.operations.default_channel_id
        store = PlanStore(self.config.planning.plans_dir, channel_id)
        loop_state = store.load_loop_state()
        if loop_state and loop_state.active_plan_id == state.planning_provenance.get("plan_id"):
            loop_state.stage = stage
            loop_state.cycle_phase = "publish"
            loop_state.updated_at = datetime.now().astimezone()
            store.save_loop_state(loop_state)
