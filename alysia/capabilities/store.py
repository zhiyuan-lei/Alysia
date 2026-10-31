from __future__ import annotations

from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel

from alysia.core.io import atomic_write_json

ModelT = TypeVar("ModelT", bound=BaseModel)


def atomic_json(path: Path, payload: Any) -> Path:
    """兼容旧导入；统一委托到带 flush/fsync 的 core helper。"""
    return atomic_write_json(path, payload)


def load_models(directory: Path, model: type[ModelT]) -> list[ModelT]:
    if not directory.is_dir():
        return []
    return [model.model_validate_json(path.read_text(encoding="utf-8")) for path in sorted(directory.glob("*.json"))]
