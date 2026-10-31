from __future__ import annotations

import hashlib
import json
import platform
import sys
from pathlib import Path

from alysia.core.config import AlysiaConfig
from alysia.schemas import EnvironmentSnapshot


def stable_json_hash(payload: object) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def file_manifest(root: Path, paths: list[Path]) -> list[dict[str, str | int]]:
    manifest: list[dict[str, str | int]] = []
    for path in sorted({item.resolve() for item in paths if item.is_file()}, key=lambda item: item.as_posix().casefold()):
        try:
            relative = path.relative_to(root.resolve()).as_posix()
        except ValueError:
            relative = path.as_posix()
        content = path.read_bytes()
        manifest.append({"path": relative, "sha256": hashlib.sha256(content).hexdigest(), "size": len(content)})
    return manifest


def worktree_fingerprint(project_root: Path) -> str:
    candidates = [path for path in (project_root / "alysia").rglob("*.py") if "__pycache__" not in path.parts]
    candidates.extend(path for path in (project_root / "tests" / "fixtures" / "evaluation").rglob("*") if path.is_file())
    candidates.extend(path for path in (project_root / "tests").glob("test_evaluation*.py") if path.is_file())
    candidates.extend(path for path in (project_root / "tests").glob("test_regression_matrix*.py") if path.is_file())
    candidates.extend(path for path in (project_root / name for name in ("pyproject.toml", "config.example.yaml")) if path.is_file())
    return stable_json_hash(file_manifest(project_root, candidates))


def fixture_manifest_hash(project_root: Path, fixture_paths: list[Path]) -> str:
    return stable_json_hash(file_manifest(project_root, fixture_paths))


def environment_snapshot(config: AlysiaConfig) -> EnvironmentSnapshot:
    snapshot = config.model_dump(mode="json")
    return EnvironmentSnapshot(
        python_version=sys.version.split()[0],
        platform=platform.platform(),
        machine=platform.machine(),
        config_hash=stable_json_hash(snapshot),
        config_snapshot=snapshot,
        hardware=config.hardware_profile.model_dump(mode="json"),
        external_services={"default_suite": "offline", "h3": "explicit_integration_only"},
    )
