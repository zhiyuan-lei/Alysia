#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""莉娅的热门内容调研：只读浏览 B 站，产出一份可对比的选题报告。

约束（重要）：
  - 全程只读：不评论、不点赞、不投币、不关注、不私信
  - 有节流：每次请求间隔至少 1.2 秒，避免触发风控
  - 只记录公开数据：标题、播放、点赞、弹幕、评论数、时长

用法：
  VP=workspace/lia_batch_20261028/.venv-bili/Scripts/python.exe
  $VP scripts/lia_research.py --out docs/research_20261101.md
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

BASE = Path(r"D:\Alysia")
VP = BASE / "workspace" / "lia_batch_20261028" / ".venv-bili" / "Scripts" / "python.exe"
BILI = BASE / "scripts" / "lia_bili.py"

# 与本账号相关的检索词（来自 social policy 的 related_terms）
TERMS = ["谜题", "马娘", "AI 虚拟", "原创动画", "小剧场"]


def call(*args: str, retries: int = 2) -> dict:
    """调用 lia_bili.py，返回解析后的 JSON。"""
    cmd = [str(VP), str(BILI), *args]
    for attempt in range(retries + 1):
        try:
            out = subprocess.run(cmd, capture_output=True, text=True,
                                 encoding="utf-8", errors="ignore", timeout=60)
            txt = (out.stdout or "").strip()
            if txt.startswith("{"):
                return json.loads(txt)
        except Exception:
            pass
        if attempt < retries:
            time.sleep(2 + attempt * 2)
    return {}


def throttle(sec: float = 1.2) -> None:
    time.sleep(sec)


def parse_play(v) -> int:
    """把 '12.3万' / '1234' 之类转成整数。"""
    s = str(v or "0").strip()
    mult = 1
    if s.endswith("万"):
        mult, s = 10000, s[:-1]
    elif s.endswith("亿"):
        mult, s = 100000000, s[:-1]
    try:
        return int(float(s) * mult)
    except ValueError:
        return 0


def rank_score(v: dict) -> tuple[float, str]:
    """返回 (互动率, 口径名)。hot 有 like，search 只有 review（评论数）。"""
    play = parse_play(v.get("play"))
    if play <= 0:
        return 0.0, "-"
    if v.get("like") is not None:
        return parse_play(v["like"]) / play, "点赞率"
    return parse_play(v.get("review")) / play, "评论率"


def dur_sec(v: dict) -> int:
    """hot 的 duration 是秒数，search 的是 m:ss 字符串。"""
    d = v.get("duration")
    if isinstance(d, (int, float)):
        return int(d)
    parts = str(d or "").split(":")
    try:
        if len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        return int(parts[0])
    except (ValueError, IndexError):
        return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--top", type=int, default=30, help="热榜条数")
    a = ap.parse_args()

    lines: list[str] = []
    def w(s: str = "") -> None:
        lines.append(s)
        print(s, flush=True)

    now = datetime.now()
    w(f"# 莉娅热门内容调研 · {now:%Y-%m-%d %H:%M}")
    w()
    w(f"> 自动生成，只读浏览，不含任何互动动作。")
    w()

    # 1) 全站热榜
    w("## 一、全站热榜")
    w()
    hot = call("hot", "--num", str(a.top))
    vids = hot.get("videos") or []
    throttle()
    if vids:
        w("| 播放 | 点赞率 | 时长 | 标题 |")
        w("|---|---|---|---|")
        for v in vids[:a.top]:
            t = (v.get("title") or "").replace("|", "/")[:44]
            rate, _ = rank_score(v)
            m, sec = divmod(dur_sec(v), 60)
            w(f"| {v.get('play')} | {rate:.1%} | {m}:{sec:02d} | {t} |")
    else:
        w("（热榜拉取失败）")
    w()

    # 2) 相关词搜索
    w("## 二、相关题材检索")
    w()
    collected: list[dict] = []
    for term in TERMS:
        r = call("search", term, "--num", "10")
        vs = r.get("videos") or []
        throttle()
        w(f"### {term}（{len(vs)} 条）")
        w()
        if not vs:
            w("（无结果）")
            w()
            continue
        w("| 播放 | 评论率 | 时长 | 标题 |")
        w("|---|---|---|---|")
        for v in vs[:8]:
            rate, _ = rank_score(v)
            t = (v.get("title") or "").replace("|", "/")[:44]
            m, sec = divmod(dur_sec(v), 60)
            w(f"| {v.get('play')} | {rate:.1%} | {m}:{sec:02d} | {t} |")
            v["_term"] = term
            collected.append(v)
        w()

    # 3) 亮点分析
    w("## 三、亮点分析")
    w()
    if collected:
        by_rate = sorted(collected, key=lambda v: rank_score(v)[0], reverse=True)[:8]
        w("### 评论率最高的 8 条（内容质量信号）")
        w()
        w("| 评论率 | 播放 | 时长 | 标题 |")
        w("|---|---|---|---|")
        for v in by_rate:
            rate, _ = rank_score(v)
            t = (v.get("title") or "").replace("|", "/")[:44]
            m, sec = divmod(dur_sec(v), 60)
            w(f"| {rate:.1%} | {v.get('play')} | {m}:{sec:02d} | {t} |")
        w()

        # 标题长度分布
        lens = [len(v.get("title") or "") for v in collected if v.get("title")]
        if lens:
            lens.sort()
            w("### 标题长度")
            w()
            w(f"- 样本 {len(lens)} 条，中位 {lens[len(lens)//2]} 字，"
              f"最短 {lens[0]}，最长 {lens[-1]}")
            w()

        # 时长分布
        w("### 时长分布")
        w()
        buckets = {"<1min": 0, "1-3min": 0, "3-5min": 0, ">5min": 0}
        for v in collected:
            sec = dur_sec(v)
            if sec <= 0:
                continue
            if sec < 60:
                buckets["<1min"] += 1
            elif sec < 180:
                buckets["1-3min"] += 1
            elif sec < 300:
                buckets["3-5min"] += 1
            else:
                buckets[">5min"] += 1
        for k, n in buckets.items():
            w(f"- {k}: {n} 条")
        w()
    else:
        w("（无足够样本做分析）")
        w()

    # 4) 待人工判断的空位
    w("## 四、下一步建议（自动生成，需人工确认）")
    w()
    w("- 上面点赞率高的条目，值得打开看前 15 秒怎么开场")
    w("- 标题长度中位数可作为下一条视频标题的参考区间")
    w("- 时长分布能反推观众对这个题材的耐心")
    w()
    w("---")
    w(f"生成时间：{now:%Y-%m-%d %H:%M:%S}")

    out = Path(a.out)
    if not out.is_absolute():
        out = BASE / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n已写出 {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
