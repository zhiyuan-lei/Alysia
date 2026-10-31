from __future__ import annotations

from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field

from alysia.creator.production import (
    ArtifactStatus,
    ProductionArtifactRegistry,
    ProductionPlan,
    ProductionPlanStore,
    ProductionStatus,
    ProductionTask,
    ProductionTaskStatus,
    production_now,
)
from alysia.creator.publisher import (
    PublishRecord,
    PublishRecordStatus,
    PublisherStore,
    RemotePublishState,
)
from alysia.schemas.security import Permission
from alysia.security.audit import AuditLog


class RecoveryClassification(str, Enum):
    SAFE_TO_RETRY = "SAFE_TO_RETRY"
    RECONCILE_FIRST = "RECONCILE_FIRST"
    MANUAL_INTERVENTION = "MANUAL_INTERVENTION"
    TERMINAL = "TERMINAL"


class RecoveryFinding(BaseModel):
    subsystem: str
    resource_id: str
    classification: RecoveryClassification
    reason: str
    action: str


class RecoveryReport(BaseModel):
    findings: list[RecoveryFinding] = Field(default_factory=list)

    def for_resource(self, resource_id: str) -> list[RecoveryFinding]:
        return [item for item in self.findings if item.resource_id == resource_id]


class CreatorRecoveryService:
    """Classify and repair persisted Alpha22 intermediate state without remote side effects."""

    def __init__(
        self,
        *,
        plans: ProductionPlanStore,
        artifacts: ProductionArtifactRegistry,
        publishers: PublisherStore | None = None,
        audit: AuditLog | None = None,
    ) -> None:
        self.plans = plans
        self.artifacts = artifacts
        self.publishers = publishers
        self.audit = audit

    def recover(self) -> RecoveryReport:
        report = RecoveryReport()
        self._audit("RECOVERY_STARTED", "creator-loop", "started")
        try:
            for plan in self.plans.plans():
                report.findings.extend(self._recover_plan(plan))
            if self.publishers is not None:
                for record in self.publishers.records():
                    finding = self._recover_publish(record)
                    if finding is not None:
                        report.findings.append(finding)
            self._audit("RECOVERY_COMPLETED", "creator-loop", "completed", findings=len(report.findings))
            return report
        except Exception as exc:
            self._audit("RECOVERY_FAILED", "creator-loop", "failed", error=type(exc).__name__)
            raise

    def _recover_plan(self, plan: ProductionPlan) -> list[RecoveryFinding]:
        findings: list[RecoveryFinding] = []
        changed = False
        for task in plan.tasks:
            finding = self._recover_task(plan, task)
            if finding is not None:
                findings.append(finding)
                changed = changed or finding.action != "NO_ACTION"
        if changed:
            statuses = {task.status for task in plan.tasks}
            if statuses <= {ProductionTaskStatus.SUCCEEDED, ProductionTaskStatus.SKIPPED}:
                plan.status = ProductionStatus.SUCCEEDED
            elif ProductionTaskStatus.PENDING in statuses or ProductionTaskStatus.READY in statuses:
                plan.status = ProductionStatus.RUNNING
            elif ProductionTaskStatus.FAILED in statuses:
                plan.status = ProductionStatus.FAILED
            else:
                plan.status = ProductionStatus.BLOCKED
            self.plans.save(plan)
        return findings

    def _recover_task(self, plan: ProductionPlan, task: ProductionTask) -> RecoveryFinding | None:
        if task.status == ProductionTaskStatus.SUCCEEDED:
            if self.artifacts.valid(task.output_refs):
                return None
            self._reset_task(task, "persisted artifact is missing, corrupt, or stale")
            return self._finding(
                "production",
                task.task_id,
                RecoveryClassification.SAFE_TO_RETRY,
                "succeeded task has no valid artifact",
                "RESET_PENDING",
            )

        if task.status == ProductionTaskStatus.RUNNING:
            if self.artifacts.valid(task.output_refs):
                task.status = ProductionTaskStatus.SUCCEEDED
                task.finished_at = production_now()
                return self._finding(
                    "production",
                    task.task_id,
                    RecoveryClassification.TERMINAL,
                    "valid manifest and artifact survived the interruption",
                    "MARK_SUCCEEDED",
                )
            orphan = self._recover_orphan(plan, task)
            if orphan is not None:
                return orphan
            self._reset_task(task, "interrupted while running")
            return self._finding(
                "production",
                task.task_id,
                RecoveryClassification.SAFE_TO_RETRY,
                "running task has no complete artifact",
                "RESET_PENDING",
            )

        if task.status == ProductionTaskStatus.FAILED:
            if bool(task.metadata.get("retryable", False)):
                if int(task.metadata.get("recovery_count", 0)) >= 1:
                    return self._finding(
                        "production",
                        task.task_id,
                        RecoveryClassification.MANUAL_INTERVENTION,
                        "startup recovery budget is exhausted",
                        "NO_ACTION",
                    )
                self._reset_task(task, "retryable failure recovered at startup")
                task.metadata["recovery_count"] = 1
                return self._finding(
                    "production",
                    task.task_id,
                    RecoveryClassification.SAFE_TO_RETRY,
                    "bounded retry budget was exhausted before restart",
                    "RESET_PENDING",
                )
            return self._finding(
                "production",
                task.task_id,
                RecoveryClassification.MANUAL_INTERVENTION,
                "non-retryable production failure",
                "NO_ACTION",
            )

        if task.status == ProductionTaskStatus.BLOCKED and task.error == "upstream dependency failed":
            if all(plan.task(ref).status in {ProductionTaskStatus.PENDING, ProductionTaskStatus.SUCCEEDED}
                   for ref in task.depends_on):
                self._reset_task(task, "upstream task is recoverable")
                return self._finding(
                    "production",
                    task.task_id,
                    RecoveryClassification.SAFE_TO_RETRY,
                    "upstream dependency was reset for recovery",
                    "RESET_PENDING",
                )
        return None

    def _recover_orphan(self, plan: ProductionPlan, task: ProductionTask) -> RecoveryFinding | None:
        directory = self.artifacts.task_dir(plan.job_id, task.task_id)
        candidates = [path for path in directory.iterdir() if path.is_file()]
        if len(candidates) != 1:
            if len(candidates) > 1:
                return self._finding(
                    "production",
                    task.task_id,
                    RecoveryClassification.MANUAL_INTERVENTION,
                    "multiple unregistered artifact candidates require selection",
                    "NO_ACTION",
                )
            return None
        artifact = self.artifacts.register(
            job_id=plan.job_id,
            task_id=task.task_id,
            artifact_type=task.task_type.value,
            path=candidates[0],
            metadata={"recovered_orphan": True},
        )
        if artifact.status == ArtifactStatus.VALID:
            task.output_refs = [artifact.artifact_id]
            task.status = ProductionTaskStatus.SUCCEEDED
            task.error = None
            task.finished_at = production_now()
            return self._finding(
                "production",
                task.task_id,
                RecoveryClassification.TERMINAL,
                "complete artifact existed before its manifest was persisted",
                "REGISTER_ARTIFACT",
            )
        self._reset_task(task, "orphan artifact failed integrity validation")
        return self._finding(
            "production",
            task.task_id,
            RecoveryClassification.SAFE_TO_RETRY,
            "orphan artifact is partial or invalid",
            "RESET_PENDING",
        )

    def _recover_publish(self, record: PublishRecord) -> RecoveryFinding | None:
        if record.status == PublishRecordStatus.SUBMITTING:
            record.status = PublishRecordStatus.UNKNOWN
            record.remote_state = RemotePublishState.UNKNOWN
            record.metadata["safe_to_retry"] = False
            self.publishers.save_record(record)  # type: ignore[union-attr]
            return self._finding(
                "publisher",
                record.publish_id,
                RecoveryClassification.RECONCILE_FIRST,
                "process stopped after remote submission began",
                "MARK_UNKNOWN",
            )
        if record.status in {PublishRecordStatus.PROCESSING, PublishRecordStatus.UNKNOWN}:
            return self._finding(
                "publisher",
                record.publish_id,
                RecoveryClassification.RECONCILE_FIRST,
                "remote outcome is not locally proven",
                "NO_SUBMIT",
            )
        if record.status == PublishRecordStatus.UPLOADING and not record.metadata.get("submission_started", False):
            record.status = PublishRecordStatus.FAILED
            record.remote_state = RemotePublishState.NOT_SUBMITTED
            record.metadata["safe_to_retry"] = True
            self.publishers.save_record(record)  # type: ignore[union-attr]
            return self._finding(
                "publisher",
                record.publish_id,
                RecoveryClassification.SAFE_TO_RETRY,
                "remote submission had not started",
                "MARK_RETRYABLE",
            )
        return None

    @staticmethod
    def _reset_task(task: ProductionTask, reason: str) -> None:
        history = list(task.metadata.get("recovery_attempt_history", []))
        history.append(task.attempt_count)
        task.metadata["recovery_attempt_history"] = history
        task.metadata["recovery_reason"] = reason
        task.status = ProductionTaskStatus.PENDING
        task.attempt_count = 0
        task.output_refs = []
        task.started_at = None
        task.finished_at = None
        task.error = None

    def _finding(
        self,
        subsystem: str,
        resource_id: str,
        classification: RecoveryClassification,
        reason: str,
        action: str,
    ) -> RecoveryFinding:
        finding = RecoveryFinding(
            subsystem=subsystem,
            resource_id=resource_id,
            classification=classification,
            reason=reason,
            action=action,
        )
        event = {
            RecoveryClassification.SAFE_TO_RETRY: "RECOVERY_RESUMED",
            RecoveryClassification.RECONCILE_FIRST: "RECOVERY_RECONCILIATION_REQUIRED",
            RecoveryClassification.MANUAL_INTERVENTION: "RECOVERY_FAILED",
            RecoveryClassification.TERMINAL: "RECOVERY_COMPLETED",
        }[classification]
        self._audit(event, resource_id, classification.value, subsystem=subsystem, action_taken=action)
        return finding

    def _audit(self, action: str, resource: str, result: str, **context: object) -> None:
        if self.audit is None:
            return
        self.audit.record(
            actor="system:recovery",
            action=action,
            resource=resource,
            permission=Permission.WRITE_ARTIFACT,
            decision="allow",
            result=result,
            context=dict(context),
        )
