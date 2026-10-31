#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""为莉娅宣传曲生成一段轻快的 BGM（程序化合成，无版权问题）。

和弦进行 C - Am - F - G，100 BPM，与 lyrics.json 的拍速对齐。
输出 48kHz 立体声 wav，音量压在 -18 LUFS 附近，给人声留空间。

用法：python scripts/make_bgm.py -o mv_lia/bgm.wav --seconds 34.8
"""

from __future__ import annotations

import argparse
import wave
from pathlib import Path

import numpy as np

SR = 48000

# 和弦（低八度铺底，避免和 C4-G4 的人声旋律打架）
CHORDS = {
    "C":  [130.81, 164.81, 196.00],   # C3 E3 G3
    "Am": [110.00, 130.81, 164.81],   # A2 C3 E3
    "F":  [116.54, 174.61, 220.00],   # F2 F3 A3
    "G":  [123.47, 196.00, 246.94],   # B2 G3 B3
}
PROGRESSION = ["C", "Am", "F", "G"]


def env(n: int, attack: float, decay: float, sr: int = SR) -> np.ndarray:
    a = max(1, int(attack * sr))
    e = np.ones(n)
    e[:a] = np.linspace(0, 1, a)
    tail = np.linspace(1, 0, max(1, n - a)) ** decay
    e[a:] = tail[: n - a]
    return e


def tone(freq: float, dur: float, amp: float = 1.0, kind: str = "pluck") -> np.ndarray:
    n = int(dur * SR)
    t = np.arange(n) / SR
    if kind == "pluck":
        w = (np.sin(2 * np.pi * freq * t)
             + 0.35 * np.sin(2 * np.pi * freq * 2 * t)
             + 0.15 * np.sin(2 * np.pi * freq * 3 * t))
        return amp * w * env(n, 0.006, 3.2)
    if kind == "pad":
        w = (np.sin(2 * np.pi * freq * t)
             + 0.2 * np.sin(2 * np.pi * freq * 1.005 * t))
        return amp * w * env(n, 0.15, 1.1)
    # bass
    w = np.sin(2 * np.pi * freq * t) + 0.25 * np.sin(2 * np.pi * freq * 2 * t)
    return amp * w * env(n, 0.01, 2.0)


def kick(dur: float = 0.16) -> np.ndarray:
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = 120 * np.exp(-t * 22) + 45
    return 0.85 * np.sin(2 * np.pi * np.cumsum(f) / SR) * env(n, 0.002, 4.0)


def hat(dur: float = 0.05) -> np.ndarray:
    n = int(dur * SR)
    rng = np.random.default_rng(7)
    return 0.12 * rng.standard_normal(n) * env(n, 0.001, 6.0)


def build(seconds: float, bpm: float = 100.0) -> np.ndarray:
    beat = 60.0 / bpm
    bar = beat * 4
    total = int(seconds * SR) + SR
    buf = np.zeros(total)

    n_bars = int(np.ceil(seconds / bar))
    for b in range(n_bars):
        chord = PROGRESSION[b % len(PROGRESSION)]
        notes = CHORDS[chord]
        t0 = b * bar

        # 铺底 pad：整小节
        for f in notes:
            seg = tone(f, bar, amp=0.16, kind="pad")
            i = int(t0 * SR)
            buf[i:i + len(seg)] += seg[: max(0, min(len(seg), total - i))]

        # 琶音：每拍一个和弦音
        for k in range(4):
            f = notes[k % len(notes)] * 2  # 升八度做琶音
            seg = tone(f, beat * 0.95, amp=0.22, kind="pluck")
            i = int((t0 + k * beat) * SR)
            buf[i:i + len(seg)] += seg[: max(0, min(len(seg), total - i))]

        # 低音：每小节根音
        seg = tone(notes[0] / 2, bar * 0.9, amp=0.30, kind="bass")
        i = int(t0 * SR)
        buf[i:i + len(seg)] += seg[: max(0, min(len(seg), total - i))]

        # 鼓：底鼓 1、3 拍，hihat 每半拍
        for k in (0, 2):
            seg = kick()
            i = int((t0 + k * beat) * SR)
            buf[i:i + len(seg)] += seg[: max(0, min(len(seg), total - i))]
        for k in range(8):
            seg = hat()
            i = int((t0 + k * beat / 2) * SR)
            buf[i:i + len(seg)] += seg[: max(0, min(len(seg), total - i))]

    buf = buf[: int(seconds * SR)]
    # 简单限幅 + 首尾淡入淡出
    peak = np.max(np.abs(buf)) or 1.0
    buf = buf / peak * 0.85
    fade = int(0.8 * SR)
    buf[:fade] *= np.linspace(0, 1, fade)
    buf[-fade:] *= np.linspace(1, 0, fade)
    return buf


def write_wav(path: Path, mono: np.ndarray) -> None:
    # 轻微立体声加宽
    left = mono
    right = np.concatenate([np.zeros(240), mono[:-240]]) * 0.92
    stereo = np.stack([left, right], axis=1)
    data = (np.clip(stereo, -1, 1) * 32767).astype("<i2")
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(data.tobytes())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--out", default="bgm.wav")
    ap.add_argument("--seconds", type=float, default=34.8)
    ap.add_argument("--bpm", type=float, default=100.0)
    a = ap.parse_args()
    buf = build(a.seconds, a.bpm)
    out = Path(a.out)
    write_wav(out, buf)
    print(f"已写出 {out}（{a.seconds:.1f}s, {a.bpm:.0f}bpm）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
