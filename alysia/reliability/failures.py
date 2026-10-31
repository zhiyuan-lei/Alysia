from __future__ import annotations

import errno
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from alysia.core.io import atomic_write_json
from alysia.schemas.reliability import FailureCategory, FailureRecord


class FailureClassifier:
    @staticmethod
    def classify(error: BaseException, *, stage: str = "unknown", provider: str | None = None) -> FailureCategory:
        message = str(error).lower()
        stage_value = stage.lower()
        provider_value = (provider or "").lower()
        code = getattr(error, "code", None)
        if code == "permission_denied" or "permission_denied" in message:
            return FailureCategory.PERMISSION_DENIED
        if code == "approval_invalid" or "approval_invalid" in message:
            return FailureCategory.APPROVAL_INVALID
        if "credential_unavailable" in message:
            return FailureCategory.CREDENTIAL_UNAVAILABLE
        if "policy_violation" in message:
            return FailureCategory.POLICY_VIOLATION
        if isinstance(error, TimeoutError) or "timeout" in message or "超时" in message:
            return FailureCategory.TIMEOUT
        if isinstance(error, FileNotFoundError):
            return FailureCategory.ARTIFACT_MISSING
        if isinstance(error, OSError) and getattr(error, "errno", None) == errno.ENOSPC:
            return FailureCategory.DISK_FULL
        if any(token in message for token in ("out of memory", "cuda oom", "not enough memory")):
            return FailureCategory.OOM
        if "comfyui" in provider_value or "comfyui" in message:
            return FailureCategory.COMFYUI_ERROR
        if "h3" in provider_value or "h3" in stage_value:
            return FailureCategory.H3_ERROR
        if "tts" in stage_value or "voice" in stage_value:
            return FailureCategory.TTS_ERROR
        if "asr" in stage_value or "subtitle" in stage_value:
            return FailureCategory.ASR_ERROR
        if "render" in stage_value or "ffmpeg" in message or "remotion" in message:
            return FailureCategory.RENDER_ERROR
        if any(token in message for token in ("connection refused", "unavailable", "不可达")):
            return FailureCategory.PROVIDER_UNAVAILABLE
        if any(token in message for token in ("http", "network", "connection")):
            return FailureCategory.NETWORK_ERROR
        return FailureCategory.PROVIDER_ERROR if provider else FailureCategory.UNKNOWN

    @classmethod
    def record(
        cls,
        error: BaseException,
        *,
        run_id: str | None = None,
        workflow_id: str | None = None,
        stage: str,
        provider: str | None = None,
        agent: str | None = None,
        worker: str | None = None,
        retry_count: int = 0,
        max_retries: int = 2,
        evidence_refs: list[str] | None = None,
        fallback_refs: list[str] | None = None,
    ) -> FailureRecord:
        category = cls.classify(error, stage=stage, provider=provider)
        non_retryable = category in {
            FailureCategory.CANCELLATION, FailureCategory.APPROVAL_WAIT,
            FailureCategory.PERMISSION_DENIED, FailureCategory.APPROVAL_INVALID,
            FailureCategory.CREDENTIAL_UNAVAILABLE, FailureCategory.POLICY_VIOLATION,
        }
        return FailureRecord(
            failure_id=f"failure_{uuid4().hex[:16]}",
            run_id=run_id,
            workflow_id=workflow_id,
            stage=stage,
            agent=agent,
            worker=worker,
            provider=provider,
            category=category,
            message=str(error),
            evidence_refs=evidence_refs or [],
            occurred_at=datetime.now().astimezone(),
            recoverable=category not in {
                FailureCategory.CANCELLATION, FailureCategory.PERMISSION_DENIED,
                FailureCategory.POLICY_VIOLATION,
            },
            retryable=not non_retryable,
            retry_count=retry_count,
            max_retries=max_retries,
            suggested_action="由 RecoveryPolicyEngine 生成有限恢复决策",
            fallback_refs=fallback_refs or [],
        )


class FailureStore:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, record: FailureRecord) -> Path:
        return atomic_write_json(
            self.root / f"{record.failure_id}.json",
            record.model_dump(mode="json"),
            backup_count=2,
        )

    def load(self, failure_id: str) -> FailureRecord:
        path = self.root / f"{_safe_id(failure_id)}.json"
        if not path.is_file():
            raise FileNotFoundError(path)
        return FailureRecord.model_validate_json(path.read_text(encoding="utf-8"))

    def list(self, *, run_id: str | None = None, workflow_id: str | None = None) -> list[FailureRecord]:
        records: list[FailureRecord] = []
        for path in sorted(self.root.glob("failure_*.json")):
            try:
                record = FailureRecord.model_validate_json(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if run_id is not None and record.run_id != run_id:
                continue
            if workflow_id is not None and record.workflow_id != workflow_id:
                continue
            records.append(record)
        return records


def _safe_id(value: str) -> str:
    if not value or Path(value).name != value:
        raise ValueError("failure_id 格式无效")
    return value
