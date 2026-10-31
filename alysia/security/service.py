from __future__ import annotations

from pathlib import Path
import hashlib
import json
from datetime import datetime

from alysia.core.config import AlysiaConfig
from alysia.schemas.security import Permission, SecurityStatus
from alysia.schemas import ApprovalBoundAction, ApprovalRecord

from .audit import AuditLog
from .credentials import CredentialReferenceStore, CredentialResolver
from .policy import PermissionPolicyEngine
from .redaction import Redactor, SecretScanner


class SecurityService:
    def __init__(self, config: AlysiaConfig, *, runtime_credentials: dict[str, dict[str, str]] | None = None) -> None:
        self.config = config
        self.redactor = Redactor()
        self.audit = AuditLog(config.security.audit_log_path, redactor=self.redactor)
        self.policy = PermissionPolicyEngine(
            config.security.policy_file, self.audit,
            default_deny=config.security.default_deny,
            tool_allowlist=config.security.tool_allowlist,
        )
        self.credential_store = CredentialReferenceStore(config.security.credential_reference_file)
        self.credentials = CredentialResolver(
            self.credential_store, self.policy, runtime_values=runtime_credentials,
        )
        self.scanner = SecretScanner(self.redactor)

    def status(self) -> SecurityStatus:
        return SecurityStatus(
            enabled=self.config.security.enabled,
            default_deny=self.config.security.default_deny,
            policy_version=self.policy.version,
            roles=len(self.policy.roles), permissions=len(Permission),
            audit_log=self.audit.path, audit_events=len(self.audit.list()),
            credential_references=len(self.credential_store.list()),
            system_config_open_to_agents=any(
                mapping.get(Permission.SYSTEM_CONFIG.value) != "deny"
                for mapping in self.policy.roles.values()
            ),
            limitations=[
                "application-level controls only; not an OS sandbox",
                "audit log is logically append-only, not tamper-proof",
                "os_store_ref resolution is not implemented in Alpha20",
            ],
        )

    def permissions(self) -> dict[str, dict[str, str]]:
        return self.policy.permissions()

    def authorize_governed_change(
        self,
        *,
        actor: str,
        permission: Permission,
        action_type: str,
        subject_id: str,
        payload: dict,
        approved_by: str,
        scope: str,
    ) -> ApprovalRecord:
        digest = hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
        approval = ApprovalRecord(
            action_type=action_type, subject_id=subject_id, run_id=subject_id,
            approved_by=approved_by, approved_at=datetime.now().astimezone(),
            package_hash=digest, scope=[scope],
        )
        bound = ApprovalBoundAction(
            action_type=action_type, subject_id=subject_id, artifact_hash=digest,
            required_scope=scope, consumption_ref=f"{action_type}:{subject_id}",
        )
        self.policy.enforce(
            actor=actor, permission=permission, resource=f"{action_type}:{subject_id}",
            action=f"{action_type}.apply", approval=approval, approval_action=bound,
            correlation_id=subject_id, context={"payload_hash": digest},
        )
        return self.policy.approvals.consume(approval, bound)
