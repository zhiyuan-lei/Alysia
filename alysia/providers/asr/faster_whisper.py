from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

from alysia.providers.asr.base import ASRSegment, BaseASRProvider


class FasterWhisperProvider(BaseASRProvider):
    name = "faster-whisper"

    def __init__(
        self,
        model: str = "small",
        device: str = "cuda",
        compute_type: str = "int8_float16",
        *,
        local_files_only: bool = True,
    ) -> None:
        self.model_name = model
        self.device = device
        self.compute_type = compute_type
        self.local_files_only = local_files_only
        self._model: Any | None = None
        self.fell_back_to_cpu = False
        self.fallback_reason: str | None = None

    @classmethod
    def is_available(cls) -> bool:
        return importlib.util.find_spec("faster_whisper") is not None

    def _load(self, device: str, compute_type: str) -> Any:
        if not self.is_available():
            raise RuntimeError("faster-whisper 不可用：项目环境未安装可选依赖。")
        from faster_whisper import WhisperModel

        return WhisperModel(
            self.model_name,
            device=device,
            compute_type=compute_type,
            local_files_only=self.local_files_only,
        )

    def transcribe(self, wav_path: Path, *, language: str = "zh") -> list[ASRSegment]:
        try:
            if self._model is None:
                self._model = self._load(self.device, self.compute_type)
            segments, _ = self._model.transcribe(str(wav_path), language=language, vad_filter=True)
            return [ASRSegment(start_sec=item.start, end_sec=item.end, text=item.text.strip()) for item in segments]
        except RuntimeError as exc:
            message = str(exc).lower()
            if self.device != "cuda" or not any(token in message for token in ("cuda", "memory", "cublas", "cudnn")):
                raise
            self.unload()
            self.fell_back_to_cpu = True
            self.fallback_reason = str(exc)
            self._model = self._load("cpu", "int8")
            segments, _ = self._model.transcribe(str(wav_path), language=language, vad_filter=True)
            return [ASRSegment(start_sec=item.start, end_sec=item.end, text=item.text.strip()) for item in segments]

    def unload(self) -> None:
        self._model = None
