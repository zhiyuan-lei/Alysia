from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from alysia.schemas import WorkflowPlan, WorkflowState, WorkflowStep, WorkflowTask


class WorkflowExecutionError(RuntimeError):
    pass


@dataclass
class ExecutionContext:
    task: WorkflowTask
    plan: WorkflowPlan
    step: WorkflowStep
    state: WorkflowState
    implementation_id: str
    input_artifacts: dict[str, str]
    output_paths: dict[str, Path]


@dataclass
class ExecutorSpec:
    implementation_id: str
    execution_layer: str
    source_type: str
    execute: Callable[[ExecutionContext], tuple[dict[str, str], dict]]


class WorkflowExecutorRegistry:
    def __init__(self) -> None:
        self._items: dict[tuple[str, str], ExecutorSpec] = {}

    def register(self, spec: ExecutorSpec) -> None:
        self._items[(spec.source_type, spec.implementation_id)] = spec

    def get(self, source_type: str, implementation_id: str) -> ExecutorSpec:
        try:
            return self._items[(source_type, implementation_id)]
        except KeyError as exc:
            raise WorkflowExecutionError(f"没有受信任 runtime adapter：{source_type}:{implementation_id}") from exc

    @classmethod
    def controlled_defaults(cls) -> "WorkflowExecutorRegistry":
        registry = cls()
        for implementation_id, layer in {
            "scene_selection": "production", "visual_planning": "production",
            "visual_qa": "production", "editor_integration": "studio", "video_qa": "studio",
            "research": "studio", "claim_verification": "knowledge", "writer": "studio",
        }.items():
            registry.register(ExecutorSpec(implementation_id, layer, "capability", _declarative_adapter))
        registry.register(ExecutorSpec("h3_visual_generation", "production", "skill", _declarative_adapter))
        return registry


def _declarative_adapter(context: ExecutionContext) -> tuple[dict[str, str], dict]:
    """只用于 testing/sandbox 的受信任离线 adapter；production 不会伪装真实 provider。"""
    if context.task.execution_mode != "testing":
        raise WorkflowExecutionError(
            f"{context.implementation_id} 默认 adapter 仅支持 testing；production 必须注入 Studio/Production adapter"
        )
    outputs: dict[str, str] = {}
    for artifact, path in context.output_paths.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "artifact": artifact,
            "implementation_id": context.implementation_id,
            "execution_layer": context.step.execution_layer,
            "testing": True,
            "input_artifacts": context.input_artifacts,
        }
        if artifact in {"approved_visual_clip", "video_qa_report"}:
            payload["passed"] = True
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        outputs[artifact] = str(path)
    observations = {
        "adapter": "controlled_declarative_testing",
        "execution_layer": context.step.execution_layer,
        "mock": True,
    }
    if context.implementation_id == "h3_visual_generation":
        observations.update({"h3_budget_checked": True, "peak_vram_mb": "unknown", "gpu_mode": "sequential"})
    return outputs, observations
