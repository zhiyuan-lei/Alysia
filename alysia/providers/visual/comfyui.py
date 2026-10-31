from __future__ import annotations

import copy
import json
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

from alysia.core.resources import ResourceManager
from alysia.reliability.resources import GpuBudgetBlocked, ResourceGuard
from alysia.providers.visual.base import BaseVisualGenerationProvider
from alysia.schemas.visual import (
    SceneVisualPlan,
    VisualGenerationJob,
    VisualGenerationResult,
    VisualProviderHealth,
)


class ComfyUIProvider(BaseVisualGenerationProvider):
    provider_id = "visual.comfyui"
    _submission_lock = threading.Lock()

    def __init__(
        self,
        *,
        base_url: str,
        workflow_dir: Path,
        output_dir: Path,
        timeout_sec: float = 30.0,
        job_timeout_sec: float = 7200.0,
        runtime_vram_stop_mib: int | None = None,
        runtime_ram_stop_mib: int | None = None,
        security=None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.workflow_dir = workflow_dir.resolve()
        self.output_dir = output_dir.resolve()
        self.timeout_sec = timeout_sec
        self.job_timeout_sec = job_timeout_sec
        self.runtime_vram_stop_mib = runtime_vram_stop_mib
        self.runtime_ram_stop_mib = runtime_ram_stop_mib
        self.security = security

    def load_workflow(self, workflow_id: str) -> dict[str, Any]:
        path = self.workflow_dir / f"{workflow_id}.json"
        if not path.is_file():
            raise FileNotFoundError(f"ComfyUI workflow 不存在：{path}")
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def inject_parameters(template: dict[str, Any], bindings: dict[str, Any]) -> dict[str, Any]:
        payload = copy.deepcopy(template)
        for dotted_path, value in bindings.items():
            cursor: Any = payload
            parts = dotted_path.split(".")
            for part in parts[:-1]:
                if part not in cursor or not isinstance(cursor[part], dict):
                    raise KeyError(f"workflow binding 路径不存在：{dotted_path}")
                cursor = cursor[part]
            if parts[-1] not in cursor:
                raise KeyError(f"workflow binding 字段不存在：{dotted_path}")
            cursor[parts[-1]] = value
        return payload

    def prepare_job(self, run_id: str, scene_spec: SceneVisualPlan) -> VisualGenerationJob:
        from alysia.visual.jobs import build_visual_job
        return build_visual_job(run_id, scene_spec, self.provider_id, scene_spec.generation_mode.removeprefix("h3_"))

    def workflow_payload(self, job: VisualGenerationJob) -> dict[str, Any]:
        template = self.load_workflow(job.workflow_id)
        metadata = template.get("_alysia")
        api_prompt = template.get("prompt")
        if not isinstance(metadata, dict) or metadata.get("api_format") is not True:
            raise ValueError(f"workflow {job.workflow_id} 不是 Alysia API-format workflow")
        if not isinstance(api_prompt, dict) or not api_prompt:
            raise ValueError(f"workflow {job.workflow_id} 缺少 prompt 节点图")
        prompt = job.scene.prompt
        values = self.binding_values(job, metadata)
        bindings: dict[str, Any] = {}
        for key, dotted_path in metadata.get("bindings", {}).items():
            if key in values and dotted_path:
                bindings[str(dotted_path)] = values[key]
        return self.inject_parameters(api_prompt, bindings)

    def binding_values(self, job: VisualGenerationJob, metadata: dict[str, Any]) -> dict[str, Any]:
        prompt = job.scene.prompt
        return {
            "prompt": self._prompt_text(prompt.model_dump(mode="json") if prompt else {}),
            "seed": self._seed(job),
            "duration_sec": job.scene.requested_duration_sec,
            "length": self._duration_to_frames(job.scene.requested_duration_sec),
            "width": metadata.get("defaults", {}).get("width", 608),
            "height": metadata.get("defaults", {}).get("height", 352),
            "steps": metadata.get("defaults", {}).get("steps", 6),
            "filename_prefix": f"alysia/{job.run_id}/{job.scene.scene_id}",
            "input_image": job.scene.input_image,
            "reference_images": job.scene.reference_images,
        }

    def estimated_peak_vram_mb(self, job: VisualGenerationJob) -> int | None:
        return self.load_workflow(job.workflow_id).get("_alysia", {}).get("measured_peak_vram_mb")

    def submit(self, job: VisualGenerationJob) -> str:
        with self._submission_lock:
            return self._submit_if_idle(job)

    def _submit_if_idle(self, job: VisualGenerationJob) -> str:
        self._authorize_network("comfyui.submit", job.job_id)
        guard = ResourceGuard(ResourceManager()).check(
            self.output_dir,
            gpu_heavy=True,
            estimated_peak_vram_mb=self.estimated_peak_vram_mb(job),
            require_vram_budget=True,
        )
        if guard.status == "blocked":
            raise GpuBudgetBlocked("GPU_BUDGET_BLOCKED: " + "; ".join(guard.reasons))
        queue = httpx.get(f"{self.base_url}/queue", timeout=self.timeout_sec)
        queue.raise_for_status()
        queue_state = queue.json()
        if not isinstance(queue_state, dict) or not all(
            isinstance(queue_state.get(key), list) for key in ("queue_running", "queue_pending")
        ):
            raise GpuBudgetBlocked("GPU_BUDGET_BLOCKED: 无法确认 ComfyUI 队列为空")
        if queue_state["queue_running"] or queue_state["queue_pending"]:
            raise GpuBudgetBlocked("GPU_BUDGET_BLOCKED: ComfyUI 已有任务；禁止追加 GPU 工作负载")
        response = httpx.post(
            f"{self.base_url}/prompt", json={"prompt": self.workflow_payload(job), "client_id": "alysia"},
            timeout=self.timeout_sec,
        )
        response.raise_for_status()
        return str(response.json()["prompt_id"])

    def poll(self, job: VisualGenerationJob) -> str:
        self._authorize_network("comfyui.poll", job.job_id)
        response = httpx.get(f"{self.base_url}/history/{job.job_id}", timeout=self.timeout_sec)
        response.raise_for_status()
        return "completed" if response.json().get(job.job_id) else "running"

    def generate(self, job: VisualGenerationJob) -> VisualGenerationResult:
        if self.security is not None:
            from alysia.schemas.security import Permission
            self.security.policy.enforce(
                actor="ComfyUI/H3 provider adapter", permission=Permission.GPU_EXECUTE,
                resource=f"visual-job:{job.job_id}", action="gpu.execute",
                correlation_id=job.job_id,
            )
        started = time.monotonic()
        prompt_id = self.submit(job)
        history: dict[str, Any] | None = None
        peak_vram_mib: int | None = None
        peak_ram_mib: int | None = None
        deadline = time.monotonic() + self.job_timeout_sec
        while time.monotonic() < deadline:
            if self.runtime_vram_stop_mib is not None or self.runtime_ram_stop_mib is not None:
                vram = ResourceManager.probe_vram()
                ram = ResourceManager.probe_ram()
                if vram is None or ram is None:
                    self.cancel(job)
                    raise GpuBudgetBlocked("ComfyUI 运行时资源监控不可用，已请求中断")
                peak_vram_mib = max(peak_vram_mib or 0, vram["used_mb"])
                peak_ram_mib = max(peak_ram_mib or 0, ram["used_mb"])
                if ((self.runtime_vram_stop_mib is not None and vram["used_mb"] > self.runtime_vram_stop_mib)
                        or (self.runtime_ram_stop_mib is not None and ram["used_mb"] > self.runtime_ram_stop_mib)):
                    self.cancel(job)
                    raise GpuBudgetBlocked("ComfyUI 运行时显存或内存超过预算，已请求中断")
            response = httpx.get(f"{self.base_url}/history/{prompt_id}", timeout=self.timeout_sec)
            response.raise_for_status()
            payload = response.json()
            monitor = getattr(self, "task_monitor", None)
            monitor_id = getattr(self, "task_monitor_id", None)
            if monitor is not None and monitor_id is not None:
                monitor.heartbeat(monitor_id, comfyui_prompt_id=prompt_id, queue_state="polling_history")
            if payload.get(prompt_id):
                history = payload[prompt_id]
                break
            time.sleep(1.0)
        if history is None:
            self.cancel(job)
            raise TimeoutError(f"ComfyUI job 超时：{prompt_id}")
        files: list[Path] = []
        for node in history.get("outputs", {}).values():
            for kind in ("videos", "gifs", "images"):
                for item in node.get(kind, []):
                    filename = item.get("filename")
                    subfolder = item.get("subfolder", "")
                    if filename:
                        candidate = self.output_dir / subfolder / filename
                        if candidate.is_file():
                            files.append(candidate.resolve())
        if not files:
            raise FileNotFoundError(f"ComfyUI job {prompt_id} 完成但未找到输出文件")
        return VisualGenerationResult(
            job_id=job.job_id, scene_id=job.scene.scene_id, provider=self.provider_id,
            workflow_id=job.workflow_id, workflow_version=job.workflow_version,
            output_files=files, duration_sec=job.scene.requested_duration_sec,
            resolution="unknown", generation_time_sec=time.monotonic() - started,
            seed_config={
                "comfyui_prompt_id": prompt_id,
                "requested_duration_sec": job.scene.requested_duration_sec,
                "requested_frames": self._duration_to_frames(job.scene.requested_duration_sec),
                "sampled_peak_vram_mib": peak_vram_mib,
                "sampled_peak_system_ram_mib": peak_ram_mib,
            },
            status="completed", mock=False,
        )

    def health_check(self) -> VisualProviderHealth:
        workflows: dict[str, bool] = {}
        for name in ("t2v", "i2v", "reference"):
            path = self.workflow_dir / f"{name}.json"
            valid = False
            if path.is_file():
                try:
                    payload = json.loads(path.read_text(encoding="utf-8"))
                    valid = bool(
                        payload.get("_alysia", {}).get("api_format") is True
                        and isinstance(payload.get("prompt"), dict)
                        and payload["prompt"]
                    )
                except (OSError, json.JSONDecodeError):
                    valid = False
            workflows[name] = valid
        details: list[str] = []
        available = False
        try:
            self._authorize_network("comfyui.health", None)
            response = httpx.get(f"{self.base_url}/system_stats", timeout=2.0)
            available = response.status_code == 200
            if not available:
                details.append(f"ComfyUI HTTP status={response.status_code}")
        except (httpx.HTTPError, OSError) as exc:
            details.append(f"ComfyUI API 不可达：{exc}")
        if not workflows.get("t2v", False):
            details.append("H3 T2V workflow 尚不是可执行 API-format。")
        optional_missing = [name for name in ("i2v", "reference") if not workflows.get(name, False)]
        if optional_missing:
            details.append(f"可选 H3 workflow 尚未验证：{optional_missing}")
        return VisualProviderHealth(
            provider=self.provider_id,
            available=available and workflows.get("t2v", False),
            details=details,
            workflows=workflows,
        )

    def collect_artifacts(self, job: VisualGenerationJob) -> list[str]:
        prefix = f"{job.scene.scene_id}_"
        return [str(path) for path in sorted(self.output_dir.glob(f"{prefix}*")) if path.is_file()]

    def unload(self) -> None:
        """请求 ComfyUI 释放已加载模型；失败时由后续 doctor 暴露真实状态。"""
        try:
            self._authorize_network("comfyui.unload", None)
            response = httpx.post(
                f"{self.base_url}/free",
                json={"unload_models": True, "free_memory": True},
                timeout=self.timeout_sec,
            )
            response.raise_for_status()
        except (httpx.HTTPError, OSError):
            return

    def cancel(self, job: VisualGenerationJob) -> None:
        try:
            self._authorize_network("comfyui.cancel", job.job_id)
            response = httpx.post(f"{self.base_url}/interrupt", timeout=self.timeout_sec)
            response.raise_for_status()
        except (httpx.HTTPError, OSError) as exc:
            job.error = f"ComfyUI interrupt failed: {exc}"
        job.status = "cancelled"

    @staticmethod
    def _duration_to_frames(duration_sec: float) -> int:
        raw = max(5, round(duration_sec * 24))
        return raw + (5 - (raw % 17)) % 17

    @staticmethod
    def _prompt_text(payload: dict[str, Any]) -> str:
        ordered = [
            payload.get("subject"),
            payload.get("environment"),
            payload.get("action_motion"),
            payload.get("camera"),
            payload.get("lighting_style"),
        ]
        constraints = list(payload.get("continuity_constraints") or [])
        negatives = list(payload.get("negative_constraints") or [])
        parts = [str(item).strip() for item in ordered if str(item or "").strip()]
        if constraints:
            parts.append("Continuity: " + "; ".join(str(item) for item in constraints))
        if negatives:
            parts.append("Avoid: " + "; ".join(str(item) for item in negatives))
        return ". ".join(parts)

    @staticmethod
    def _seed(job: VisualGenerationJob) -> int:
        return int(job.cache_key[:16], 16) % (2**63 - 1)

    def _authorize_network(self, action: str, correlation_id: str | None) -> None:
        if self.security is None:
            return
        decision = self.security.policy.authorize_network(
            actor="ComfyUI/H3 provider adapter", url=self.base_url,
            action=action, correlation_id=correlation_id,
        )
        if decision.decision != "allow":
            raise PermissionError(decision.reason)
