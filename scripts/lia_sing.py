#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把歌词 + 旋律转成 DiffSinger 可直接渲染的 ds 输入文件。

已固化打通链路需要的全部细节：
  - note_seq 用音名（C4），不是 MIDI 数字（模型读不了 60）
  - 音素对照模型的 62 个音素表规范化（字典里的 ir -> i）
  - ph_dur = null 走自动时长（填了反而要求四段等长）
  - 补 text / item_name（音素模式不参与编码，但代码会引用）

用法：
  python scripts/lia_sing.py mv_lia/lyrics_star.json -o mv_lia/ds_star.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

BASE = Path(r"D:\Alysia\models\diffsinger")
DICT_CANDIDATES = [
    BASE / "DiffSinger-1.7.1" / "dictionaries" / "opencpop-extension.txt",
    BASE / "DiffSinger-main" / "dictionaries" / "opencpop-extension.txt",
]

# 模型实际音素表（由加载日志确认）
MODEL_PHONES = set(
    """AP SP a ai an ang ao b c ch d e ei en eng er f g h i ia ian iang iao ie in ing
    iong iu j k l m n o ong ou p q r s sh t u ua uai uan uang ui un uo v van ve vn
    w x y z zh""".split()
)
# 字典写法与模型音素表的差异
PHONE_ALIAS = {"ir": "i", "E": "e", "En": "en"}

INITIALS = ("zh", "ch", "sh", "b", "p", "m", "f", "d", "t", "n", "l",
            "g", "k", "h", "j", "q", "x", "r", "z", "c", "s", "y", "w")


def load_dict() -> dict[str, list[str]]:
    for p in DICT_CANDIDATES:
        if p.exists():
            m = {}
            for line in p.read_text(encoding="utf-8").splitlines():
                parts = line.split("\t")
                if len(parts) >= 2:
                    m[parts[0].strip()] = parts[1].split()
            return m
    raise SystemExit("找不到 opencpop 音素字典")


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


def normalize(phones: list[str]) -> list[str]:
    fixed, unknown = [], {}
    for ph in phones:
        if ph in MODEL_PHONES:
            fixed.append(ph)
        elif ph in PHONE_ALIAS:
            fixed.append(PHONE_ALIAS[ph])
        else:
            unknown[ph] = unknown.get(ph, 0) + 1
            fixed.append("i")
    if unknown:
        print(f"警告: 以下音素不在模型表里，已兜底为 i: {unknown}")
    return fixed


def build_ds(lyrics: dict, table: dict[str, list[str]]) -> dict:
    import librosa
    from pypinyin import lazy_pinyin

    ph_seq: list[str] = []
    note_seq: list[str] = []
    note_dur: list[float] = []
    dur = float(lyrics.get("default_dur", 0.42))
    gap = float(lyrics.get("line_gap", 0.25))

    for li, line in enumerate(lyrics["lines"]):
        syllables = lazy_pinyin(line["text"])
        notes = line["notes"]
        if len(syllables) != len(notes):
            print(f"警告: 第{li+1}句「{line['text']}」{len(syllables)} 音节 vs {len(notes)} 音高，按较少者对齐")
        for syl, midi in zip(syllables, notes):
            phones = split_phone(syl, table)
            n = len(phones)
            for k, ph in enumerate(phones):
                ph_seq.append(ph)
                note_seq.append("rest" if int(midi) <= 0 else librosa.midi_to_note(int(midi)))
                if n == 1:
                    note_dur.append(round(dur, 4))
                elif k == 0:
                    note_dur.append(round(dur * 0.30, 4))
                else:
                    note_dur.append(round(dur * 0.70 / (n - 1), 4))
        if li != len(lyrics["lines"]) - 1:
            ph_seq.append("SP")
            note_seq.append("rest")
            note_dur.append(round(gap, 4))

    ph_seq = normalize(ph_seq)
    return {
        "ph_seq": " ".join(ph_seq),
        "note_seq": " ".join(note_seq),
        "note_dur_seq": " ".join(f"{x:.3f}" for x in note_dur),
        "is_slur_seq": " ".join("0" for _ in ph_seq),
        "ph_dur": None,
        "input_type": "phoneme",
        "f0_timestep": 0.005,
        "text": " ".join(x["text"] for x in lyrics["lines"]),
        "item_name": "lia_mv",
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("lyrics_json")
    ap.add_argument("-o", "--out", default=None)
    a = ap.parse_args()

    lyrics = json.loads(Path(a.lyrics_json).read_text(encoding="utf-8"))
    ds = build_ds(lyrics, load_dict())
    out = Path(a.out) if a.out else Path(a.lyrics_json).with_name("ds.json")
    out.write_text(json.dumps(ds, ensure_ascii=False, indent=2), encoding="utf-8")

    total = sum(float(x) for x in ds["note_dur_seq"].split())
    print(f"音素 {len(ds['ph_seq'].split())} / 音符 {len(ds['note_seq'].split())} / 时长 {total:.1f}s")
    print(f"已写出 {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
