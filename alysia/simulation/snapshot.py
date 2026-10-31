from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from alysia.core.config import AlysiaConfig
from alysia.production.registry import ProviderCapabilityRegistry, SystemDoctorSnapshot
from alysia.schemas import WorldStateSnapshot


class WorldStateSnapshotBuilder:
    """只汇总可观测 artifact；缺失项显式保留，不补造事实。"""

    def __init__(self, config: AlysiaConfig, project_root: Path = Path(".")) -> None:
        self.config = config
        self.project_root = project_root.resolve()

    def build(self) -> WorldStateSnapshot:
        now = datetime.now().astimezone()
        refs: dict[str, list[str]] = {}
        missing: list[str] = []
        channel_state = self._json("memory/channels/main/channel_memory.json", refs, missing, "channel_state") or {}
        goals = self._models("supervisor/goals/*.json", refs, "active_goals")
        active_goals = [item for item in goals if item.get("status") == "active"]
        metrics = self._models("memory/episodes/*.json", refs, "recent_content_metrics")[-10:]
        metric_summaries = [
            {
                "run_id": item.get("run_id"), "source": item.get("source"),
                "metrics_summary": item.get("metrics_summary", {}),
                "fingerprint_summary": item.get("fingerprint_summary", {}),
            }
            for item in metrics
        ]
        identity_path = self.project_root / "identity" / "creator_identity.yaml"
        identity: dict[str, Any] = {}
        if identity_path.is_file():
            identity = yaml.safe_load(identity_path.read_text(encoding="utf-8")) or {}
            refs["current_identity"] = [self._ref(identity_path)]
        else:
            missing.append("identity/creator_identity.yaml")
        experiments = self._models("memory/channels/main/experiments/*.json", refs, "active_experiments")
        active_experiments = [item for item in experiments if item.get("status") in {"approved", "running"}]
        doctor = SystemDoctorSnapshot.capture()
        providers = ProviderCapabilityRegistry.default(self.config, doctor).list()
        provider_health = [
            {
                "provider_id": item.provider_id,
                "health_status": item.health_status,
                "health_details": item.health_details,
                "estimated_vram_mb": item.estimated_vram_mb,
                "gpu_heavy": item.gpu_heavy,
            }
            for item in providers
        ]
        production_metrics = self._models("runs/*/production/execution_metrics.json", refs, "production_metrics")
        production_health = {
            "execution_metric_files": len(production_metrics),
            "sequential_gpu_required": self.config.production.sequential_gpu_required,
            "h3_configured": bool(
                self.config.visual_generation.h3.comfyui_dir
                and self.config.visual_generation.h3.model_path
            ),
        }
        approvals: list[dict[str, Any]] = []
        for project in self._models("supervisor/projects/*.json", refs, "supervisor_projects"):
            for run in project.get("planned_runs", []):
                if run.get("approval_status") != "approved":
                    approvals.append({"type": "content_run", "id": run.get("planned_run_id")})
        known_constraints = [
            "single GPU heavy task at a time",
            f"local VRAM planning budget={self.config.production.max_local_vram_mb} MiB",
            "simulation may not publish or write real Analytics/Memory",
        ]
        digest = hashlib.sha256(json.dumps({
            "channel": channel_state, "goals": active_goals, "metrics": metric_summaries,
            "identity": identity.get("version"), "provider_health": provider_health,
        }, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16]
        return WorldStateSnapshot(
            snapshot_id=f"world_{digest}", channel_state=channel_state,
            active_goals=active_goals, recent_content_metrics_summaries=metric_summaries,
            current_identity={
                "creator_name": identity.get("creator_name"),
                "version": identity.get("version"),
                "mission_statement": identity.get("mission_statement"),
            } if identity else {},
            active_experiments=active_experiments, production_health=production_health,
            provider_health=provider_health,
            resource_profile={
                "gpu_name": doctor.gpu_name,
                "gpu_total_vram_mb": doctor.gpu_total_vram_mb,
                "gpu_used_vram_mb": doctor.gpu_used_vram_mb,
                "ram_budget_mb": 24576,
            },
            outstanding_approvals=approvals, known_constraints=known_constraints,
            source_refs=refs, missing_sources=missing, captured_at=now,
        )

    def _json(self, relative: str, refs: dict[str, list[str]], missing: list[str], key: str) -> dict | None:
        path = self.project_root / relative
        if not path.is_file():
            missing.append(relative)
            return None
        refs[key] = [self._ref(path)]
        return json.loads(path.read_text(encoding="utf-8"))

    def _models(self, pattern: str, refs: dict[str, list[str]], key: str) -> list[dict[str, Any]]:
        paths = sorted(self.project_root.glob(pattern))
        refs[key] = [self._ref(path) for path in paths]
        result: list[dict[str, Any]] = []
        for path in paths:
            try:
                result.append(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                continue
        return result

    def _ref(self, path: Path) -> str:
        return path.resolve().relative_to(self.project_root).as_posix()

