#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""从混音里提取主旋律，量化成音符序列（用于给热门曲重填词）。

思路：pyin 取基频 -> 按固定网格取样 -> 量化到半音 -> 合并同音高的连续格。
输出可直接塞进 lyrics.json 的 notes 字段（MIDI 音号）。

用法：
  python scripts/extract_melody.py src/wem.wav --start 30 --dur 20 --grid 0.25
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("audio")
    ap.add_argument("--start", type=float, default=0.0)
    ap.add_argument("--dur", type=float, default=20.0)
    ap.add_argument("--grid", type=float, default=0.25, help="取样网格（秒）")
    ap.add_argument("--fmin", type=float, default=130.0)
    ap.add_argument("--fmax", type=float, default=800.0)
    a = ap.parse_args()

    import librosa

    y, sr = librosa.load(a.audio, sr=22050, mono=True, offset=a.start, duration=a.dur)
    print(f"载入 {len(y)/sr:.1f}s @ {sr}Hz")

    # pyin：比 yin 稳，慢一些
    f0, voiced, _ = librosa.pyin(y, fmin=a.fmin, fmax=a.fmax, sr=sr, frame_length=2048)
    times = librosa.times_like(f0, sr=sr)
    print(f"f0 帧数 {len(f0)}，有声比例 {np.mean(~np.isnan(f0)):.1%}")

    n_grid = int(a.dur / a.grid)
    notes, cells = [], []
    for i in range(n_grid):
        t = i * a.grid
        idx = np.searchsorted(times, t)
        idx = min(idx, len(f0) - 1)
        v = f0[idx]
        if np.isnan(v):
            cells.append(0)
        else:
            midi = int(round(librosa.hz_to_midi(v)))
            cells.append(max(0, min(127, midi)))

    # 合并连续同音高，得到"音符 + 时长格数"
    runs = []
    for m in cells:
        if runs and runs[-1][0] == m:
            runs[-1][1] += 1
        else:
            runs.append([m, 1])

    out = {
        "grid": a.grid,
        "notes": [m for m, _ in runs],
        "cells": [c for _, c in runs],
        "midi_preview": [m for m, _ in runs][:40],
        "freq_preview": [round(float(librosa.midi_to_hz(m)), 1) if m else 0 for m, _ in runs][:40],
    }
    print("音符串（MIDI）:", out["midi_preview"])
    print("对应音名:", [librosa.midi_to_note(m) if m else "rest" for m, _ in runs][:40])
    print(f"共 {len(runs)} 个音，覆盖 {sum(c for _, c in runs) * a.grid:.1f}s")

    p = Path(a.audio).with_name("melody.json")
    p.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print("已写出", p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
