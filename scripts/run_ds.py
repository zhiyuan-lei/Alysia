#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""运行 DiffSinger v1.7.1 的 main.py，并补上被新 scipy 移除的旧 API。

DiffSinger v1.7.1 依赖 scipy 1.9 的 `scipy.signal.kaiser`，
而 scipy 1.13 把它移到了 `scipy.signal.windows.kaiser`。

用法（参数原样透传给 main.py）：
  python scripts/run_ds.py <ds.json> --exp opencpop --ckpt 160000 --pitch --out <dir>
"""

from __future__ import annotations

import runpy
import sys
from pathlib import Path

DS_ROOT = Path(r"D:\Alysia\models\diffsinger\DiffSinger-1.7.1")

# --- 兼容补丁：老代码引用的、新 scipy 已移除或改位的符号 ---
import scipy.signal  # noqa: E402
import scipy.signal.windows as _w  # noqa: E402

if not hasattr(scipy.signal, "kaiser"):
    scipy.signal.kaiser = _w.kaiser

# torch 2.6+ 的 torch.load 默认 weights_only=True，老 ckpt 会加载失败
import torch  # noqa: E402
_orig_load = torch.load


def _patched_load(*args, **kwargs):
    kwargs.setdefault("weights_only", False)
    return _orig_load(*args, **kwargs)


torch.load = _patched_load


def main() -> int:
    import os

    # 先把所有路径参数解析成绝对路径，再 chdir（否则相对路径会跑到 DiffSinger 目录下）
    argv = sys.argv[1:]
    out_dir = None
    for i, a in enumerate(argv):
        if a.endswith(".json"):
            argv[i] = str(Path(a).resolve())
        if a == "--out" and i + 1 < len(argv):
            out_dir = Path(argv[i + 1]).resolve()
            argv[i + 1] = str(out_dir)

    os.chdir(DS_ROOT)          # DiffSinger 用相对路径找 dictionaries / checkpoints
    sys.path.insert(0, str(DS_ROOT))
    sys.argv = ["main.py"] + argv
    runpy.run_path(str(DS_ROOT / "main.py"), run_name="__main__")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
