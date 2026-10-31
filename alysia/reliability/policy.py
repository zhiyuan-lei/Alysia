from __future__ import annotations

from datetime import datetime
from typing import Any

from alysia.schemas.reliability import FailureCategory, FailureRecord, RecoveryDecision


class RecoveryPolicyEngine:
    def __init__(
        self,
        *,
        max_retries_per_stage: int = 2,
        max_recovery_rounds: int = 3,
        exponential_backoff: bool = True,
        backoff_base_sec: float = 1.0,
        require_checkpoint_before_destructive_rebuild: bool = True,
    ) -> None:
        self.max_retries_per_stage = max_retries_per_stage
        self.max_recovery_rounds = max_recovery_rounds
        self.exponential_backoff = exponential_backoff
        self.backoff_base_sec = backoff_base_sec
        self.require_checkpoint_before_destructive_rebuild = require_checkpoint_before_destructive_rebuild

    def decide(
        self,
        failure: FailureRecord,
        *,
        current_state: Any | None = None,
        production_plan: Any | None = None,
        approved_fallbacks: list[str] | None = None,
        checkpoint_id: str | None = None,
        artifact_owner: str | None = None,
    ) -> RecoveryDecision:
        del current_state, production_plan
        fallbacks = approved_fallbacks or failure.fallback_refs
        now = datetime.now().astimezone()
        if failure.recovery_round >= self.max_recovery_rounds:
            return RecoveryDecision(
                failure_id=failure.failure_id, action="escalate_human",
                reason=f"达到 max_recovery_rounds={self.max_recovery_rounds}",
                requires_human=True, recovery_round=failure.recovery_round, decided_at=now,
            )
        if not failure.recoverable or failure.category == FailureCategory.CANCELLATION:
            return RecoveryDecision(
                failure_id=failure.failure_id, action="terminal_fail", reason="故障不可自动恢复",
                recovery_round=failure.recovery_round, decided_at=now,
            )
        if failure.category == FailureCategory.APPROVAL_WAIT:
            return RecoveryDecision(
                failure_id=failure.failure_id, action="escalate_human", reason="等待人工批准",
                requires_human=True, recovery_round=failure.recovery_round, decided_at=now,
            )
        if failure.category in {FailureCategory.APPROVAL_INVALID, FailureCategory.CREDENTIAL_UNAVAILABLE}:
            return RecoveryDecision(
                failure_id=failure.failure_id, action="escalate_human",
                reason="安全前置条件未满足；不得自动重试或放宽策略",
                requires_human=True, recovery_round=failure.recovery_round, decided_at=now,
            )
        if failure.category in {FailureCategory.PERMISSION_DENIED, FailureCategory.POLICY_VIOLATION}:
            return RecoveryDecision(
                failure_id=failure.failure_id, action="terminal_fail",
                reason="权限/策略拒绝是终止条件；Recovery 不得绕过",
                recovery_round=failure.recovery_round, decided_at=now,
            )
        if failure.category in {
            FailureCategory.DISK_LOW, FailureCategory.DISK_FULL,
            FailureCategory.MEMORY_PRESSURE, FailureCategory.GPU_MEMORY_PRESSURE,
        }:
            return RecoveryDecision(
                failure_id=failure.failure_id, action="pause_waiting_resource",
                reason="资源守卫要求暂停；不得删除用户文件或静默继续",
                requires_human=True, recovery_round=failure.recovery_round, decided_at=now,
            )
        if failure.category == FailureCategory.STATE_CORRUPT:
            action = "restore_checkpoint" if checkpoint_id else "escalate_human"
            return RecoveryDecision(
                failure_id=failure.failure_id, action=action,
                reason="状态损坏必须恢复已验证 checkpoint；没有有效副本时禁止猜测",
                checkpoint_id=checkpoint_id, requires_human=checkpoint_id is None,
                recovery_round=failure.recovery_round, decided_at=now,
            )
        if failure.category in {FailureCategory.ARTIFACT_CORRUPT, FailureCategory.ARTIFACT_MISSING}:
            if self.require_checkpoint_before_destructive_rebuild and checkpoint_id is None:
                return RecoveryDecision(
                    failure_id=failure.failure_id, action="escalate_human",
                    reason="重建前缺少 checkpoint", requires_human=True,
                    recovery_round=failure.recovery_round, decided_at=now,
                )
            return RecoveryDecision(
                failure_id=failure.failure_id, action="invalidate_artifact_and_rebuild_stage",
                reason="只失效损坏 artifact 的 owner stage 及必要下游",
                checkpoint_id=checkpoint_id, artifact_owner=artifact_owner,
                recovery_round=failure.recovery_round, decided_at=now,
            )
        if failure.category in {FailureCategory.OOM, FailureCategory.H3_ERROR, FailureCategory.COMFYUI_ERROR} and fallbacks:
            return RecoveryDecision(
                failure_id=failure.failure_id, action="use_approved_fallback",
                reason="重型视觉故障使用 ProductionPlan 明确批准的 fallback",
                fallback_ref=fallbacks[0], quality_impact="视觉质量/动态性可能降低；必须写入降级事件",
                recovery_round=failure.recovery_round, decided_at=now,
            )
        if failure.retryable and failure.retry_count < min(failure.max_retries, self.max_retries_per_stage):
            delay = self.backoff_base_sec * (2**failure.retry_count) if self.exponential_backoff else self.backoff_base_sec
            return RecoveryDecision(
                failure_id=failure.failure_id,
                action="retry_with_backoff" if delay > 0 else "retry_same_step",
                reason="故障可重试且未超过阶段上限", retry_after_sec=delay,
                recovery_round=failure.recovery_round, decided_at=now,
            )
        if artifact_owner:
            return RecoveryDecision(
                failure_id=failure.failure_id, action="rollback_to_artifact_owner",
                reason="重试已耗尽，回退给 artifact owner 定向修复", artifact_owner=artifact_owner,
                recovery_round=failure.recovery_round, decided_at=now,
            )
        return RecoveryDecision(
            failure_id=failure.failure_id, action="escalate_human",
            reason="没有安全且已批准的自动恢复路径", requires_human=True,
            recovery_round=failure.recovery_round, decided_at=now,
        )
