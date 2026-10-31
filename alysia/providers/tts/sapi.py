from __future__ import annotations

import json
import math
import os
import shutil
import statistics
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

from alysia.providers.tts.base import BaseTTSProvider
from alysia.schemas.audio import TTSRequest, TTSResult


_SYNTHESIZE_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
Add-Type -AssemblyName System.Speech
$request = Get-Content -Raw -LiteralPath $env:ALYSIA_SAPI_REQUEST_FILE | ConvertFrom-Json
$synth = [System.Speech.Synthesis.SpeechSynthesizer]::new()
$events = [System.Collections.Generic.List[object]]::new()
$handler = [System.EventHandler[System.Speech.Synthesis.SpeakProgressEventArgs]] {
    param($sender, $eventArgs)
    $events.Add([pscustomobject]@{
        character_start = $eventArgs.CharacterPosition
        character_length = $eventArgs.CharacterCount
        start_sec = [Math]::Round($eventArgs.AudioPosition.TotalSeconds, 6)
        text = $eventArgs.Text
    })
}
try {
    $voices = @($synth.GetInstalledVoices() | Where-Object { $_.Enabled })
    if (-not $voices) { throw 'Windows SAPI 没有可用语音' }
    $selected = $null
    if ($request.voice -and $request.voice -ne 'default') {
        $selected = $voices | Where-Object { $_.VoiceInfo.Name -eq $request.voice } | Select-Object -First 1
        if ($null -eq $selected) {
            $selected = $voices | Where-Object { $_.VoiceInfo.Name -like "*$($request.voice)*" } | Select-Object -First 1
        }
        if ($null -eq $selected) { throw "找不到 SAPI voice：$($request.voice)" }
    } else {
        $selected = $voices | Where-Object { $_.VoiceInfo.Culture.Name -eq $request.language } | Select-Object -First 1
        if ($null -eq $selected -and $request.language -like 'zh-*') {
            $selected = $voices | Where-Object { $_.VoiceInfo.Culture.TwoLetterISOLanguageName -eq 'zh' } | Select-Object -First 1
        }
        if ($null -eq $selected) { $selected = $voices[0] }
    }
    $synth.SelectVoice($selected.VoiceInfo.Name)
    $synth.Rate = [int]$request.rate
    $format = [System.Speech.AudioFormat.SpeechAudioFormatInfo]::new(
        [int]$request.sample_rate,
        [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen,
        [System.Speech.AudioFormat.AudioChannel]::Mono
    )
    $synth.add_SpeakProgress($handler)
    $synth.SetOutputToWaveFile([string]$request.output_path, $format)
    $synth.Speak([string]$request.text)
    $synth.SetOutputToNull()
    @{
        voice = $selected.VoiceInfo.Name
        word_timings = @($events)
    } | ConvertTo-Json -Compress -Depth 5 | Set-Content -LiteralPath $request.metadata_path -Encoding utf8NoBOM
} finally {
    try { $synth.remove_SpeakProgress($handler) } catch {}
    $synth.Dispose()
}
"""


class SapiTTSProvider(BaseTTSProvider):
    """使用 Windows 自带中文语音生成真实旁白，并保留词级起始时间。"""

    name = "sapi"

    @classmethod
    def is_available(cls) -> bool:
        return sys.platform == "win32" and shutil.which("pwsh") is not None

    async def synthesize(self, request: TTSRequest) -> TTSResult:
        pwsh = shutil.which("pwsh")
        if sys.platform != "win32" or pwsh is None:
            raise RuntimeError("Windows SAPI 不可用：需要 Windows 和 PowerShell 7。")

        request.output_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "text": request.text,
            "language": request.language,
            "voice": request.voice,
            "rate": _speed_to_sapi_rate(request.speed),
            "sample_rate": request.sample_rate,
            "output_path": str(request.output_path.resolve()),
        }
        with tempfile.TemporaryDirectory(prefix="alysia-sapi-") as temp_dir:
            request_file = Path(temp_dir) / "request.json"
            metadata_file = Path(temp_dir) / "metadata.json"
            script_file = Path(temp_dir) / "synthesize.ps1"
            payload["metadata_path"] = str(metadata_file)
            request_file.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            script_file.write_text(_SYNTHESIZE_SCRIPT, encoding="utf-8")
            environment = os.environ.copy()
            environment["ALYSIA_SAPI_REQUEST_FILE"] = str(request_file)
            result = subprocess.run(
                [pwsh, "-NoProfile", "-NonInteractive", "-File", str(script_file)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=environment,
                timeout=180,
                check=False,
            )
            metadata = (
                json.loads(metadata_file.read_text(encoding="utf-8"))
                if result.returncode == 0 and metadata_file.is_file()
                else None
            )
        if result.returncode != 0:
            details = (result.stderr or result.stdout).strip()
            raise RuntimeError(f"Windows SAPI 合成失败：{details[-2000:]}")
        if metadata is None:
            raise RuntimeError("Windows SAPI 未返回语音元数据。")
        with wave.open(str(request.output_path), "rb") as wav_file:
            frames = wav_file.getnframes()
            sample_rate = wav_file.getframerate()
            channels = wav_file.getnchannels()
        duration_sec = frames / sample_rate
        metadata["word_timings"], metadata["timing_scale"] = _normalize_timings(
            metadata.get("word_timings", []),
            duration_sec,
        )
        return TTSResult(
            wav_path=request.output_path,
            duration_sec=duration_sec,
            sample_rate=sample_rate,
            channels=channels,
            provider=self.name,
            metadata=metadata,
        )


def _speed_to_sapi_rate(speed: float) -> int:
    return max(-10, min(10, round(math.log2(speed) * 5)))


def _normalize_timings(timings: list[dict], duration_sec: float) -> tuple[list[dict], float]:
    if not timings:
        return [], 1.0
    starts = [float(item["start_sec"]) for item in timings]
    deltas = [later - earlier for earlier, later in zip(starts, starts[1:]) if later > earlier]
    tail = statistics.median(deltas) if deltas else 0.3
    estimated_end = starts[-1] + max(0.12, min(1.2, tail))
    scale = min(1.0, duration_sec / estimated_end) if estimated_end > 0 else 1.0
    normalized = [
        {**item, "start_sec": round(min(duration_sec, float(item["start_sec"]) * scale), 6)}
        for item in timings
    ]
    return normalized, round(scale, 8)
