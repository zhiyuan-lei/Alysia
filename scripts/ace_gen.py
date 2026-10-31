#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""通过 ComfyUI API 调用 ACE-Step 生成整首歌（含人声+伴奏）。

用法：
  python scripts/ace_gen.py --lyrics-file lyrics.txt --style "cute kawaii pop" \
      --seconds 30 -o out.mp3 [--cpu-offload]
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.request
import uuid
from pathlib import Path

COMFY = "http://127.0.0.1:8188"


def post(path: str, payload: dict) -> dict:
    req = urllib.request.Request(
        COMFY + path, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def get(path: str):
    with urllib.request.urlopen(COMFY + path, timeout=30) as r:
        return json.loads(r.read())


def build(style: str, lyrics: str, seconds: float, seed: int,
          steps: int = 12, cfg: float = 15.0, cpu_offload: bool = True) -> dict:
    return {
        "1": {"class_type": "ACEModelLoader", "inputs": {
            "dcae_checkpoint": "music_dcae_f8c8",
            "vocoder_checkpoint": "music_vocoder",
            "ace_step_checkpoint": "ace_step_transformer",
            "text_encoder_checkpoint": "umt5-base",
            "cpu_offload": cpu_offload,
            "torch_compile": False}},
        "2": {"class_type": "GenerationParameters", "inputs": {
            "audio_duration": float(seconds),
            "infer_step": int(steps),
            "guidance_scale": float(cfg),
            "scheduler_type": "euler",
            "cfg_type": "apg",
            "omega_scale": 10.0,
            "seed": int(seed),
            "guidance_interval": 0.5,
            "guidance_interval_decay": 0.0,
            "min_guidance_scale": 3,
            "use_erg_tag": True,
            "use_erg_lyric": False,
            "use_erg_diffusion": True,
            "oss_steps": "",
            "guidance_scale_text": 3.0,
            "guidance_scale_lyric": 3.0}},
        "3": {"class_type": "MultiLinePromptACES",
              "inputs": {"multi_line_prompt": style}},
        "4": {"class_type": "MultiLineLyrics",
              "inputs": {"multi_line_prompt": lyrics}},
        "5": {"class_type": "ACEStepGen", "inputs": {
            "models": ["1", 0],
            "prompt": ["3", 0],
            "lyrics": ["4", 0],
            "parameters": ["2", 0]}},
        "6": {"class_type": "SaveAudio", "inputs": {
            "audio": ["5", 0],
            "filename_prefix": "audio/lia_ace"}},
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lyrics-file", required=True)
    ap.add_argument("--style", required=True)
    ap.add_argument("--seconds", type=float, default=30)
    ap.add_argument("--seed", type=int, default=20261029)
    ap.add_argument("--steps", type=int, default=12)
    ap.add_argument("--cfg", type=float, default=15.0)
    ap.add_argument("--no-offload", action="store_true")
    ap.add_argument("-o", "--out", required=True)
    a = ap.parse_args()

    lyrics = Path(a.lyrics_file).read_text(encoding="utf-8").strip()
    print(f"歌词 {len(lyrics)} 字 / 风格「{a.style}」/ {a.seconds:.0f}s")

    wf = build(a.style, lyrics, a.seconds, a.seed, a.steps, a.cfg, not a.no_offload)
    cid = str(uuid.uuid4())
    res = post("/prompt", {"prompt": wf, "client_id": cid})
    pid = res.get("prompt_id")
    print("queued", pid, flush=True)

    t0 = time.time()
    while time.time() - t0 < 1800:
        time.sleep(5)
        h = get(f"/history/{pid}")
        if pid in h:
            outs = h[pid].get("outputs", {})
            files = []
            for node in outs.values():
                for k in ("audio", "images", "gifs", "videos"):
                    for f in (node.get(k) or []):
                        if isinstance(f, dict) and f.get("filename"):
                            files.append(f["filename"])
            if files:
                base = Path(r"D:\ComfyUI\output")
                src = base / files[-1]
                if not src.exists():
                    cand = sorted(base.rglob(Path(files[-1]).name))
                    if cand:
                        src = cand[-1]
                dst = Path(a.out)
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.write_bytes(src.read_bytes())
                print(f"done {time.time()-t0:.0f}s -> {dst} "
                      f"({dst.stat().st_size//1024} KB)", flush=True)
                return 0
            print("finished but no audio output", flush=True)
            print(json.dumps(outs, ensure_ascii=False)[:500])
            return 2
        if int(time.time() - t0) % 60 < 5:
            print(f"  ...{int(time.time()-t0)}s", flush=True)
    raise SystemExit("超时")


if __name__ == "__main__":
    raise SystemExit(main())
