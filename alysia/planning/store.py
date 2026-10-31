from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from alysia.schemas import ContentPlan, CreatorLoopState, PlanningQAReport


class PlanStore:
    def __init__(self, root: Path, channel_id: str = "main") -> None:
        self.root = root.resolve()
        self.channel_id = channel_id
        self.root.mkdir(parents=True, exist_ok=True)

    @property
    def loop_state_path(self) -> Path:
        if self.channel_id == "main":
            return self.root / "creator_loop_state.json"
        if not self.channel_id.replace("_", "").replace("-", "").isalnum():
            raise ValueError("channel_id 格式无效")
        return self.root / f"creator_loop_state.{self.channel_id}.json"

    def plan_dir(self, plan_id: str) -> Path:
        if not plan_id or Path(plan_id).name != plan_id:
            raise ValueError("plan_id 格式无效")
        return self.root / plan_id

    def save_artifact(self, plan_id: str, filename: str, payload: Any) -> Path:
        path = self.plan_dir(plan_id) / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        data = self._jsonable(payload)
        self._atomic_write(path, json.dumps(data, ensure_ascii=False, indent=2, default=str) + "\n")
        return path

    def read_artifact(self, plan_id: str, filename: str) -> Any:
        path = self.plan_dir(plan_id) / filename
        if not path.is_file():
            raise FileNotFoundError(f"规划产物不存在：{path}")
        return json.loads(path.read_text(encoding="utf-8"))

    def save_plan(self, plan: ContentPlan) -> None:
        self.save_artifact(plan.plan_id, "content_plan.json", plan)
        self._atomic_write(self.plan_dir(plan.plan_id) / "content_plan.md", self._to_markdown(plan))

    def load_plan(self, plan_id: str) -> ContentPlan:
        return ContentPlan.model_validate(self.read_artifact(plan_id, "content_plan.json"))

    def load_qa(self, plan_id: str) -> PlanningQAReport:
        return PlanningQAReport.model_validate(self.read_artifact(plan_id, "planning_qa_report.json"))

    def save_loop_state(self, state: CreatorLoopState) -> None:
        self._atomic_write(
            self.loop_state_path,
            json.dumps(state.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        )

    def load_loop_state(self) -> CreatorLoopState | None:
        if not self.loop_state_path.is_file():
            return None
        return CreatorLoopState.model_validate_json(self.loop_state_path.read_text(encoding="utf-8"))

    @staticmethod
    def _jsonable(payload: Any) -> Any:
        if hasattr(payload, "model_dump"):
            return payload.model_dump(mode="json")
        if isinstance(payload, list):
            return [PlanStore._jsonable(item) for item in payload]
        if isinstance(payload, tuple):
            return [PlanStore._jsonable(item) for item in payload]
        if isinstance(payload, dict):
            return {key: PlanStore._jsonable(value) for key, value in payload.items()}
        return payload

    @staticmethod
    def _to_markdown(plan: ContentPlan) -> str:
        lines = [
            f"# Content Plan {plan.plan_id}",
            "",
            f"- 来源：`{plan.source}` / `{plan.provider}`",
            f"- 测试计划：`{str(plan.testing).lower()}`",
            f"- 状态：`{plan.status}`",
            f"- 周期：{plan.horizon_days} 天",
            "",
            "| 优先级 | 日期 | 状态 | 主题 |",
            "|---:|---|---|---|",
        ]
        lines.extend(
            f"| {slot.priority} | {slot.planned_date.isoformat()} | {slot.status} | {slot.topic} |"
            for slot in plan.slots
        )
        return "\n".join(lines) + "\n"

    @staticmethod
    def _atomic_write(path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(content, encoding="utf-8", newline="\n")
        temporary.replace(path)
