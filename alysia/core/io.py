from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Callable, TypeVar


class StateRecoveryError(RuntimeError):
    def __init__(self, path: Path, errors: list[str]) -> None:
        super().__init__(f"状态无法恢复：{path}；" + "; ".join(errors))
        self.path = path
        self.errors = errors


T = TypeVar("T")


def atomic_write_text(path: Path, content: str, *, backup_count: int = 0) -> Path:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    if backup_count > 0 and path.is_file():
        _rotate_backups(path, backup_count)
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary_name = stream.name
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, path)
        _fsync_directory(path.parent)
        return path
    finally:
        if temporary_name:
            temporary = Path(temporary_name)
            if temporary.exists():
                temporary.unlink()


def atomic_write_json(path: Path, payload: Any, *, backup_count: int = 0) -> Path:
    encoded = json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n"
    return atomic_write_text(path, encoded, backup_count=backup_count)


def load_json_with_recovery(
    path: Path,
    *,
    validator: Callable[[Any], T] | None = None,
    backup_count: int = 2,
    on_recovery: Callable[[Path], None] | None = None,
) -> T | Any:
    errors: list[str] = []
    candidates = [path, *[backup_path(path, index) for index in range(1, backup_count + 1)]]
    for index, candidate in enumerate(candidates):
        if not candidate.is_file():
            errors.append(f"missing:{candidate.name}")
            continue
        try:
            payload = json.loads(candidate.read_text(encoding="utf-8"))
            value = validator(payload) if validator is not None else payload
        except (OSError, ValueError, TypeError) as exc:
            errors.append(f"invalid:{candidate.name}:{exc}")
            continue
        if index > 0:
            atomic_write_json(path, payload, backup_count=0)
            if on_recovery is not None:
                on_recovery(candidate)
        return value
    raise StateRecoveryError(path, errors)


def backup_path(path: Path, index: int) -> Path:
    return path.with_name(f"{path.name}.bak{index}")


def _rotate_backups(path: Path, backup_count: int) -> None:
    for index in range(backup_count, 1, -1):
        previous = backup_path(path, index - 1)
        current = backup_path(path, index)
        if previous.is_file():
            os.replace(previous, current)
    first = backup_path(path, 1)
    shutil.copy2(path, first)
    # Windows 的 FlushFileBuffers 要求可写 handle；append 模式不会改动内容。
    with first.open("ab") as stream:
        os.fsync(stream.fileno())


def _fsync_directory(directory: Path) -> None:
    if os.name == "nt":
        return
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
