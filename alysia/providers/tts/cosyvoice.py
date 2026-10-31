from __future__ import annotations

import importlib.util
import wave
from array import array
from pathlib import Path
from typing import Any

from alysia.providers.tts.base import BaseTTSProvider
from alysia.schemas.audio import TTSRequest, TTSResult


class CosyVoiceProvider(BaseTTSProvider):
    """CosyVoice 惰性适配器；不会自动下载模型或修改环境。"""

    name = "cosyvoice"

    def __init__(self, model_dir: Path | None = None) -> None:
        self.model_dir = model_dir
        self._engine: Any | None = None

    @classmethod
    def is_available(cls) -> bool:
        return importlib.util.find_spec("cosyvoice") is not None

    def _load(self) -> Any:
        if not self.is_available():
            raise RuntimeError("CosyVoice 不可用：项目环境未安装 cosyvoice；alpha.3 不会自动下载或安装大型模型。")
        if self.model_dir is None or not self.model_dir.exists():
            raise RuntimeError("CosyVoice 不可用：请在 tts.model_dir 配置已存在的本地模型目录。")
        if self._engine is None:
            try:
                from cosyvoice.cli.cosyvoice import CosyVoice2
            except ImportError as exc:
                raise RuntimeError("当前 cosyvoice 包不提供 CosyVoice2 API，无法使用此适配器。") from exc
            self._engine = CosyVoice2(str(self.model_dir), load_jit=False, load_trt=False, fp16=True)
        return self._engine

    async def synthesize(self, request: TTSRequest) -> TTSResult:
        engine = self._load()
        if request.speed != 1.0:
            raise RuntimeError("当前 CosyVoice 适配器尚不安全支持 speed != 1.0。")
        chunks = list(engine.inference_sft(request.text, request.voice, stream=False))
        if not chunks:
            raise RuntimeError("CosyVoice 未返回音频。")
        pcm = array("h")
        for chunk in chunks:
            speech = chunk["tts_speech"].detach().float().cpu().reshape(-1).tolist()
            pcm.extend(max(-32768, min(32767, round(float(value) * 32767))) for value in speech)
        sample_rate = int(getattr(engine, "sample_rate", request.sample_rate))
        request.output_path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(request.output_path), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(pcm.tobytes())
        return TTSResult(
            wav_path=request.output_path,
            duration_sec=len(pcm) / sample_rate,
            sample_rate=sample_rate,
            channels=1,
            provider=self.name,
            metadata={"model_dir": str(self.model_dir)},
        )

    def unload(self) -> None:
        self._engine = None
