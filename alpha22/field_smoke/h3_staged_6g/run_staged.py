"""Monitor sequential owned workers; never force-terminate a process."""
from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from alysia.core.resources import ResourceManager

ROOT = Path(__file__).resolve().parent
RUN = ROOT / datetime.now().strftime("run_%Y%m%d_%H%M%S")
PYTHON = Path(r"D:\ComfyUI\.venv\Scripts\python.exe")


def snapshot():
    return {"time": datetime.now().astimezone().isoformat(),
            "gpu": ResourceManager.probe_vram(), "ram": ResourceManager.probe_ram()}


def save(name, data):
    (RUN / name).write_text(json.dumps(data, indent=2), encoding="utf-8")


def main():
    RUN.mkdir(parents=True, exist_ok=False)
    summary = {"test_only": True, "run_dir": str(RUN), "status": "RUNNING", "stages": []}
    save("summary.json", summary)
    print(f"RUN_DIR={RUN}", flush=True)
    phases = ("load_diffusion",) if "--load-only" in sys.argv else ("encode", "sample", "decode")
    for phase in phases:
        before = snapshot()
        gpu, ram = before["gpu"], before["ram"]
        if not gpu or not ram or gpu["used_mb"] >= 6144 or ram["commit_available_mb"] < 2048:
            summary.update(status="BLOCKED", reason="unsafe_stage_baseline", baseline=before)
            break
        allocator_mib = min(5632, 6144 - gpu["used_mb"] - 512)
        env = {**os.environ, "ALYSIA_STAGED_RUN": str(RUN), "ALYSIA_STAGED_PHASE": phase,
               "ALYSIA_CUDA_ALLOCATOR_MIB": str(allocator_mib), "PYTHONUNBUFFERED": "1"}
        flags = (["--novram", "--reserve-vram", "2", "--disable-async-offload"]
                 if phase in {"sample", "load_diffusion"} else ["--cpu", "--cpu-vae"])
        flags += ["--disable-pinned-memory", "--disable-smart-memory", "--preview-method", "none"]
        launch = [str(PYTHON), str(ROOT / "stage_worker.py"), *flags]
        samples = [before]
        started = time.monotonic()
        stop_requested = None
        print(f"STAGE_START={phase} allocator_limit_mib={allocator_mib}", flush=True)
        with (RUN / f"{phase}_stdout.log").open("w", encoding="utf-8") as out, \
             (RUN / f"{phase}_stderr.log").open("w", encoding="utf-8") as err:
            worker = subprocess.Popen(launch, cwd=r"D:\ComfyUI", env=env, stdout=out, stderr=err,
                                      creationflags=subprocess.CREATE_NO_WINDOW)
            while worker.poll() is None:
                current = snapshot()
                samples.append(current)
                g, r = current["gpu"], current["ram"]
                exceeded = (not g or not r or g["used_mb"] > 6144 or r["used_mb"] > 24576
                            or r["commit_available_mb"] < 1024 or time.monotonic() - started > 1200)
                if exceeded and stop_requested is None:
                    stop_requested = time.monotonic()
                    (RUN / "STOP").write_text("resource_or_timeout", encoding="utf-8")
                    print(f"COOPERATIVE_STOP={phase}", flush=True)
                if stop_requested and time.monotonic() - stop_requested > 60:
                    summary.update(status="BLOCKED", reason="owned_worker_pending_cooperative_exit", pid=worker.pid)
                    save(f"{phase}_samples.json", samples)
                    save("summary.json", summary)
                    return 2
                time.sleep(0.5)
        after = snapshot()
        samples.append(after)
        child_path = RUN / f"{phase}_result.json"
        child = json.loads(child_path.read_text(encoding="utf-8")) if child_path.exists() else {}
        report = {"stage": phase, "exit_code": worker.returncode, "command": launch,
                  "status": child.get("status", "FAIL_NATIVE_OR_STARTUP"), "child": child,
                  "baseline": before, "after": after, "sample_count": len(samples),
                  "observed_vram_peak_mib": max(s["gpu"]["used_mb"] for s in samples if s["gpu"]),
                  "observed_ram_peak_mib": max(s["ram"]["used_mb"] for s in samples if s["ram"]),
                  "elapsed_seconds": round(time.monotonic() - started, 3), "cooperative_stop": stop_requested is not None}
        summary["stages"].append(report)
        save(f"{phase}_samples.json", samples)
        save("summary.json", summary)
        print(json.dumps(report), flush=True)
        if worker.returncode != 0 or report["status"] != "PASS" or stop_requested:
            summary["status"] = "FAIL"
            break
    else:
        summary["status"] = "PASS"
    save("summary.json", summary)
    print(f"STAGED_RESULT={summary['status']}", flush=True)
    return 0 if summary["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
