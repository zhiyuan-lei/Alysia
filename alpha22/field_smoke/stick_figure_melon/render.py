"""Standalone original limited-animation experiment; not an Alysia workflow."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import shutil
import struct
import subprocess
import wave

from PIL import Image, ImageDraw, ImageFont


WIDTH, HEIGHT, FPS, DURATION = 1280, 720, 24, 8
FRAMES = FPS * DURATION
INK = (24, 25, 28)
GREEN = (119, 181, 118)
PALE = (226, 246, 225)
FONT_PATH = Path("C:/Windows/Fonts/msyh.ttc")


class InkCanvas:
    def __init__(self) -> None:
        self.scale = 2
        self.image = Image.new("RGB", (WIDTH * self.scale, HEIGHT * self.scale), "white")
        self.pen = ImageDraw.Draw(self.image)
        self.fonts: dict[int, ImageFont.FreeTypeFont] = {}

    def p(self, point):
        return tuple(round(value * self.scale) for value in point)

    def line(self, points, width=6, color=INK):
        scaled = [self.p(point) for point in points]
        self.pen.line(scaled, fill=color, width=width * self.scale, joint="curve")
        radius = width * self.scale / 2
        for x, y in (scaled[0], scaled[-1]):
            self.pen.ellipse((x - radius, y - radius, x + radius, y + radius), fill=color)

    def ellipse(self, box, fill="white", outline=INK, width=5):
        self.pen.ellipse(self.p(box), fill=fill, outline=outline, width=width * self.scale)

    def rounded(self, box, radius=16, fill="white", outline=INK, width=5):
        self.pen.rounded_rectangle(self.p(box), radius=radius * self.scale,
                                   fill=fill, outline=outline, width=width * self.scale)

    def text(self, text, x, y, size=28, fill=INK):
        if size not in self.fonts:
            self.fonts[size] = ImageFont.truetype(str(FONT_PATH), size * self.scale)
        self.pen.text(self.p((x, y)), text, font=self.fonts[size], fill=fill, anchor="mm")

    def finish(self):
        return self.image.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)


def bubble(canvas: InkCanvas, text: str, center_x: float, y: float, tail_x: float):
    half = max(100, len(text) * 19)
    canvas.rounded((center_x - half, y - 38, center_x + half, y + 38), 27)
    canvas.line([(center_x - 22, y + 38), (tail_x, y + 70), (center_x + 6, y + 38)], 4)
    canvas.text(text, center_x, y, 29)


def person(canvas: InkCanvas, cx: float, *, role: str, expression: str,
           arm: tuple[float, float] | None = None, bob: float = 0.0):
    head_y = 266 + bob
    chest_y = 378 + bob
    canvas.ellipse((cx - 54, head_y - 54, cx + 54, head_y + 54), width=7)
    if role == "seller":
        canvas.line([(cx - 38, head_y - 46), (cx - 16, head_y - 68),
                     (cx + 29, head_y - 62), (cx + 43, head_y - 45)], 7)
    else:
        canvas.line([(cx - 11, head_y - 50), (cx + 8, head_y - 68),
                     (cx + 24, head_y - 52)], 6)
    if expression == "surprised":
        for dx in (-21, 21):
            canvas.ellipse((cx + dx - 12, head_y - 15, cx + dx + 12, head_y + 10), width=4)
            canvas.ellipse((cx + dx - 3, head_y - 5, cx + dx + 3, head_y + 2), fill=INK, outline=INK)
        canvas.ellipse((cx - 12, head_y + 18, cx + 12, head_y + 44), width=5)
    else:
        for dx in (-21, 21):
            canvas.ellipse((cx + dx - 5, head_y - 13, cx + dx + 5, head_y - 3), fill=INK, outline=INK)
        canvas.line([(cx - 16, head_y + 20), (cx, head_y + (33 if expression == "grin" else 27)),
                     (cx + 18, head_y + 20)], 4)
    canvas.line([(cx, head_y + 55), (cx, chest_y + 55)], 8)
    canvas.line([(cx, chest_y + 55), (cx - 37, 600)], 8)
    canvas.line([(cx, chest_y + 55), (cx + 37, 600)], 8)
    canvas.line([(cx - 37, 600), (cx - 57, 600)], 7)
    canvas.line([(cx + 37, 600), (cx + 57, 600)], 7)
    if arm is None:
        arm = ((cx + 90, 422) if role == "seller" else (cx - 94, 426))
    side = 1 if role == "seller" else -1
    canvas.line([(cx + 16 * side, chest_y - 8), (cx + 48 * side, chest_y + 32), arm], 7)
    canvas.ellipse((arm[0] - 8, arm[1] - 8, arm[0] + 8, arm[1] + 8), fill="white", width=4)
    canvas.line([(cx - 17 * side, chest_y - 5), (cx - 70 * side, chest_y + 65)], 7)


def melon(canvas: InkCanvas, cx: float, cy: float, *, awake=False,
          squash=1.0, stretch=1.0, stride=0, speed=False):
    half_w, half_h = 75 * stretch, 52 * squash
    if awake:
        leg_y = cy + half_h
        canvas.line([(cx - 28, leg_y - 2), (cx - 35 + stride, leg_y + 42),
                     (cx - 53 + stride, leg_y + 46)], 5)
        canvas.line([(cx + 28, leg_y - 2), (cx + 36 - stride, leg_y + 42),
                     (cx + 55 - stride, leg_y + 46)], 5)
    canvas.ellipse((cx - half_w, cy - half_h, cx + half_w, cy + half_h),
                   fill=PALE, outline=INK, width=6)
    for offset in (-35, 0, 35):
        canvas.line([(cx + offset * 0.7, cy - half_h + 13),
                     (cx + offset, cy), (cx + offset * 0.7, cy + half_h - 13)], 4, GREEN)
    if awake:
        for dx in (-20, 20):
            canvas.ellipse((cx + dx - 6, cy - 16, cx + dx + 6, cy - 2), fill=INK, outline=INK)
        canvas.line([(cx - 14, cy + 19), (cx, cy + 27), (cx + 14, cy + 19)], 3)
    if speed:
        for dx, length in ((95, 75), (126, 47), (158, 64)):
            canvas.line([(cx - dx - length, cy - 20), (cx - dx, cy - 20)], 4)
            canvas.line([(cx - dx - length / 2, cy + 25), (cx - dx + 8, cy + 25)], 3)


def quantized_frame(frame: int) -> int:
    """Hold drawings on twos or threes; reserve ones for the knock impact."""
    if frame < 24:
        return frame // 3 * 3
    if frame < 77:
        return frame // 2 * 2
    if frame < 96:
        return frame
    if frame < 118:
        return 99 if frame < 106 else 109
    if frame < 151:
        return frame // 2 * 2
    return 151


def draw_frame(tick: int) -> Image.Image:
    c = InkCanvas()
    # Sparse background: all motion is readable against fixed white space.
    c.line([(70, 619), (1210, 619)], 3, (190, 190, 190))
    c.rounded((356, 465, 925, 496), 8, fill=(250, 250, 250), width=5)
    c.line([(391, 496), (391, 619)], 6)
    c.line([(889, 496), (889, 619)], 6)
    c.rounded((420, 521, 532, 571), 8, fill=(255, 255, 255), width=4)
    c.text("瓜摊", 476, 546, 29)

    buyer_x = 1040 + (185 * (1 - min(tick / 24, 1)) ** 2 if tick < 24 else 0)
    buyer_expression = "surprised" if tick >= 99 else "normal"
    seller_expression = "surprised" if tick >= 99 else ("grin" if tick >= 53 else "normal")
    buyer_arm = None
    seller_arm = None
    if 24 <= tick < 77:
        progress = min((tick - 24) / 18, 1)
        buyer_arm = (buyer_x - 93 - 58 * progress, 425 - 18 * progress)
    if 53 <= tick < 96:
        seller_arm = (350 + 80 * min((tick - 53) / 13, 1), 416 - 23 * min((tick - 53) / 13, 1))
    if 77 <= tick < 96:
        if tick < 87:
            buyer_arm = (buyer_x - 132 + (87 - tick) * 2, 397 - (87 - tick) * 3)
        elif tick < 91:
            buyer_arm = (buyer_x - 126 - (tick - 87) * 65, 392 + (tick - 87) * 5)
        else:
            buyer_arm = (buyer_x - 260, 420)
    person(c, 255, role="seller", expression=seller_expression, arm=seller_arm,
           bob=(2 if 53 <= tick < 77 and tick % 8 < 4 else 0))
    person(c, buyer_x, role="buyer", expression=buyer_expression, arm=buyer_arm,
           bob=(3 if tick < 24 and tick % 6 < 3 else 0))

    if tick < 118:
        squash = 0.68 if 91 <= tick < 96 else 1.0
        stretch = 1.16 if 91 <= tick < 96 else 1.0
        melon(c, 641, 411 + (13 if squash < 1 else 0), awake=tick >= 99,
              squash=squash, stretch=stretch,
              stride=(7 if tick >= 109 else 0))
    elif tick < 151:
        progress = (tick - 118) / 33
        cx = 641 + 750 * progress * progress
        melon(c, cx, 414 - 24 * math.sin(math.pi * progress * 2), awake=True,
              squash=(0.72 if tick < 122 else 0.94),
              stretch=(1.28 if tick < 122 else 1.10),
              stride=(10 if tick % 4 < 2 else -10), speed=tick > 123)

    if 24 <= tick < 53:
        bubble(c, "挑个熟的！", 971, 113, 1030)
    elif 53 <= tick < 77:
        bubble(c, "它自己会挑。", 315, 119, 252)
    elif 89 <= tick < 96:
        c.text("咚！", 760, 322, 38)
        for dx, dy in ((-38, -53), (0, -64), (39, -47)):
            c.line([(641 + dx, 410 + dy), (641 + dx * 1.25, 410 + dy * 1.3)], 5)
    elif 151 <= tick:
        bubble(c, "我挑下班！", 1055, 122, 1168)
        c.text("……", 641, 394, 42)
    if 99 <= tick < 118:
        c.text("?!", 641, 321, 35)
    return c.finish()


def make_foley(path: Path) -> None:
    sample_rate = 44100
    seconds = DURATION
    events = ((3.74, 0.15, 520, 0.19), (4.94, 0.45, 220, 0.12),
              (5.30, 0.09, 680, 0.08), (5.63, 0.09, 750, 0.08),
              (5.91, 0.09, 810, 0.08), (6.35, 0.18, 430, 0.10))
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        buffer = bytearray()
        for sample in range(seconds * sample_rate):
            t = sample / sample_rate
            value = 0.0
            for start, length, frequency, amplitude in events:
                offset = t - start
                if 0 <= offset < length:
                    envelope = (1 - offset / length) ** 2
                    bend = frequency * (1 + 0.65 * offset / length)
                    value += amplitude * envelope * math.sin(2 * math.pi * bend * offset)
            buffer.extend(struct.pack("<h", max(-32768, min(32767, int(value * 32767)))))
        wav.writeframes(buffer)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=Path("workspace/stick_figure_melon"))
    args = parser.parse_args()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if not ffmpeg or not ffprobe or not FONT_PATH.is_file():
        raise RuntimeError("需要 ffmpeg、ffprobe 和 Windows 微软雅黑字体")
    audio = output / "original_foley.wav"
    make_foley(audio)
    video = output / "melon_takes_a_day_off_720p.mp4"
    command = [ffmpeg, "-nostdin", "-y", "-v", "error", "-f", "rawvideo",
               "-pixel_format", "rgb24", "-video_size", f"{WIDTH}x{HEIGHT}",
               "-framerate", str(FPS), "-i", "pipe:0", "-i", str(audio),
               "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p",
               "-c:a", "aac", "-b:a", "128k", "-shortest", "-movflags", "+faststart", str(video)]
    unique_drawings: set[str] = set()
    with (output / "ffmpeg_stderr.log").open("wb") as error_stream:
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stderr=error_stream)
        assert process.stdin is not None
        for frame in range(FRAMES):
            drawing = draw_frame(quantized_frame(frame))
            pixels = drawing.tobytes()
            unique_drawings.add(hashlib.sha256(pixels).hexdigest())
            process.stdin.write(pixels)
        process.stdin.close()
        return_code = process.wait()
    if return_code:
        raise RuntimeError((output / "ffmpeg_stderr.log").read_text(errors="replace"))
    result = subprocess.run([ffprobe, "-v", "error", "-count_frames", "-show_entries",
                             "stream=codec_type,width,height,nb_read_frames:format=duration",
                             "-of", "json", str(video)], capture_output=True, text=True, check=True)
    probe = json.loads(result.stdout)
    video_stream = next(stream for stream in probe["streams"] if stream["codec_type"] == "video")
    assert (video_stream["width"], video_stream["height"]) == (WIDTH, HEIGHT)
    assert int(video_stream["nb_read_frames"]) == FRAMES
    metadata = {"status": "VALIDATED_PROTOTYPE_NOT_INTEGRATED", "title": "会挑下班的瓜",
                "video": str(video), "frames": FRAMES, "fps": FPS,
                "duration_sec": float(probe["format"]["duration"]),
                "unique_drawings": len(unique_drawings), "audio": "programmatically synthesized foley",
                "sha256": hashlib.sha256(video.read_bytes()).hexdigest(),
                "bytes": video.stat().st_size}
    (output / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(metadata, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
