#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""莉娅的 B站 执行层：薄封装 bilibili-mcp。

底层是 dsh-bili-pond（大肥鱼）内置的 `vendor/bilibili-mcp`，本脚本只做 I/O，
不做任何判断——窗口、额度、去重、人设、回执仍由 `alysia.cli social` 和
`identity/lia_persona.md` 决定。

必须用装好依赖的解释器跑：
    D:/Alysia/workspace/lia_batch_20261028/.venv-bili/Scripts/python.exe

命令：

    check                       验证凭证是否有效
    login                       生成登录二维码（输出图片路径）
    login-check                 轮询扫码结果
    video BV1xxxxxxxxx          视频信息（标题/UP/播放/时长）
    subtitle BV1xxxxxxxxx       字幕文本
    comments BV1xxxxxxxxx       评论列表（含子评论）
    hot [--ps 20]               站内热门
    search "关键词" --num 10     搜索
    reply BV1xxxxxxxxx "文本" [--rpid N] [--root M] [--dry-run]
                                发评论 / 回复（rpid=0 为新楼）

`reply` 加 --dry-run 只打印将要发送的内容，不调接口。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

MCP_DIR = Path(r"D:\Alysia\tools\bilibili-mcp")
sys.path.insert(0, str(MCP_DIR))

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

import mcp_server as m  # noqa: E402


def show(obj) -> None:
    """mcp 工具都返回 JSON 字符串，尽量结构化输出。"""
    if isinstance(obj, str):
        try:
            data = json.loads(obj)
            print(json.dumps(data, ensure_ascii=False, indent=1))
            return
        except Exception:
            print(obj)
            return
    print(json.dumps(obj, ensure_ascii=False, indent=1))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="莉娅的 B站 执行层（bilibili-mcp 薄封装）")
    ap.add_argument("action", choices=[
        "check", "login", "login-check", "video", "subtitle",
        "comments", "hot", "search", "reply"])
    ap.add_argument("target", nargs="?", help="bvid 或搜索关键词或评论文本")
    ap.add_argument("text", nargs="?", help="reply 时的评论文本")
    ap.add_argument("--num", type=int, default=30)
    ap.add_argument("--order", default="like")
    ap.add_argument("--ps", type=int, default=20)
    ap.add_argument("--rpid", type=int, default=0)
    ap.add_argument("--root", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    a = args.action

    if a == "check":
        show(asyncio.run(m.bili_check_credential()))
    elif a == "login":
        show(asyncio.run(m.bili_login()))
    elif a == "login-check":
        show(asyncio.run(m.bili_login_check()))
    elif a == "video":
        show(asyncio.run(m.bili_video_info(args.target)))
    elif a == "subtitle":
        show(asyncio.run(m.bili_subtitle(args.target)))
    elif a == "comments":
        show(asyncio.run(m.bili_comments(args.target, num=args.num, order=args.order)))
    elif a == "hot":
        show(asyncio.run(m.bili_hot_videos(pn=1, ps=args.ps)))
    elif a == "search":
        show(asyncio.run(m.bili_search(args.target, num=args.num)))
    elif a == "reply":
        bvid = args.target
        # 文本可能是第二个位置参数，也可能是 --text 形式
        text = args.text
        if not bvid or not text:
            print(json.dumps({"error": "reply 需要 bvid 和评论文本"}, ensure_ascii=False))
            return 2
        if args.dry_run:
            print(json.dumps({
                "dry_run": True, "bvid": bvid, "text": text,
                "rpid": args.rpid, "root": args.root,
                "kind": "new_comment" if args.rpid == 0 else "reply",
            }, ensure_ascii=False, indent=1))
            return 0
        show(asyncio.run(m.bili_reply(bvid, text, rpid=args.rpid, root=args.root)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
