#!/usr/bin/env bash
cd /d/Alysia
D=workspace/lia_batch_20261028/mv_lia
OUT=$D/clips_final
mkdir -p "$OUT"
for f in "$D"/clips_1024/*.mp4; do
  n=$(basename "$f" .mp4)
  dst="$OUT/$n.mp4"
  [ -f "$dst" ] && { echo "[$n] 跳过"; continue; }
  echo "[$n] lanczos 1080p + 60fps $(date +%H:%M:%S)"
  ffmpeg -v error -y -i "$f" \
    -vf "scale=1920:1080:flags=lanczos,minterpolate=fps=60:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1" \
    -c:v libx264 -preset medium -crf 17 -pix_fmt yuv420p -an "$dst"
  echo "  done $(ffprobe -v error -select_streams v:0 -show_entries stream=nb_frames -of csv=p=0 "$dst") 帧"
done
echo "FAST ALL DONE"
