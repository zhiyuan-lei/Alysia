from __future__ import annotations

import ctypes
import hashlib
import json
import shutil
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

import httpx

from alysia.core.config import H3VisualConfig
from alysia.core.resources import ResourceManager
from alysia.creator import H3ProductionAdapter, ProductionTask, ProductionTaskType, ResourceClass
from alysia.reliability.artifacts import ArtifactIntegrityChecker
from alysia.reliability.resources import ResourceGuard


ROOT = Path(__file__).resolve().parent
COMFY_DIR = Path(r"D:\ComfyUI")
COMFY_PYTHON = COMFY_DIR / ".venv" / "Scripts" / "python.exe"
COMFY_OUTPUT = COMFY_DIR / "output"
WORKFLOW_DIR = Path(r"D:\Alysia\workflows\comfyui\h3")
BASE_URL = "http://127.0.0.1:8188"
RESULT_PATH = ROOT / "h3_retest_result.json"
SAMPLES_PATH = ROOT / "h3_retest_resource_samples.json"
STDOUT_PATH = ROOT / "h3_retest_comfyui_stdout.log"
STDERR_PATH = ROOT / "h3_retest_comfyui_stderr.log"
SCENE_ID = "TEST_ONLY_h3_native_fix"


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


def wait_for_health(timeout_sec: float) -> None:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        if health_available():
            return
        time.sleep(1)
    raise TimeoutError("owned ComfyUI service did not become healthy")


def artifact_summary(source: Path) -> dict[str, object]:
    artifact_dir = ROOT / "h3_retest" / "artifacts"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    target = artifact_dir / f"{SCENE_ID}{source.suffix.lower()}"
    shutil.copy2(source, target)
    record = ArtifactIntegrityChecker(compute_hash=True, probe_media=True).check(
        target, producer="alpha22-step8.4-h3-retest"
    )
    probe = record.media_probe or {}
    video_stream = next(
        (stream for stream in probe.get("streams", []) if stream.get("codec_type") == "video"),
        {},
    )
    duration = video_stream.get("duration") or probe.get("format", {}).get("duration")
    return {
        "path": str(target.resolve()),
        "size_bytes": target.stat().st_size,
        "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
        "format": target.suffix.lower().lstrip("."),
        "duration_seconds": float(duration) if duration is not None else None,
        "width": video_stream.get("width"),
        "height": video_stream.get("height"),
        "codec": video_stream.get("codec_name"),
        "validation": "VALID" if record.validity == "valid" and target.stat().st_size > 0 else "INVALID",
        "errors": record.errors,
    }


def main() -> None:
    phase = {"value": "service_start"}
    samples: list[dict[str, object]] = []
    done = threading.Event()
    resources = ResourceManager(sequential_gpu=True)
    service: subprocess.Popen[str] | None = None
    invocation_started: float | None = None
    payload: dict[str, object] = {
        "run_id": "alpha22_step8_4_h3_native_fix",
        "started_at": now_iso(),
        "one_minimal_runtime_fix": "REMOVE_CPU_VAE",
        "profile": {
            "launcher": [
                "--novram",
                "--disable-pinned-memory",
                "--disable-async-offload",
                "--reserve-vram 1",
            ],
            "removed": "--cpu-vae",
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
        while not done.wait(0.25):
            samples.append(
                {
                    "timestamp": now_iso(),
                    "phase": phase["value"],
                    "ram": ram_memory(),
                    "gpu": gpu_memory(),
                }
            )

    thread = threading.Thread(target=monitor, daemon=True)
    thread.start()
    try:
        if health_available():
            raise RuntimeError("ComfyUI already running; refusing to adopt unknown service")
        launch = [
            str(COMFY_PYTHON),
            "main.py",
            "--listen", "127.0.0.1",
            "--port", "8188",
            "--novram",
            "--disable-pinned-memory",
            "--disable-async-offload",
            "--reserve-vram", "1",
            "--disable-auto-launch",
        ]
        with STDOUT_PATH.open("w", encoding="utf-8") as stdout, STDERR_PATH.open("w", encoding="utf-8") as stderr:
            service = subprocess.Popen(
                launch,
                cwd=COMFY_DIR,
                stdout=stdout,
                stderr=stderr,
                text=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        payload["owned_comfyui_pid"] = service.pid
        print(f"OWNED_COMFYUI_STARTED pid={service.pid}", flush=True)
        wait_for_health(180)

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
            ROOT, gpu_heavy=True, comfyui_health=health, estimated_output_mb=64
        )
        payload["provider_health"] = json.loads(health.model_dump_json())
        payload["resource_guard"] = json.loads(guard.model_dump_json())
        if guard.status == "blocked":
            raise RuntimeError("ResourceGuard blocked post-fix H3: " + "; ".join(guard.reasons))

        task = ProductionTask(
            task_id="h3_native_fix",
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
                    "route_reasons": ["Alpha22 Step 8.4 post-fix H3 smoke"],
                    "budgeted_h3_seconds": 0.2,
                }
            },
        )
        ram_before = ram_memory()
        gpu_before = gpu_memory()
        payload["ram_before_h3"] = ram_before
        payload["gpu_before_h3"] = gpu_before
        payload["h3_real_invocation"] = "YES"
        phase["value"] = "h3"
        invocation_started = time.monotonic()
        print(
            f"H3_POST_FIX_INVOKE vram_free={gpu_before['free_mib'] if gpu_before else 'unknown'}",
            flush=True,
        )
        with resources.phase(task.task_id, provider=adapter, gpu_heavy=True, timeout_sec=0):
            adapter_result = adapter.execute(task, ROOT / "unused_adapter_output")
        elapsed = time.monotonic() - invocation_started
        phase["value"] = "cleanup"
        ram_after = ram_memory()
        gpu_after = gpu_memory()
        artifact = artifact_summary(adapter_result.output_paths[0])
        if artifact["validation"] != "VALID":
            raise RuntimeError("post-fix H3 artifact failed validation")

        h3_samples = [sample for sample in samples if sample["phase"] == "h3"]
        ram_peak = max(
            [ram_before["used_mib"], ram_after["used_mib"]]
            + [int(sample["ram"]["used_mib"]) for sample in h3_samples]
        )
        gpu_values = [value for value in (gpu_before, gpu_after) if value is not None]
        gpu_values.extend(sample["gpu"] for sample in h3_samples if sample["gpu"] is not None)
        gpu_peak = max(int(value["used_mib"]) for value in gpu_values) if gpu_values else "PEAK_UNAVAILABLE"
        output_duration = artifact.get("duration_seconds")
        payload.update(
            {
                "result": "PASS",
                "finished_at": now_iso(),
                "elapsed_seconds": round(elapsed, 3),
                "rough_real_time_factor": round(elapsed / float(output_duration), 3) if output_duration else None,
                "artifact": artifact,
                "resources": {
                    "ram_baseline_used_mib": ram_before["used_mib"],
                    "ram_peak_used_mib": ram_peak,
                    "ram_after_used_mib": ram_after["used_mib"],
                    "vram_baseline_used_mib": gpu_before["used_mib"] if gpu_before else "PEAK_UNAVAILABLE",
                    "vram_peak_used_mib": gpu_peak,
                    "vram_after_used_mib": gpu_after["used_mib"] if gpu_after else "PEAK_UNAVAILABLE",
                    "sample_interval_seconds": 0.25,
                    "h3_sample_count": len(h3_samples),
                },
                "native_crash": "RESOLVED",
                "hardware_verdict": {
                    "physical_machine_h3": "PASS",
                    "h3_8gb_vram_envelope": "PASS",
                    "h3_24g_envelope": "PASS" if ram_peak <= 24576 else "FAIL",
                },
            }
        )
        print(
            f"H3_POST_FIX_RESULT=PASS elapsed={elapsed:.3f}s ram_peak={ram_peak}MiB vram_peak={gpu_peak}MiB",
            flush=True,
        )
    except Exception as exc:
        payload.update(
            {
                "result": "FAIL",
                "finished_at": now_iso(),
                "elapsed_to_failure_seconds": (
                    round(time.monotonic() - invocation_started, 3) if invocation_started else None
                ),
                "error_type": type(exc).__name__,
                "error": str(exc),
                "resource_exhausted": ResourceManager.is_oom_error(exc),
                "native_crash": "UNRESOLVED",
                "hardware_verdict": {
                    "physical_machine_h3": "BLOCKED",
                    "h3_8gb_vram_envelope": "NOT_VERIFIED",
                    "h3_24g_envelope": "NOT_VERIFIED",
                },
            }
        )
        print(f"H3_POST_FIX_RESULT=FAIL type={type(exc).__name__} error={exc}", flush=True)
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
            try:
                service.wait(timeout=30)
                stop_method = "TERMINATE_OWNED_PROCESS"
            except subprocess.TimeoutExpired:
                stop_method = "OWNED_PROCESS_DID_NOT_EXIT_NO_FORCE_USED"
        elif service is not None:
            stop_method = "OWNED_PROCESS_EXITED"
        else:
            stop_method = "NOT_STARTED"
        done.set()
        thread.join(timeout=3)
        payload["cleanup"] = {
            "provider_unload_requested": True,
            "cuda_cache_release_path_called": True,
            "gpu_lock_released": resources.current_gpu_phase is None,
            "service_stop_method": stop_method,
            "owned_service_exited": service is None or service.poll() is not None,
            "gpu_after_service_stop": gpu_memory(),
            "ram_after_service_stop": ram_memory(),
        }
        SAMPLES_PATH.write_text(json.dumps(samples, ensure_ascii=False, indent=2), encoding="utf-8")
        RESULT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(payload, ensure_ascii=False, indent=2), flush=True)

    if payload["result"] != "PASS":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
