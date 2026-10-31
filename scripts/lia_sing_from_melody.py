#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把提取出的旋律（含原始节奏格数与连续 f0）转成 DiffSinger 输入。

与 lia_sing.py 的区别：
  - 每字时长取自原曲的 cells（0.25s/格），不再用固定时长
  - 可选注入 f0 曲线（从原唱提取），让音高有滑音和起伏，不是一格一格的跳

用法：
  python scripts/lia_sing_from_melody.py \
      --melody src/sep/htdemucs/wem/melody.json \
      --f0 src/sep/htdemucs/wem/f0.npy \
      --lyrics "屏幕一亮我就醒|竖起耳朵听你讲|..." \
      -o mv_lia/ds_wem.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

MODEL_PHONES = set(
    """AP SP a ai an ang ao b c ch d e ei en eng er f g h i ia ian iang iao ie in ing
    iong iu j k l m n o ong ou p q r s sh t u ua uai uan uang ui un uo v van ve vn
    w x y z zh""".split()
)
PHONE_ALIAS = {"ir": "i", "E": "e", "En": "en"}
INITIALS = ("zh", "ch", "sh", "b", "p", "m", "f", "d", "t", "n", "l",
            "g", "k", "h", "j", "q", "x", "r", "z", "c", "s", "y", "w")

DICT = Path(r"D:\Alysia\models\diffsinger\DiffSinger-1.7.1\dictionaries\opencpop-extension.txt")


def load_dict() -> dict[str, list[str]]:
    m = {}
    for line in DICT.read_text(encoding="utf-8").splitlines():
        parts = line.split("\t")
        if len(parts) >= 2:
            m[parts[0].strip()] = parts[1].split()
    return m


def split_phone(py: str, table: dict[str, list[str]]) -> list[str]:
    py = py.lower().strip()
    if py in table:
        return table[py]
    for ini in INITIALS:
        if py.startswith(ini) and len(py) > len(ini):
            rest = py[len(ini):]
            if rest in table:
                return table[ini] + table[rest] if ini in table else table[rest]
            return [ini, rest]
    return [py]


def normalize(phones):
    out, bad = [], {}
    for ph in phones:
        if ph in MODEL_PHONES:
            out.append(ph)
        elif ph in PHONE_ALIAS:
            out.append(PHONE_ALIAS[ph])
        else:
            bad[ph] = bad.get(ph, 0) + 1
            out.append("i")
    if bad:
        print("警告: 未知音素已兜底:", bad)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--melody", required=True)
    ap.add_argument("--lyrics", required=True, help="用 | 分隔每句")
    ap.add_argument("--f0", help="可选的 f0 曲线 .npy")
    ap.add_argument("--f0-timestep", type=float, default=0.005)
    ap.add_argument("--grid", type=float, default=0.25)
    ap.add_argument("--transpose", type=int, default=0, help="整体升/降半音数")
    ap.add_argument("-o", "--out", required=True)
    a = ap.parse_args()

    import librosa
    from pypinyin import lazy_pinyin

    mel = json.loads(Path(a.melody).read_text(encoding="utf-8"))
    pairs = [(n, c) for n, c in zip(mel["notes"], mel["cells"]) if n > 0]
    lines = [s for s in a.lyrics.split("|") if s]
    chars = list("".join(lines))
    if len(chars) != len(pairs):
        print(f"字数 {len(chars)} vs 音符 {len(pairs)}，按较少者截断")
    n = min(len(chars), len(pairs))
    chars, pairs = chars[:n], pairs[:n]

    table = load_dict()
    ph_seq, note_seq, ph_dur, is_slur = [], [], [], []
    for ch, (midi, cells) in zip(chars, pairs):
        syl = lazy_pinyin(ch)[0]
        phones = split_phone(syl, table)
        dur = cells * a.grid
        k = len(phones)
        for i, ph in enumerate(phones):
            ph_seq.append(ph)
            # 声母起音(0)，韵母延音到下一个字(1)：字头清楚，字尾连贯
            is_slur.append(1 if i > 0 else 0)
            note_seq.append(librosa.midi_to_note(int(midi) + a.transpose).replace("♯", "#").replace("♭", "b"))
            if k == 1:
                ph_dur.append(dur)
            elif i == 0:
                ph_dur.append(dur * 0.28)
            else:
                ph_dur.append(dur * 0.72 / (k - 1))
    ph_seq = normalize(ph_seq)
    total = float(np.sum(ph_dur))
    print(f"音素 {len(ph_seq)} / 总时长 {total:.2f}s（按原曲节奏）")

    ds = {
        "ph_seq": " ".join(ph_seq),
        "note_seq": " ".join(note_seq),
        "note_dur_seq": " ".join(f"{d:.4f}" for d in ph_dur),
        "ph_dur": " ".join(f"{d:.4f}" for d in ph_dur),
        "is_slur_seq": " ".join(str(v) for v in is_slur),
        "input_type": "phoneme",
        "f0_timestep": a.f0_timestep,
        "text": "".join(chars),
        "item_name": "lia_mv",
    }

    # 注入 f0：把原唱的音高曲线重采样到 ph_dur 的总长度上
    if a.f0 and Path(a.f0).exists():
        f0 = np.load(a.f0)
        src_n = len(f0)
        dst_n = int(total / a.f0_timestep)
        idx = np.linspace(0, src_n - 1, dst_n)
        f0_rs = np.interp(idx, np.arange(src_n), f0)
        f0_rs = np.nan_to_num(f0_rs, nan=0.0)
        ds["f0_seq"] = " ".join(f"{v:.1f}" for v in f0_rs)
        voiced = float(np.mean(f0_rs > 0))
        print(f"已注入 f0 曲线：{dst_n} 点，有声比例 {voiced:.0%}")

    Path(a.out).write_text(json.dumps(ds, ensure_ascii=False, indent=2), encoding="utf-8")
    print("已写出", a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
