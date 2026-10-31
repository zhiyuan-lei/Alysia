#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""从已登录的 Edge profile 导出 B站 凭证给 bilibili-mcp 用。

思路：.publish_profile 里已经登录着莉娅账号（投稿用的就是它）。
bilibili-api 只需要 4 个值：SESSDATA / bili_jct / buvid3 / dedeuserid。
Chrome/Edge 的 cookie 值是 v10 加密（AES-256-CBC，密钥被 DPAPI 包住），
本机同一用户可以直接解。

用 anaconda 的 python 跑（需要 cryptography + win32crypt）。
输出到 tools/bilibili-mcp/bili_credential.json，与扫码登录写的是同一份。

用法：python scripts/lia_cred_from_browser.py [--profile <目录>]
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

PROFILE = Path(r"D:\Alysia\workspace\lia_batch_20261028\.publish_profile")
CRED_OUT = Path(r"D:\Alysia\tools\bilibili-mcp\bili_credential.json")

WANT = {"SESSDATA", "bili_jct", "buvid3", "DedeUserID", "DedeUserID__ckMd5"}


def aes_key_from_local_state(profile: Path) -> bytes:
    import win32crypt
    state = json.loads((profile / "Local State").read_text(encoding="utf-8"))
    enc = base64.b64decode(state["os_crypt"]["encrypted_key"])
    assert enc.startswith(b"DPAPI"), "encrypted_key 不是 DPAPI 前缀"
    # CryptUnprotectData 返回 (描述, 数据) 或直接 bytes，视 pywin32 版本
    out = win32crypt.CryptUnprotectData(enc[5:], None, None, None, 0)
    return out[1] if isinstance(out, tuple) else out


def decrypt_value(blob: bytes, key: bytes) -> str | None:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    if not blob:
        return None
    prefix, payload = blob[:3], blob[3:]
    if prefix == b"v10" or prefix == b"v11":
        # Chromium 自 v10 起：nonce(12) + ciphertext + tag(16)
        try:
            raw = AESGCM(key).decrypt(payload[:12], payload[12:], None)
            # Chromium 在明文前加了 32 字节的 domain hash，剥掉才是 cookie 值
            return (raw[32:] if len(raw) > 32 else raw).decode("utf-8")
        except Exception:
            pass
        # 老版本：AES-256-CBC + IV=b' '*16
        try:
            from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
            dec = Cipher(algorithms.AES(key), modes.CBC(b" " * 16)).decryptor()
            raw = dec.update(payload) + dec.finalize()
            return raw[:-raw[-1]].decode("utf-8")
        except Exception:
            return None
    if prefix == b"v20":
        return None  # app-bound encryption，换实例解不了
    try:
        return blob.decode("utf-8")
    except Exception:
        return None


def read_cookies(profile: Path) -> dict[str, str]:
    src = profile / "Default" / "Network" / "Cookies"
    if not src.exists():
        raise SystemExit(f"找不到 Cookies: {src}")
    # 每次用全新文件名：同名临时库残留的 -wal/-shm 会回放旧状态，导致读到空快照
    fd, tmp_name = tempfile.mkstemp(prefix="lia_ck_", suffix=".db")
    os.close(fd)
    tmp = Path(tmp_name)
    shutil.copy2(src, tmp)
    db = sqlite3.connect(str(tmp))
    rows = db.execute(
        "select host_key,name,value,encrypted_value from cookies where host_key like '%bilibili%'"
    ).fetchall()
    db.close()
    key = aes_key_from_local_state(profile)
    out = {}
    for host, name, plain, enc in rows:
        if plain:
            out[name] = plain
            continue
        v = decrypt_value(enc, key)
        if v:
            out[name] = v
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default=str(PROFILE))
    a = ap.parse_args()
    profile = Path(a.profile)

    cookies = read_cookies(profile)
    print(f"解出 cookie {len(cookies)} 条: {sorted(cookies)[:10]}", flush=True)

    missing = [k for k in ("SESSDATA", "bili_jct", "buvid3", "DedeUserID") if not cookies.get(k)]
    if missing:
        print(json.dumps({"ok": False, "missing": missing,
                          "hint": "该 profile 里没有完整登录态，需要在浏览器里重新登录 B站"},
                         ensure_ascii=False))
        return 2

    cred = {
        "sessdata": cookies["SESSDATA"],
        "bili_jct": cookies["bili_jct"],
        "buvid3": cookies["buvid3"],
        "dedeuserid": cookies["DedeUserID"],
    }
    CRED_OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = CRED_OUT.with_suffix(".tmp")
    tmp.write_text(json.dumps(cred, ensure_ascii=False), encoding="utf-8")
    tmp.replace(CRED_OUT)
    print(json.dumps({"ok": True, "written": str(CRED_OUT), "uid": cred["dedeuserid"]},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
