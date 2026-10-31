from __future__ import annotations

from pathlib import Path

import yaml

from alysia.schemas import NarrativeFramework


class NarrativeLibrary:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def load_all(self) -> list[NarrativeFramework]:
        if not self.root.is_dir():
            raise FileNotFoundError(f"叙事模板目录不存在：{self.root}")
        frameworks = [
            NarrativeFramework.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")) or {})
            for path in sorted(self.root.glob("*.yaml"))
        ]
        identifiers = [item.id for item in frameworks]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("叙事模板 id 必须唯一")
        return frameworks
