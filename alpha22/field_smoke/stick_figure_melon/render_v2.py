"""Standalone hand-drawn 买瓜 story test; does not register an Alysia workflow."""
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


WIDTH, HEIGHT, FPS, SECONDS = 1280, 720, 24, 12
INK = (26, 29, 30)
GREEN = (103, 166, 105)
PALE = (221, 242, 217)
PINK = (241, 164, 169)
RED = (188, 70, 73)
PAPER = (255, 253, 247)
FONT = Path("C:/Windows/Fonts/msyh.ttc")


class Canvas:
    def __init__(self) -> None:
        self.scale = 2
        self.image = Image.new("RGB", (WIDTH * 2, HEIGHT * 2), PAPER)
        self.pen = ImageDraw.Draw(self.image)
        self.fonts: dict[int, ImageFont.FreeTypeFont] = {}

    def xy(self, x: float, y: float) -> tuple[int, int]:
        return round(x * 2), round(y * 2)

    def line(self, points, width=5, fill=INK):
        coords = [self.xy(x, y) for x, y in points]
        self.pen.line(coords, fill=fill, width=width * 2, joint="curve")
        r = width
        for x, y in (coords[0], coords[-1]):
            self.pen.ellipse((x-r, y-r, x+r, y+r), fill=fill)

    def ellipse(self, box, fill=PAPER, outline=INK, width=4):
        self.pen.ellipse((*self.xy(*box[:2]), *self.xy(*box[2:])),
                         fill=fill, outline=outline, width=width * 2)

    def rect(self, box, fill=PAPER, outline=INK, width=4, radius=0):
        bounds = (*self.xy(*box[:2]), *self.xy(*box[2:]))
        self.pen.rounded_rectangle(bounds, radius=radius * 2, fill=fill,
                                   outline=outline, width=width * 2)

    def poly(self, points, fill, outline=INK, width=4):
        coords = [self.xy(x, y) for x, y in points]
        self.pen.polygon(coords, fill=fill)
        self.pen.line(coords + [coords[0]], fill=outline, width=width * 2, joint="curve")

    def text(self, value, x, y, size=26, fill=INK):
        if size not in self.fonts:
            self.fonts[size] = ImageFont.truetype(str(FONT), size * 2)
        self.pen.text(self.xy(x, y), value, font=self.fonts[size], fill=fill, anchor="mm")

    def finish(self):
        return self.image.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)


def ease(value: float) -> float:
    p = max(0.0, min(1.0, value))
    return p * p * (3 - 2 * p)


def speech(c: Canvas, text: str, x: float, y: float, tail: float):
    half = max(108, 18 * len(text) + 30)
    c.rect((x-half, y-36, x+half, y+36), radius=22, width=4)
    c.poly([(x-12, y+35), (tail, y+67), (x+15, y+35)], PAPER, width=3)
    c.text(text, x, y-2, 28)


def background(c: Canvas, sign_swing: float):
    c.line([(55, 638), (1218, 638)], 3, (155, 151, 143))
    for x in (103, 181, 264, 348, 432, 516, 600, 684, 768, 852):
        color = PALE if (x // 80) % 2 else (247, 247, 235)
        c.poly([(x, 80), (x+84, 80), (x+69, 159), (x-12, 159)], color, width=2)
    c.line([(99, 80), (946, 80)], 6)
    c.line([(112, 160), (112, 634)], 7)
    c.line([(917, 160), (917, 634)], 7)
    c.rect((104, 105, 893, 154), fill=(253, 250, 233), radius=8, width=4)
    c.text("今日鲜瓜", 496, 128, 30)
    for x in (70, 165, 275):
        c.ellipse((x, 595, x+105, 655), fill=PALE, width=3)
        c.line([(x+18, 608), (x+45, 635), (x+75, 607)], 2, GREEN)
    c.rect((1095, 525, 1240, 617), fill=(246, 237, 218), radius=3, width=4)
    c.line([(1095, 555), (1240, 555)], 2)
    c.line([(1120, 525), (1120, 617)], 2)
    c.rect((405, 457, 886, 493), fill=(244, 227, 191), radius=7, width=5)
    c.line([(444, 492), (444, 628)], 7)
    c.line([(850, 492), (850, 628)], 7)
    c.line([(444, 560), (850, 560)], 3)
    c.rect((505, 509, 594, 577), fill=(245, 245, 227), radius=6, width=3)
    c.text("瓜", 549, 542, 30)
    # A small hanging price placard is a secondary animation, not dialogue.
    sign_x = 759 + sign_swing
    c.line([(sign_x-41, 159), (sign_x-41, 261)], 2)
    c.line([(sign_x+41, 159), (sign_x+41, 261)], 2)
    c.rect((sign_x-69, 254, sign_x+69, 312), fill=(255, 250, 226), radius=7, width=4)
    c.text("2元/斤", sign_x, 282, 24)


def face(c: Canvas, x: float, y: float, mood: str):
    c.ellipse((x-53, y-54, x+53, y+54), width=6)
    if mood in ("shock", "angry"):
        eye_w, eye_h = 13, 19
    elif mood == "skeptic":
        eye_w, eye_h = 14, 10
    else:
        eye_w, eye_h = 12, 14
    for dx in (-22, 22):
        ey = y-9 if mood != "skeptic" else y-6
        c.ellipse((x+dx-eye_w, ey-eye_h, x+dx+eye_w, ey+eye_h), width=3)
        px = x+dx+(5 if mood == "skeptic" else 0)
        c.ellipse((px-4, ey-4, px+4, ey+4), fill=INK, outline=INK, width=1)
    if mood == "angry":
        c.line([(x-42, y-34), (x-11, y-23)], 5)
        c.line([(x+42, y-34), (x+11, y-23)], 5)
        c.ellipse((x-14, y+17, x+15, y+35), fill=INK, width=2)
    elif mood == "shock":
        c.line([(x-40, y-37), (x-15, y-41)], 4)
        c.line([(x+15, y-41), (x+40, y-37)], 4)
        c.ellipse((x-10, y+16, x+10, y+42), fill=INK, width=2)
    elif mood == "skeptic":
        c.line([(x-39, y-28), (x-12, y-30)], 4)
        c.line([(x+10, y-34), (x+40, y-22)], 4)
        c.line([(x-12, y+26), (x+21, y+23)], 4)
    elif mood == "smug":
        c.line([(x-40, y-33), (x-13, y-28)], 3)
        c.line([(x+14, y-26), (x+40, y-37)], 3)
        c.line([(x-16, y+21), (x+6, y+34), (x+25, y+18)], 4)
    else:
        c.line([(x-34, y-34), (x-13, y-31)], 3)
        c.line([(x+13, y-31), (x+34, y-34)], 3)
        c.line([(x-13, y+24), (x, y+30), (x+17, y+22)], 3)
    if mood in ("shock", "angry"):
        c.ellipse((x+55, y+9, x+63, y+30), fill=(165, 202, 224), width=2)


def character(c: Canvas, x: float, role: str, mood: str, *, lean=0.0,
              bob=0.0, stride=0.0, gesture="rest", arm_target=None, motion=0.0):
    hx, hy = x+lean*38, 305+bob-lean*10
    shoulder = (x+lean*18, 395+bob)
    hip = (x, 532+bob)
    c.line([shoulder, hip], 8)
    c.line([hip, (x-38+stride, 633), (x-57+stride, 633)], 7)
    c.line([hip, (x+38-stride, 633), (x+60-stride, 633)], 7)
    left_shoulder = (shoulder[0]-15, shoulder[1]+6)
    right_shoulder = (shoulder[0]+15, shoulder[1]+6)
    if role == "seller":
        hem_swing = 8*math.sin(motion*9)*min(1, abs(lean)+abs(bob)/3)
        c.poly([(x-24, 425+bob), (x+25, 425+bob), (x+35+lean*9+hem_swing, 546+bob),
                (x-38+hem_swing, 546+bob)], fill=(235, 248, 232), width=3)
        for yy in (455, 486, 518):
            c.line([(x-26, yy+bob), (x+29, yy+bob)], 2, GREEN)
        target = arm_target or (x+130, 436+bob)
        elbow = (x+86+lean*10, 406+bob)
        c.line([right_shoulder, elbow, target], 7)
        if gesture == "point":
            c.line([target, (target[0]+20, target[1]-8)], 4)
        elif gesture == "knife":
            c.line([target, (target[0]+26, target[1]+19)], 7, (104, 75, 55))
            c.poly([(target[0]+24, target[1]+17), (target[0]+62, target[1]+34),
                    (target[0]+48, target[1]+40)], fill=(172, 179, 183), width=2)
        else:
            c.ellipse((target[0]-8, target[1]-8, target[0]+8, target[1]+8), width=3)
        c.line([left_shoulder, (x-72, 450+bob), (x-89, 496+bob)], 7)
        c.ellipse((x-97, 488+bob, x-81, 504+bob), width=3)
    else:
        target = arm_target or (x-117, 447+bob)
        elbow = (x-87-lean*9, 410+bob)
        c.line([left_shoulder, elbow, target], 7)
        if gesture in ("point", "tap"):
            c.line([target, (target[0]-19, target[1]-6)], 4)
        else:
            c.ellipse((target[0]-8, target[1]-8, target[0]+8, target[1]+8), width=3)
        c.line([right_shoulder, (x+68, 451+bob), (x+66, 505+bob)], 7)
        c.ellipse((x+58, 497+bob, x+74, 513+bob), width=3)
        scarf_swing = 10*math.sin(motion*11)*min(1, abs(lean)+abs(bob)/3)
        c.poly([(hx-34, hy+45), (hx+23, hy+56), (hx+41+lean*8+scarf_swing, hy+81),
                (hx-18, hy+68)], fill=(248, 224, 221), outline=RED, width=3)
        c.line([(hx+22, hy+61), (hx+48+lean*9+scarf_swing, hy+84)], 4, RED)
    face(c, hx, hy, mood)
    if role == "seller":
        c.poly([(hx-50, hy-53), (hx-22, hy-78), (hx+35, hy-72),
                (hx+52, hy-49)], fill=PALE, width=4)
        c.line([(hx-57, hy-51), (hx+60, hy-50)], 5, GREEN)
    else:
        c.line([(hx-33, hy-49), (hx-18, hy-64), (hx-4, hy-53),
                (hx+15, hy-70), (hx+31, hy-49)], 5)


def watermelon(c: Canvas, reveal: float, bounce: float, squash: float):
    x, y = 651, 421+bounce
    c.ellipse((x-70, y-48*squash, x+70, y+48*squash), fill=PALE, width=5)
    for offset in (-38, -14, 15, 39):
        c.line([(x+offset*.6, y-38*squash), (x+offset, y),
                (x+offset*.6, y+38*squash)], 3, GREEN)
    c.line([(x-2, y-50*squash), (x+2, y-63*squash), (x+11, y-65*squash)], 3, GREEN)
    if reveal > 0:
        open_width = 18+55*reveal
        c.poly([(x+5, y-40), (x+open_width, y-20), (x+open_width-13, y+35),
                (x+13, y+39)], fill=(247, 232, 226), width=3)
        c.poly([(x+15, y-27), (x+open_width-8, y-17), (x+open_width-19, y+21),
                (x+20, y+28)], fill=PINK, outline=GREEN, width=3)
        for dx, dy in ((29, -5), (40, 8), (52, -10)):
            if dx < open_width-4:
                c.ellipse((x+dx-2, y+dy-4, x+dx+2, y+dy+4), fill=INK, width=1)
        wedge_x = x+99+20*reveal
        wedge_y = y-25-24*reveal
        c.poly([(wedge_x-33, wedge_y-21), (wedge_x+24, wedge_y-13),
                (wedge_x+3, wedge_y+31)], fill=PINK, outline=GREEN, width=4)
        c.ellipse((wedge_x-5, wedge_y-2, wedge_x+1, wedge_y+6), fill=INK, width=1)


def held_tick(frame: int) -> int:
    if 151 <= frame < 178:
        return frame  # one-frame accents around cutting and reveal
    if frame >= 242:
        return 242+(frame-242)//6*6
    return frame//2*2


def draw_frame(frame: int) -> Image.Image:
    t = frame/FPS
    c = Canvas()
    swing = 5*math.sin(max(0, t-7.2)*8)*math.exp(-max(0, t-7.2)*.45) if t >= 7.2 else 0
    background(c, swing)
    buyer_x = 1120-116*ease(t/1.25)
    seller_mood = ("normal" if t < 2.5 else "smug" if t < 7.15
                   else "shock" if t < 8.6 else "angry")
    buyer_mood = ("normal" if t < 3.5 else "skeptic" if t < 7.15
                  else "shock" if t < 8.1 else "skeptic")
    buyer_lean = (0 if t < 3.45 else .65*ease((t-3.45)/.55) if t < 5.0
                  else .28 if t < 8.7 else .8*ease((t-8.7)/.65))
    seller_lean = (0 if t < 5 else .35 if t < 7.4 else
                   -.45 if t < 8.6 else .72*ease((t-8.6)/.9))
    bob = 3*math.sin(t*15) if t < 1.25 else 0
    stride = 15*math.sin(t*16) if t < 1.25 else 0
    seller_gesture, seller_target = "rest", None
    buyer_gesture, buyer_target = "rest", None
    if 2.5 <= t < 3.5:
        seller_gesture, seller_target = "point", (481, 323)
    if 3.5 <= t < 5.1:
        buyer_gesture = "tap" if t >= 4.45 else "point"
        buyer_target = (762, 406 if t >= 4.45 else 391)
    if 5.1 <= t < 6.2:
        seller_target = (312, 424)
    if 6.2 <= t < 7.4:
        seller_gesture = "knife"
        progress = ease((t-6.2)/1.0)
        seller_target = (540+56*progress, 337+48*progress)
    if 7.4 <= t < 8.7:
        buyer_gesture, buyer_target = "point", (752, 421)
    if t >= 8.7:
        buyer_gesture, buyer_target = "point", (795, 412)
        seller_gesture, seller_target = "point", (480, 416)
    character(c, 275, "seller", seller_mood, lean=seller_lean,
              gesture=seller_gesture, arm_target=seller_target, motion=t)
    character(c, buyer_x, "buyer", buyer_mood, lean=buyer_lean, bob=bob,
              stride=stride, gesture=buyer_gesture, arm_target=buyer_target, motion=t)
    reveal = ease((t-6.91)/.38) if t >= 6.91 else 0
    impact = math.sin(math.pi*ease((t-6.91)/.6)) if 6.91 <= t <= 7.51 else 0
    watermelon(c, reveal, -9*impact, 1-.18*impact)
    if 1.3 <= t < 2.5:
        speech(c, "瓜多少钱？", 1012, 206, 1016)
    elif 2.5 <= t < 3.5:
        speech(c, "两块一斤。", 291, 203, 278)
    elif 3.5 <= t < 5.1:
        speech(c, "这瓜保熟吗？", 1013, 203, 993)
    elif 5.1 <= t < 6.2:
        speech(c, "包熟！", 290, 203, 278)
    elif 7.4 <= t < 8.7:
        speech(c, "这不对吧？", 1012, 201, 1016)
    elif 8.7 <= t < 10.1:
        speech(c, "你找茬？", 289, 203, 278)
    if 6.89 <= t < 7.28:
        c.text("咔！", 566, 350, 34)
        for dx in (-19, 16, 46):
            c.line([(637+dx, 355), (637+dx*1.5, 333)], 3)
    if 7.35 <= t < 8.25:
        c.text("?!", 646, 329, 37)
    if t >= 9.0:
        for x, direction in ((405, 1), (885, -1)):
            for dy in (-34, 0, 39):
                c.line([(x, 374+dy), (x+38*direction, 360+dy)], 3)
    if t >= 10.1:
        c.text("……", 646, 355, 38)
        if t >= 11.2:
            c.ellipse((729, 470, 734, 477), fill=INK, width=1)
    return c.finish()


def make_sound(path: Path):
    rate = 44100
    events = ((.8, .08, 530, .06), (4.55, .16, 340, .12),
              (6.99, .18, 750, .16), (7.40, .22, 180, .09),
              (9.15, .12, 265, .08), (11.2, .08, 470, .08))
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        samples = bytearray()
        for i in range(SECONDS*rate):
            now = i/rate
            value = 0.0
            for start, duration, frequency, volume in events:
                phase = now-start
                if 0 <= phase < duration:
                    value += volume*(1-phase/duration)**2*math.sin(2*math.pi*frequency*phase)
            samples.extend(struct.pack("<h", max(-32768, min(32767, round(value*32767)))))
        wav.writeframes(samples)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=Path("workspace/stick_figure_melon"))
    output = parser.parse_args().output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    ffmpeg, ffprobe = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if not ffmpeg or not ffprobe or not FONT.is_file():
        raise RuntimeError("需要 ffmpeg、ffprobe 和微软雅黑字体")
    sound = output/"original_foley_v2.wav"
    video = output/"melon_ripe_question_v2_720p.mp4"
    make_sound(sound)
    command = [ffmpeg, "-nostdin", "-y", "-v", "error", "-f", "rawvideo",
               "-pixel_format", "rgb24", "-video_size", f"{WIDTH}x{HEIGHT}",
               "-framerate", str(FPS), "-i", "pipe:0", "-i", str(sound),
               "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p",
               "-c:a", "aac", "-b:a", "128k", "-shortest", "-movflags", "+faststart", str(video)]
    unique = set()
    last_tick, last_pixels = -1, b""
    error_file = output/"ffmpeg_stderr_v2.log"
    with error_file.open("wb") as stderr:
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stderr=stderr)
        assert process.stdin is not None
        for frame in range(FPS*SECONDS):
            tick = held_tick(frame)
            if tick != last_tick:
                last_pixels = draw_frame(tick).tobytes()
                unique.add(hashlib.sha256(last_pixels).hexdigest())
                last_tick = tick
            process.stdin.write(last_pixels)
        process.stdin.close()
        code = process.wait()
    if code:
        raise RuntimeError(error_file.read_text(errors="replace"))
    check = subprocess.run([ffprobe, "-v", "error", "-count_frames", "-show_entries",
                            "stream=codec_type,width,height,nb_read_frames:format=duration",
                            "-of", "json", str(video)], capture_output=True, text=True, check=True)
    probe = json.loads(check.stdout)
    stream = next(item for item in probe["streams"] if item["codec_type"] == "video")
    assert (stream["width"], stream["height"], int(stream["nb_read_frames"])) == (WIDTH, HEIGHT, FPS*SECONDS)
    metadata = {"status": "VALIDATED_PROTOTYPE_NOT_INTEGRATED", "title": "买瓜：保熟吗？",
                "video": str(video), "fps": FPS, "frames": FPS*SECONDS,
                "duration_sec": float(probe["format"]["duration"]),
                "unique_drawings": len(unique), "audio": "original synthesized foley",
                "sha256": hashlib.sha256(video.read_bytes()).hexdigest(), "bytes": video.stat().st_size}
    (output/"metadata_v2.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(metadata, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
