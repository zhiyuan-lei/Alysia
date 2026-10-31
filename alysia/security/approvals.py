from __future__ import annotations

from datetime import datetime

from alysia.schemas import ApprovalRecord
from alysia.schemas.security import ApprovalBoundAction, ApprovalValidationResult


class ApprovalValidator:
    FORBIDDEN_APPROVERS = {"", "system", "agent", "alysia", "automation", "supervisor"}

    def validate(self, approval: ApprovalRecord | None, action: ApprovalBoundAction) -> ApprovalValidationResult:
        if approval is None:
            return ApprovalValidationResult(valid=False, errors=["approval_missing"])
        errors: list[str] = []
        approver = approval.approved_by.strip().casefold()
        if approver in self.FORBIDDEN_APPROVERS:
            errors.append("approval_not_human")
        if approval.action_type != action.action_type:
            errors.append("approval_action_mismatch")
        if approval.subject_id != action.subject_id:
            errors.append("approval_subject_mismatch")
        if action.artifact_hash is not None and approval.package_hash != action.artifact_hash:
            errors.append("approval_artifact_hash_mismatch")
        if action.required_scope not in approval.scope:
            errors.append("approval_scope_mismatch")
        now = datetime.now().astimezone()
        if approval.expires_at is not None and now >= approval.expires_at:
            errors.append("approval_expired")
        replay = approval.consumed_at is not None and approval.consumed_by != action.consumption_ref
        if replay:
            errors.append("approval_replay")
        return ApprovalValidationResult(
            valid=not errors, errors=errors, approval_ref=approval.approval_id, replay=replay,
        )

    def consume(self, approval: ApprovalRecord, action: ApprovalBoundAction) -> ApprovalRecord:
        result = self.validate(approval, action)
        if not result.valid:
            raise PermissionError("approval_invalid: " + ", ".join(result.errors))
        if approval.consumed_at is None:
            approval.consumed_at = datetime.now().astimezone()
            approval.consumed_by = action.consumption_ref or action.subject_id
        return approval
