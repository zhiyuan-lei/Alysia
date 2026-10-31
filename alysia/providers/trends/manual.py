from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from alysia.providers.trends.base import BaseTrendProvider, deduplicate_trends
from alysia.schemas import TrendItem


class ManualTrendProvider(BaseTrendProvider):
    source_kind = "manual"

    def __init__(self, source_file: Path) -> None:
        self.source_file = source_file

    def gather(self, *, max_items: int, freshness_days: int) -> list[TrendItem]:
        rows = self._read_rows()
        items = [self._to_item(row) for row in rows]
        eligible = [
            item for item in items if item.freshness_days is None or item.freshness_days <= freshness_days
        ]
        return deduplicate_trends(eligible)[:max_items]

    def _read_rows(self) -> list[dict[str, Any]]:
        if self.source_file.suffix.casefold() == ".json":
            payload = json.loads(self.source_file.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                payload = payload.get("items", [])
            if not isinstance(payload, list):
                raise ValueError("趋势 JSON 必须是数组或包含 items 数组")
            return [dict(row) for row in payload]
        if self.source_file.suffix.casefold() == ".csv":
            with self.source_file.open("r", encoding="utf-8-sig", newline="") as stream:
                return [dict(row) for row in csv.DictReader(stream)]
        raise ValueError("趋势导入仅支持 JSON 或 CSV")

    def _to_item(self, row: dict[str, Any]) -> TrendItem:
        now = datetime.now().astimezone()
        topic = str(row.get("topic") or "").strip()
        source = str(row.get("source") or "").strip()
        if not topic or not source:
            raise ValueError("每条趋势必须包含 topic 和 source")
        published_at = row.get("published_at") or None
        freshness = row.get("freshness_days")
        if freshness in (None, "") and published_at:
            parsed = datetime.fromisoformat(str(published_at).replace("Z", "+00:00"))
            freshness = max(0.0, (now - parsed.astimezone()).total_seconds() / 86400)
        keywords = row.get("keywords") or []
        if isinstance(keywords, str):
            keywords = [part.strip() for part in keywords.split(",") if part.strip()]
        digest = hashlib.sha256(f"{source}|{topic}".encode("utf-8")).hexdigest()[:12]
        popularity = row.get("popularity_hint")
        if popularity == "":
            popularity = None
        return TrendItem(
            id=str(row.get("id") or f"manual_{digest}"),
            topic=topic,
            source=source,
            source_kind="manual",
            url=row.get("url") or None,
            published_at=published_at,
            observed_at=row.get("observed_at") or now,
            popularity_hint=popularity,
            summary=str(row.get("summary") or ""),
            keywords=keywords,
            category=str(row.get("category") or "未分类"),
            confidence=float(row.get("confidence") or 0.5),
            freshness_days=float(freshness) if freshness not in (None, "") else None,
        )
