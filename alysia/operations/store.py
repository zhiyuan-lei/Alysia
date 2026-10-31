from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from alysia.schemas import (
    AudienceModel,
    ChannelMemory,
    ContentStyleMemory,
    ContentExperiment,
    CreatorDashboard,
    MultiVideoPerformanceAnalysis,
)


class ChannelStore:
    """按 channel_id 隔离的可审计长期运营状态。"""

    def __init__(self, memory_root: Path) -> None:
        self.root = memory_root.resolve() / "channels"
        self.root.mkdir(parents=True, exist_ok=True)

    def channel_dir(self, channel_id: str) -> Path:
        if not channel_id or Path(channel_id).name != channel_id or not channel_id.replace("_", "").replace("-", "").isalnum():
            raise ValueError("channel_id 只能包含字母、数字、下划线和连字符")
        return self.root / channel_id

    def save_memory(self, memory: ChannelMemory) -> Path:
        return self._save(memory.channel_id, "channel_memory.json", memory)

    def load_memory(self, channel_id: str) -> ChannelMemory | None:
        return self._load_optional(channel_id, "channel_memory.json", ChannelMemory)

    def save_analysis(self, analysis: MultiVideoPerformanceAnalysis) -> Path:
        return self._save(analysis.channel_id, "multi_video_analysis.json", analysis)

    def load_analysis(self, channel_id: str) -> MultiVideoPerformanceAnalysis | None:
        return self._load_optional(channel_id, "multi_video_analysis.json", MultiVideoPerformanceAnalysis)

    def save_audience(self, audience: AudienceModel) -> Path:
        return self._save(audience.channel_id, "audience_model.json", audience)

    def load_audience(self, channel_id: str) -> AudienceModel | None:
        return self._load_optional(channel_id, "audience_model.json", AudienceModel)

    def save_dashboard(self, dashboard: CreatorDashboard) -> Path:
        return self._save(dashboard.channel_id, "dashboard.json", dashboard)

    def load_dashboard(self, channel_id: str) -> CreatorDashboard | None:
        return self._load_optional(channel_id, "dashboard.json", CreatorDashboard)

    def save_experiment(self, experiment: ContentExperiment) -> Path:
        return self._save(experiment.channel_id, f"experiments/{experiment.id}.json", experiment)

    def save_style_memory(self, memory: ContentStyleMemory) -> Path:
        return self._save(memory.channel_id, "content_style_memory.json", memory)

    def load_style_memory(self, channel_id: str) -> ContentStyleMemory | None:
        return self._load_optional(channel_id, "content_style_memory.json", ContentStyleMemory)

    def load_experiment(self, channel_id: str, experiment_id: str) -> ContentExperiment:
        path = self.channel_dir(channel_id) / "experiments" / f"{experiment_id}.json"
        if not path.is_file():
            raise FileNotFoundError(f"找不到 experiment：{experiment_id}")
        return ContentExperiment.model_validate_json(path.read_text(encoding="utf-8"))

    def list_experiments(self, channel_id: str) -> list[ContentExperiment]:
        directory = self.channel_dir(channel_id) / "experiments"
        if not directory.is_dir():
            return []
        return [
            ContentExperiment.model_validate_json(path.read_text(encoding="utf-8"))
            for path in sorted(directory.glob("*.json"))
        ]

    def _save(self, channel_id: str, relative: str, payload: Any) -> Path:
        path = self.channel_dir(channel_id) / relative
        data = payload.model_dump(mode="json") if hasattr(payload, "model_dump") else payload
        encoded = json.dumps(data, ensure_ascii=False, indent=2, default=str) + "\n"
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(encoded, encoding="utf-8", newline="\n")
        temporary.replace(path)
        return path

    def _load_optional(self, channel_id: str, relative: str, model: type):
        path = self.channel_dir(channel_id) / relative
        if not path.is_file():
            return None
        return model.model_validate_json(path.read_text(encoding="utf-8"))
