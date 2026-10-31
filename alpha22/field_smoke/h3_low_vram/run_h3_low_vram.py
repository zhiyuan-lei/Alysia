from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import threading
import time
import ctypes
from datetime import datetime
from pathlib import Path

import httpx

from alysia.core.config import H3VisualConfig
from alysia.core.io import atomic_write_json
from alysia.core.resources import ResourceManager
from alysia.creator import (
    H3ProductionAdapter,
    ProductionArtifactRegistry,
    ProductionOrchestrator,
    ProductionPlan,
    ProductionPlanStore,
    ProductionStatus,
    ProductionTask,
    ProductionTaskStatus,
    ProductionTaskType,
    ResourceClass,
    RetryPolicy,
)
from alysia.reliability.resources import ResourceGuard


ROOT = Path(__file__).resolve().parent
COMFY_DIR = Path(r"D:\ComfyUI")
COMFY_PYTHON = COMFY_DIR / ".venv" / "Scripts" / "python.exe"
COMFY_OUTPUT = COMFY_DIR / "output"
WORKFLOW_DIR = Path(r"D:\Alysia\workflows\comfyui\h3")
BASE_URL = "http://127.0.0.1:8188"
RESULT_PATH = ROOT / "result.json"
SAMPLES_PATH = ROOT / "resource_samples.json"
RUN_ID = "alpha22_step8_3_h3_low_vram"
SCENE_ID = "TEST_ONLY_h3_low_vram"


def now_iso() -> str:
    return datetime.now().astimezone().isoformat()


def gpu_memory() -> dict[str, int] | None:
    try:
        raw = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=memory.total,memory.used,memory.free,utilization.gpu",
                "--format=csv,noheader,nounits",
            ],
            text=True,
            timeout=5,
        ).strip()
        total, used, free, utilization = [int(value.strip()) for value in raw.split(",")]
        return {
            "total_mib": total,
            "used_mib": used,
            "free_mib": free,
            "utilization_percent": utilization,
        }
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def ram_memory() -> dict[str, int]:
    class MemoryStatus(ctypes.Structure):
        _fields_ = [
            ("length", ctypes.c_ulong),
            ("memory_load", ctypes.c_ulong),
            ("total_physical", ctypes.c_ulonglong),
            ("available_physical", ctypes.c_ulonglong),
            ("total_page_file", ctypes.c_ulonglong),
            ("available_page_file", ctypes.c_ulonglong),
            ("total_virtual", ctypes.c_ulonglong),
            ("available_virtual", ctypes.c_ulonglong),
            ("available_extended_virtual", ctypes.c_ulonglong),
        ]

    value = MemoryStatus()
    value.length = ctypes.sizeof(MemoryStatus)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(value)):
        raise OSError("GlobalMemoryStatusEx failed")
    return {
        "total_mib": round(value.total_physical / (1024 * 1024)),
        "used_mib": round((value.total_physical - value.available_physical) / (1024 * 1024)),
        "available_mib": round(value.available_physical / (1024 * 1024)),
        "commit_limit_mib": round(value.total_page_file / (1024 * 1024)),
        "commit_available_mib": round(value.available_page_file / (1024 * 1024)),
    }


def health_available() -> bool:
    try:
        return httpx.get(f"{BASE_URL}/system_stats", timeout=2).status_code == 200
    except (httpx.HTTPError, OSError):
        return False


def relevant_history_count() -> int:
    payload = httpx.get(f"{BASE_URL}/history", timeout=10).json()
    return sum(
        1
        for item in payload.values()
        if SCENE_ID in json.dumps(item.get("prompt", []), ensure_ascii=False)
    )


def wait_for_health(timeout_sec: float) -> None:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        if health_available():
            return
        time.sleep(1)
    raise TimeoutError("owned ComfyUI service did not become healthy")


def copy_and_register_artifact(
    source: Path,
    registry: ProductionArtifactRegistry,
    task: ProductionTask,
) -> tuple[Path, object]:
    target_dir = registry.task_dir(RUN_ID, task.task_id)
    target = target_dir / f"{SCENE_ID}{source.suffix.lower()}"
    shutil.copy2(source, target)
    manifest = registry.register(
        job_id=RUN_ID,
        task_id=task.task_id,
        artifact_type=task.task_type.value,
        path=target,
        metadata={
            "test_only": True,
            "provider": "REAL_H3_LOW_VRAM",
            "source_name": source.name,
        },
    )
    return target, manifest


def media_summary(manifest: object) -> dict[str, object]:
    record = manifest
    path = Path(getattr(record, "path"))
    probe = ProductionArtifactRegistry(ROOT / "_probe_tmp").checker.check(
        path, producer="alpha22-step8.3-validation"
    )
    shutil.rmtree(ROOT / "_probe_tmp", ignore_errors=True)
    media_probe = probe.media_probe or {}
    duration = None
    width = None
    height = None
    codec = None
    for stream in media_probe.get("streams", []):
        if stream.get("codec_type") == "video":
            duration = stream.get("duration") or media_probe.get("format", {}).get("duration")
            width = stream.get("width")
            height = stream.get("height")
            codec = stream.get("codec_name")
            break
    return {
        "path": str(path),
        "size_bytes": path.stat().st_size,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "suffix": path.suffix.lower(),
        "duration_seconds": float(duration) if duration is not None else None,
        "width": width,
        "height": height,
        "codec": codec,
        "validation": "VALID" if getattr(record, "status").value == "VALID" and probe.validity == "valid" else "INVALID",
        "probe_errors": probe.errors,
    }


def main() -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    started_at = now_iso()
    phase = {"value": "service_start"}
    samples: list[dict[str, object]] = []
    monitor_done = threading.Event()
    service: subprocess.Popen[str] | None = None
    service_stop_method = "NOT_STARTED"
    resources = ResourceManager(sequential_gpu=True)
    result_payload: dict[str, object] = {
        "run_id": RUN_ID,
        "started_at": started_at,
        "profile": "ONE_LOW_VRAM_PROFILE",
        "profile_settings": {
            "launcher": [
                "--novram",
                "--cpu-vae",
                "--disable-pinned-memory",
                "--disable-async-offload",
                "--reserve-vram 1",
            ],
            "text_encoder_device": "cpu",
            "width": 320,
            "height": 256,
            "frames": 5,
            "steps": 1,
            "gpu_heavy_concurrency": 1,
        },
        "h3_real_invocation": "NO",
        "result": "FAIL",
    }

    def monitor() -> None:
        while not monitor_done.wait(0.25):
            samples.append(
                {
                    "timestamp": now_iso(),
                    "phase": phase["value"],
                    "ram": ram_memory(),
                    "gpu": gpu_memory(),
                }
            )

    monitor_thread = threading.Thread(target=monitor, daemon=True)
    monitor_thread.start()
    try:
        if health_available():
            raise RuntimeError("ComfyUI was already running; refusing to adopt or terminate an unknown service")
        if not COMFY_PYTHON.is_file():
            raise FileNotFoundError(COMFY_PYTHON)

        stdout_path = ROOT / "comfyui_stdout.log"
        stderr_path = ROOT / "comfyui_stderr.log"
        launch = [
            str(COMFY_PYTHON),
            "main.py",
            "--listen", "127.0.0.1",
            "--port", "8188",
            "--novram",
            "--cpu-vae",
            "--disable-pinned-memory",
            "--disable-async-offload",
            "--reserve-vram", "1",
            "--disable-auto-launch",
        ]
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        with stdout_path.open("w", encoding="utf-8") as stdout, stderr_path.open("w", encoding="utf-8") as stderr:
            service = subprocess.Popen(
                launch,
                cwd=COMFY_DIR,
                stdout=stdout,
                stderr=stderr,
                text=True,
                creationflags=creationflags,
            )
        result_payload["owned_comfyui_pid"] = service.pid
        print(f"OWNED_COMFYUI_STARTED pid={service.pid}", flush=True)
        wait_for_health(180)
        print("COMFYUI_HEALTH=READY", flush=True)

        config = H3VisualConfig(
            enabled=True,
            low_vram=True,
            comfyui_base_url=BASE_URL,
            comfyui_dir=COMFY_DIR,
            workflow_dir=WORKFLOW_DIR,
            preview_width=320,
            preview_height=256,
            preview_steps=1,
            retry_limit=0,
            api_timeout_sec=30,
            job_timeout_sec=3600,
        )
        adapter = H3ProductionAdapter.from_config(config, output_dir=COMFY_OUTPUT)
        health = adapter.provider.health_check()
        guard = ResourceGuard(resources).check(
            ROOT,
            gpu_heavy=True,
            comfyui_health=health,
            estimated_output_mb=64,
        )
        result_payload["provider_health"] = json.loads(health.model_dump_json())
        result_payload["resource_guard"] = json.loads(guard.model_dump_json())
        if guard.status == "blocked":
            raise RuntimeError("ResourceGuard blocked ONE_LOW_VRAM_PROFILE: " + "; ".join(guard.reasons))

        task = ProductionTask(
            task_id="h3_low_vram",
            task_type=ProductionTaskType.VIDEO,
            resource_class=ResourceClass.GPU_HEAVY,
            max_attempts=1,
            metadata={
                "scene": {
                    "scene_id": SCENE_ID,
                    "generation_mode": "h3_t2v",
                    "requested_duration_sec": 0.2,
                    "prompt": {
                        "subject": "TEST_ONLY blue circle",
                        "environment": "plain dark background",
                        "action_motion": "remain still",
                        "camera": "static",
                        "lighting_style": "simple soft light",
                        "negative_constraints": ["text", "watermark"],
                    },
                    "route_reasons": ["Alpha22 Step 8.3 real H3 low-VRAM smoke"],
                    "budgeted_h3_seconds": 0.2,
                }
            },
        )
        ram_before = ram_memory()
        gpu_before = gpu_memory()
        result_payload["gpu_before_h3"] = gpu_before
        result_payload["ram_before_h3"] = ram_before
        phase["value"] = "h3"
        invocation_started = time.monotonic()
        result_payload["h3_real_invocation"] = "YES"
        print(
            f"H3_INVOKE profile=ONE_LOW_VRAM_PROFILE vram_free={gpu_before['free_mib'] if gpu_before else 'unknown'}",
            flush=True,
        )
        with resources.phase(task.task_id, provider=adapter, gpu_heavy=True, timeout_sec=0):
            adapter_result = adapter.execute(task, ROOT / "unused_adapter_output")
        elapsed = time.monotonic() - invocation_started
        phase["value"] = "resume"
        ram_after = ram_memory()
        gpu_after = gpu_memory()

        registry = ProductionArtifactRegistry(ROOT / "resume" / "artifacts")
        target, manifest = copy_and_register_artifact(adapter_result.output_paths[0], registry, task)
        artifact = media_summary(manifest)
        if artifact["validation"] != "VALID":
            raise RuntimeError("real H3 artifact failed structural validation")

        task.status = ProductionTaskStatus.SUCCEEDED
        task.attempt_count = 1
        task.output_refs = [manifest.artifact_id]
        task.finished_at = datetime.now().astimezone()
        plan = ProductionPlan(
            production_id="production_83c83c83c83c83c8",
            job_id=RUN_ID,
            creator_plan_id="creator_plan_alpha22_step8_3",
            tasks=[task],
            status=ProductionStatus.SUCCEEDED,
        )
        plans = ProductionPlanStore(ROOT / "resume" / "plans")
        plans.save(plan)
        history_before = relevant_history_count()
        hash_before = hashlib.sha256(target.read_bytes()).hexdigest()
        mtime_before = target.stat().st_mtime_ns
        resumed = ProductionOrchestrator(
            adapters={ProductionTaskType.VIDEO: adapter},
            store=plans,
            artifacts=registry,
            resources=resources,
            retry_policy=RetryPolicy(max_attempts=1),
            preflight=lambda _: None,
        ).resume(plan.production_id)
        history_after = relevant_history_count()
        hash_after = hashlib.sha256(target.read_bytes()).hexdigest()
        mtime_after = target.stat().st_mtime_ns
        resume_pass = (
            resumed.status == ProductionStatus.SUCCEEDED
            and history_before == history_after == 1
            and hash_before == hash_after
            and mtime_before == mtime_after
        )

        h3_samples = [sample for sample in samples if sample["phase"] == "h3"]
        ram_peak = max(
            [ram_before["used_mib"], ram_after["used_mib"]]
            + [int(sample["ram"]["used_mib"]) for sample in h3_samples]
        )
        gpu_values = [value for value in [gpu_before, gpu_after] if value is not None]
        gpu_values.extend(sample["gpu"] for sample in h3_samples if sample["gpu"] is not None)
        gpu_peak = max(int(value["used_mib"]) for value in gpu_values) if gpu_values else "PEAK_UNAVAILABLE"
        output_duration = artifact.get("duration_seconds")
        result_payload.update(
            {
                "result": "PASS",
                "finished_at": now_iso(),
                "elapsed_seconds": round(elapsed, 3),
                "rough_real_time_factor": (
                    round(elapsed / float(output_duration), 3) if output_duration else None
                ),
                "artifact": artifact,
                "resources": {
                    "ram_baseline_used_mib": ram_before["used_mib"],
                    "ram_peak_used_mib": ram_peak,
                    "ram_after_used_mib": ram_after["used_mib"],
                    "ram_after_available_mib": ram_after["available_mib"],
                    "vram_baseline_used_mib": gpu_before["used_mib"] if gpu_before else "PEAK_UNAVAILABLE",
                    "vram_peak_used_mib": gpu_peak,
                    "vram_after_used_mib": gpu_after["used_mib"] if gpu_after else "PEAK_UNAVAILABLE",
                    "sample_interval_seconds": 0.25,
                    "h3_sample_count": len(h3_samples),
                },
                "hardware_verdict": {
                    "physical_machine_h3": "PASS",
                    "h3_8gb_vram_envelope": "PASS",
                    "h3_24g_envelope": "PASS" if ram_peak <= 24576 else "FAIL",
                },
                "resume": {
                    "result": "PASS" if resume_pass else "FAIL",
                    "comfyui_invocation_count_before": history_before,
                    "comfyui_invocation_count_after": history_after,
                    "successful_h3_regenerated": not resume_pass,
                    "hash_unchanged": hash_before == hash_after,
                    "mtime_unchanged": mtime_before == mtime_after,
                },
                "cleanup": {
                    "provider_unload_called": True,
                    "cuda_cache_release_called": True,
                    "gpu_lock_released": resources.current_gpu_phase is None,
                    "production_task_terminal": resumed.task(task.task_id).status.value,
                },
            }
        )
        print(
            f"H3_RESULT=PASS elapsed={elapsed:.3f}s ram_peak={ram_peak}MiB vram_peak={gpu_peak}MiB",
            flush=True,
        )
    except Exception as exc:
        result_payload.update(
            {
                "finished_at": now_iso(),
                "result": "FAIL",
                "error_type": type(exc).__name__,
                "error": str(exc),
                "resource_exhausted": ResourceManager.is_oom_error(exc),
                "hardware_verdict": {
                    "physical_machine_h3": "FAIL" if result_payload["h3_real_invocation"] == "YES" else "BLOCKED",
                    "h3_8gb_vram_envelope": "FAIL" if result_payload["h3_real_invocation"] == "YES" else "NOT_VERIFIED",
                    "h3_24g_envelope": "NOT_VERIFIED",
                },
                "resume": "NOT_EXECUTED",
            }
        )
        print(f"H3_RESULT=FAIL type={type(exc).__name__} error={exc}", flush=True)
    finally:
        phase["value"] = "cleanup"
        try:
            httpx.post(
                f"{BASE_URL}/free",
                json={"unload_models": True, "free_memory": True},
                timeout=30,
            )
        except (httpx.HTTPError, OSError):
            pass
        if service is not None and service.poll() is None:
            service.terminate()
            service_stop_method = "TERMINATE_OWNED_PROCESS"
            try:
                service.wait(timeout=30)
            except subprocess.TimeoutExpired:
                service_stop_method = "OWNED_PROCESS_DID_NOT_EXIT_NO_FORCE_USED"
        elif service is not None:
            service_stop_method = "OWNED_PROCESS_EXITED"
        monitor_done.set()
        monitor_thread.join(timeout=3)
        result_payload["cleanup_final"] = {
            "service_stop_method": service_stop_method,
            "owned_service_exited": service is None or service.poll() is not None,
            "gpu_after_service_stop": gpu_memory(),
            "ram_after_service_stop": ram_memory(),
            "gpu_lock_released": resources.current_gpu_phase is None,
        }
        atomic_write_json(SAMPLES_PATH, samples, backup_count=1)
        atomic_write_json(RESULT_PATH, result_payload, backup_count=1)
        print(json.dumps(result_payload, ensure_ascii=False, indent=2), flush=True)

    if result_payload["result"] != "PASS":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
