from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from alysia.core.resources import ResourceManager
from alysia.schemas.reliability import ResourceGuardResult


class GpuBudgetBlocked(ValueError):
    """A GPU request was rejected before submission; do not retry automatically."""


class ResourceGuard:
    def __init__(
        self,
        resources: ResourceManager,
        *,
        min_disk_free_gb: float = 5.0,
        warning_disk_free_gb: float = 10.0,
        min_ram_available_mb: int = 2048,
        warning_ram_available_mb: int = 4096,
        min_vram_free_mb: int = 768,
        warning_vram_free_mb: int = 1536,
        max_task_vram_mb: int = 6144,
    ) -> None:
        self.resources = resources
        self.thresholds = {
            "min_disk_free_gb": min_disk_free_gb,
            "warning_disk_free_gb": warning_disk_free_gb,
            "min_ram_available_mb": min_ram_available_mb,
            "warning_ram_available_mb": warning_ram_available_mb,
            "min_vram_free_mb": min_vram_free_mb,
            "warning_vram_free_mb": warning_vram_free_mb,
            "max_task_vram_mb": min(max_task_vram_mb, 6144),
        }

    def check(
        self,
        target_path: Path,
        *,
        gpu_heavy: bool = False,
        comfyui_health: Any | None = None,
        estimated_output_mb: int = 0,
        estimated_peak_vram_mb: int | None = None,
        require_vram_budget: bool = False,
    ) -> ResourceGuardResult:
        probe_path = target_path.resolve()
        while not probe_path.exists() and probe_path.parent != probe_path:
            probe_path = probe_path.parent
        disk = shutil.disk_usage(probe_path)
        disk_free_gb = disk.free / (1024**3)
        ram = self.resources.probe_ram()
        vram = self.resources.probe_vram() if gpu_heavy else None
        observed: dict[str, int | float | str | bool | None] = {
            "disk_free_gb": round(disk_free_gb, 3),
            "estimated_output_mb": estimated_output_mb,
            "ram_available_mb": ram.get("available_mb") if ram else None,
            "vram_free_mb": vram.get("free_mb") if vram else None,
            "estimated_peak_vram_mb": estimated_peak_vram_mb,
            "comfyui_available": getattr(comfyui_health, "available", None) if comfyui_health is not None else None,
        }
        reasons: list[str] = []
        blocked = False
        warning = False
        if gpu_heavy and require_vram_budget:
            budget = self.thresholds["max_task_vram_mb"]
            if type(estimated_peak_vram_mb) is not int or estimated_peak_vram_mb < 0:
                blocked = True
                reasons.append("GPU 任务峰值显存未知或无效；禁止提交未经预算验证的任务")
            elif estimated_peak_vram_mb > budget:
                blocked = True
                reasons.append(f"GPU 任务预计峰值 {estimated_peak_vram_mb} MiB 超过 {budget} MiB 预算")
            if not vram or not all(key in vram for key in ("total_mb", "used_mb", "free_mb")):
                blocked = True
                reasons.append("无法读取完整 GPU 显存快照；禁止提交")
            elif type(estimated_peak_vram_mb) is int and estimated_peak_vram_mb >= 0:
                # Conservative admission: include existing desktop/model allocations.
                projected = vram["used_mb"] + estimated_peak_vram_mb
                observed["projected_total_vram_mb"] = projected
                if projected > budget or vram["free_mb"] - estimated_peak_vram_mb < self.thresholds["min_vram_free_mb"]:
                    blocked = True
                    reasons.append("当前占用加任务峰值超过显存预算或侵占保留空间；等待资源释放")
        if disk_free_gb < self.thresholds["min_disk_free_gb"] or disk.free < estimated_output_mb * 1024 * 1024:
            blocked = True
            reasons.append("磁盘空间低于执行下限；默认暂停且不删除用户文件")
        elif disk_free_gb < self.thresholds["warning_disk_free_gb"]:
            warning = True
            reasons.append("磁盘空间接近下限")
        if ram and ram["available_mb"] < self.thresholds["min_ram_available_mb"]:
            blocked = True
            reasons.append("系统可用 RAM 低于执行下限")
        elif ram and ram["available_mb"] < self.thresholds["warning_ram_available_mb"]:
            warning = True
            reasons.append("系统可用 RAM 接近下限")
        if gpu_heavy and vram and vram["free_mb"] < self.thresholds["min_vram_free_mb"]:
            blocked = True
            reasons.append("GPU VRAM 低于执行下限")
        elif gpu_heavy and vram and vram["free_mb"] < self.thresholds["warning_vram_free_mb"]:
            warning = True
            reasons.append("GPU VRAM 接近下限")
        if comfyui_health is not None and getattr(comfyui_health, "available", False) is False:
            blocked = True
            reasons.append("ComfyUI health 不可用")
        return ResourceGuardResult(
            status="blocked" if blocked else "warning" if warning else "safe",
            observed_values=observed, thresholds=self.thresholds, reasons=reasons,
            checked_at=datetime.now().astimezone(),
        )
