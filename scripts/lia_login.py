#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""B站扫码登录：生成二维码并在同一进程内轮询，直到保存凭证。

必须同一个进程里跑 —— bilibili-mcp 的登录会话只存在内存里，
分两次调用 bili_login / bili_login_check 会丢会话。

用装好依赖的解释器：
    D:/Alysia/workspace/lia_batch_20261028/.venv-bili/Scripts/python.exe

用法：python scripts/lia_login.py [--timeout 210]
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
except Exception:
    pass

import mcp_server as m  # noqa: E402


async def main(timeout: int) -> int:
    r = json.loads(await m.bili_login())
    if r.get("status") != "qrcode_ready":
        print(json.dumps(r, ensure_ascii=False))
        return 1
    print(f"QR_READY {r.get('qrcode_file')}", flush=True)

    waited = 0
    while waited < timeout:
        await asyncio.sleep(3)
        waited += 3
        try:
            s = json.loads(await m.bili_login_check())
        except Exception as e:
            print(f"CHECK_ERR {e}", flush=True)
            continue
        st = s.get("status")
        if st in ("scanning", "confirming"):
            print(f"WAITING {st}", flush=True)
            continue
        if st == "done":
            print("LOGIN_DONE", flush=True)
            print(json.dumps(s, ensure_ascii=False))
            return 0
        if st == "timeout":
            print("LOGIN_TIMEOUT", flush=True)
            return 2
        print(f"STATE {st}", flush=True)
    print("GAVE_UP", flush=True)
    return 3


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--timeout", type=int, default=210)
    a = ap.parse_args()
    sys.exit(asyncio.run(main(a.timeout)))
