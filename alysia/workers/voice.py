from __future__ import annotations

import hashlib
import json
import wave
from pathlib import Path

from alysia.core.config import TTSConfig
from alysia.core.resources import ResourceManager
from alysia.core.run import RunManager, RunState
from alysia.providers.tts import BaseTTSProvider
from alysia.schemas import AudioManifest, AudioScene, SpeechTiming, Storyboard, TTSRequest
from alysia.workers.text import normalize_narration
from alysia.workers.wav import concatenate_wavs, inspect_wav
from alysia.reliability.monitor import LongRunningTaskMonitor


class VoiceWorker:
    def __init__(
        self,
        manager: RunManager,
        config: TTSConfig,
        provider: BaseTTSProvider,
        resources: ResourceManager,
    ) -> None:
        self.manager = manager
        self.config = config
        self.provider = provider
        self.resources = resources

    async def run(self, state: RunState, storyboard: Storyboard, *, force: bool = False) -> AudioManifest:
        run_dir = self.manager.run_dir(state.run_id)
        manifest_path = run_dir / "audio" / "audio_manifest.json"
        previous = self._load_previous(manifest_path)
        previous_by_id = {scene.scene_id: scene for scene in previous.scenes} if previous else {}
        audio_scenes: list[AudioScene] = []
        scene_paths: list[Path] = []
        provider_rate: int | None = None
        cursor = 0.0
        pause_sec = self.config.pause_between_scenes_ms / 1000.0

        monitor = LongRunningTaskMonitor(run_dir / "reliability" / "tasks")
        with monitor.track("tts", expected_timeout=1800, run_id=state.run_id) as monitored_task, self.resources.phase(
            "tts", provider=self.provider, gpu_heavy=self.provider.name != "mock"
        ):
            for storyboard_index, scene in enumerate(storyboard.scenes, start=1):
                monitor.heartbeat(monitored_task.task_id, scene_id=scene.id, scene_index=storyboard_index)
                normalized = normalize_narration(scene.narration)
                if not normalized:
                    continue
                output_path = run_dir / "audio" / "scenes" / f"scene_{storyboard_index:03d}.wav"
                input_hash = self._input_hash(scene.id, normalized)
                cached = previous_by_id.get(scene.id)
                relative_output = output_path.relative_to(run_dir).as_posix()
                use_cache = bool(
                    not force
                    and cached
                    and cached.input_hash == input_hash
                    and cached.file == relative_output
                    and output_path.is_file()
                )
                if use_cache:
                    try:
                        info = inspect_wav(output_path)
                        self._validate_scene_format(output_path, info, provider_rate)
                        result_provider = cached.provider
                        word_timings = cached.word_timings
                    except (OSError, EOFError, wave.Error):
                        use_cache = False
                if not use_cache:
                    result = await self.provider.synthesize(
                        TTSRequest(
                            text=normalized,
                            scene_id=scene.id,
                            section_id=scene.section_id,
                            language=self.config.language,
                            voice=self.config.voice,
                            speed=self.config.speed,
                            sample_rate=self.config.sample_rate,
                            output_path=output_path,
                        )
                    )
                    if result.wav_path.resolve() != output_path.resolve():
                        raise ValueError("TTS provider 必须写入请求指定的 output_path")
                    info = inspect_wav(output_path)
                    result_provider = result.provider
                    word_timings = [
                        SpeechTiming.model_validate(item)
                        for item in result.metadata.get("word_timings", [])
                    ]
                self._validate_scene_format(output_path, info, provider_rate)
                provider_rate = provider_rate or int(info["sample_rate"])
                duration = float(info["duration_sec"])
                start = cursor
                end = start + duration
                audio_scenes.append(
                    AudioScene(
                        index=len(audio_scenes) + 1,
                        scene_id=scene.id,
                        section_id=scene.section_id,
                        original_text=scene.narration,
                        normalized_text=normalized,
                        file=relative_output,
                        duration_sec=round(duration, 6),
                        start_sec=round(start, 6),
                        end_sec=round(end, 6),
                        provider=result_provider,
                        input_hash=input_hash,
                        word_timings=word_timings,
                    )
                )
                scene_paths.append(output_path)
                cursor = end + pause_sec

        if not audio_scenes:
            raise ValueError("Storyboard 没有可生成旁白的 scene")
        narration_path = run_dir / "audio" / "narration.wav"
        narration_info = concatenate_wavs(
            scene_paths,
            narration_path,
            pause_between_scenes_ms=self.config.pause_between_scenes_ms,
        )
        manifest = AudioManifest(
            sample_rate=int(narration_info["sample_rate"]),
            pause_between_scenes_ms=self.config.pause_between_scenes_ms,
            total_duration_sec=round(float(narration_info["duration_sec"]), 6),
            scenes=audio_scenes,
        )
        self.manager.write_json(state.run_id, "audio/audio_manifest.json", manifest.model_dump(mode="json"))
        return manifest

    def _input_hash(self, scene_id: str, normalized_text: str) -> str:
        payload = {
            "scene_id": scene_id,
            "text": normalized_text,
            "provider": self.provider.name,
            "language": self.config.language,
            "voice": self.config.voice,
            "speed": self.config.speed,
            "sample_rate": self.config.sample_rate,
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()

    @staticmethod
    def _load_previous(path: Path) -> AudioManifest | None:
        if not path.is_file():
            return None
        try:
            return AudioManifest.model_validate_json(path.read_text(encoding="utf-8"))
        except ValueError:
            return None

    @staticmethod
    def _validate_scene_format(path: Path, info: dict[str, int | float], provider_rate: int | None) -> None:
        if info["channels"] != 1 or info["sample_width_bytes"] != 2 or info["duration_sec"] <= 0:
            raise ValueError(f"TTS 输出必须是非空 PCM16 mono WAV：{path}")
        if provider_rate is not None and info["sample_rate"] != provider_rate:
            raise ValueError("同一 narration 中的 scene sample rate 必须一致")
