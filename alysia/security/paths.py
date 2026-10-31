from __future__ import annotations

from pathlib import Path


class PathGuard:
    def __init__(self, allowed_roots: list[Path], *, denied_roots: list[Path] | None = None) -> None:
        self.allowed_roots = [path.resolve() for path in allowed_roots]
        self.denied_roots = [path.resolve() for path in (denied_roots or [])]

    def safe_resolve(self, value: Path | str, *, base: Path | None = None, for_write: bool = False) -> Path:
        raw = Path(value)
        if any(part == ".." for part in raw.parts):
            raise PermissionError("path_traversal_rejected")
        candidate = ((base or Path.cwd()) / raw if not raw.is_absolute() else raw).resolve()
        if any(self._within(candidate, denied) for denied in self.denied_roots):
            raise PermissionError("credential_or_denied_path_rejected")
        if not any(self._within(candidate, allowed) for allowed in self.allowed_roots):
            operation = "write" if for_write else "read"
            raise PermissionError(f"path_outside_allowlist:{operation}:{candidate}")
        return candidate

    @staticmethod
    def _within(candidate: Path, root: Path) -> bool:
        try:
            return candidate == root or candidate.is_relative_to(root)
        except (OSError, ValueError):
            return False
