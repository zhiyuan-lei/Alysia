from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from alysia.schemas.storyboard import VisualType


class VideoSubtitle(BaseModel):
    id: int = Field(ge=1)
    scene_id: str = Field(min_length=1)
    start_frame: int = Field(ge=0)
    end_frame: int = Field(gt=0)
    text: str = Field(min_length=1)

    @model_validator(mode="after")
    def end_follows_start(self) -> "VideoSubtitle":
        if self.end_frame <= self.start_frame:
            raise ValueError("video subtitle end_frame 必须大于 start_frame")
        return self


class VideoScene(BaseModel):
    id: str = Field(min_length=1)
    start_frame: int = Field(ge=0)
    duration_frames: int = Field(gt=0)
    type: VisualType
    narration: str = ""
    visual: dict[str, Any] = Field(default_factory=dict)
    subtitle_range: tuple[int, int] | None = None


class VideoComposition(BaseModel):
    format_version: int = 1
    title: str = Field(min_length=1)
    width: int = Field(ge=320)
    height: int = Field(ge=240)
    fps: int = Field(ge=1, le=120)
    duration_frames: int = Field(gt=0)
    audio_file: str = Field(min_length=1)
    scenes: list[VideoScene] = Field(min_length=1)
    subtitles: list[VideoSubtitle] = Field(default_factory=list)
    subtitle_style: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def timeline_fits_composition(self) -> "VideoComposition":
        previous_end = 0
        for scene in self.scenes:
            if scene.start_frame != previous_end:
                raise ValueError("video scene 时间线必须连续")
            previous_end = scene.start_frame + scene.duration_frames
        if previous_end != self.duration_frames:
            raise ValueError("video scene 总帧数必须等于 composition 总帧数")
        if any(segment.end_frame > self.duration_frames for segment in self.subtitles):
            raise ValueError("video subtitle 超出 composition 总帧数")
        return self


class VideoRenderResult(BaseModel):
    mp4_path: Path
    duration_sec: float = Field(gt=0)
    resolution: str = Field(min_length=3)
    fps: float = Field(gt=0)
    renderer: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class VideoProbe(BaseModel):
    duration_sec: float = Field(gt=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    fps: float = Field(gt=0)
    video_codec: str = Field(min_length=1)
    audio_codec: str = Field(min_length=1)
    audio_sample_rate: int = Field(gt=0)
    audio_channels: int = Field(ge=1, le=8)


class VideoQAReport(BaseModel):
    passed: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metrics: dict[str, float | int | str | bool] = Field(default_factory=dict)
    disclaimer: str = "alpha.4 仅执行基础工程视频检查，不等同于内容或审美审核。"


RendererName = Literal["mock", "remotion"]
