from __future__ import annotations

import math
import re
import wave
from array import array

from alysia.providers.tts.base import BaseTTSProvider
from alysia.schemas.audio import TTSRequest, TTSResult


class MockTTSProvider(BaseTTSProvider):
    """离线、确定性的可听 tone provider，仅用于流程测试。"""

    name = "mock"

    def __init__(self) -> None:
        self.call_count = 0

    async def synthesize(self, request: TTSRequest) -> TTSResult:
        self.call_count += 1
        request.output_path.parent.mkdir(parents=True, exist_ok=True)
        duration_sec = _estimate_duration(request.text, request.speed)
        frame_count = max(1, round(duration_sec * request.sample_rate))
        samples = array("h")
        edge_frames = min(round(request.sample_rate * 0.04), frame_count // 4)
        for frame in range(frame_count):
            edge_gain = 1.0
            if edge_frames:
                edge_gain = min(1.0, frame / edge_frames, (frame_count - frame - 1) / edge_frames)
            syllable_gain = 0.72 + 0.28 * math.sin(2 * math.pi * 3.1 * frame / request.sample_rate)
            value = int(4200 * max(0.0, edge_gain) * syllable_gain * math.sin(2 * math.pi * 220 * frame / request.sample_rate))
            samples.append(value)

        with wave.open(str(request.output_path), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(request.sample_rate)
            wav_file.writeframes(samples.tobytes())

        actual_duration = frame_count / request.sample_rate
        return TTSResult(
            wav_path=request.output_path,
            duration_sec=actual_duration,
            sample_rate=request.sample_rate,
            channels=1,
            provider=self.name,
            metadata={"kind": "deterministic_test_tone", "frame_count": frame_count},
        )


def _estimate_duration(text: str, speed: float) -> float:
    spoken_units = len(re.sub(r"\s+", "", text))
    punctuation_pauses = len(re.findall(r"[。！？；：，,.!?;:]", text)) * 0.08
    return max(0.8, spoken_units / (5.2 * speed) + punctuation_pauses)
