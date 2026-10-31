from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class TTSRequest(BaseModel):
    text: str = Field(min_length=1)
    scene_id: str = Field(min_length=1)
    section_id: str = ""
    language: str = "zh-CN"
    voice: str = "default"
    speed: float = Field(default=1.0, gt=0.25, le=4.0)
    sample_rate: int = Field(default=24000, ge=8000, le=96000)
    output_path: Path


class TTSResult(BaseModel):
    wav_path: Path
    duration_sec: float = Field(gt=0)
    sample_rate: int = Field(ge=8000)
    channels: int = Field(ge=1, le=2)
    provider: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SpeechTiming(BaseModel):
    character_start: int = Field(ge=0)
    character_length: int = Field(ge=1)
    start_sec: float = Field(ge=0)
    text: str = Field(min_length=1)


class AudioScene(BaseModel):
    index: int = Field(ge=1)
    scene_id: str = Field(min_length=1)
    section_id: str = ""
    original_text: str = Field(min_length=1)
    normalized_text: str = Field(min_length=1)
    file: str = Field(min_length=1)
    duration_sec: float = Field(gt=0)
    start_sec: float = Field(ge=0)
    end_sec: float = Field(gt=0)
    provider: str = Field(min_length=1)
    input_hash: str = Field(min_length=8)
    word_timings: list[SpeechTiming] = Field(default_factory=list)

    @model_validator(mode="after")
    def end_follows_start(self) -> "AudioScene":
        if self.end_sec <= self.start_sec:
            raise ValueError("audio scene end_sec 必须大于 start_sec")
        if any(timing.start_sec > self.duration_sec + 0.001 for timing in self.word_timings):
            raise ValueError("TTS word timing 不能超出 scene WAV 时长")
        return self


class AudioManifest(BaseModel):
    format_version: int = 1
    sample_rate: int = Field(default=24000, ge=8000)
    channels: Literal[1] = 1
    sample_width_bytes: Literal[2] = 2
    encoding: Literal["pcm_s16le"] = "pcm_s16le"
    pause_between_scenes_ms: int = Field(default=250, ge=0, le=5000)
    narration_file: str = "audio/narration.wav"
    total_duration_sec: float = Field(gt=0)
    scenes: list[AudioScene] = Field(min_length=1)


class SubtitleSegment(BaseModel):
    id: int = Field(ge=1)
    scene_id: str = Field(min_length=1)
    start_sec: float = Field(ge=0)
    end_sec: float = Field(gt=0)
    text: str = Field(min_length=1)
    source: Literal["deterministic", "tts", "asr"] = "deterministic"

    @model_validator(mode="after")
    def end_follows_start(self) -> "SubtitleSegment":
        if self.end_sec <= self.start_sec:
            raise ValueError("subtitle end_sec 必须大于 start_sec")
        return self


class SubtitleDocument(BaseModel):
    format_version: int = 1
    total_duration_sec: float = Field(gt=0)
    source: Literal["deterministic", "tts", "asr"] = "deterministic"
    segments: list[SubtitleSegment] = Field(min_length=1)


class AudioQAReport(BaseModel):
    passed: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metrics: dict[str, float | int | str] = Field(default_factory=dict)
    disclaimer: str = "alpha.3 仅执行基础工程音频检查，不等同于专业广播级响度检测。"
