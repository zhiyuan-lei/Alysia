from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from alysia.schemas import ApprovalRecord
from alysia.schemas.security import (
    ApprovalBoundAction,
    Permission,
    PermissionDecision,
    SecurityActionError,
)

from .approvals import ApprovalValidator
from .audit import AuditLog
from .network import NetworkPolicy
from .tools import ToolAllowlist


class PermissionPolicyEngine:
    def __init__(
        self,
        policy_file: Path,
        audit: AuditLog,
        *,
        default_deny: bool = True,
        tool_allowlist: list[str] | None = None,
    ) -> None:
        self.policy_file = policy_file.resolve()
        self.audit = audit
        self.default_deny = default_deny
        self.approvals = ApprovalValidator()
        self.network = NetworkPolicy()
        self.tools = ToolAllowlist(tool_allowlist or ["ffmpeg", "ffprobe", "python", "node", "npm", "npx"])
        payload = yaml.safe_load(self.policy_file.read_text(encoding="utf-8")) if self.policy_file.is_file() else {}
        self.version = str((payload or {}).get("version") or "missing")
        self.roles: dict[str, dict[str, str]] = dict((payload or {}).get("roles") or {})

    def decide(self, *, actor: str, permission: Permission, resource: str) -> PermissionDecision:
        configured = self.roles.get(actor, {}).get(permission.value)
        value = configured if configured in {"allow", "deny", "require_approval"} else "deny"
        if permission == Permission.SYSTEM_CONFIG:
            value = "deny"
        reason = (
            "explicit_role_policy" if configured is not None
            else "default_deny" if self.default_deny
            else "missing_policy"
        )
        return PermissionDecision(
            actor=actor, permission=permission, resource=resource, decision=value,
            reason=reason, policy_refs=[f"{self.policy_file}#{self.version}:{actor}:{permission.value}"],
            timestamp=datetime.now().astimezone(),
        )

    def authorize(
        self,
        *,
        actor: str,
        permission: Permission,
        resource: str,
        action: str,
        approval: ApprovalRecord | None = None,
        approval_action: ApprovalBoundAction | None = None,
        correlation_id: str | None = None,
        run_id: str | None = None,
        workflow_id: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> PermissionDecision:
        decision = self.decide(actor=actor, permission=permission, resource=resource)
        if decision.decision == "require_approval":
            validation = self.approvals.validate(approval, approval_action) if approval_action is not None else None
            if validation is not None and validation.valid:
                decision = decision.model_copy(update={
                    "decision": "allow",
                    "reason": "valid_scoped_human_approval",
                    "approval_ref": validation.approval_ref,
                    "timestamp": datetime.now().astimezone(),
                })
            elif validation is not None:
                decision = decision.model_copy(update={
                    "reason": "approval_invalid:" + ",".join(validation.errors),
                    "approval_ref": validation.approval_ref,
                })
        result = "authorized" if decision.decision == "allow" else "awaiting_approval" if decision.decision == "require_approval" else "blocked"
        self.audit.record_decision(
            decision, action=action, result=result, correlation_id=correlation_id,
            run_id=run_id, workflow_id=workflow_id, context=context,
        )
        return decision

    def enforce(self, **kwargs) -> PermissionDecision:
        decision = self.authorize(**kwargs)
        if decision.decision != "allow":
            code = "approval_invalid" if decision.decision == "require_approval" else "permission_denied"
            raise SecurityActionError(decision, code=code)
        return decision

    def authorize_network(self, *, actor: str, url: str, action: str, correlation_id: str | None = None) -> PermissionDecision:
        network = self.network.check(actor, url)
        if not network.allowed:
            decision = PermissionDecision(
                actor=actor, permission=Permission.NETWORK_PUBLIC, resource=url, decision="deny",
                reason=network.reason, policy_refs=[f"network:{network.category}"],
                timestamp=datetime.now().astimezone(),
            )
            self.audit.record_decision(decision, action=action, result="blocked", correlation_id=correlation_id)
            return decision
        return self.authorize(
            actor=actor, permission=Permission.NETWORK_PUBLIC, resource=url,
            action=action, correlation_id=correlation_id,
            context={"network_category": network.category},
        )

    def authorize_tool(
        self,
        *,
        actor: str,
        executable: str,
        approved_context: bool,
        action: str = "tool.execute",
        correlation_id: str | None = None,
    ) -> PermissionDecision:
        tool = self.tools.check(actor, executable, approved_context=approved_context)
        if not tool.allowed:
            decision = PermissionDecision(
                actor=actor, permission=Permission.EXECUTE_LOCAL_TOOL,
                resource=f"tool:{tool.tool}", decision="deny", reason=tool.reason,
                policy_refs=["tool-allowlist"], timestamp=datetime.now().astimezone(),
            )
            self.audit.record_decision(decision, action=action, result="blocked", correlation_id=correlation_id)
            return decision
        return self.authorize(
            actor=actor, permission=Permission.EXECUTE_LOCAL_TOOL,
            resource=f"tool:{tool.tool}", action=action, correlation_id=correlation_id,
        )

    def permissions(self) -> dict[str, dict[str, str]]:
        return {role: dict(sorted(mapping.items())) for role, mapping in sorted(self.roles.items())}
