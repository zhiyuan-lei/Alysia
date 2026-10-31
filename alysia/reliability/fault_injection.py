from __future__ import annotations

from collections.abc import Callable
from typing import Any


class FaultInjector:
    """只供显式测试构造；production 默认 disabled。"""

    def __init__(self, *, enabled: bool = False, faults: dict[str, BaseException | Callable[[], Any]] | None = None) -> None:
        self.enabled = enabled
        self.faults = faults or {}

    def trigger(self, name: str) -> None:
        if not self.enabled:
            return
        fault = self.faults.get(name)
        if fault is None:
            return
        if callable(fault):
            result = fault()
            if isinstance(result, BaseException):
                raise result
            return
        raise fault

