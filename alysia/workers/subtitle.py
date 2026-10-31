from __future__ import annotations

import math
import re
import json
from datetime import datetime
from pathlib import Path

from loguru import logger

from alysia.core.config import SubtitleConfig
from alysia.core.resources import ResourceManager
from alysia.core.run import RunManager, RunState
from alysia.providers.asr import ASRSegment, BaseASRProvider
from alysia.schemas import AudioManifest, Storyboard, SubtitleDocument, SubtitleSegment
from alysia.schemas import FallbackRecord, ProductionPlan
from alysia.production.metrics import ExecutionMetricsStore
from alysia.reliability.monitor import LongRunningTaskMonitor


class SubtitleWorker:
    def __init__(
        self,
        manager: RunManager,
        config: SubtitleConfig,
        resources: ResourceManager,
        asr_provider: BaseASRProvider | None = None,
    ) -> None:
        self.manager = manager
        self.config = config
        self.resources = resources
        self.asr_provider = asr_provider

    def run(self, state: RunState, storyboard: Storyboard, manifest: AudioManifest) -> SubtitleDocument:
        scene_ids = {scene.id for scene in storyboard.scenes}
        unknown = {scene.scene_id for scene in manifest.scenes} - scene_ids
        if unknown:
            raise ValueError(f"audio manifest 含未知 scene：{', '.join(sorted(unknown))}")

        asr_segments: list[ASRSegment] = []
        if self.asr_provider is not None:
            narration_path = self.manager.run_dir(state.run_id) / manifest.narration_file
            try:
                monitor = LongRunningTaskMonitor(self.manager.run_dir(state.run_id) / "reliability" / "tasks")
                with monitor.track("asr", expected_timeout=1800, run_id=state.run_id), self.resources.phase(
                    "asr", provider=self.asr_provider, gpu_heavy=self.asr_provider.name != "mock"
                ):
                    asr_segments = self.asr_provider.transcribe(narration_path, language="zh")
                if getattr(self.asr_provider, "fell_back_to_cpu", False):
                    self._record_fallback(
                        state,
                        original_choice=f"asr.{self.asr_provider.name}:cuda",
                        failure_reason=getattr(self.asr_provider, "fallback_reason", None) or "CUDA ASR 失败",
                        fallback_choice=f"asr.{self.asr_provider.name}:cpu",
                        quality_impact="质量目标不变；预计时延增加，GPU 显存占用降低",
                    )
            except Exception as exc:  # 可选校准失败时保留可靠的 deterministic 主路径
                logger.warning("ASR alignment skipped: {}", exc)
                self._record_fallback(
                    state,
                    original_choice=f"asr.{self.asr_provider.name}",
                    failure_reason=str(exc),
                    fallback_choice="subtitle.deterministic",
                    quality_impact="失去 ASR 时间校准；保留原稿文字并按真实音频时长确定性分配",
                )
                asr_segments = []

        segments: list[SubtitleSegment] = []
        for audio_scene in manifest.scenes:
            window_start, window_end, aligned = _scene_window(
                audio_scene.start_sec,
                audio_scene.end_sec,
                asr_segments,
            )
            chunks = _fit_chunks(
                _split_text(audio_scene.normalized_text, self.config.max_chars_per_line),
                window_end - window_start,
                self.config.min_duration_sec,
                self.config.max_duration_sec,
            )
            if not aligned and audio_scene.word_timings:
                scene_source = "tts"
                windows = _tts_windows(audio_scene.normalized_text, chunks, audio_scene.word_timings, audio_scene.duration_sec)
                windows = [(audio_scene.start_sec + start, audio_scene.start_sec + end) for start, end in windows]
            else:
                scene_source = "asr" if aligned else "deterministic"
                durations = _allocate_durations(
                    chunks,
                    window_end - window_start,
                    self.config.min_duration_sec,
                    self.config.max_duration_sec,
                )
                cursor = window_start
                windows = []
                for index, duration in enumerate(durations):
                    end = window_end if index == len(durations) - 1 else cursor + duration
                    windows.append((cursor, end))
                    cursor = end
            for chunk, (start, end) in zip(chunks, windows, strict=True):
                segments.append(
                    SubtitleSegment(
                        id=len(segments) + 1,
                        scene_id=audio_scene.scene_id,
                        start_sec=round(start, 3),
                        end_sec=round(end, 3),
                        text=chunk,
                        source=scene_source,
                    )
                )

        sources = {segment.source for segment in segments}
        document_source = "asr" if "asr" in sources else "tts" if "tts" in sources else "deterministic"
        document = SubtitleDocument(
            total_duration_sec=manifest.total_duration_sec,
            source=document_source,
            segments=segments,
        )
        self.manager.write_json(state.run_id, "subtitles/subtitles.json", document.model_dump(mode="json"))
        srt = "\n\n".join(
            f"{segment.id}\n{_srt_time(segment.start_sec)} --> {_srt_time(segment.end_sec)}\n{segment.text}"
            for segment in document.segments
        )
        self.manager.write_text(state.run_id, "subtitles/subtitles.srt", srt)
        return document

    def _record_fallback(
        self,
        state: RunState,
        *,
        original_choice: str,
        failure_reason: str,
        fallback_choice: str,
        quality_impact: str,
    ) -> None:
        record = FallbackRecord(
            stage_id="subtitle_alignment",
            original_choice=original_choice,
            failure_reason=failure_reason,
            fallback_choice=fallback_choice,
            quality_impact=quality_impact,
            occurred_at=datetime.now().astimezone(),
        )
        run_dir = self.manager.run_dir(state.run_id)
        plan_path = run_dir / "production" / "production_plan.json"
        if plan_path.is_file():
            try:
                plan = ProductionPlan.model_validate_json(plan_path.read_text(encoding="utf-8"))
                ExecutionMetricsStore(run_dir, run_id=state.run_id, plan_id=plan.plan_id).record_fallback(record)
                return
            except (OSError, ValueError):
                pass
        path = run_dir / "production" / "degradation_events.json"
        payload = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else []
        payload.append(record.model_dump(mode="json"))
        self.manager.write_json(state.run_id, "production/degradation_events.json", payload)


def _split_text(text: str, max_chars: int) -> list[str]:
    value = re.sub(r"\s+", " ", text).strip()
    clauses = [part.strip() for part in re.findall(r"[^。！？!?；;，,、]+[。！？!?；;，,、]?", value) if part.strip()]
    chunks: list[str] = []
    pending = ""
    for clause in clauses or [value]:
        parts = _balanced_parts(clause, max_chars)
        for part in parts:
            if pending and len(pending) + len(part) > max_chars:
                chunks.append(pending)
                pending = ""
            pending += part
            if part.endswith(("。", "！", "？", "!", "?", "；", ";")):
                chunks.append(pending)
                pending = ""
    if pending:
        chunks.append(pending)
    return chunks


def _balanced_parts(text: str, max_chars: int) -> list[str]:
    value = text.strip()
    if len(value) <= max_chars:
        return [value] if value else []
    count = math.ceil(len(value) / max_chars)
    parts: list[str] = []
    remaining = value
    while len(remaining) > max_chars:
        remaining_count = count - len(parts)
        target = max(1, round(len(remaining) / remaining_count))
        lower = max(1, target - 4)
        upper = min(max_chars, target + 4)
        candidates = [
            index
            for index in range(lower, upper + 1)
            if not (_ascii_word_char(remaining[index - 1]) and _ascii_word_char(remaining[index]))
        ]
        split_at = min(candidates, key=lambda index: (abs(index - target), -index)) if candidates else target
        parts.append(remaining[:split_at].strip())
        remaining = remaining[split_at:].strip()
    if remaining:
        parts.append(remaining)
    return parts


def _ascii_word_char(value: str) -> bool:
    return value.isascii() and (value.isalnum() or value in "_-.")


def _fit_chunks(chunks: list[str], duration: float, minimum: float, maximum: float) -> list[str]:
    if not chunks:
        raise ValueError("字幕文本不能为空")
    minimum_count = max(1, math.ceil(duration / maximum - 1e-9))
    maximum_count = max(1, math.floor(duration / minimum + 1e-9))
    target = min(max(len(chunks), minimum_count), maximum_count)
    fitted = list(chunks)
    while len(fitted) < target:
        index = max(range(len(fitted)), key=lambda item: len(fitted[item]))
        value = fitted[index]
        if len(value) <= 1:
            break
        midpoint = max(1, math.ceil(len(value) / 2))
        parts = _balanced_parts(value, midpoint)
        if len(parts) < 2:
            break
        fitted[index : index + 1] = parts
    while len(fitted) > target:
        index = min(range(len(fitted) - 1), key=lambda item: len(fitted[item]) + len(fitted[item + 1]))
        fitted[index : index + 2] = [fitted[index] + fitted[index + 1]]
    return fitted


def _tts_windows(text: str, chunks: list[str], timings: list, duration: float) -> list[tuple[float, float]]:
    compact_text = re.sub(r"\s+", "", text)
    event_positions = [
        (
            len(re.sub(r"\s+", "", text[: timing.character_start])),
            timing.start_sec,
        )
        for timing in timings
    ]
    boundaries = [0.0]
    consumed = 0
    for chunk in chunks[:-1]:
        consumed += len(re.sub(r"\s+", "", chunk))
        candidate = next((start for position, start in event_positions if position >= consumed), None)
        if candidate is None:
            candidate = duration * consumed / max(1, len(compact_text))
        boundaries.append(max(boundaries[-1] + 0.05, min(float(candidate), duration - 0.05)))
    boundaries.append(duration)
    return list(zip(boundaries, boundaries[1:]))


def _allocate_durations(chunks: list[str], total: float, minimum: float, maximum: float) -> list[float]:
    count = len(chunks)
    if count == 1:
        return [total]
    weights = [max(1, len(re.sub(r"\s+", "", chunk))) for chunk in chunks]
    allocations = [0.0] * count
    active = set(range(count))
    remaining = total
    while active:
        weight_sum = sum(weights[index] for index in active)
        changed = False
        for index in list(active):
            share = remaining * weights[index] / weight_sum
            if share < minimum:
                allocations[index] = minimum
                remaining -= minimum
                active.remove(index)
                changed = True
                break
            if share > maximum:
                allocations[index] = maximum
                remaining -= maximum
                active.remove(index)
                changed = True
                break
        if changed:
            continue
        for index in active:
            allocations[index] = remaining * weights[index] / weight_sum
        break
    allocations[-1] += total - sum(allocations)
    return allocations


def _scene_window(start: float, end: float, asr_segments: list[ASRSegment]) -> tuple[float, float, bool]:
    overlapping = [segment for segment in asr_segments if segment.end_sec > start and segment.start_sec < end]
    if not overlapping:
        return start, end, False
    aligned_start = max(start, overlapping[0].start_sec)
    aligned_end = min(end, overlapping[-1].end_sec)
    return (aligned_start, aligned_end, True) if aligned_end > aligned_start else (start, end, False)


def _srt_time(seconds: float) -> str:
    milliseconds = max(0, round(seconds * 1000))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"
