from __future__ import annotations

import math
import statistics
import wave
from array import array
from pathlib import Path
from typing import Any


def inspect_wav(path: Path) -> dict[str, int | float]:
    with wave.open(str(path), "rb") as wav_file:
        frames = wav_file.getnframes()
        sample_rate = wav_file.getframerate()
        return {
            "channels": wav_file.getnchannels(),
            "sample_width_bytes": wav_file.getsampwidth(),
            "sample_rate": sample_rate,
            "frames": frames,
            "duration_sec": frames / sample_rate if sample_rate else 0.0,
        }


def concatenate_wavs(
    scene_paths: list[Path],
    output_path: Path,
    *,
    pause_between_scenes_ms: int,
) -> dict[str, int | float]:
    if not scene_paths:
        raise ValueError("没有可拼接的 scene WAV")
    first = inspect_wav(scene_paths[0])
    expected = (first["channels"], first["sample_width_bytes"], first["sample_rate"])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    silence_frames = round(int(first["sample_rate"]) * pause_between_scenes_ms / 1000)
    silence = b"\x00" * silence_frames * int(first["channels"]) * int(first["sample_width_bytes"])
    with wave.open(str(output_path), "wb") as output:
        output.setnchannels(int(first["channels"]))
        output.setsampwidth(int(first["sample_width_bytes"]))
        output.setframerate(int(first["sample_rate"]))
        for index, scene_path in enumerate(scene_paths):
            current = inspect_wav(scene_path)
            actual = (current["channels"], current["sample_width_bytes"], current["sample_rate"])
            if actual != expected:
                raise ValueError(f"scene WAV 格式不一致：{scene_path.name} {actual} != {expected}")
            with wave.open(str(scene_path), "rb") as source:
                output.writeframes(source.readframes(source.getnframes()))
            if index < len(scene_paths) - 1 and silence_frames:
                output.writeframes(silence)
    return inspect_wav(output_path)


def signal_metrics(path: Path) -> dict[str, float]:
    peak = 0
    squared_sum = 0.0
    sample_count = 0
    clipped = 0
    window_rms: list[float] = []
    window_zero_crossing_rate: list[float] = []
    with wave.open(str(path), "rb") as wav_file:
        if wav_file.getsampwidth() != 2:
            raise ValueError("signal_metrics 仅支持 PCM16 WAV")
        window_frames = max(1, wav_file.getframerate() // 10)
        while True:
            raw = wav_file.readframes(window_frames)
            if not raw:
                break
            samples = array("h")
            samples.frombytes(raw)
            window_squared_sum = 0.0
            for sample in samples:
                absolute = abs(sample)
                peak = max(peak, absolute)
                squared_sum += float(sample) * sample
                window_squared_sum += float(sample) * sample
                clipped += absolute >= 32760
            sample_count += len(samples)
            window_rms.append(math.sqrt(window_squared_sum / len(samples)) / 32768.0)
            crossings = sum(
                1
                for previous, current in zip(samples, samples[1:])
                if (previous < 0 <= current) or (previous >= 0 > current)
            )
            window_zero_crossing_rate.append(crossings / len(samples))
    if not sample_count:
        return {"peak": 0.0, "rms": 0.0, "clipping_ratio": 0.0}
    active = [
        (rms, zero_crossing)
        for rms, zero_crossing in zip(window_rms, window_zero_crossing_rate, strict=True)
        if rms >= 0.005
    ]
    active_rms = [item[0] for item in active]
    active_zero_crossing = [item[1] for item in active]
    return {
        "peak": peak / 32768.0,
        "rms": math.sqrt(squared_sum / sample_count) / 32768.0,
        "clipping_ratio": clipped / sample_count,
        "active_window_ratio": len(active) / len(window_rms) if window_rms else 0.0,
        "active_rms_cv": _coefficient_of_variation(active_rms),
        "active_zero_crossing_cv": _coefficient_of_variation(active_zero_crossing),
    }


def _coefficient_of_variation(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = statistics.fmean(values)
    return statistics.pstdev(values) / mean if mean else 0.0
