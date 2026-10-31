# -*- coding: utf-8 -*-
"""分段多线程下载（HF 单连接被限速时用）。"""
import os, sys, time
import requests
from concurrent.futures import ThreadPoolExecutor

def dl(url: str, out: str, n: int = 16):
    head = requests.head(url, allow_redirects=True, timeout=30)
    size = int(head.headers.get("Content-Length") or 0)
    if not size:
        r = requests.get(url, stream=True, timeout=30)
        size = int(r.headers.get("Content-Length") or 0)
        r.close()
    print(f"size={size/1024/1024:.1f}MB workers={n}", flush=True)
    part = size // n
    tmp = out + ".parts"
    os.makedirs(tmp, exist_ok=True)

    def worker(i):
        s = i * part
        e = size - 1 if i == n - 1 else (i + 1) * part - 1
        p = os.path.join(tmp, f"{i:03d}")
        if os.path.exists(p) and os.path.getsize(p) == e - s + 1:
            return
        for attempt in range(4):
            try:
                with requests.get(url, headers={"Range": f"bytes={s}-{e}"},
                                  stream=True, timeout=90) as r:
                    with open(p, "wb") as f:
                        for c in r.iter_content(1 << 16):
                            f.write(c)
                return
            except Exception as ex:
                if attempt == 3:
                    raise SystemExit(f"part {i} failed: {ex}")
                time.sleep(2)

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=n) as ex:
        list(ex.map(worker, range(n)))
    with open(out, "wb") as f:
        for i in range(n):
            f.write(open(os.path.join(tmp, f"{i:03d}"), "rb").read())
    got = os.path.getsize(out)
    print(f"done {got/1024/1024:.1f}MB in {time.time()-t0:.0f}s "
          f"({got/1024/max(1,time.time()-t0):.0f} KB/s)", flush=True)

if __name__ == "__main__":
    dl(sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 16)
