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

from PIL import Image

from alysia.core.io import atomic_write_json
from alysia.core.resources import ResourceManager
from alysia.providers.visual.comfyui import ComfyUIProvider
from alysia.schemas.visual import SceneVisualPlan, VisualGenerationJob


ROOT = Path(__file__).resolve().parent
COMFY_OUTPUT = Path(r"D:\ComfyUI\output")


def gpu_memory() -> dict[str, int] | None:
    try:
        raw = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=memory.total,memory.used,memory.free",
                "--format=csv,noheader,nounits",
            ],
            text=True,
            timeout=5,
        ).strip()
        total, used, free = [int(value.strip()) for value in raw.split(",")]
        return {"total_mib": total, "used_mib": used, "free_mib": free}
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
        "total_bytes": int(value.total_physical),
        "available_bytes": int(value.available_physical),
        "used_bytes": int(value.total_physical - value.available_physical),
    }


def main() -> None:
    started_at = datetime.now().astimezone()
    ram_before = ram_memory()
    gpu_before = gpu_memory()
    samples: list[dict[str, object]] = []
    done = threading.Event()

    def monitor() -> None:
        while not done.wait(0.25):
            samples.append({"ram": ram_memory(), "gpu": gpu_memory()})

    provider = ComfyUIProvider(
        base_url="http://127.0.0.1:8188",
        workflow_dir=ROOT / "comfyui" / "workflows",
        output_dir=COMFY_OUTPUT,
        timeout_sec=10,
        job_timeout_sec=60,
    )
    scene = SceneVisualPlan(
        scene_id="TEST_ONLY_comfyui_stage_a",
        generation_mode="static_image",
        requested_duration_sec=1,
        route_reasons=["Alpha22 Step 8 real ComfyUI adapter health smoke"],
    )
    job = VisualGenerationJob(
        job_id="visual_job_alpha22_step8_comfyui",
        run_id="alpha22_step8_field_smoke",
        scene=scene,
        provider=provider.provider_id,
        workflow_id="field_smoke_image",
        workflow_version="field-smoke-1",
        cache_key=hashlib.sha256(b"alpha22-step8-comfyui-stage-a").hexdigest(),
        created_at=started_at,
        updated_at=started_at,
    )
    resources = ResourceManager(sequential_gpu=True)
    thread = threading.Thread(target=monitor, daemon=True)
    thread.start()
    started = time.monotonic()
    try:
        with resources.phase("alpha22-step8-comfyui", provider=provider, gpu_heavy=True, timeout_sec=0):
            result = provider.generate(job)
    finally:
        done.set()
        thread.join(timeout=2)
        provider.unload()
    elapsed = time.monotonic() - started
    source = result.output_files[0].resolve()
    target = (ROOT / "comfyui" / "TEST_ONLY_comfyui_stage_a.png").resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    with Image.open(target) as image:
        width, height = image.size
        image_format = image.format
    ram_after = ram_memory()
    gpu_after = gpu_memory()
    ram_used = [ram_before["used_bytes"], ram_after["used_bytes"]]
    gpu_used = [value["used_mib"] for value in (gpu_before, gpu_after) if value is not None]
    for sample in samples:
        ram_used.append(int(sample["ram"]["used_bytes"]))  # type: ignore[index]
        if sample["gpu"] is not None:
            gpu_used.append(int(sample["gpu"]["used_mib"]))  # type: ignore[index]
    payload = {
        "stage": "A_COMFYUI_HEALTH",
        "result": "PASS",
        "adapter": "REAL",
        "service": "REAL_COMFYUI",
        "model_loaded": False,
        "workflow": "built-in EmptyImage -> SaveImage",
        "run_id": job.run_id,
        "job_id": job.job_id,
        "started_at": started_at.isoformat(),
        "finished_at": datetime.now().astimezone().isoformat(),
        "elapsed_seconds": round(elapsed, 3),
        "artifact": {
            "path": str(target),
            "source_path": str(source),
            "size_bytes": target.stat().st_size,
            "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
            "format": image_format,
            "width": width,
            "height": height,
            "validation": "VALID" if target.stat().st_size > 0 and (width, height) == (64, 64) else "INVALID",
        },
        "resources": {
            "ram_before": ram_before,
            "ram_peak_used_bytes": max(ram_used),
            "ram_after": ram_after,
            "vram_before": gpu_before,
            "vram_peak_used_mib": max(gpu_used) if gpu_used else "PEAK_UNAVAILABLE",
            "vram_after": gpu_after,
        },
        "cleanup": {
            "provider_unload_called": True,
            "resource_lock_released": resources.current_gpu_phase is None,
        },
        "provider_result": json.loads(result.model_dump_json()),
    }
    if payload["artifact"]["validation"] != "VALID":
        payload["result"] = "FAIL"
    atomic_write_json(ROOT / "comfyui" / "stage_a_result.json", payload, backup_count=1)
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
