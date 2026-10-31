from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from alysia.core.config import CoverConfig
from alysia.providers.cover.base import BaseCoverGenerator


class TemplateCoverGenerator(BaseCoverGenerator):
    def __init__(self, config: CoverConfig, template_version: str = "v1") -> None:
        self.config = config
        self.template_version = template_version

    def generate(
        self,
        output_path: Path,
        *,
        title: str,
        subtitle: str | None = None,
        background_path: Path | None = None,
        logo_text: str = "ALYSIA",
        theme_elements: list[str] | None = None,
    ) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        image = self._background(background_path)
        draw = ImageDraw.Draw(image)
        width, height = image.size

        accent = (91, 236, 255)
        draw.rounded_rectangle(
            (round(width * 0.055), round(height * 0.09), round(width * 0.1), round(height * 0.72)),
            radius=max(8, width // 160),
            fill=accent,
        )
        draw.ellipse((round(width * 0.78), round(height * 0.05), round(width * 1.02), round(height * 0.48)), fill=(57, 64, 116))
        draw.ellipse((round(width * 0.83), round(height * 0.48), round(width * 1.05), round(height * 0.94)), fill=(31, 145, 166))

        logo_font = _font(max(20, width // 40), bold=True)
        small_font = _font(max(18, width // 50), bold=False)

        draw.text((round(width * 0.135), round(height * 0.09)), logo_text, font=logo_font, fill=accent)
        title_lines, title_font = _fit_text(
            draw,
            title,
            max_width=round(width * 0.62),
            max_height=round(height * 0.44),
            max_lines=3,
            start_size=max(42, width // 15),
            min_size=max(32, width // 25),
            bold=True,
        )
        draw.multiline_text(
            (round(width * 0.135), round(height * 0.22)),
            title_lines,
            font=title_font,
            fill=(247, 249, 255),
            spacing=max(8, height // 50),
        )
        if subtitle:
            subtitle_lines, subtitle_font = _fit_text(
                draw,
                subtitle,
                max_width=round(width * 0.61),
                max_height=round(height * 0.12),
                max_lines=2,
                start_size=max(24, width // 34),
                min_size=max(20, width // 48),
                bold=False,
            )
            draw.multiline_text(
                (round(width * 0.14), round(height * 0.73)),
                subtitle_lines,
                font=subtitle_font,
                fill=(205, 217, 235),
                spacing=max(4, height // 100),
            )
        elements = [item for item in (theme_elements or []) if item.strip()][:3]
        if elements:
            draw.text(
                (round(width * 0.14), round(height * 0.86)),
                "  ·  ".join(elements),
                font=small_font,
                fill=(153, 175, 205),
            )

        save_format = "JPEG" if self.config.format == "jpeg" else "PNG"
        if save_format == "JPEG":
            image = image.convert("RGB")
        image.save(output_path, format=save_format, quality=94)
        return output_path

    def _background(self, background_path: Path | None) -> Image.Image:
        size = (self.config.width, self.config.height)
        if background_path is not None and background_path.is_file():
            with Image.open(background_path) as source:
                return source.convert("RGB").resize(size, Image.Resampling.LANCZOS)
        image = Image.new("RGB", size)
        pixels = image.load()
        for y in range(size[1]):
            ratio = y / max(1, size[1] - 1)
            color = (
                round(10 + 10 * ratio),
                round(17 + 17 * ratio),
                round(38 + 27 * ratio),
            )
            for x in range(size[0]):
                pixels[x, y] = color
        return image


class MockCoverGenerator(TemplateCoverGenerator):
    def generate(self, output_path: Path, **kwargs) -> Path:  # type: ignore[no-untyped-def]
        kwargs["logo_text"] = "ALYSIA MOCK"
        return super().generate(output_path, **kwargs)


def _font(size: int, *, bold: bool) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    windows_fonts = Path("C:/Windows/Fonts")
    names = ["msyhbd.ttc", "msyh.ttc", "simhei.ttf"] if bold else ["msyh.ttc", "simhei.ttf"]
    for name in names:
        path = windows_fonts / name
        if path.is_file():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


def _fit_text(
    draw: ImageDraw.ImageDraw,
    value: str,
    *,
    max_width: int,
    max_height: int,
    max_lines: int,
    start_size: int,
    min_size: int,
    bold: bool,
) -> tuple[str, ImageFont.FreeTypeFont | ImageFont.ImageFont]:
    spacing = 10
    for size in range(start_size, min_size - 1, -2):
        font = _font(size, bold=bold)
        lines = _wrap_pixels(draw, value, font, max_width)
        if len(lines) <= max_lines:
            text = "\n".join(lines)
            bounds = draw.multiline_textbbox((0, 0), text, font=font, spacing=spacing)
            if bounds[2] <= max_width and bounds[3] <= max_height:
                return text, font
    font = _font(min_size, bold=bold)
    lines = _wrap_pixels(draw, value, font, max_width)
    clipped = lines[:max_lines]
    if len(lines) > max_lines and clipped:
        clipped[-1] = _ellipsis_to_width(draw, clipped[-1], font, max_width)
    return "\n".join(clipped), font


def _wrap_pixels(
    draw: ImageDraw.ImageDraw,
    value: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    max_width: int,
) -> list[str]:
    lines: list[str] = []
    current = ""
    for character in " ".join(value.split()):
        candidate = current + character
        if current and draw.textlength(candidate, font=font) > max_width:
            lines.append(current.rstrip())
            current = character.lstrip()
        else:
            current = candidate
    if current:
        lines.append(current.rstrip())
    return lines or [value]


def _ellipsis_to_width(
    draw: ImageDraw.ImageDraw,
    value: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    max_width: int,
) -> str:
    text = value.rstrip("，。；; ")
    while text and draw.textlength(text + "…", font=font) > max_width:
        text = text[:-1].rstrip()
    return text + "…"
