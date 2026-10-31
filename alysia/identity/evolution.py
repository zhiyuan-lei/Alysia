from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from alysia.identity.store import IdentityStore
from alysia.schemas import CreatorIdentity, IdentityChangeProposal
from alysia.schemas.security import Permission


class IdentityEvolutionService:
    def __init__(self, store: IdentityStore, *, require_approval: bool = True, security=None) -> None:
        self.store = store
        self.require_approval = require_approval
        self.security = security

    def propose(
        self,
        *,
        proposed_change: dict[str, Any],
        reason: str,
        evidence: list[str],
        expected_effect: str,
        risk: str,
    ) -> IdentityChangeProposal:
        current = self.store.load_current()
        proposal = IdentityChangeProposal(
            id=f"identity_change_{uuid4().hex[:12]}",
            identity_version=current.version,
            proposed_change=proposed_change,
            reason=reason,
            evidence=evidence,
            expected_effect=expected_effect,
            risk=risk,
            approval_required=True,
            created_at=datetime.now().astimezone(),
        )
        self.store.save_proposal(proposal)
        return proposal

    def approve(self, proposal_id: str, *, approved_by: str) -> CreatorIdentity:
        if not self.require_approval:
            raise ValueError("身份版本仍必须通过人工审批，不能关闭批准门")
        actor = approved_by.strip()
        if not actor or actor.casefold() in {"system", "agent", "alysia", "automation"}:
            raise ValueError("身份变更必须由明确的人工审核者批准")
        proposal = self.store.load_proposal(proposal_id)
        if self.security is not None:
            self.security.authorize_governed_change(
                actor="Supervisor", permission=Permission.MODIFY_IDENTITY,
                action_type="identity_change", subject_id=proposal_id,
                payload=proposal.model_dump(mode="json"), approved_by=actor,
                scope=f"identity:{proposal_id}:v{proposal.identity_version}",
            )
        current = self.store.load_current()
        if proposal.status == "approved":
            return current
        if proposal.identity_version != current.version:
            raise ValueError("proposal 基于旧身份版本，请重新提案")
        protected = {"version", "created_at", "updated_at"}
        if protected & proposal.proposed_change.keys():
            raise ValueError("proposal 不能直接修改版本或时间字段")
        unknown = set(proposal.proposed_change) - set(CreatorIdentity.model_fields)
        if unknown:
            raise ValueError(f"proposal 包含未知身份字段：{', '.join(sorted(unknown))}")
        payload = current.model_dump(mode="python")
        payload.update(proposal.proposed_change)
        payload["updated_at"] = datetime.now().astimezone()
        changed = CreatorIdentity.model_validate(payload)
        version = self.store.save_new_version(changed)
        proposal.status = "approved"
        proposal.approved_by = actor
        proposal.approved_at = datetime.now().astimezone()
        self.store.save_proposal(proposal)
        return version
