#!/usr/bin/env bash
cd /d/Alysia
D=workspace/lia_batch_20261028/mv_lia
PY=/d/ComfyUI/.venv/Scripts/python.exe
mkdir -p "$D/clips14_1080" "$D/clips14_60"
for f in "$D"/clips_1024/*.mp4; do
  n=$(basename "$f" .mp4)
  up="$D/clips14_1080/$n.mp4"
  fps="$D/clips14_60/$n.mp4"
  if [ ! -f "$up" ]; then
    echo "[$n] 超分 $(date +%H:%M:%S)"
    "$PY" scripts/upscale_video.py "$f" -o "$up" --width 1920 --height 1080 2>&1 | tail -1
  fi
  if [ ! -f "$fps" ]; then
    echo "[$n] 插帧 $(date +%H:%M:%S)"
    ffmpeg -v error -y -i "$up" -vf "minterpolate=fps=60:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1" \
      -c:v libx264 -preset medium -crf 17 -pix_fmt yuv420p -an "$fps"
    echo "[$n] 完成 $(ffprobe -v error -select_streams v:0 -show_entries stream=nb_frames -of csv=p=0 "$fps") 帧"
  fi
done
echo "POST ALL DONE"
