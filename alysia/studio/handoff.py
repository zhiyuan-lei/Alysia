from __future__ import annotations

from alysia.studio.protocol import AgentHandoff, ArtifactRef, stable_studio_id, studio_now


class HandoffProtocol:
    @staticmethod
    def create(
        *,
        run_id: str,
        sequence: int,
        from_agent: str,
        to_agent: str,
        objective: str,
        required_inputs: list[str],
        provided_artifacts: list[ArtifactRef],
        acceptance_criteria: list[str],
        constraints: list[str],
        open_questions: list[str] | None = None,
        risks: list[str] | None = None,
    ) -> AgentHandoff:
        return AgentHandoff(
            handoff_id=stable_studio_id("handoff", run_id, str(sequence), from_agent, to_agent),
            from_agent=from_agent,
            to_agent=to_agent,
            objective=objective,
            required_inputs=required_inputs,
            provided_artifacts=provided_artifacts,
            acceptance_criteria=acceptance_criteria,
            constraints=constraints,
            open_questions=open_questions or [],
            risks=risks or [],
        )

    @staticmethod
    def accept(handoff: AgentHandoff, *, available_kinds: set[str]) -> AgentHandoff:
        if handoff.status != "pending":
            raise ValueError("只有 pending handoff 可以 accepted")
        provided = {item.kind for item in handoff.provided_artifacts} | available_kinds
        missing = [item for item in handoff.required_inputs if item not in provided and item != "topic"]
        if missing:
            return handoff.model_copy(
                update={
                    "status": "rejected",
                    "status_reason": "缺少 required_inputs：" + ", ".join(missing),
                    "updated_at": studio_now(),
                }
            )
        return handoff.model_copy(update={"status": "accepted", "updated_at": studio_now()})

    @staticmethod
    def complete(handoff: AgentHandoff) -> AgentHandoff:
        if handoff.status != "accepted":
            raise ValueError("只有 accepted handoff 可以 completed")
        return handoff.model_copy(update={"status": "completed", "updated_at": studio_now()})

    @staticmethod
    def reject(handoff: AgentHandoff, reason: str) -> AgentHandoff:
        if handoff.status not in {"pending", "accepted"}:
            raise ValueError("当前 handoff 状态不能 rejected")
        return handoff.model_copy(
            update={"status": "rejected", "status_reason": reason, "updated_at": studio_now()}
        )

    @staticmethod
    def escalate(handoff: AgentHandoff, reason: str) -> AgentHandoff:
        if handoff.status not in {"pending", "accepted"}:
            raise ValueError("当前 handoff 状态不能 escalated")
        return handoff.model_copy(
            update={"status": "escalated", "status_reason": reason, "updated_at": studio_now()}
        )

