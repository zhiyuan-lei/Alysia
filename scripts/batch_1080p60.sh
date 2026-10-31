#!/usr/bin/env bash
# 6 段高清片段 -> 1080p 超分 -> 60fps 插帧
set -u
cd /d/Alysia
D=workspace/lia_batch_20261028/mv_lia
UP=$D/clips_1080
FPS=$D/clips_60fps
mkdir -p "$UP" "$FPS"
PY=/d/ComfyUI/.venv/Scripts/python.exe

for f in "$D"/clips_hd/*.mp4; do
  n=$(basename "$f" .mp4)
  echo "=== $n 超分 ==="
  if [ -f "$UP/$n.mp4" ]; then
    echo "  已存在，跳过"
  else
    "$PY" scripts/upscale_video.py "$f" -o "$UP/$n.mp4" --width 1920 --height 1080 2>&1 | tail -2
  fi
  echo "=== $n 插帧 60fps ==="
  if [ -f "$FPS/$n.mp4" ]; then
    echo "  已存在，跳过"
  else
    ffmpeg -v error -y -i "$UP/$n.mp4" \
      -vf "minterpolate=fps=60:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1" \
      -c:v libx264 -preset medium -crf 17 -pix_fmt yuv420p -an "$FPS/$n.mp4"
    echo "  done $(ffprobe -v error -select_streams v:0 -show_entries stream=nb_frames -of csv=p=0 "$FPS/$n.mp4") 帧"
  fi
done
echo "ALL DONE"
