# -*- coding: utf-8 -*-
import json, sys, time, urllib.request, uuid, importlib.util
from pathlib import Path
spec = importlib.util.spec_from_file_location("hc", r"D:\Alysia\scripts\lia_h3_clip.py")
hc = importlib.util.module_from_spec(spec); spec.loader.exec_module(hc)
BASE = Path(r"D:\Alysia\workspace\lia_batch_20261028\mv_lia")
shots = json.loads((BASE/"shots_hd.json").read_text(encoding="utf-8"))
OUT = BASE/"clips_hd"; OUT.mkdir(parents=True, exist_ok=True)

def log(m):
    print(m, flush=True)

for i, s in enumerate(shots, 1):
    dst = OUT/f"{s['name']}.mp4"
    if dst.exists() and dst.stat().st_size > 1000:
        log(f"[{i}/6] {s['name']} 已存在，跳过"); continue
    log(f"[{i}/6] {s['name']} 提交…")
    wf = hc.build_prompt(s["image"], s["text"], s["seed"], length=39, width=896, height=512,
                         steps=6, prefix=f"alysia/hd{i:02d}")
    req = urllib.request.Request("http://127.0.0.1:8188/prompt",
        data=json.dumps({"prompt":wf,"client_id":str(uuid.uuid4())}).encode(),
        headers={"Content-Type":"application/json"})
    try:
        r = json.loads(urllib.request.urlopen(req, timeout=60).read())
    except urllib.error.HTTPError as e:
        log(f"  提交失败 {e.code}: {e.read().decode('utf-8','ignore')[:300]}"); continue
    pid = r["prompt_id"]; log(f"  queued {pid}")
    t0=time.time(); ok=False
    for _ in range(240):
        time.sleep(5)
        try:
            h = json.loads(urllib.request.urlopen(f"http://127.0.0.1:8188/history/{pid}", timeout=20).read())
        except Exception:
            continue
        if pid in h:
            files=[]
            for node in (h[pid].get("outputs") or {}).values():
                for k in ("videos","images","gifs"):
                    for f in (node.get(k) or []):
                        if isinstance(f,dict) and f.get("filename"): files.append(f["filename"])
            if files:
                base = Path(r"D:\ComfyUI\output"); src = base/files[-1]
                if not src.exists():
                    c = sorted(base.rglob(Path(files[-1]).name)); src = c[-1] if c else src
                dst.write_bytes(src.read_bytes())
                log(f"  完成 {time.time()-t0:.0f}s -> {dst.name} ({dst.stat().st_size//1024}KB)"); ok=True
            else:
                log(f"  执行完但无输出: {json.dumps((h[pid].get('outputs') or {}), ensure_ascii=False)[:200]}")
            break
    if not ok: log(f"  {s['name']} 失败/超时")
log("ALL DONE")
