from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping

import yaml

from alysia.schemas.security import CredentialReference, Permission, SecurityActionError


class CredentialUnavailableError(RuntimeError):
    pass


class CredentialReferenceStore:
    def __init__(self, path: Path) -> None:
        self.path = path.resolve()

    def list(self) -> list[CredentialReference]:
        if not self.path.is_file():
            return []
        payload = yaml.safe_load(self.path.read_text(encoding="utf-8")) or {}
        return [CredentialReference.model_validate(item) for item in payload.get("credentials", [])]

    def get(self, credential_id: str) -> CredentialReference:
        for reference in self.list():
            if reference.credential_id == credential_id:
                return reference
        raise KeyError(f"credential reference 不存在：{credential_id}")


class CredentialResolver:
    """Resolves references at runtime only. Returned values must never be persisted."""

    def __init__(self, store: CredentialReferenceStore, enforcer, *, runtime_values: Mapping[str, Mapping[str, str]] | None = None) -> None:
        self.store = store
        self.enforcer = enforcer
        self.runtime_values = dict(runtime_values or {})

    def resolve(self, credential_id: str, *, actor: str, correlation_id: str | None = None) -> dict[str, str]:
        decision = self.enforcer.authorize(
            actor=actor, permission=Permission.READ_CREDENTIAL_REF,
            resource=f"credential-ref:{credential_id}", action="credential.lookup",
            correlation_id=correlation_id,
        )
        if decision.decision != "allow":
            raise SecurityActionError(decision)
        reference = self.store.get(credential_id)
        if reference.source_type == "env":
            values = {name: os.environ.get(name, "") for name in reference.key_names}
        elif reference.source_type == "manual_runtime_ref":
            values = dict(self.runtime_values.get(credential_id, {}))
        else:
            raise CredentialUnavailableError("os_store_ref 仅保留接口，Alpha20 未实现系统凭证库读取")
        missing = [name for name in reference.key_names if not values.get(name)]
        if missing:
            raise CredentialUnavailableError("credential_unavailable: " + ", ".join(missing))
        return {name: values[name] for name in reference.key_names}
