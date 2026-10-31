from __future__ import annotations

import ctypes
import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parent
CHILD = ROOT / "text_encoder_isolation.py"
COMFY_PYTHON = Path(r"D:\ComfyUI\.venv\Scripts\python.exe")
POST_FIX = "--post-fix" in sys.argv
RESULT = ROOT / ("text_encoder_post_fix_result.json" if POST_FIX else "text_encoder_isolation_result.json")
STDOUT = ROOT / ("text_encoder_post_fix_stdout.log" if POST_FIX else "text_encoder_isolation_stdout.log")
STDERR = ROOT / ("text_encoder_post_fix_stderr.log" if POST_FIX else "text_encoder_isolation_stderr.log")


def now_iso() -> str:
    return datetime.now().astimezone().isoformat()


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
        "used_mib": round((value.total_physical - value.available_physical) / (1024 * 1024)),
        "available_mib": round(value.available_physical / (1024 * 1024)),
        "commit_available_mib": round(value.available_page_file / (1024 * 1024)),
    }


def main() -> None:
    samples: list[dict[str, object]] = []
    done = threading.Event()

    def monitor() -> None:
        while not done.wait(0.25):
            samples.append({"timestamp": now_iso(), "ram": ram_memory()})

    baseline = ram_memory()
    started_at = now_iso()
    thread = threading.Thread(target=monitor, daemon=True)
    thread.start()
    started = time.monotonic()
    command = [
        str(COMFY_PYTHON),
        "-X", "faulthandler",
        str(CHILD),
        "--novram",
        "--disable-pinned-memory",
        "--disable-async-offload",
        "--reserve-vram", "1",
    ]
    if not POST_FIX:
        command.insert(5, "--cpu-vae")
    child_environment = os.environ.copy()
    if POST_FIX:
        child_environment["ALYSIA_84_PHASE"] = "post_fix"
    with STDOUT.open("w", encoding="utf-8") as stdout, STDERR.open("w", encoding="utf-8") as stderr:
        process = subprocess.run(
            command,
            cwd=Path(r"D:\ComfyUI"),
            stdout=stdout,
            stderr=stderr,
            text=True,
            timeout=1800,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            env=child_environment,
        )
    elapsed = time.monotonic() - started
    done.set()
    thread.join(timeout=3)
    after = ram_memory()
    ram_peak = max([baseline["used_mib"], after["used_mib"]] + [sample["ram"]["used_mib"] for sample in samples])
    ram_min_available = min([baseline["available_mib"], after["available_mib"]] + [sample["ram"]["available_mib"] for sample in samples])
    commit_min_available = min([baseline["commit_available_mib"], after["commit_available_mib"]] + [sample["ram"]["commit_available_mib"] for sample in samples])
    child_result = None
    child_path = ROOT / (
        "text_encoder_post_fix_child_result.json"
        if POST_FIX
        else "text_encoder_isolation_child_result.json"
    )
    if child_path.is_file():
        child_result = json.loads(child_path.read_text(encoding="utf-8"))
    payload = {
        "result": "PASS" if process.returncode == 0 and child_result and child_result.get("result") == "PASS" else "FAIL",
        "started_at": started_at,
        "finished_at": now_iso(),
        "elapsed_seconds": round(elapsed, 3),
        "exit_code_signed": process.returncode,
        "exit_code_hex": hex(process.returncode & 0xFFFFFFFF),
        "same_interpreter": str(COMFY_PYTHON),
        "runtime_fix": "REMOVE_CPU_VAE" if POST_FIX else "NONE",
        "component": "real H3 qwen3vl_32b_minimax_h3_nvfp4_awq text encoder",
        "video_generation": False,
        "vae_loaded": False,
        "diffusion_loaded": False,
        "child_result": child_result,
        "resources": {
            "ram_baseline_used_mib": baseline["used_mib"],
            "ram_peak_used_mib": ram_peak,
            "ram_after_used_mib": after["used_mib"],
            "ram_min_available_mib": ram_min_available,
            "commit_min_available_mib": commit_min_available,
            "sample_interval_seconds": 0.25,
            "sample_count": len(samples),
        },
        "stdout_log": str(STDOUT),
        "stderr_log": str(STDERR),
    }
    RESULT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2), flush=True)
    if payload["result"] != "PASS":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
