#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""莉娅一期视频的生产与投稿流水线。

一条命令从 narration.txt 走到「已提交」：

    python scripts/lia_publish.py run <期目录> --submit

也可以只跑某几段，或用已有成品重新投稿：

    python scripts/lia_publish.py run <期目录> --steps frames,tts,build
    python scripts/lia_publish.py scaffold <期目录>          # 生成 scenes.json / episode.json 草稿
    python scripts/lia_publish.py publish <期目录> --submit  # 只投稿（要求 film.mp4 + cover.jpg 已存在）

期目录约定：

    <期目录>/
      narration.txt     必需，= 旁白逐段，一行一段
      scenes.json       可选，= 每段的标题/卡片/姿态；缺失时按 narration 自动生成
      episode.json      可选，= 标题/简介/标签/分区/声明；缺失时用推导值
      frames/ audio/ segs/ film.mp4 cover.jpg   由本脚本产出
      publish_receipt.json                      投稿后回执

安全性：不加 --submit 时只做到「成片 + 封面就绪」，不会向外发布。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------- 常量

FONT_B = "C:/Windows/Fonts/msyhbd.ttc"
FONT_R = "C:/Windows/Fonts/msyh.ttc"

# 立绘来源：优先期目录 assets/，回退到共享参考素材
REF_ASSETS = Path(r"D:\Alysia\workspace\lia_batch_20261028\ep10_three_second_spell\assets")
REF_SCORE = Path(r"D:\Alysia\workspace\lia_batch_20261028\ep10_three_second_spell\audio\original_score.wav")

# 投稿浏览器：独立 profile，登录态持久化在这里
PROFILE_DIR = Path(r"D:\Alysia\workspace\lia_batch_20261028\.publish_profile")
CDP_PORT = 9222
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

VOICE = "zh-CN-XiaoyiNeural"
RATE = "+8%"

W, H = 1920, 1080
BG1, BG2 = (38, 24, 56), (19, 12, 30)
CARD, BORDER = (18, 14, 28), (126, 100, 158)
GOLD, PINK = (247, 201, 108), (232, 150, 190)
WHITE, MUTED = (255, 252, 250), (172, 154, 192)

POSES = ["explain", "think", "worry", "proud", "confused", "determined",
         "surprise", "relieved", "tired", "pout", "point", "reveal", "wave", "celebrate"]

CATEGORY_DEFAULT = "动画"
DECLARATION_DEFAULT = "含AI生成内容"


# ---------------------------------------------------------------- 通用

def run(cmd, **kw):
    """执行外部命令，失败时带上 stderr 抛错。"""
    p = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if p.returncode != 0:
        raise RuntimeError(f"命令失败: {' '.join(map(str, cmd))}\n{p.stderr[-800:]}")
    return p.stdout


def probe_duration(path: Path) -> float:
    out = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
               "-of", "csv=p=0", str(path)])
    return float(out.strip())


def log(msg: str) -> None:
    print(msg, flush=True)


# ---------------------------------------------------------------- 读取期目录

def read_narration(ep: Path) -> list[str]:
    raw = (ep / "narration.txt").read_text(encoding="utf-8")
    lines = [ln.strip() for ln in raw.split("\n") if ln.strip()]
    if not lines:
        raise SystemExit(f"{ep}/narration.txt 是空的")
    return lines


def guess_title(line: str, limit: int = 14) -> str:
    """从旁白里截一个像标题的片段。"""
    s = re.sub(r"^[“\"'（(]+", "", line)
    m = re.split(r"[。！？；，：、]", s)
    head = m[0] if m and m[0] else s
    if len(head) > limit:
        head = head[:limit]
    return head.strip() or "莉娅故事"


def guess_card(line: str) -> list:
    """按句子特征猜一个卡片样式，够用即可，人可以在 scenes.json 里改。"""
    nums = re.findall(r"\d+", line)
    if nums:
        big = nums[0]
        return ["big", big, "画面示意"]
    if len(line) <= 16:
        return ["q", line]
    if "？" in line:
        return ["q", re.split(r"[？。]", line)[0][:16]]
    return ["bullets", [line[:18], line[18:36]] if len(line) > 18 else [line[:18]]]


def load_scenes(ep: Path, narration: list[str]) -> list[dict]:
    p = ep / "scenes.json"
    if p.exists():
        data = json.loads(p.read_text(encoding="utf-8"))
        if len(data) != len(narration):
            log(f"提醒: scenes.json 有 {len(data)} 段，narration 有 {len(narration)} 段，按 narration 为准")
        scenes = []
        for i, line in enumerate(narration):
            s = data[i] if i < len(data) else {}
            scenes.append({
                "title": s.get("title") or guess_title(line),
                "card": s.get("card") or guess_card(line),
                "pose": s.get("pose") or POSES[i % len(POSES)],
                "subtitle": line,
            })
        return scenes
    return [{
        "title": guess_title(line),
        "card": guess_card(line),
        "pose": POSES[i % len(POSES)],
        "subtitle": line,
    } for i, line in enumerate(narration)]


def load_meta(ep: Path, narration: list[str]) -> dict:
    p = ep / "episode.json"
    if p.exists():
        meta = json.loads(p.read_text(encoding="utf-8"))
    else:
        meta = {}
    first = narration[0] if narration else ""
    meta.setdefault("title", first[:24] or "莉娅故事")
    meta.setdefault("desc", "\n\n".join(narration[:3]) + "\n\n莉娅的原创剧情动画。人物、事件与世界观均为虚构，含AI生成内容。")
    meta.setdefault("tags", ["原创动画", "AI", "马娘", "剧情", "莉娅"])
    meta.setdefault("category", CATEGORY_DEFAULT)
    meta.setdefault("declaration", DECLARATION_DEFAULT)
    meta.setdefault("cover", {})
    # 系列化：series + issue 同时存在时，画面左上角显示「系列 · 题号」而不是段号
    meta.setdefault("series", "")
    meta.setdefault("issue", "")
    return meta


# ---------------------------------------------------------------- 画面

def render_frames(ep: Path, scenes: list[dict], force: bool = False, series: str = "", issue: str = "") -> list[Path]:
    from PIL import Image, ImageDraw, ImageFont

    out = ep / "frames"
    out.mkdir(parents=True, exist_ok=True)
    assets = ep / "assets" if (ep / "assets").is_dir() else REF_ASSETS
    if not assets.is_dir():
        raise SystemExit(f"找不到立绘目录: {assets}")

    def font(path, size):
        return ImageFont.truetype(path, size)

    def gradient(w, h, c1, c2):
        strip = Image.new("RGB", (1, h))
        d = ImageDraw.Draw(strip)
        for y in range(h):
            t = y / max(1, h - 1)
            d.point((0, y), tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3)))
        return strip.resize((w, h), Image.BILINEAR)

    def wrap(d, text, fnt, maxw):
        """按标点断句、再按宽度组装，避免拆词和中式标点落在行首。"""
        def width(t):
            return d.textlength(t, font=fnt)

        chunks = [c for c in re.split(r"(?<=[。！？，、；：])", text) if c]
        lines, cur = [], ""
        for ch in chunks:
            if width(cur + ch) <= maxw:
                cur += ch
                continue
            if cur:
                lines.append(cur)
            if width(ch) <= maxw:
                cur = ch
            else:
                # 单句本身就超宽，只能硬切
                seg = ""
                for c in ch:
                    if width(seg + c) <= maxw:
                        seg += c
                    else:
                        lines.append(seg)
                        seg = c
                cur = seg
        if cur:
            lines.append(cur)
        return lines

    def soft_light(base, cx, cy, r, color, alpha):
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        steps = 26
        for i in range(steps, 0, -1):
            rr = int(r * i / steps)
            d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr],
                      fill=color + (int(alpha * (1 - i / steps) ** 1.6),))
        return Image.alpha_composite(base.convert("RGBA"), layer)

    def draw_card(d, kind, payload, ix0, iy0, ix1, iy1):
        """payload 恒为 card[1:]，各样式从里面按位置取参数。"""
        icx, icy = (ix0 + ix1) // 2, (iy0 + iy1) // 2

        def at(i, default=None):
            return payload[i] if len(payload) > i else default

        if kind == "big":
            d.text((ix0, icy - 262), str(at(0, "")), font=font(FONT_B, 300), fill=GOLD)
            tail = at(1, "")
            if tail:
                d.text((ix0, icy + 128), str(tail), font=font(FONT_R, 36), fill=MUTED)
        elif kind == "q":
            d.text((ix0, icy - 110), str(at(0, "")), font=font(FONT_B, 96), fill=GOLD)
            d.line([ix0, icy + 40, ix1, icy + 40], fill=BORDER, width=3)
        elif kind == "bullets":
            items = at(0, []) or []
            y = iy0 + 40
            for it in items:
                if y + 92 > iy1:
                    break
                d.rounded_rectangle([ix0, y, ix1, y + 92], radius=14, fill=(38, 30, 50))
                d.text((ix0 + 34, y + 24), str(it), font=font(FONT_R, 40), fill=(236, 228, 244))
                y += 112
        elif kind == "list":
            items = at(0, []) or []
            head = at(1, "")
            y = iy0 + (74 if head else 20)
            if head:
                d.text((ix0, iy0), str(head), font=font(FONT_B, 30), fill=PINK)
            for it in items:
                if y + 66 > iy1:
                    break
                d.ellipse([ix0, y + 14, ix0 + 14, y + 28], fill=GOLD)
                d.text((ix0 + 34, y), str(it), font=font(FONT_R, 38), fill=(236, 228, 244))
                y += 66
        elif kind == "bars":
            data = at(0, []) or []
            n = max(1, len(data))
            gap = 90
            avail = ix1 - ix0
            bw = min(300, max(120, (avail - gap * (n - 1)) // n))
            total = n * bw + (n - 1) * gap
            x = ix0 + max(0, (avail - total) // 2)
            mx = max([v for _, v in data] or [1]) or 1
            base_y = iy1 - 40
            for name, v in data:
                hgt = int(340 * v / mx)
                d.rounded_rectangle([x, base_y - hgt, x + bw, base_y], radius=10,
                                    fill=(GOLD if v else (90, 76, 110)))
                d.text((x + 12, base_y - hgt - 52), str(v), font=font(FONT_B, 38), fill=(236, 228, 244))
                d.text((x + 12, base_y + 12), str(name), font=font(FONT_R, 28), fill=MUTED)
                x += bw + gap
        elif kind == "grid":
            items = at(0, []) or []
            cols, cw, chh, gp = 3, 300, 210, 40
            for i, lab in enumerate(items):
                r, c = divmod(i, cols)
                x = ix0 + c * (cw + gp)
                y = iy0 + r * (chh + gp)
                if y + chh > iy1:
                    break
                d.rounded_rectangle([x, y, x + cw, y + chh], radius=14,
                                    fill=(40, 32, 52), outline=BORDER, width=2)
                d.text((x + 24, y + 24), str(lab), font=font(FONT_R, 30), fill=(210, 196, 230))
        else:
            txt = str(at(0, ""))
            lines = wrap(d, txt, font(FONT_R, 44), ix1 - ix0 - 80)
            y = iy0 + 40
            for ln in lines[:6]:
                d.text((ix0, y), ln, font=font(FONT_R, 44), fill=(232, 224, 242))
                y += 62

    produced = []
    for idx, sc in enumerate(scenes, 1):
        path = out / f"s{idx:02d}.png"
        produced.append(path)
        if path.exists() and not force:
            continue

        base = gradient(W, H, BG1, BG2).convert("RGBA")
        base = soft_light(base, 1560, 300, 620, (120, 90, 190), 55)
        base = soft_light(base, 260, 900, 700, (70, 50, 120), 45)
        d = ImageDraw.Draw(base)

        tag = f"{series} · {issue}" if (series and issue) else f"莉娅故事 · {idx:02d}"
        tf = font(FONT_R, 26)
        tw = d.textlength(tag, font=tf)
        d.rounded_rectangle([96, 74, 96 + tw + 52, 120], radius=23,
                            fill=(56, 41, 76), outline=(150, 124, 182), width=2)
        d.text((122, 83), tag, font=tf, fill=(238, 226, 246))

        d.text((100, 148), sc["title"], font=font(FONT_B, 78), fill=WHITE)

        cx0, cy0, cx1, cy1 = 108, 320, 1230, 860
        d.rounded_rectangle([cx0, cy0, cx1, cy1], radius=26, fill=CARD, outline=BORDER, width=3)
        d.text((cx0 + 40, cy0 + 28), "虚构界面", font=font(FONT_R, 26), fill=(150, 130, 172))

        card = list(sc["card"]) if isinstance(sc["card"], (list, tuple)) else ["bullets", str(sc["card"])]
        kind = card[0] if card else "bullets"
        payload = card[1:]
        draw_card(d, kind, payload, cx0 + 40, cy0 + 96, cx1 - 40, cy1 - 44)

        pose = sc.get("pose", "think")
        png = assets / f"presenter_{pose}.png"
        if not png.exists():
            png = assets / "presenter_think.png"
        ch = Image.open(png).convert("RGBA")
        th = 860
        ch = ch.resize((int(ch.width * th / ch.height), th), Image.LANCZOS)
        base.alpha_composite(ch, (W - ch.width - 110, 126))
        d = ImageDraw.Draw(base)

        dec = "原创虚构剧情 · 含AI生成内容"
        df = font(FONT_R, 24)
        d.text((W - d.textlength(dec, font=df) - 96, 70), dec, font=df, fill=(196, 180, 212))
        sig = "莉娅 / 原创 AI 演绎"
        sf = font(FONT_R, 24)
        d.text((W - d.textlength(sig, font=sf) - 96, 112), sig, font=sf, fill=(196, 180, 212))

        sub_f = font(FONT_R, 44)
        # 字幕限制在左侧安全区（立绘从 x=1290 起），否则长句右端会被人物压住
        SUB_MAXW, SUB_CX = 1040, 620
        lines = wrap(d, sc["subtitle"], sub_f, SUB_MAXW)
        if len(lines) > 1 and len(lines[-1]) <= 2:
            lines[-2] += lines[-1]
            lines.pop()
        lh = 58
        # 底部对齐固定基线，避免两行字幕压到卡片下边缘
        y = 1020 - lh * len(lines)
        for ln in lines:
            x = SUB_CX - d.textlength(ln, font=sub_f) / 2
            for dx, dy in ((-2, 0), (2, 0), (0, -2), (0, 2)):
                d.text((x + dx, y + dy), ln, font=sub_f, fill=(0, 0, 0))
            d.text((x, y), ln, font=sub_f, fill=WHITE)
            y += lh

        d.line([100, 1046, W - 100, 1046], fill=(190, 172, 210), width=2)
        base.convert("RGB").save(path, quality=95)
        log(f"  画面 {path.name}")

    return produced


# ---------------------------------------------------------------- 配音

def synth_tts(ep: Path, narration: list[str], force: bool = False) -> list[Path]:
    import asyncio
    import edge_tts

    out = ep / "audio"
    out.mkdir(parents=True, exist_ok=True)
    paths = [out / f"s{i:02d}.mp3" for i in range(1, len(narration) + 1)]
    todo = [(p, t) for p, t in zip(paths, narration) if force or not p.exists()]
    if not todo:
        log("  配音已存在，跳过")
        return paths

    async def go():
        for p, text in todo:
            for attempt in range(3):
                try:
                    await edge_tts.Communicate(text, VOICE, rate=RATE).save(str(p))
                    log(f"  配音 {p.name}")
                    break
                except Exception:
                    if attempt == 2:
                        raise
                    await asyncio.sleep(2)

    asyncio.run(go())
    return paths


# ---------------------------------------------------------------- 合成

def build_video(ep: Path, force: bool = False) -> Path:
    frames = sorted((ep / "frames").glob("s*.png"))
    audios = sorted((ep / "audio").glob("s*.mp3"))
    if len(frames) != len(audios):
        raise SystemExit(f"画面 {len(frames)} 张，配音 {len(audios)} 段，数量不一致")
    final = ep / "film.mp4"
    if final.exists() and not force:
        log("  成片已存在，跳过")
        return final

    segs = ep / "segs"
    segs.mkdir(parents=True, exist_ok=True)
    seg_files = []
    for i, (fr, au) in enumerate(zip(frames, audios), 1):
        seg = segs / f"seg{i:02d}.mp4"
        seg_files.append(seg)
        if seg.exists() and not force:
            continue
        dur = probe_duration(au)
        vf = ("zoompan=z='min(zoom+0.00055,1.085)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
              ":d=1:s=1920x1080:fps=30,format=yuv420p")
        run(["ffmpeg", "-v", "error", "-y", "-loop", "1", "-framerate", "30",
             "-i", str(fr), "-i", str(au), "-vf", vf, "-t", f"{dur + 0.30:.3f}",
             "-af", "apad=pad_dur=0.30,afade=t=in:st=0:d=0.04",
             "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-r", "30",
             "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2", "-shortest", str(seg)])

    lst = segs / "list.txt"
    lst.write_text("".join(f"file '{s.as_posix()}'\n" for s in seg_files), encoding="utf-8")
    raw = ep / "film_raw.mp4"
    run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
         "-c", "copy", str(raw)])
    total = probe_duration(raw)
    log(f"  拼接完成 {total:.1f}s")

    if REF_SCORE.exists():
        run(["ffmpeg", "-v", "error", "-y", "-i", str(raw), "-stream_loop", "-1", "-i", str(REF_SCORE),
             "-filter_complex",
             f"[0:a]loudnorm=I=-16:TP=-1.5:LRA=11[a0];"
             f"[1:a]volume=0.11,atrim=0:{total:.2f},afade=t=in:st=0:d=1.5,"
             f"afade=t=out:st={max(0, total-7):.2f}:d=7[a1];"
             f"[a0][a1]amix=inputs=2:duration=first:normalize=0[a]",
             "-map", "0:v", "-map", "[a]", "-c:v", "copy",
             "-c:a", "aac", "-b:a", "192k", "-ar", "48000", str(final)])
    else:
        shutil.copy2(raw, final)
        log("  未找到配乐，仅旁白")
    log(f"  成片 {final}")
    return final


# ---------------------------------------------------------------- 封面

def make_cover(ep: Path, meta: dict, force: bool = False) -> Path:
    from PIL import Image, ImageDraw, ImageFont

    out = ep / "cover.jpg"
    if out.exists() and not force:
        log("  封面已存在，跳过")
        return out

    assets = ep / "assets" if (ep / "assets").is_dir() else REF_ASSETS
    cfg = meta.get("cover") or {}
    line1 = cfg.get("line1") or meta["title"][:12]
    line2 = cfg.get("line2") or ""
    big = str(cfg.get("big") or "")
    sub = cfg.get("sub") or ""
    pose = cfg.get("pose") or "tired"

    def font(p, s):
        return ImageFont.truetype(p, s)

    strip = Image.new("RGB", (1, H))
    d = ImageDraw.Draw(strip)
    c1, c2 = (46, 28, 68), (16, 10, 26)
    for y in range(H):
        t = y / (H - 1)
        d.point((0, y), tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3)))
    base = strip.resize((W, H), Image.BILINEAR).convert("RGBA")

    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dl = ImageDraw.Draw(lay)
    for i in range(26, 0, -1):
        rr = int(700 * i / 26)
        dl.ellipse([1500 - rr, 240 - rr, 1500 + rr, 240 + rr],
                   fill=(130, 95, 200, int(60 * (1 - i / 26) ** 1.6)))
    base = Image.alpha_composite(base, lay)
    d = ImageDraw.Draw(base)

    d.text((100, 170), line1, font=font(FONT_B, 92), fill=WHITE)
    if line2:
        d.text((100, 290), line2, font=font(FONT_B, 92), fill=WHITE)
    if big:
        d.text((96, 380), big, font=font(FONT_B, 330), fill=GOLD)
    if sub:
        d.text((100, 830), sub, font=font(FONT_R, 52), fill=(214, 198, 232))
    d.line([100, 986, W - 100, 986], fill=(190, 172, 210), width=2)
    d.text((100, 1000), "莉娅的谜题小屋 · 原创 AI 演绎", font=font(FONT_R, 30), fill=(200, 184, 216))

    png = assets / f"presenter_{pose}.png"
    if not png.exists():
        png = assets / "presenter_think.png"
    ch = Image.open(png).convert("RGBA")
    th = 900
    ch = ch.resize((int(ch.width * th / ch.height), th), Image.LANCZOS)
    base.alpha_composite(ch, (W - ch.width - 70, 120))
    base.convert("RGB").save(out, quality=94)
    log(f"  封面 {out.name}")
    return out


# ---------------------------------------------------------------- 投稿

def ensure_browser():
    """确保有一个带 CDP 的 Edge 实例在跑，返回 playwright 连接。"""
    from playwright.sync_api import sync_playwright

    import urllib.request

    def alive():
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{CDP_PORT}/json/version", timeout=3)
            return True
        except Exception:
            return False

    if not alive():
        PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        subprocess.Popen([EDGE, f"--user-data-dir={PROFILE_DIR}",
                          f"--remote-debugging-port={CDP_PORT}",
                          "--remote-allow-origins=*", "--no-first-run", "--start-maximized"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(30):
            time.sleep(1)
            if alive():
                break
        else:
            raise SystemExit("Edge 调试端口没起来")

    pw = sync_playwright().start()
    browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{CDP_PORT}")
    ctx = browser.contexts[0]
    pg = ctx.pages[0] if ctx.pages else ctx.new_page()
    pg.bring_to_front()
    return pw, browser, ctx, pg


def check_login(ctx) -> dict:
    r = ctx.request.get("https://api.bilibili.com/x/web-interface/nav", timeout=20000)
    d = (r.json() or {}).get("data") or {}
    return d


def wait_login(ctx, pg, timeout=600) -> dict:
    d = check_login(ctx)
    if d.get("isLogin"):
        return d
    log("需要登录：请在打开的窗口里扫码，最多等 10 分钟")
    pg.goto("https://passport.bilibili.com/login", timeout=90000)
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(4)
        d = check_login(ctx)
        if d.get("isLogin"):
            return d
    raise SystemExit("登录超时")


def click_text(pg, text, frames=None) -> str:
    expr = """(t)=>{
      const els=Array.from(document.querySelectorAll('div,span,button,li')).filter(e=>(e.innerText||'').trim()===t&&e.offsetParent!==null);
      if(!els.length) return 'NO'; els[els.length-1].click(); return 'OK';
    }"""
    for fr in (frames or [pg]):
        try:
            if fr.evaluate(expr, text) == "OK":
                return "OK"
        except Exception:
            continue
    return "NO"


def find_upload_input(pg):
    for _ in range(40):
        for fr in pg.frames:
            try:
                for el in fr.query_selector_all('input[type=file]'):
                    acc = el.get_attribute("accept") or ""
                    if ".mp4" in acc:
                        return el
            except Exception:
                continue
        time.sleep(1)
    return None


def fill_text(pg, selector: str, value: str) -> bool:
    el = pg.query_selector(selector)
    if not el:
        return False
    el.click()
    pg.keyboard.press("Control+A")
    pg.keyboard.press("Delete")
    el.fill(value)
    return True


def fill_desc(pg, desc: str) -> bool:
    ed = pg.query_selector(".ql-editor")
    if not ed:
        return False
    ed.click()
    for i, para in enumerate(desc.split("\n")):
        if not para.strip():
            pg.keyboard.press("Enter")
            continue
        pg.keyboard.type(para)
        pg.wait_for_timeout(120)
        pg.keyboard.press("Enter")
    return True


def add_tags(pg, tags: list[str]) -> int:
    tl = pg.query_selector('input[placeholder="按回车键Enter创建标签"]')
    if not tl:
        return 0
    n = 0
    for t in tags:
        tl.click()
        pg.wait_for_timeout(120)
        tl.type(t)
        pg.wait_for_timeout(220)
        pg.keyboard.press("Enter")
        pg.wait_for_timeout(320)
        n += 1
    return n


def pick_category(pg, name: str) -> bool:
    pg.evaluate("()=>document.body.click()")
    pg.wait_for_timeout(400)
    try:
        pg.locator(".selector-container").click(force=True)
    except Exception:
        return False
    pg.wait_for_timeout(1200)
    r = pg.evaluate("""(t)=>{
      const box=Array.from(document.querySelectorAll('div,ul')).find(e=>{const x=(e.innerText||'');return x.includes('科技数码')&&x.includes('汽车')&&x.length<600;});
      if(!box) return 'NOBOX';
      const el=Array.from(box.querySelectorAll('*')).filter(e=>e.children.length===0&&(e.innerText||'').trim()===t)[0];
      if(!el) return 'NOITEM';
      ['mouseenter','mousedown','mouseup','click'].forEach(k=>el.dispatchEvent(new MouseEvent(k,{bubbles:true,cancelable:true,view:window})));
      return 'OK';
    }""", name)
    pg.wait_for_timeout(1400)
    return r == "OK"


def pick_declaration(pg, text: str) -> bool:
    d = pg.query_selector('input[placeholder="请选择符合您视频内容的创作声明"]')
    if not d:
        return False
    d.click()
    pg.wait_for_timeout(1000)
    r = pg.evaluate("""(t)=>{
      const norm=s=>(s||'').replace(/\\s+/g,'');
      const els=Array.from(document.querySelectorAll('li')).filter(e=>norm(e.innerText)===norm(t));
      if(!els.length) return 'NO';
      els[els.length-1].click(); return 'OK';
    }""", text)
    pg.wait_for_timeout(800)
    pg.evaluate("()=>document.body.click()")
    return r == "OK"


def upload_cover(pg, cover: Path) -> bool:
    click_text(pg, "添加封面")
    pg.wait_for_timeout(3000)
    for fr in pg.frames:
        try:
            for el in fr.query_selector_all('input[type=file]'):
                acc = (el.get_attribute("accept") or "").lower()
                if "image" in acc:
                    el.set_input_files(str(cover))
                    pg.wait_for_timeout(4000)
                    click_text(pg, "完成")
                    pg.wait_for_timeout(2500)
                    # 双比例同步确认
                    if "确认同步" in pg.inner_text("body"):
                        click_text(pg, "确认同步")
                        pg.wait_for_timeout(2500)
                        click_text(pg, "完成")
                        pg.wait_for_timeout(2500)
                    return "封面制作" not in pg.inner_text("body")
        except Exception:
            continue
    return False


def publish(ep: Path, meta: dict, submit: bool, dry_run: bool = False, check: bool = False) -> dict:
    film = ep / "film.mp4"
    cover = ep / "cover.jpg"
    if not film.exists():
        raise SystemExit(f"缺成片: {film}")
    if not cover.exists():
        raise SystemExit(f"缺封面: {cover}")

    receipt_path = ep / "publish_receipt.json"
    receipt = {
        "title": meta["title"],
        "category": meta["category"],
        "declaration": meta["declaration"],
        "tags": meta["tags"],
        "film_bytes": film.stat().st_size,
        "duration_sec": round(probe_duration(film), 2),
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "status": "started",
    }

    pw, browser, ctx, pg = ensure_browser()
    try:
        who = wait_login(ctx, pg)
        receipt["account"] = {"uid": who.get("mid"), "name": who.get("uname")}
        log(f"  账号: {who.get('uname')} ({who.get('mid')})")

        pg.goto("https://member.bilibili.com/platform/upload/video/frame", timeout=90000)
        pg.wait_for_timeout(5000)

        el = find_upload_input(pg)
        if not el:
            pg.screenshot(path=str(ep / "fail_no_input.png"))
            raise SystemExit("找不到视频上传控件")

        if check:
            receipt["status"] = "check_ok"
            receipt["note"] = "仅验证浏览器/登录/投稿页/上传控件，未上传任何文件"
            receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
            log("  自检通过：登录、投稿页、上传控件均正常")
            return receipt
        el.set_input_files(str(film))
        log("  视频已提交上传，等待转码")

        done = False
        for _ in range(180):
            pg.wait_for_timeout(2000)
            if "上传完成" in pg.inner_text("body"):
                done = True
                break
        if not done:
            pg.screenshot(path=str(ep / "fail_upload.png"))
            raise SystemExit("上传未完成")
        log("  上传完成")

        fill_text(pg, 'input[placeholder="请输入稿件标题"]', meta["title"])
        fill_desc(pg, meta["desc"])
        add_tags(pg, meta["tags"])
        log("  标题/简介/标签已填")

        pick_category(pg, meta["category"])
        pick_declaration(pg, meta["declaration"])
        log("  分区/声明已选")

        okc = upload_cover(pg, cover)
        receipt["cover_ok"] = okc
        log(f"  封面 {'已应用' if okc else '未确认'}")
        if not okc:
            pg.screenshot(path=str(ep / "fail_cover.png"))
            raise SystemExit("封面上传失败，未提交")

        pg.screenshot(path=str(ep / "before_submit.png"), full_page=True)
        if dry_run or not submit:
            receipt["status"] = "ready_not_submitted"
            receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
            log("  已就绪，未提交（加 --submit 才会发布）")
            return receipt

        pg.evaluate("()=>{const e=document.querySelector('.submit-add'); if(e) e.click();}")
        log("  已点击投稿，等待结果")
        ok = False
        for _ in range(40):
            pg.wait_for_timeout(1500)
            if "upload-manager" in pg.url:
                ok = True
                break
            txt = pg.inner_text("body")
            if "上传成功" in txt or "投稿成功" in txt or "投递成功" in txt:
                ok = True
                break
            errs = [l for l in txt.split("\n") if "请先" in l and "封面" in l]
            if errs:
                pg.screenshot(path=str(ep / "fail_submit.png"))
                raise SystemExit(f"提交被拒: {errs[0]}")

        receipt["status"] = "submitted" if ok else "unknown"
        receipt["submitted_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        pg.screenshot(path=str(ep / "after_submit.png"), full_page=True)

        # 去稿件管理页核实
        if ok:
            pg.goto("https://member.bilibili.com/platform/upload-manager/article", timeout=90000)
            pg.wait_for_timeout(6000)
            txt = pg.inner_text("body")
            receipt["manager_verified"] = meta["title"][:12] in txt
            (ep / "manager_snapshot.txt").write_text(txt, encoding="utf-8")

        receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
        log(f"  结果: {receipt['status']}")
        return receipt
    finally:
        try:
            pw.stop()
        except Exception:
            pass


# ---------------------------------------------------------------- 命令

def cmd_scaffold(ep: Path) -> None:
    narration = read_narration(ep)
    scenes = load_scenes(ep, narration)
    meta = load_meta(ep, narration)
    (ep / "scenes.json").write_text(json.dumps(scenes, ensure_ascii=False, indent=2), encoding="utf-8")
    (ep / "episode.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"已生成 {ep/'scenes.json'}（{len(scenes)} 段）和 {ep/'episode.json'}，请人工校对标题与卡片")


def cmd_run(ep: Path, steps: list[str], force: bool, submit: bool, dry_run: bool, check: bool = False) -> None:
    narration = read_narration(ep)
    scenes = load_scenes(ep, narration)
    meta = load_meta(ep, narration)

    if "frames" in steps:
        log(f"[1/5] 画面 {len(scenes)} 张")
        render_frames(ep, scenes, force, meta.get("series", ""), str(meta.get("issue", "")))
    if "tts" in steps:
        log(f"[2/5] 配音 {len(narration)} 段")
        synth_tts(ep, narration, force)
    if "build" in steps:
        log("[3/5] 合成")
        build_video(ep, force)
    if "cover" in steps:
        log("[4/5] 封面")
        make_cover(ep, meta, force)
    if "publish" in steps:
        log("[5/5] 投稿")
        publish(ep, meta, submit, dry_run, check)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="莉娅一期视频的生产与投稿流水线")
    ap.add_argument("command", choices=["run", "scaffold", "publish"])
    ap.add_argument("episode", help="期目录，例如 workspace/lia_batch_20261028/ep12_xxx")
    ap.add_argument("--steps", default="frames,tts,build,cover,publish",
                    help="要执行的步骤，逗号分隔：frames,tts,build,cover,publish")
    ap.add_argument("--force", action="store_true", help="重做已存在的产物")
    ap.add_argument("--submit", action="store_true", help="真正提交发布（不加则停在待提交）")
    ap.add_argument("--dry-run", action="store_true", help="只上传填表，不点投稿")
    ap.add_argument("--check", action="store_true", help="只验证浏览器/登录/控件，不上传文件")
    args = ap.parse_args(argv)

    ep = Path(args.episode).resolve()
    if not ep.is_dir():
        raise SystemExit(f"期目录不存在: {ep}")

    if args.command == "scaffold":
        cmd_scaffold(ep)
    elif args.command == "publish":
        meta = load_meta(ep, read_narration(ep))
        publish(ep, meta, args.submit, args.dry_run, args.check)
    else:
        steps = [s.strip() for s in args.steps.split(",") if s.strip()]
        cmd_run(ep, steps, args.force, args.submit, args.dry_run, args.check)
    return 0


if __name__ == "__main__":
    sys.exit(main())
