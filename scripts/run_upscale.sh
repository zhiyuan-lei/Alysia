#!/usr/bin/env bash
cd /d/Alysia
D=workspace/lia_batch_20261028/mv_lia
PY=/d/ComfyUI/.venv/Scripts/python.exe
for f in "$D"/clips_hd/*.mp4; do
  n=$(basename "$f" .mp4)
  out="$D/clips_1080/$n.mp4"
  if [ -f "$out" ]; then echo "[$n] 已存在，跳过"; continue; fi
  echo "[$n] 超分开始 $(date +%H:%M:%S)"
  "$PY" scripts/upscale_video.py "$f" -o "$out" --width 1920 --height 1080
  echo "[$n] 完成 $(date +%H:%M:%S) -> $(ls -la "$out" | awk '{print $5}') bytes"
done
echo "UPSCALE ALL DONE"
