from __future__ import annotations

import asyncio
import math
import struct
import wave
from pathlib import Path

from alysia.core.config import AlysiaConfig, SubtitleConfig, VideoConfig
from alysia.core.orchestrator import AlysiaOrchestrator
from alysia.core.run import RunManager
from alysia.core.state import Stage
from alysia.providers.video import MockVideoRenderer
from alysia.schemas import (
    AudioManifest,
    AudioScene,
    Scene,
    Storyboard,
    SubtitleDocument,
    SubtitleSegment,
    VideoComposition,
)
from alysia.workers.composition import CompositionWorker
from alysia.workers.media import probe_media, require_media_executable
from alysia.workers.video_qa import VideoQAWorker, parse_ffprobe
from tests.helpers import make_config


def _storyboard() -> Storyboard:
    return Storyboard(
        title="视频测试",
        target_duration_sec=30,
        scenes=[
            Scene(
                id="scene-1",
                section_id="section-1",
                duration_sec=30,
                narration="Alysia 视频测试。",
                visual_type="title",
                screen_text="Alysia",
            )
        ],
    )


def _write_tone(path: Path, duration_sec: float = 0.8, sample_rate: int = 24000) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame_count = round(duration_sec * sample_rate)
    frames = bytearray()
    for index in range(frame_count):
        value = round(3000 * math.sin(2 * math.pi * 440 * index / sample_rate))
        frames.extend(struct.pack("<h", value))
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(sample_rate)
        stream.writeframes(frames)


def _fixture(tmp_path: Path):
    config = make_config(tmp_path / "runs")
    config.video = VideoConfig(renderer="mock", width=640, height=360, fps=30)
    manager = RunManager(config.runtime.runs_dir)
    state = manager.create("视频测试", config.model_dump(mode="json"))
    storyboard = _storyboard()
    manifest = AudioManifest(
        total_duration_sec=0.8,
        scenes=[
            AudioScene(
                index=1,
                scene_id="scene-1",
                section_id="section-1",
                original_text="Alysia 视频测试。",
                normalized_text="Alysia 视频测试。",
                file="audio/scenes/scene_001.wav",
                duration_sec=0.8,
                start_sec=0,
                end_sec=0.8,
                provider="mock",
                input_hash="12345678",
            )
        ],
    )
    subtitles = SubtitleDocument(
        total_duration_sec=0.8,
        segments=[SubtitleSegment(id=1, scene_id="scene-1", start_sec=0, end_sec=0.8, text="Alysia 视频测试。")],
    )
    run_dir = manager.run_dir(state.run_id)
    _write_tone(run_dir / "audio/narration.wav")
    _write_tone(run_dir / "audio/scenes/scene_001.wav")
    manager.write_json(state.run_id, "storyboard.json", storyboard.model_dump(mode="json"))
    manager.write_json(state.run_id, "audio/audio_manifest.json", manifest.model_dump(mode="json"))
    manager.write_json(state.run_id, "subtitles/subtitles.json", subtitles.model_dump(mode="json"))
    manager.write_json(state.run_id, "audio_qa_report.json", {"passed": True})
    state.artifacts.update(
        {
            "storyboard": "storyboard.json",
            "audio_manifest": "audio/audio_manifest.json",
            "narration": "audio/narration.wav",
            "subtitles_json": "subtitles/subtitles.json",
            "audio_qa_report": "audio_qa_report.json",
        }
    )
    state.completed_stages.extend([Stage.STORYBOARDING, Stage.GENERATING_VOICE, Stage.GENERATING_SUBTITLES, Stage.QA])
    state.audio_pipeline_completed = True
    state.pipeline_phase = "audio_ready"
    state.milestone = "audio_ready"
    manager.save(state)
    return config, manager, state, storyboard, manifest, subtitles


def test_video_schema() -> None:
    composition = VideoComposition(
        title="schema",
        width=1920,
        height=1080,
        fps=30,
        duration_frames=30,
        audio_file="audio/narration.wav",
        scenes=[{"id": "one", "start_frame": 0, "duration_frames": 30, "type": "text"}],
    )
    assert composition.duration_frames == 30
    assert composition.scenes[0].type.value == "text"


def test_mock_renderer(tmp_path) -> None:
    config, manager, state, storyboard, manifest, subtitles = _fixture(tmp_path)
    output = manager.run_dir(state.run_id) / "video/temp/mock.mp4"
    result = MockVideoRenderer(config.video, config.render).render(storyboard, manifest, subtitles, output)
    probe = parse_ffprobe(probe_media(output, require_media_executable("ffprobe")))
    assert result.renderer == "mock"
    assert output.stat().st_size > 0
    assert probe.video_codec == "h264"
    assert probe.audio_codec == "aac"


def test_composition_generation(tmp_path) -> None:
    config, manager, state, storyboard, manifest, subtitles = _fixture(tmp_path)
    composition = CompositionWorker(manager, config.video, SubtitleConfig()).run(
        state, storyboard, manifest, subtitles
    )
    assert composition.duration_frames == 24
    assert composition.scenes[0].start_frame == 0
    assert composition.scenes[0].duration_frames == 24
    assert (manager.run_dir(state.run_id) / "video/composition.json").is_file()


def test_subtitle_mapping(tmp_path) -> None:
    config, manager, state, storyboard, manifest, subtitles = _fixture(tmp_path)
    composition = CompositionWorker(manager, config.video, SubtitleConfig()).run(
        state, storyboard, manifest, subtitles
    )
    assert composition.subtitles[0].start_frame == 0
    assert composition.subtitles[0].end_frame == 24
    assert composition.scenes[0].subtitle_range == (0, 1)


def test_ffprobe_parser() -> None:
    parsed = parse_ffprobe(
        {
            "streams": [
                {"codec_type": "video", "codec_name": "h264", "width": 1920, "height": 1080, "avg_frame_rate": "30/1"},
                {"codec_type": "audio", "codec_name": "aac", "sample_rate": "48000", "channels": 2},
            ],
            "format": {"duration": "12.5"},
        }
    )
    assert parsed.fps == 30
    assert parsed.duration_sec == 12.5
    assert parsed.audio_sample_rate == 48000
    assert parsed.audio_channels == 2


def test_render_idempotent(tmp_path) -> None:
    config, manager, state, *_ = _fixture(tmp_path)
    orchestrator = AlysiaOrchestrator(config)
    first = asyncio.run(orchestrator.render(state.run_id))
    final_path = manager.run_dir(state.run_id) / first.artifacts["final_video"]
    first_mtime = final_path.stat().st_mtime_ns
    second = asyncio.run(orchestrator.render(state.run_id))
    assert second.milestone == "video_ready"
    assert second.video_pipeline_completed is True
    assert final_path.stat().st_mtime_ns == first_mtime


def test_video_qa(tmp_path) -> None:
    config, manager, state, *_ = _fixture(tmp_path)
    orchestrator = AlysiaOrchestrator(config)
    rendered = asyncio.run(orchestrator.render(state.run_id))
    final_path = manager.run_dir(state.run_id) / rendered.artifacts["final_video"]
    report = VideoQAWorker(config).run(final_path, 0.8)
    assert report.passed is True
    assert report.metrics["width"] == 640
    assert report.metrics["height"] == 360
    assert report.metrics["audio_sample_rate"] == 48000
    assert report.metrics["audio_channels"] == 2
    assert report.metrics["decodable"] is True
