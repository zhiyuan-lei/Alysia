from __future__ import annotations

import asyncio
import json
import wave
from pathlib import Path

import pytest
from typer.testing import CliRunner

from alysia.cli import app
from alysia.core.config import SubtitleConfig, TTSConfig
from alysia.core.orchestrator import AlysiaOrchestrator
from alysia.core.resources import ResourceManager
from alysia.core.run import RunManager
from alysia.providers.tts import MockTTSProvider, SapiTTSProvider
from alysia.schemas import AudioManifest, Scene, Storyboard, TTSRequest
from alysia.workers import AudioQAWorker, SubtitleWorker, VoiceWorker
from alysia.workers.subtitle import _split_text
from alysia.workers.wav import inspect_wav
from tests.helpers import make_config, write_config


def _storyboard(text: str = "这是用于验证音频闭环的中文旁白。") -> Storyboard:
    return Storyboard(
        title="音频测试",
        target_duration_sec=30,
        scenes=[
            Scene(
                id="scene-1",
                section_id="section-1",
                duration_sec=30,
                narration=text,
                visual_type="text",
            )
        ],
    )


def _voice_fixture(tmp_path: Path, text: str = "这是用于验证音频闭环的中文旁白。"):
    manager = RunManager(tmp_path / "runs")
    state = manager.create("音频测试", {})
    provider = MockTTSProvider()
    worker = VoiceWorker(manager, TTSConfig(), provider, ResourceManager())
    storyboard = _storyboard(text)
    manifest = asyncio.run(worker.run(state, storyboard))
    return manager, state, storyboard, manifest, provider


def test_tts_mock_generates_wav(tmp_path) -> None:
    output = tmp_path / "mock.wav"
    provider = MockTTSProvider()
    result = asyncio.run(
        provider.synthesize(
            TTSRequest(
                text="你好，Alysia。",
                scene_id="scene-1",
                sample_rate=24000,
                output_path=output,
            )
        )
    )

    with wave.open(str(output), "rb") as wav_file:
        assert wav_file.getnchannels() == 1
        assert wav_file.getsampwidth() == 2
        assert wav_file.getframerate() == 24000
        assert wav_file.getnframes() > 0
    assert result.duration_sec > 0


def test_audio_manifest(tmp_path) -> None:
    manager, state, _, manifest, _ = _voice_fixture(tmp_path)
    run_dir = manager.run_dir(state.run_id)

    saved = AudioManifest.model_validate_json((run_dir / "audio/audio_manifest.json").read_text(encoding="utf-8"))
    assert saved == manifest
    assert saved.channels == 1
    assert saved.sample_rate == 24000
    assert saved.scenes[0].original_text
    assert saved.scenes[0].normalized_text
    assert (run_dir / saved.narration_file).is_file()


def test_voice_cache_idempotent(tmp_path) -> None:
    manager, state, storyboard, _, provider = _voice_fixture(tmp_path)
    scene_path = manager.run_dir(state.run_id) / "audio/scenes/scene_001.wav"
    original_mtime = scene_path.stat().st_mtime_ns

    worker = VoiceWorker(manager, TTSConfig(), provider, ResourceManager())
    asyncio.run(worker.run(state, storyboard))

    assert provider.call_count == 1
    assert scene_path.stat().st_mtime_ns == original_mtime


def test_subtitle_deterministic(tmp_path) -> None:
    manager, state, storyboard, manifest, _ = _voice_fixture(tmp_path)
    worker = SubtitleWorker(manager, SubtitleConfig(max_chars_per_line=10), ResourceManager())

    document = worker.run(state, storyboard, manifest)

    assert document.source == "deterministic"
    assert all(segment.source == "deterministic" for segment in document.segments)
    assert all(len(segment.text) <= 10 for segment in document.segments)
    assert (manager.run_dir(state.run_id) / "subtitles/subtitles.srt").is_file()


def test_subtitle_monotonic(tmp_path) -> None:
    manager, state, storyboard, manifest, _ = _voice_fixture(
        tmp_path,
        "第一句用于测试。第二句仍然需要严格对齐，而且不能产生重叠。",
    )
    document = SubtitleWorker(manager, SubtitleConfig(), ResourceManager()).run(state, storyboard, manifest)

    previous_end = 0.0
    for segment in document.segments:
        assert segment.start_sec >= previous_end - 1e-6
        assert segment.end_sec > segment.start_sec
        assert segment.end_sec <= manifest.total_duration_sec + 0.001
        previous_end = segment.end_sec


def test_audio_qa_rejects_mock_tone(tmp_path) -> None:
    manager, state, storyboard, manifest, _ = _voice_fixture(tmp_path)
    subtitles = SubtitleWorker(manager, SubtitleConfig(), ResourceManager()).run(state, storyboard, manifest)

    report = AudioQAWorker(manager).run(state, storyboard, manifest, subtitles)

    assert report.passed is False
    assert any("MockTTS" in error for error in report.errors)


def test_audio_qa_allows_explicit_test_tone(tmp_path) -> None:
    manager, state, storyboard, manifest, _ = _voice_fixture(tmp_path)
    subtitles = SubtitleWorker(manager, SubtitleConfig(), ResourceManager()).run(state, storyboard, manifest)

    report = AudioQAWorker(manager, allow_test_tone=True).run(state, storyboard, manifest, subtitles)

    assert report.passed is True
    assert report.errors == []
    assert report.metrics["subtitle_speech_coverage"] >= 0.8


def test_audio_qa_rejects_persistent_tone_even_if_provider_is_renamed(tmp_path) -> None:
    manager, state, storyboard, manifest, _ = _voice_fixture(tmp_path)
    for scene in manifest.scenes:
        scene.provider = "fixture"
    subtitles = SubtitleWorker(manager, SubtitleConfig(), ResourceManager()).run(state, storyboard, manifest)

    report = AudioQAWorker(manager).run(state, storyboard, manifest, subtitles)

    assert report.passed is False
    assert any("缺乏语音动态" in error for error in report.errors)


def test_subtitle_split_balances_long_clause_without_orphan() -> None:
    text = "Agent 强调围绕目标调用工具并推进任务；"

    chunks = _split_text(text, 20)

    assert "".join(chunks).replace(" ", "") == text.replace(" ", "")
    assert all(len(chunk) <= 20 for chunk in chunks)
    assert all(not chunk.endswith("任") for chunk in chunks)
    assert all(chunk != "务；" for chunk in chunks)


def test_subtitle_split_preserves_sentence_and_weak_punctuation_boundaries() -> None:
    chunks = _split_text(
        "先区分两个概念。Agent 强调围绕目标调用工具并推进任务；"
        "只有当行动、验证、迁移与持续学习形成可靠闭环时，",
        22,
    )

    assert chunks[0] == "先区分两个概念。"
    assert chunks[1] == "Agent 强调围绕目标调用工具并推进任务；"
    assert "只有当行动、验证、" in chunks
    assert all(len(chunk) <= 22 for chunk in chunks)


@pytest.mark.skipif(not SapiTTSProvider.is_available(), reason="Windows SAPI 不可用")
def test_sapi_tts_produces_speech_timings(tmp_path) -> None:
    output = tmp_path / "sapi.wav"
    provider = SapiTTSProvider()

    result = asyncio.run(
        provider.synthesize(
            TTSRequest(
                text="你好，我是 Alysia。这是一段中文配音测试。",
                scene_id="scene-1",
                language="zh-CN",
                voice="default",
                sample_rate=24000,
                output_path=output,
            )
        )
    )

    info = inspect_wav(output)
    assert result.provider == "sapi"
    assert info["sample_rate"] == 24000
    assert info["channels"] == 1
    assert result.metadata["voice"]
    assert len(result.metadata["word_timings"]) >= 5
    assert result.metadata["word_timings"][-1]["start_sec"] < result.duration_sec


def test_orchestrator_resume_to_audio_ready(tmp_path) -> None:
    orchestrator = AlysiaOrchestrator(make_config(tmp_path / "runs"))
    text_state = asyncio.run(orchestrator.create("为什么AI Agent还不是AGI？"))

    state = asyncio.run(orchestrator.resume(text_state.run_id))
    run_dir = orchestrator.manager.run_dir(state.run_id)

    assert state.milestone == "audio_ready"
    assert state.pipeline_phase == "audio_ready"
    assert state.audio_pipeline_completed is True
    assert (run_dir / "audio/narration.wav").is_file()
    assert (run_dir / "subtitles/subtitles.srt").is_file()
    assert json.loads((run_dir / "audio_qa_report.json").read_text(encoding="utf-8"))["passed"] is True

    voice_state = asyncio.run(orchestrator.voice(state.run_id, force=True))
    assert voice_state.milestone == "voice_ready"
    assert voice_state.audio_pipeline_completed is False
    assert "subtitles_json" not in voice_state.artifacts
    rebuilt = asyncio.run(orchestrator.resume(state.run_id))
    assert rebuilt.milestone == "audio_ready"
    assert rebuilt.audio_pipeline_completed is True


def test_cli_audio_mock(tmp_path) -> None:
    config_path = tmp_path / "config.yaml"
    write_config(config_path, tmp_path / "runs")
    runner = CliRunner()
    environment = {"ALYSIA_CONFIG_FILE": str(config_path)}
    created = runner.invoke(app, ["create", "音频 CLI 测试", "--provider", "mock"], env=environment)
    assert created.exit_code == 0, created.stdout
    run_id = created.stdout.split("run_id:", 1)[1].splitlines()[0].strip()

    resumed = runner.invoke(
        app,
        ["resume", run_id, "--tts-provider", "mock", "--asr-provider", "none"],
        env=environment,
    )
    status = runner.invoke(app, ["audio-status", run_id], env=environment)

    assert resumed.exit_code == 0, resumed.stdout
    assert "audio_ready" in resumed.stdout
    assert status.exit_code == 0, status.stdout
    assert '"audio_pipeline_completed": true' in status.stdout
    saved = RunManager(tmp_path / "runs").load(run_id)
    assert saved.config_snapshot["tts"]["provider"] == "mock"
