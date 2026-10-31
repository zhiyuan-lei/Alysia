from __future__ import annotations

from pathlib import Path

from alysia.schemas.security import ToolDecision


class ToolAllowlist:
    def __init__(self, allowed: list[str]) -> None:
        self.allowed = {item.casefold() for item in allowed}

    def check(self, actor: str, executable: str | Path, *, approved_context: bool = True) -> ToolDecision:
        name = Path(executable).stem.casefold()
        if actor == "SkillSandbox" and not approved_context:
            return ToolDecision(actor=actor, tool=name, allowed=False, reason="unapproved_skill_cannot_execute")
        allowed = name in self.allowed
        return ToolDecision(
            actor=actor, tool=name, allowed=allowed,
            reason="tool_allowlist_match" if allowed else "tool_not_allowlisted",
        )
