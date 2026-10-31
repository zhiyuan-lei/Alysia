from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from alysia.schemas import ExecutionMetrics, FallbackRecord, StageExecutionMetric


class ExecutionMetricsStore:
    def __init__(self, run_dir: Path, *, run_id: str, plan_id: str) -> None:
        self.run_dir = run_dir.resolve()
        self.path = self.run_dir / "production" / "execution_metrics.json"
        self.run_id = run_id
        self.plan_id = plan_id

    def load(self) -> ExecutionMetrics:
        if self.path.is_file():
            existing = ExecutionMetrics.model_validate_json(self.path.read_text(encoding="utf-8"))
            if existing.plan_id == self.plan_id:
                return existing
        now = datetime.now().astimezone()
        return ExecutionMetrics(
            run_id=self.run_id,
            plan_id=self.plan_id,
            started_at=now,
            updated_at=now,
        )

    def record_stage(self, metric: StageExecutionMetric) -> ExecutionMetrics:
        metrics = self.load()
        metrics.stages.append(metric)
        metrics.updated_at = datetime.now().astimezone()
        self._save(metrics)
        return metrics

    def record_fallback(self, record: FallbackRecord) -> ExecutionMetrics:
        metrics = self.load()
        metrics.fallbacks.append(record)
        metrics.updated_at = datetime.now().astimezone()
        self._save(metrics)
        return metrics

    def _save(self, metrics: ExecutionMetrics) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(metrics.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.path)
