from __future__ import annotations

from pathlib import Path

from alysia.schemas import SkillSecurityPolicy
from alysia.security.paths import PathGuard


class SkillSandbox:
    """逻辑 path/capability guard；不声称提供 OS 级安全隔离。"""

    def __init__(
        self, workspace_root: Path, sandbox_root: Path,
        policy: SkillSecurityPolicy | None = None, *, security=None,
    ) -> None:
        self.workspace_root = workspace_root.resolve()
        self.sandbox_root = sandbox_root.resolve()
        self.policy = policy or SkillSecurityPolicy()
        self.security = security
        self.sandbox_root.mkdir(parents=True, exist_ok=True)
        self.path_guard = PathGuard(
            [self.sandbox_root],
            denied_roots=[
                self.workspace_root / ".git", self.workspace_root / ".env",
                self.workspace_root / "config" / "credential_references.yaml",
                self.workspace_root / "workspace" / ".credentials",
            ],
        )

    def path_for(self, skill_id: str, relative: str = ".") -> Path:
        if not skill_id or Path(skill_id).name != skill_id:
            raise ValueError("skill_id 格式无效")
        if any(part == ".." for part in Path(relative).parts):
            if self.security is not None:
                from alysia.schemas.security import Permission
                self.security.audit.record(
                    actor="SkillSandbox", action="path.resolve",
                    resource=f"sandbox:{skill_id}", permission=Permission.WRITE_ARTIFACT,
                    decision="deny", result="path_traversal_rejected",
                    correlation_id=skill_id, context={"relative": relative},
                )
            raise PermissionError("path_traversal_rejected")
        target = self.path_guard.safe_resolve(
            self.sandbox_root / skill_id / relative, for_write=True,
        )
        self._assert_within(target, self.sandbox_root / skill_id)
        if self._is_core_source(target) and not self.policy.core_source_write_allowed:
            raise PermissionError("Skill sandbox 不允许修改 Alysia 核心 source tree")
        return target

    def assert_operation(self, *, network: bool = False, credentials: bool = False, core_write: bool = False) -> None:
        if network and not self.policy.network_allowed:
            raise PermissionError("Skill sandbox 默认禁止网络")
        if credentials and not self.policy.credentials_allowed:
            raise PermissionError("Skill sandbox 默认不提供平台凭证")
        if core_write and not self.policy.core_source_write_allowed:
            raise PermissionError("Skill sandbox 默认禁止修改核心源码")

    def initialize(self, skill_id: str) -> Path:
        path = self.path_for(skill_id)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def assert_execute(self, executable: str | Path, *, approved_skill: bool) -> None:
        if self.security is None:
            if not approved_skill:
                raise PermissionError("unapproved_skill_cannot_execute")
            return
        decision = self.security.policy.authorize_tool(
            actor="SkillSandbox", executable=str(executable), approved_context=approved_skill,
        )
        if decision.decision != "allow":
            raise PermissionError(decision.reason)

    @staticmethod
    def _assert_within(target: Path, root: Path) -> None:
        root = root.resolve()
        if target != root and root not in target.parents:
            raise PermissionError(f"Sandbox path 越界：{target}")

    def _is_core_source(self, target: Path) -> bool:
        core_roots = [self.workspace_root / "alysia", self.workspace_root / "pyproject.toml"]
        return any(target == root or (root.is_dir() and root in target.parents) for root in core_roots)
