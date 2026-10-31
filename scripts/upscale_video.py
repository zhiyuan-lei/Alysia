#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""用 spandrel + RealESRGAN 批量超分视频（逐帧推理，比走 ComfyUI API 快）。

必须用 ComfyUI 的 venv 跑（它有 torch + spandrel）：
  D:/ComfyUI/.venv/Scripts/python.exe scripts/upscale_video.py in.mp4 -o out.mp4 --scale 4

流程：拆帧 -> 批量推理 -> 缩回目标分辨率 -> 合成（保留原音轨）。
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import tempfile
from pathlib import Path

MODEL = r"D:\ComfyUI\models\upscale_models\RealESRGAN_x4plus_anime_6B.pth"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--width", type=int, default=1280, help="最终输出宽度")
    ap.add_argument("--height", type=int, default=720)
    ap.add_argument("--batch", type=int, default=4)
    a = ap.parse_args()

    import numpy as np
    import torch
    from PIL import Image
    from spandrel import ModelLoader

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"device={device}")
    mdl = ModelLoader().load_from_file(a.model).model.eval().to(device)
    # fp16 推理：显存减半、速度快一倍，超分质量几乎无差
    if device == "cuda":
        mdl = mdl.half()

    tmp = Path(tempfile.mkdtemp(prefix="up_"))
    src_dir = tmp / "src"
    out_dir = tmp / "out"
    src_dir.mkdir(); out_dir.mkdir()

    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", a.video,
                    str(src_dir / "%05d.png")], check=True)
    frames = sorted(src_dir.glob("*.png"))
    print(f"拆出 {len(frames)} 帧")

    def to_tensor(paths):
        arrs = []
        for p in paths:
            im = np.asarray(Image.open(p).convert("RGB"), dtype=np.float32) / 255.0
            arrs.append(torch.from_numpy(im).permute(2, 0, 1))
        t = torch.stack(arrs).to(device)
        return t.half() if device == "cuda" else t

    t0 = __import__("time").time()
    for i in range(0, len(frames), a.batch):
        chunk = frames[i:i + a.batch]
        with torch.no_grad():
            out = mdl(to_tensor(chunk))
        out = out.float().clamp(0, 1).cpu()
        for j, p in enumerate(chunk):
            im = Image.fromarray((out[j].permute(1, 2, 0).numpy() * 255).round().astype("uint8"))
            im = im.resize((a.width, a.height), Image.LANCZOS)
            im.save(out_dir / p.name)
        done = min(i + a.batch, len(frames))
        if done % 40 == 0 or done == len(frames):
            print(f"  {done}/{len(frames)}  {__import__('time').time()-t0:.0f}s", flush=True)

    subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", "30",
                    "-i", str(out_dir / "%05d.png"), "-i", a.video,
                    "-map", "0:v", "-map", "1:a?", "-c:v", "libx264",
                    "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "192k", "-shortest", a.out], check=True)
    print(f"完成 {a.out}  ({__import__('time').time()-t0:.0f}s)")
    shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
