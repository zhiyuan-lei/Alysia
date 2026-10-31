from __future__ import annotations

import csv
import json
from pathlib import Path

from alysia.providers.analytics.base import BaseAnalyticsProvider
from alysia.schemas import VideoMetrics


class ManualAnalyticsProvider(BaseAnalyticsProvider):
    def load(self, run_id: str, source: Path | None = None) -> VideoMetrics:
        if source is None or not source.is_file():
            raise FileNotFoundError(f"找不到 Analytics 文件：{source}")
        if source.suffix.lower() == ".json":
            payload = json.loads(source.read_text(encoding="utf-8"))
        elif source.suffix.lower() == ".csv":
            with source.open("r", encoding="utf-8-sig", newline="") as stream:
                rows = list(csv.DictReader(stream))
            if len(rows) != 1:
                raise ValueError("CSV 必须且只能包含一条视频指标记录")
            payload = {key: self._parse_csv(value) for key, value in rows[0].items() if value != ""}
        else:
            raise ValueError("Analytics 导入仅支持 JSON 或 CSV")
        payload.setdefault("run_id", run_id)
        if payload["run_id"] != run_id:
            raise ValueError("导入文件的 run_id 与命令参数不一致")
        payload.setdefault("source", "manual")
        return VideoMetrics.model_validate(payload)

    @staticmethod
    def _parse_csv(value: str) -> object:
        cleaned = value.strip()
        if cleaned.startswith("[") or cleaned.startswith("{"):
            return json.loads(cleaned)
        if cleaned.lower() in {"true", "false"}:
            return cleaned.lower() == "true"
        try:
            return float(cleaned) if "." in cleaned else int(cleaned)
        except ValueError:
            return cleaned

