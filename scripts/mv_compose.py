#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把 H3 动作片段 + BGM +（可选）歌声 + 歌词字幕 合成宣传片。

用法：
  python scripts/mv_compose.py --clips mv_lia/clips --bgm mv_lia/bgm.wav \
      --lyrics mv_lia/lyrics.json -o mv_lia/mv_preview.mp4
  # 有歌声时加 --vocal mv_lia/vocal.wav

片段循环拼到歌词总长度；歌词按每句的字数与拍速推进。
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

FONT = "C\:/Windows/Fonts/msyhbd.ttc"  # ffmpeg filter 里冒号必须转义
OUT_W, OUT_H = 1280, 720


def probe_dur(p: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(p)], capture_output=True, text=True, check=True)
    return float(out.stdout.strip())


def line_timeline(lyrics: dict) -> list[tuple[float, float, str]]:
    """按字数和拍速算每句的起止时间。"""
    dur = float(lyrics.get("default_dur", 0.42))
    gap = float(lyrics.get("line_gap", 0.3))
    t = 0.0
    rows = []
    for line in lyrics["lines"]:
        n = len(line["text"])
        d = n * dur
        rows.append((t, t + d, line["text"]))
        t += d + gap
    return rows


def esc(text: str) -> str:
    return text.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\u2019")


def build(clips: list[Path], bgm: Path | None, vocal: Path | None,
          lyrics: dict, out: Path) -> None:
    rows = line_timeline(lyrics)
    total = rows[-1][1] + 0.6

    # 1) 归一化每段到统一分辨率与时长，拼成一条循环不足就重复
    seg_files = []
    for c in clips:
        seg_files.append(c)
    durs = [probe_dur(c) for c in seg_files]
    cycle = sum(durs)
    n_loops = max(1, int(total // cycle) + (1 if total % cycle else 0))

    inputs = []
    filters = []
    idx = 0
    planned = []
    acc = 0.0
    for _ in range(n_loops):
        for c, d in zip(seg_files, durs):
            if acc >= total:
                break
            inputs += ["-i", str(c)]
            planned.append((idx, d))
            idx += 1
            acc += d
        if acc >= total:
            break

    for i, (idx_i, d) in enumerate(planned):
        filters.append(
            f"[{idx_i}:v]scale={OUT_W}:{OUT_H}:force_original_aspect_ratio=increase,"
            f"crop={OUT_W}:{OUT_H},setsar=1,fps=30,format=yuv420p,"
            f"trim=duration={d:.3f}[v{i}]")

    concat_in = "".join(f"[v{i}]" for i in range(len(planned)))
    filters.append(f"{concat_in}concat=n={len(planned)}:v=1:a=0[vcat]")

    # 2) 左侧信息面板：盖住首帧里那个空框，换成系列名
    filters.append(
        f"[vcat]drawbox=x=42:y=184:w=484:h=246:color=0x221530@0.92:t=fill,"
        f"drawtext=fontfile='{FONT}':text='莉娅的谜题小屋':"
        f"fontcolor=0xF7C96C:fontsize=44:x=60:y=232,"
        f"drawtext=fontfile='{FONT}':text='谜题 · 第 001 期':"
        f"fontcolor=0xD8CCEE:fontsize=28:x=60:y=300,"
        f"drawtext=fontfile='{FONT}':text='AI 马娘 · 原创':"
        f"fontcolor=0xB8A8CC:fontsize=24:x=60:y=352[panel]")

    # 3) 歌词字幕
    cur = "panel"
    for k, (s, e, txt) in enumerate(rows):
        nxt = f"s{k}"
        filters.append(
            f"[{cur}]drawtext=fontfile='{FONT}':text='{esc(txt)}':"
            f"fontcolor=white:fontsize=48:borderw=6:bordercolor=black@0.85:"
            f"x=(w-text_w)/2:y=h-150:enable='between(t,{s:.2f},{e:.2f})'[{nxt}]")
        cur = nxt

    filters.append(f"[{cur}]trim=duration={total:.3f},setpts=PTS-STARTPTS[vout]")

    # 3) 音频：BGM + 可选歌声
    audio_inputs = []
    if bgm:
        audio_inputs.append(("bgm", bgm))
    if vocal:
        audio_inputs.append(("vocal", vocal))

    a_idx = idx
    alabels = []
    for name, p in audio_inputs:
        inputs += ["-i", str(p)]
        alabels.append((name, a_idx))
        a_idx += 1

    if len(alabels) == 2:
        (n1, i1), (n2, i2) = alabels
        # 歌声为主，BGM 压到 28%
        filters.append(f"[{i1}:a]volume=0.28,atrim=0:{total:.3f},"
                       f"afade=t=out:st={max(0,total-2):.2f}:d=2[abgm]")
        filters.append(f"[{i2}:a]loudnorm=I=-16:TP=-1.5:LRA=11,atrim=0:{total:.3f}[avoc]")
        filters.append("[avoc][abgm]amix=inputs=2:duration=first:normalize=0[aout]")
    elif len(alabels) == 1:
        (n1, i1) = alabels[0]
        if n1 == "bgm":
            filters.append(f"[{i1}:a]volume=0.55,atrim=0:{total:.3f},"
                           f"afade=t=out:st={max(0,total-2):.2f}:d=2[aout]")
        else:
            filters.append(f"[{i1}:a]loudnorm=I=-16:TP=-1.5:LRA=11,atrim=0:{total:.3f}[aout]")
    else:
        raise SystemExit("至少需要 BGM 或歌声之一")

    cmd = ["ffmpeg", "-v", "error", "-y"] + inputs + [
        "-filter_complex", ";".join(filters),
        "-map", "[vout]", "-map", "[aout]",
        "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-r", "30",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
        "-t", f"{total:.3f}", str(out)]
    subprocess.run(cmd, check=True)
    print(f"已写出 {out}（{total:.1f}s, {OUT_W}x{OUT_H}）")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--clips", required=True)
    ap.add_argument("--bgm")
    ap.add_argument("--vocal")
    ap.add_argument("--lyrics", required=True)
    ap.add_argument("-o", "--out", default="mv.mp4")
    a = ap.parse_args()

    clip_dir = Path(a.clips)
    clips = sorted(clip_dir.glob("*.mp4"))
    if not clips:
        raise SystemExit(f"{clip_dir} 里没有片段")
    print(f"片段 {len(clips)} 个: {[c.name for c in clips]}")

    lyrics = json.loads(Path(a.lyrics).read_text(encoding="utf-8"))
    build(clips, Path(a.bgm) if a.bgm else None,
          Path(a.vocal) if a.vocal else None, lyrics, Path(a.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
