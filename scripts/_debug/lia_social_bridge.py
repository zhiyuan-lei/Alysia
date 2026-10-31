#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""莉娅社交互动的浏览器桥接层（替代原来的 Codex CUA）。

只负责浏览器 I/O：读评论、读视频上下文、发评论。规则、额度、去重、人设
全部由 `alysia.cli social` 与 identity/lia_persona.md 决定，本脚本不做判断。

用法：

    python scripts/lia_social_bridge.py own                 # 读自己视频下的评论
    python scripts/lia_social_bridge.py context BV1xxxxxxxxx # 读某视频的标题/简介/热评
    python scripts/lia_social_bridge.py send BV1xxxxxxxxx "评论内容" --image 截图.png
    python scripts/lia_social_bridge.py check                # 只看登录与端口

所有写入动作都会截图，并把结果以 JSON 打到 stdout，供 social receipt 引用。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

PROFILE_DIR = Path(r"D:\Alysia\workspace\lia_batch_20261028\.publish_profile")
CDP_PORT = 9222
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
EVIDENCE = Path(r"D:\Alysia\workspace\social\evidence")

# 递归穿透所有 open shadow root
JS_WALK = r"""
(() => {
  const out = [];
  const walk = (root, depth) => {
    if (!root || depth > 8) return;
    root.querySelectorAll('*').forEach(e => {
      const tag = e.tagName.toLowerCase();
      const cls = (typeof e.className === 'string' ? e.className : '');
      if (tag === 'div' && e.getAttribute('contenteditable') === 'true') {
        out.push({kind: 'editable', cls: cls.slice(0,60), depth});
      }
      const t = (e.innerText || '').trim();
      if ((tag === 'button' || tag === 'span') && t && t.length <= 4 &&
          (t === '发布' || t === '发送' || t === '回复' || t === '确定')) {
        out.push({kind: 'btn', text: t, depth});
      }
      if (e.shadowRoot) walk(e.shadowRoot, depth + 1);
    });
  };
  walk(document, 0);
  return out;
})()
"""

JS_TEXTS = r"""
(() => {
  const out = [];
  const skip = new Set(['script','style','noscript','link','meta','template']);
  const walk = (root, depth) => {
    if (!root || depth > 8) return;
    root.querySelectorAll('*').forEach(e => {
      const tag = e.tagName.toLowerCase();
      if (skip.has(tag)) return;
      const editable = e.getAttribute && e.getAttribute('contenteditable') === 'true';
      if (!e.children.length || editable) {
        const t = (e.innerText || '').trim();
        if (t && t.length > 1 && t.length < 600) out.push(t);
      }
      if (e.shadowRoot) walk(e.shadowRoot, depth + 1);
    });
  };
  walk(document, 0);
  return [...new Set(out)].slice(0, 60);
})()
"""

JS_FOCUS = r"""
() => {
  const eds = [];
  const walk = (root, depth) => {
    if (!root || depth > 8) return;
    root.querySelectorAll('*').forEach(e => {
      if (e.getAttribute && e.getAttribute('contenteditable') === 'true') eds.push(e);
      if (e.shadowRoot) walk(e.shadowRoot, depth + 1);
    });
  };
  walk(document, 0);
  const vis = eds.filter(e => e.getClientRects().length > 0);
  if (!vis.length) return 'NO_EDITOR';
  const el = vis[0];
  el.scrollIntoView({block: 'center'});
  el.focus();
  return 'FOCUSED:' + vis.length;
}
"""

JS_COMMENT_TEXTS = r"""
() => {
  const host = document.querySelector('bili-comments');
  if (!host || !host.shadowRoot) return [];
  const skip = new Set(['script', 'style', 'noscript', 'link', 'meta', 'template']);
  const ui = new Set(['评论', '最热', '最新', '发布', '发送', '回复', '请输入内容', '展开',
                      '收起', '查看更多', '没有更多评论', '同时转发到我的动态',
                      '选择或输入你想@的人', '天青色等烟雨，评论区在等你']);
  const out = [];
  const walk = (root, depth) => {
    if (!root || depth > 8) return;
    root.querySelectorAll('*').forEach(e => {
      if (skip.has(e.tagName.toLowerCase())) return;
      if (!e.children.length) {
        const t = (e.innerText || '').trim();
        if (t && t.length > 3 && t.length < 500 && !ui.has(t)
            && !t.startsWith(':host') && !t.includes('{')) out.push(t);
      }
      if (e.shadowRoot) walk(e.shadowRoot, depth + 1);
    });
  };
  walk(host.shadowRoot, 0);
  return [...new Set(out)].slice(0, 50);
}
"""

JS_EDITOR_TEXT = r"""
() => {
  const eds = [];
  const walk = (root, depth) => {
    if (!root || depth > 8) return;
    root.querySelectorAll('*').forEach(e => {
      if (e.getAttribute && e.getAttribute('contenteditable') === 'true') eds.push(e);
      if (e.shadowRoot) walk(e.shadowRoot, depth + 1);
    });
  };
  walk(document, 0);
  return eds.map(e => e.textContent || '').join('');
}
"""

JS_CLICK_PUBLISH = r"""
() => {
  const cands = [];
  const walk = (root, depth) => {
    if (!root || depth > 8) return;
    root.querySelectorAll('*').forEach(e => {
      const t = (e.innerText || '').trim();
      const tag = e.tagName.toLowerCase();
      if ((tag === 'button' || tag === 'span' || tag === 'div') && t === '发布' &&
          (e.offsetParent !== null || e.getClientRects().length)) {
        cands.push(e);
      }
      if (e.shadowRoot) walk(e.shadowRoot, depth + 1);
    });
  };
  walk(document, 0);
  const enabled = cands.filter(e => !e.disabled && !/disabled/i.test(e.className || ''));
  if (!enabled.length) return 'NO_BTN';
  const el = enabled[0];
  el.scrollIntoView({block: 'center'});
  el.click();
  return 'CLICKED:' + enabled.length;
}
"""


def alive() -> bool:
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{CDP_PORT}/json/version", timeout=3)
        return True
    except Exception:
        return False


def ensure_browser():
    if not alive():
        PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        import subprocess
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

    from playwright.sync_api import sync_playwright
    pw = sync_playwright().start()
    browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{CDP_PORT}")
    ctx = browser.contexts[0]
    pg = ctx.pages[0] if ctx.pages else ctx.new_page()
    pg.bring_to_front()
    return pw, ctx, pg


def whoami(ctx) -> dict:
    r = ctx.request.get("https://api.bilibili.com/x/web-interface/nav", timeout=20000)
    return (r.json() or {}).get("data") or {}


def shot(pg, name: str) -> str:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    p = EVIDENCE / f"{name}_{time.strftime('%Y%m%d_%H%M%S')}.png"
    pg.screenshot(path=str(p), full_page=False)
    return str(p)


def video_context(pg, bvid: str) -> dict:
    pg.goto(f"https://www.bilibili.com/video/{bvid}/", timeout=90000)
    pg.wait_for_timeout(6000)
    title = pg.title().replace("_哔哩哔哩_bilibili", "")
    desc = ""
    for sel in [".desc-info-text", ".basic-desc-info", "div.desc-info"]:
        try:
            el = pg.query_selector(sel)
            if el:
                desc = el.inner_text()[:600]
                break
        except Exception:
            continue
    # 滚到评论区再读
    try:
        pg.evaluate("()=>{const e=document.querySelector('bili-comments'); if(e) e.scrollIntoView({block:'center'});}")
        pg.wait_for_timeout(3000)
        for _ in range(2):
            pg.mouse.wheel(0, 800)
            pg.wait_for_timeout(1000)
    except Exception:
        pass
    texts = pg.evaluate(JS_COMMENT_TEXTS)
    return {"bvid": bvid, "url": pg.url, "title": title, "desc": desc,
            "comments_sample": texts[:40], "observed_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}


def own_comments(pg) -> dict:
    pg.goto("https://member.bilibili.com/platform/comment/article", timeout=90000)
    pg.wait_for_timeout(8000)
    body = pg.inner_text("body")
    lines = [l.strip() for l in body.split("\n") if l.strip()]
    try:
        for label in ["视频评论", "用户可见评论"]:
            el = pg.get_by_text(label, exact=True).first
            if el.count():
                el.click()
                pg.wait_for_timeout(2500)
                break
    except Exception:
        pass
    body2 = pg.inner_text("body")
    return {
        "page": "comment-manager",
        "empty": "还没有评论" in body2,
        "raw_tail": [l for l in body2.split("\n") if l.strip()][-40:],
        "observed_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "screenshot": shot(pg, "own_comments"),
    }


def send(pg, bvid: str, text: str, dry_run: bool = False) -> dict:
    pg.goto(f"https://www.bilibili.com/video/{bvid}/", timeout=90000)
    pg.wait_for_timeout(6000)
    try:
        pg.evaluate("()=>{const e=document.querySelector('bili-comments'); if(e) e.scrollIntoView({block:'center'});}")
        pg.wait_for_timeout(2500)
        pg.mouse.wheel(0, 600)
        pg.wait_for_timeout(1500)
    except Exception:
        pass
    before = shot(pg, f"before_send_{bvid}")
    filled = pg.evaluate(JS_FOCUS)
    pg.wait_for_timeout(600)
    if filled.startswith("FOCUSED"):
        pg.keyboard.type(text, delay=45)
        pg.wait_for_timeout(1000)
    editor_text = pg.evaluate(JS_EDITOR_TEXT)
    present = text[:8] in editor_text
    if dry_run:
        pg.screenshot(path=str(EVIDENCE / f"dryrun_{bvid}.png"))
        return {"bvid": bvid, "dry_run": True, "filled": filled, "present": present,
                "before": before, "sent": False}
    clicked = pg.evaluate(JS_CLICK_PUBLISH)
    pg.wait_for_timeout(4000)
    after = shot(pg, f"after_send_{bvid}")
    editor_after = pg.evaluate(JS_EDITOR_TEXT)
    texts2 = pg.evaluate(JS_TEXTS)
    ok = clicked.startswith("CLICKED") and (
        text[:8] not in editor_after or any(text[:12] in t for t in texts2))
    return {"bvid": bvid, "text": text, "filled": filled, "clicked": clicked,
            "verified": ok, "before": before, "after": after,
            "observed_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="莉娅社交互动的浏览器桥接")
    ap.add_argument("action", choices=["check", "own", "context", "send"])
    ap.add_argument("target", nargs="?", help="bvid 或评论内容（按 action 决定）")
    ap.add_argument("text", nargs="?", help="send 时的评论内容")
    ap.add_argument("--dry-run", action="store_true", help="只填入不点发布，用于验证选择器")
    args = ap.parse_args(argv)

    pw, ctx, pg = ensure_browser()
    try:
        me = whoami(ctx)
        if not me.get("isLogin"):
            print(json.dumps({"error": "not_logged_in", "hint": "打开窗口扫码登录后重试"}, ensure_ascii=False))
            return 2
        base = {"account_uid": str(me.get("mid")), "account_name": me.get("uname")}

        if args.action == "check":
            print(json.dumps({**base, "cdp": "ok", "logged_in": True}, ensure_ascii=False, indent=1))
        elif args.action == "own":
            print(json.dumps({**base, **own_comments(pg)}, ensure_ascii=False, indent=1))
        elif args.action == "context":
            if not args.target:
                raise SystemExit("context 需要 bvid")
            print(json.dumps({**base, **video_context(pg, args.target)}, ensure_ascii=False, indent=1))
        elif args.action == "send":
            if not args.target or not args.text:
                raise SystemExit('send 需要 bvid 与评论文本：send BV1xxx "..."')
            print(json.dumps({**base, **send(pg, args.target, args.text, args.dry_run)},
                             ensure_ascii=False, indent=1))
        return 0
    finally:
        try:
            pw.stop()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
