#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""从音符序列生成干净的 f0 曲线（cascade 模式必需）。

和「从原唱提取 f0」的区别：这里每个音素严格用自己那个音符的频率，
不存在 pyin 的八度误判和噪声。边界处做 25ms 线性滑音，避免音高突变太生硬。

用法：
  python scripts/build_f0.py mv_lia/ds_wem4.json -o mv_lia/ds_wem5.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np


def note_to_freq(name: str) -> float:
    import librosa
    if not name or name == "rest":
        return 0.0
    try:
        return float(librosa.midi_to_hz(librosa.note_to_midi(name)))
    except Exception:
        return 0.0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("ds")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--portamento", type=float, default=0.025, help="边界滑音时长（秒）")
    ap.add_argument("--vibrato", type=float, default=0.0, help="颤音深度（比例，0 关闭）")
    a = ap.parse_args()

    ds = json.loads(Path(a.ds).read_text(encoding="utf-8"))
    notes = ds["note_seq"].split()
    durs = [float(x) for x in ds["ph_dur"].split()]
    ts = float(ds.get("f0_timestep", 0.005))
    total = sum(durs)
    n = max(1, int(total / ts))

    # 每个音素覆盖的时间段，填对应频率
    f0 = np.zeros(n)
    bounds = []
    t = 0.0
    for name, dur in zip(notes, durs):
        s, e = int(t / ts), min(n, int((t + dur) / ts))
        f0[s:e] = note_to_freq(name)
        bounds.append((s, e, f0[s]))
        t += dur

    # 边界滑音：在音素交界处用 portamento 时长做线性过渡
    k = max(1, int(a.portamento / ts))
    for i in range(1, len(bounds)):
        s, _, cur = bounds[i]
        prev = bounds[i - 1][2]
        if prev <= 0 or cur <= 0:
            continue
        for j in range(k):
            idx = s + j
            if idx >= n:
                break
            w = j / k
            f0[idx] = prev * (1 - w) + cur * w

    # 可选颤音：5.5Hz 正弦调制，只作用于有声段
    if a.vibrato > 0:
        tt = np.arange(n) * ts
        voiced = f0 > 0
        f0[voiced] *= (1 + a.vibrato * np.sin(2 * np.pi * 5.5 * tt[voiced]))

    ds["f0_seq"] = " ".join(f"{v:.2f}" for v in f0)
    Path(a.out).write_text(json.dumps(ds, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"f0 点数 {n}，有声比例 {np.mean(f0 > 0):.0%}，总时长 {total:.2f}s")
    print(f"已写出 {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
