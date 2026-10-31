#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""用 MiniMax H3 的 i2v 给莉娅生成动作片段（首帧固定为立绘，保证角色一致）。

用法：
  python scripts/lia_h3_clip.py "动作描述" --image lia_mv_wave.png --out wave01
  python scripts/lia_h3_clip.py --batch shots.json

ComfyUI 需在 8188 就绪，模型与工作流见 workflows/comfyui/h3/t2v.json。
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.request
import uuid
from pathlib import Path

COMFY = "http://127.0.0.1:8188"
OUT_DIR = Path(r"D:\Alysia\workspace\lia_batch_20261028\mv_lia\clips")


def build_prompt(image: str, text: str, seed: int, length: int = 73,
                 width: int = 608, height: int = 352, steps: int = 6,
                 prefix: str = "alysia/mv") -> dict:
    return {
        "1": {"class_type": "UNETLoader",
              "inputs": {"unet_name": "minimax_h3_fl2va_pruned_int8_convrot.safetensors",
                         "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader",
              "inputs": {"clip_name": "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors",
                         "type": "minimax", "device": "cpu"}},
        "3": {"class_type": "VAELoader",
              "inputs": {"vae_name": "minimax_h3_video_vae_fp16.safetensors"}},
        "13": {"class_type": "LoadImage", "inputs": {"image": image}},
        "4": {"class_type": "MiniMaxH3ImageToVideo",
              "inputs": {"clip": ["2", 0], "vae": ["3", 0], "prompt": text,
                         "width": width, "height": height, "length": length,
                         "first_frame": ["13", 0]}},
        "5": {"class_type": "BasicScheduler",
              "inputs": {"model": ["1", 0], "scheduler": "simple", "steps": steps, "denoise": 1.0}},
        "6": {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}},
        "7": {"class_type": "BasicGuider",
              "inputs": {"model": ["1", 0], "conditioning": ["4", 0]}},
        "8": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "res_multistep"}},
        "9": {"class_type": "SamplerCustomAdvanced",
              "inputs": {"noise": ["6", 0], "guider": ["7", 0], "sampler": ["8", 0],
                         "sigmas": ["5", 0], "latent_image": ["4", 1]}},
        "10": {"class_type": "VAEDecode", "inputs": {"samples": ["9", 0], "vae": ["3", 0]}},
        "11": {"class_type": "CreateVideo",
               "inputs": {"images": ["10", 0], "fps": 24.0, "bit_depth": 8}},
        "12": {"class_type": "SaveVideo",
               "inputs": {"video": ["11", 0], "filename_prefix": prefix, "format": "mp4",
                          "codec": "auto"}},
    }


def post(path: str, payload: dict) -> dict:
    req = urllib.request.Request(
        COMFY + path,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def get(path: str):
    with urllib.request.urlopen(COMFY + path, timeout=30) as r:
        return json.loads(r.read())


def run_one(name: str, image: str, text: str, seed: int) -> Path:
    cid = str(uuid.uuid4())
    # 每段用唯一前缀：SaveVideo 的计数器会重置，同一前缀会撞名导致不落盘
    res = post("/prompt", {"prompt": build_prompt(image, text, seed, prefix=f"alysia/mv_{name}"),
                           "client_id": cid})
    pid = res.get("prompt_id")
    print(f"[{name}] queued {pid}", flush=True)
    t0 = time.time()
    while time.time() - t0 < 900:
        time.sleep(5)
        h = get(f"/history/{pid}")
        if pid in h:
            outs = h[pid].get("outputs", {})
            files = []
            for node in outs.values():
                for key in ("images", "videos", "gifs"):
                    for f in node.get(key, []) or []:
                        if isinstance(f, dict) and f.get("filename"):
                            files.append(f["filename"])
            if files:
                base = Path(r"D:\ComfyUI\output")
                src = base / files[-1]
                if not src.exists():
                    # filename_prefix 含子目录时，文件落在 output/alysia/ 下
                    cand = sorted(base.rglob(Path(files[-1]).name))
                    if cand:
                        src = cand[-1]
                OUT_DIR.mkdir(parents=True, exist_ok=True)
                dst = OUT_DIR / f"{name}{src.suffix}"
                dst.write_bytes(src.read_bytes())
                print(f"[{name}] done {time.time()-t0:.0f}s -> {dst} "
                      f"({dst.stat().st_size//1024} KB)", flush=True)
                return dst
            print(f"[{name}] finished but no output", flush=True)
            break
    raise SystemExit(f"[{name}] 超时或失败")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("text", nargs="?")
    ap.add_argument("--image", default="lia_mv_wave.png")
    ap.add_argument("--out", default="clip")
    ap.add_argument("--seed", type=int, default=20261029)
    ap.add_argument("--batch", help="shots.json: [{name,image,text,seed}]")
    a = ap.parse_args()

    if a.batch:
        shots = json.loads(Path(a.batch).read_text(encoding="utf-8"))
        for i, s in enumerate(shots, 1):
            print(f"--- {i}/{len(shots)} {s['name']}", flush=True)
            run_one(s["name"], s.get("image", a.image), s["text"],
                    s.get("seed", a.seed + i))
        return 0

    if not a.text:
        raise SystemExit("需要动作描述，或用 --batch")
    run_one(a.out, a.image, a.text, a.seed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
