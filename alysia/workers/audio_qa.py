from __future__ import annotations

import re
from difflib import SequenceMatcher

from alysia.core.run import RunManager, RunState
from alysia.schemas import AudioManifest, AudioQAReport, Storyboard, SubtitleDocument
from alysia.workers.text import normalize_narration
from alysia.workers.wav import inspect_wav, signal_metrics


class AudioQAWorker:
    def __init__(self, manager: RunManager, *, allow_test_tone: bool = False) -> None:
        self.manager = manager
        self.allow_test_tone = allow_test_tone

    def run(
        self,
        state: RunState,
        storyboard: Storyboard,
        manifest: AudioManifest,
        subtitles: SubtitleDocument,
    ) -> AudioQAReport:
        errors: list[str] = []
        warnings: list[str] = []
        run_dir = self.manager.run_dir(state.run_id)
        narration_path = run_dir / manifest.narration_file
        metrics: dict[str, float | int | str] = {
            "manifest_scene_count": len(manifest.scenes),
            "subtitle_segment_count": len(subtitles.segments),
        }
        providers = sorted({scene.provider for scene in manifest.scenes})
        metrics["tts_providers"] = ",".join(providers)
        if "mock" in providers and not self.allow_test_tone:
            errors.append("检测到 MockTTS 测试音；测试 tone 不能作为正式旁白进入视频流水线")

        if not narration_path.is_file():
            errors.append("narration.wav 不存在")
            return AudioQAReport(passed=False, errors=errors, warnings=warnings, metrics=metrics)
        try:
            info = inspect_wav(narration_path)
            metrics.update({f"narration_{key}": value for key, value in info.items()})
        except (OSError, EOFError) as exc:
            errors.append(f"narration.wav 无法解码：{exc}")
            return AudioQAReport(passed=False, errors=errors, warnings=warnings, metrics=metrics)
        if info["duration_sec"] <= 0:
            errors.append("narration.wav 时长为零")
        if abs(float(info["duration_sec"]) - manifest.total_duration_sec) > 0.03:
            errors.append("audio manifest 总时长与 narration.wav 不一致")
        if info["channels"] != 1 or info["sample_width_bytes"] != 2:
            errors.append("narration.wav 不是 PCM16 mono")

        expected_scenes = [scene for scene in storyboard.scenes if normalize_narration(scene.narration)]
        if len(expected_scenes) != len(manifest.scenes):
            errors.append("scene WAV 数与有旁白的 storyboard scene 数不一致")
        if abs(subtitles.total_duration_sec - manifest.total_duration_sec) > 0.03:
            errors.append("subtitles 总时长与 audio manifest 不一致")

        previous_end = 0.0
        speech_duration = 0.0
        for index, scene in enumerate(manifest.scenes):
            scene_path = run_dir / scene.file
            if not scene_path.is_file():
                errors.append(f"scene WAV 不存在：{scene.file}")
                continue
            try:
                scene_info = inspect_wav(scene_path)
            except (OSError, EOFError) as exc:
                errors.append(f"scene WAV 无法解码：{scene.file}：{exc}")
                continue
            if scene_info["duration_sec"] <= 0 or scene.end_sec <= scene.start_sec:
                errors.append(f"scene 音频时长无效：{scene.scene_id}")
            if scene.start_sec + 1e-6 < previous_end:
                errors.append(f"audio manifest 时间反向或重叠：{scene.scene_id}")
            if index > 0:
                expected_gap = manifest.pause_between_scenes_ms / 1000.0
                actual_gap = scene.start_sec - previous_end
                if abs(actual_gap - expected_gap) > 0.03:
                    warnings.append(f"scene 间停顿偏离配置：{scene.scene_id}")
            previous_end = scene.end_sec
            speech_duration += scene.duration_sec

        audio_signal = signal_metrics(narration_path)
        metrics.update(audio_signal)
        if audio_signal["rms"] < 0.001 or audio_signal["peak"] < 0.005:
            errors.append("narration.wav 近乎全静音")
        if audio_signal["peak"] >= 0.98:
            warnings.append("narration.wav 峰值接近 clipping")
        if audio_signal["clipping_ratio"] > 0.001:
            errors.append("narration.wav 存在严重 clipping")
        if (
            not self.allow_test_tone
            and audio_signal["active_window_ratio"] > 0.9
            and audio_signal["active_rms_cv"] < 0.35
            and audio_signal["active_zero_crossing_cv"] < 0.05
        ):
            errors.append("narration.wav 缺乏语音动态，疑似持续测试音或稳定噪声")

        previous_end = 0.0
        covered = 0.0
        for segment in subtitles.segments:
            if segment.start_sec + 1e-6 < previous_end:
                errors.append(f"字幕重叠或时间反向：{segment.id}")
            if segment.end_sec > manifest.total_duration_sec + 0.03:
                errors.append(f"字幕越过 narration 时长：{segment.id}")
            previous_end = segment.end_sec
            covered += segment.end_sec - segment.start_sec
        coverage = covered / speech_duration if speech_duration else 0.0
        metrics["subtitle_speech_coverage"] = round(coverage, 6)
        if coverage < 0.8:
            errors.append("字幕未覆盖大部分旁白时长")

        source_text = _comparable("".join(scene.normalized_text for scene in manifest.scenes))
        subtitle_text = _comparable("".join(segment.text for segment in subtitles.segments))
        text_coverage = SequenceMatcher(None, source_text, subtitle_text).ratio() if source_text else 0.0
        metrics["subtitle_text_similarity"] = round(text_coverage, 6)
        if text_coverage < 0.9:
            errors.append("字幕文本与原旁白严重缺失")

        return AudioQAReport(
            passed=not errors,
            errors=errors,
            warnings=warnings,
            metrics=metrics,
        )


def _comparable(value: str) -> str:
    return re.sub(r"\W+", "", value, flags=re.UNICODE).lower()
