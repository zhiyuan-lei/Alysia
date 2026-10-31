from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from alysia.core.io import atomic_write_text
from alysia.schemas.security import AuditEvent, Permission, PermissionDecision

from .redaction import Redactor


class AuditLog:
    """Application-level append-only logical audit log; it is not tamper-proof."""

    def __init__(self, path: Path, *, redactor: Redactor | None = None) -> None:
        self.path = path.resolve()
        self.redactor = redactor or Redactor()

    def record(
        self,
        *,
        actor: str,
        action: str,
        resource: str,
        permission: Permission,
        decision: str,
        result: str,
        approval_ref: str | None = None,
        correlation_id: str | None = None,
        run_id: str | None = None,
        workflow_id: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> AuditEvent:
        event = AuditEvent(
            event_id=f"audit_{uuid4().hex[:20]}", timestamp=datetime.now().astimezone(),
            actor=actor, action=action, resource=resource, permission=permission,
            decision=decision, approval_ref=approval_ref, result=result,
            correlation_id=correlation_id, run_id=run_id, workflow_id=workflow_id,
            redacted_context=self.redactor.redact_value(context or {}),
        )
        line = json.dumps(event.model_dump(mode="json"), ensure_ascii=False, default=str)
        existing = self.path.read_text(encoding="utf-8") if self.path.is_file() else ""
        atomic_write_text(self.path, existing + line + "\n", backup_count=2)
        return event

    def record_decision(
        self,
        decision: PermissionDecision,
        *,
        action: str,
        result: str,
        correlation_id: str | None = None,
        run_id: str | None = None,
        workflow_id: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> AuditEvent:
        return self.record(
            actor=decision.actor, action=action, resource=decision.resource,
            permission=decision.permission, decision=decision.decision,
            approval_ref=decision.approval_ref, result=result,
            correlation_id=correlation_id, run_id=run_id, workflow_id=workflow_id,
            context=context,
        )

    def list(self, *, run_id: str | None = None) -> list[AuditEvent]:
        if not self.path.is_file():
            return []
        events: list[AuditEvent] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                event = AuditEvent.model_validate_json(line)
            except ValueError:
                continue
            if run_id is None or event.run_id == run_id:
                events.append(event)
        return events
