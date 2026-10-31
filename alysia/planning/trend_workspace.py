from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from alysia.providers.trends import ManualTrendProvider


class TrendWorkspace:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def write_template(self) -> Path:
        path = self.root / "trends_template.json"
        payload = {
            "items": [
                {
                    "topic": "",
                    "source": "",
                    "url": None,
                    "published_at": None,
                    "observed_at": None,
                    "popularity_hint": None,
                    "summary": "",
                    "keywords": [],
                    "category": "",
                    "confidence": 0.5,
                    "freshness_days": None,
                }
            ]
        }
        self._write_json(path, payload)
        return path

    def import_file(self, source: Path, *, max_items: int, freshness_days: int) -> Path:
        items = ManualTrendProvider(source).gather(max_items=max_items, freshness_days=freshness_days)
        stamp = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S_%f")
        path = self.root / f"import_{stamp}.json"
        self._write_json(path, {"source_kind": "manual", "items": [item.model_dump(mode="json") for item in items]})
        return path

    def latest_import(self) -> Path:
        files = sorted(self.root.glob("import_*.json"), reverse=True)
        if not files:
            raise FileNotFoundError("未找到已导入趋势，请先运行 trends import")
        return files[0]

    @staticmethod
    def _write_json(path: Path, payload: object) -> None:
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
        temporary.replace(path)
