from __future__ import annotations

import csv
import json
from pathlib import Path

from alysia.providers.feedback.base import BaseFeedbackProvider
from alysia.schemas import FeedbackRecord


class ManualFeedbackProvider(BaseFeedbackProvider):
    name = "manual"

    def collect(self, run_id: str, external_id: str, source: Path | None = None) -> FeedbackRecord:
        if source is None or not source.is_file():
            raise FileNotFoundError(f"找不到反馈文件：{source}")
        if source.suffix.lower() == ".json":
            payload = json.loads(source.read_text(encoding="utf-8"))
        elif source.suffix.lower() == ".csv":
            with source.open("r", encoding="utf-8-sig", newline="") as stream:
                rows = list(csv.DictReader(stream))
            if len(rows) != 1:
                raise ValueError("反馈 CSV 必须且只能包含一条记录")
            payload = {key: self._parse(value) for key, value in rows[0].items() if value != ""}
        else:
            raise ValueError("反馈导入仅支持 JSON 或 CSV")
        payload.setdefault("run_id", run_id)
        payload.setdefault("external_id", external_id)
        payload.setdefault("source", "manual")
        if payload["run_id"] != run_id or payload["external_id"] != external_id:
            raise ValueError("反馈文件的 run_id/external_id 与发布映射不一致")
        return FeedbackRecord.model_validate(payload)

    @staticmethod
    def _parse(value: str) -> object:
        cleaned = value.strip()
        if cleaned.startswith("[") or cleaned.startswith("{"):
            return json.loads(cleaned)
        try:
            return float(cleaned) if "." in cleaned else int(cleaned)
        except ValueError:
            return cleaned

