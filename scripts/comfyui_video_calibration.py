"""Calibrate the safe built-in-node ComfyUI video graph before Alysia submission.

The graph makes a solid-color clip; it does not validate H3 prompt semantics.
"""
from __future__ import annotations

import json
from pathlib import Path
import time

import httpx

from alysia.core.io import atomic_write_json
from alysia.core.resources import ResourceManager


GRAPH = Path("alpha22/field_smoke/local_creator/comfyui_cpu_video_graph.json")
EVIDENCE = Path("alpha22/field_smoke/local_creator/comfyui_cpu_video_calibration.json")
BASE = "http://127.0.0.1:8188"


def main() -> None:
    graph = json.loads(GRAPH.read_text(encoding="utf-8"))
    with httpx.Client(base_url=BASE, timeout=10) as client:
        queue = client.get("/queue").json()
        if queue.get("queue_running") or queue.get("queue_pending"):
            raise RuntimeError("ComfyUI 队列非空，不执行校准")
        baseline_vram = ResourceManager.probe_vram()
        baseline_ram = ResourceManager.probe_ram()
        if baseline_vram is None or baseline_ram is None:
            raise RuntimeError("无法采样 GPU 或系统 RAM")
        response = client.post("/prompt", json={"prompt": graph, "client_id": "alysia-calibration"})
        response.raise_for_status()
        payload = response.json()
        if payload.get("node_errors"):
            raise RuntimeError(f"ComfyUI 节点校验失败：{payload['node_errors']}")
        prompt_id = payload["prompt_id"]
        start = time.monotonic()
        peak_vram = baseline_vram["used_mb"]
        peak_ram = baseline_ram["used_mb"]
        while time.monotonic() - start < 120:
            vram = ResourceManager.probe_vram()
            ram = ResourceManager.probe_ram()
            if vram is None or ram is None:
                client.post("/interrupt")
                raise RuntimeError("运行时资源探测中断")
            peak_vram = max(peak_vram, vram["used_mb"])
            peak_ram = max(peak_ram, ram["used_mb"])
            if peak_vram > 7680 or peak_ram > 24576:
                client.post("/interrupt")
                raise RuntimeError("校准超出 7.5 GiB VRAM / 24 GiB RAM 停止线")
            history = client.get(f"/history/{prompt_id}").json().get(prompt_id)
            if history:
                result = {
                    "prompt_id": prompt_id,
                    "elapsed_sec": round(time.monotonic() - start, 3),
                    "baseline_vram_mib": baseline_vram["used_mb"],
                    "sampled_peak_vram_mib": peak_vram,
                    "sampled_incremental_vram_mib": max(0, peak_vram - baseline_vram["used_mb"]),
                    "baseline_system_ram_mib": baseline_ram["used_mb"],
                    "sampled_peak_system_ram_mib": peak_ram,
                    "outputs": history.get("outputs", {}),
                    "status": history.get("status", {}),
                }
                atomic_write_json(EVIDENCE, result)
                print(json.dumps(result, ensure_ascii=False, indent=2))
                return
            time.sleep(0.2)
        client.post("/interrupt")
        raise TimeoutError("ComfyUI 视频校准超时")


if __name__ == "__main__":
    main()
