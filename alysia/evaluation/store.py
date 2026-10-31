from __future__ import annotations

import json
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from alysia.schemas import BaselineSnapshot, EvaluationComparison, EvaluationGateResult, EvaluationRun


T = TypeVar("T", bound=BaseModel)


class EvaluationStore:
    def __init__(self, root: Path = Path("evaluation")) -> None:
        self.root = root
        self.runs_dir = root / "runs"
        self.baselines_dir = root / "baselines"
        self.comparisons_dir = root / "comparisons"
        self.gates_dir = root / "gates"

    def save_run(self, run: EvaluationRun) -> Path:
        return self._write(self.runs_dir / f"{run.evaluation_id}.json", run)

    def get_run(self, evaluation_id: str) -> EvaluationRun:
        return self._read(self.runs_dir / f"{evaluation_id}.json", EvaluationRun)

    def save_baseline(self, baseline: BaselineSnapshot) -> Path:
        return self._write(self.baselines_dir / f"{baseline.baseline_id}.json", baseline)

    def get_baseline(self, baseline_id: str) -> BaselineSnapshot:
        return self._read(self.baselines_dir / f"{baseline_id}.json", BaselineSnapshot)

    def list_baselines(self) -> list[BaselineSnapshot]:
        if not self.baselines_dir.is_dir():
            return []
        return [self._read(path, BaselineSnapshot) for path in sorted(self.baselines_dir.glob("*.json"))]

    def latest_baseline(self) -> BaselineSnapshot:
        items = self.list_baselines()
        if not items:
            raise FileNotFoundError("尚未创建 evaluation baseline")
        return max(items, key=lambda item: item.created_at)

    def save_comparison(self, comparison: EvaluationComparison) -> Path:
        return self._write(self.comparisons_dir / f"{comparison.comparison_id}.json", comparison)

    def save_gate(self, gate: EvaluationGateResult) -> Path:
        name = f"{gate.baseline_id}__{gate.evaluation_id}.json"
        return self._write(self.gates_dir / name, gate)

    @staticmethod
    def _read(path: Path, model: type[T]) -> T:
        if not path.is_file():
            raise FileNotFoundError(path)
        return model.model_validate_json(path.read_text(encoding="utf-8"))

    @staticmethod
    def _write(path: Path, model: BaseModel) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(path.suffix + ".tmp")
        # 显式 newline="\n"：默认的通用换行转换会在 Windows 上写 CRLF，
        # 让入库的 LF 产物每次重写都变成 git diff。
        with temp.open("w", encoding="utf-8", newline="\n") as stream:
            stream.write(
                json.dumps(
                    model.model_dump(mode="json"),
                    ensure_ascii=False, indent=2, sort_keys=True, default=str,
                )
            )
            stream.flush()
        temp.replace(path)
        return path
