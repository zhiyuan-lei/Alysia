from __future__ import annotations

import wave
from pathlib import Path

from alysia.providers.asr.base import ASRSegment, BaseASRProvider


class MockASRProvider(BaseASRProvider):
    name = "mock"

    def transcribe(self, wav_path: Path, *, language: str = "zh") -> list[ASRSegment]:
        del language
        with wave.open(str(wav_path), "rb") as wav_file:
            duration = wav_file.getnframes() / wav_file.getframerate()
        return [ASRSegment(start_sec=0, end_sec=duration, text="")]
