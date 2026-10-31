from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path

import pytest

from alysia.analytics import ContentFingerprintBuilder, PerformanceAnalyzer, derive_metrics
from alysia.core.config import CoverConfig, VideoConfig
from alysia.core.orchestrator import AlysiaOrchestrator
from alysia.learning.lessons import LessonExtractor
from alysia.learning.memory import MemoryStore
from alysia.learning.pipeline import LearningPipeline
from alysia.learning.planner import NextExperimentPlanner
from alysia.learning.strategy import StrategyEngine
from alysia.providers.analytics import ManualAnalyticsProvider
from alysia.schemas import (
    ContentFingerprint,
    LessonCandidate,
    PerformanceAnalysis,
    RetentionPoint,
    VideoMetrics,
)
from tests.helpers import make_config


def _metrics(run_id: str = "run-1", *, source: str = "manual") -> VideoMetrics:
    return VideoMetrics(
        run_id=run_id,
        platform="bilibili",
        collected_at=datetime.now().astimezone(),
        source=source,
        impressions=10_000,
        views=420,
        likes=28,
        comments=7,
        favorites=19,
        shares=4,
        followers_gained=3,
        avg_view_duration_sec=31.2,
        avg_view_percentage=0.38,
        completion_rate=0.31,
        ctr=0.042,
        retention_points=[
            RetentionPoint(second=0, percentage=1),
            RetentionPoint(second=30, percentage=0.58),
            RetentionPoint(second=60, percentage=0.35),
        ],
    )


def _fingerprint(run_id: str = "run-1") -> ContentFingerprint:
    return ContentFingerprint(
        run_id=run_id,
        topic="为什么 AI Agent 还不是 AGI？",
        title="为什么 AI Agent 还不是 AGI",
        title_style="问题型",
        duration_sec=82,
        hook_length_sec=12,
        scene_count=3,
        subtitle_density=3.2,
        average_subtitle_chars=14,
        narration_chars=300,
        narration_speed_chars_per_sec=3.65,
        visual_type_distribution={"title": 1, "diagram": 1, "text": 1},
        number_of_sources=2,
        cover_template="existing_publish_cover",
        cover_text_length=18,
        tags=["AI Agent", "AGI"],
        category="科技",
    )


def _analysis(metrics: VideoMetrics | None = None, fingerprint: ContentFingerprint | None = None) -> PerformanceAnalysis:
    metrics = metrics or _metrics()
    fingerprint = fingerprint or _fingerprint(metrics.run_id)
    return PerformanceAnalyzer().analyze(metrics, derive_metrics(metrics), fingerprint, {})


def _review_ready_run(tmp_path: Path) -> tuple[AlysiaOrchestrator, object]:
    config = make_config(tmp_path / "runs")
    config.video = VideoConfig(renderer="mock", width=640, height=360, fps=30)
    config.publish.cover = CoverConfig(width=640, height=360, format="png")
    orchestrator = AlysiaOrchestrator(config)
    state = asyncio.run(orchestrator.create("为什么AI Agent还不是AGI？"))
    state = asyncio.run(orchestrator.resume(state.run_id))
    state = asyncio.run(orchestrator.render(state.run_id))
    state = asyncio.run(orchestrator.package(state.run_id))
    state = asyncio.run(orchestrator.publish_check(state.run_id))
    return orchestrator, state


def _write_metrics(path: Path, run_id: str, *, source: str = "manual") -> None:
    path.write_text(_metrics(run_id, source=source).model_dump_json(indent=2), encoding="utf-8")


def test_metrics_schema() -> None:
    partial = VideoMetrics(
        run_id="run-1",
        platform="bilibili",
        collected_at=datetime.now().astimezone(),
    )
    assert partial.views is None
    assert partial.retention_points == []
    with pytest.raises(ValueError, match="严格递增"):
        VideoMetrics(
            run_id="run-1",
            collected_at=datetime.now().astimezone(),
            retention_points=[
                RetentionPoint(second=30, percentage=0.5),
                RetentionPoint(second=10, percentage=0.8),
            ],
        )


def test_derived_metrics() -> None:
    derived = derive_metrics(_metrics())
    assert derived.like_rate.value == pytest.approx(28 / 420, abs=1e-6)
    assert derived.engagement_rate.formula == "(likes + comments + favorites + shares) / views"
    partial = VideoMetrics(run_id="run-1", collected_at=datetime.now().astimezone(), views=100)
    assert derive_metrics(partial).like_rate.value is None
    assert derive_metrics(partial).like_rate.missing_inputs == ["likes"]


def test_content_fingerprint(tmp_path: Path) -> None:
    orchestrator, state = _review_ready_run(tmp_path)
    fingerprint = ContentFingerprintBuilder(orchestrator.manager).build(state)
    assert fingerprint.topic == state.topic
    assert fingerprint.scene_count == 3
    assert fingerprint.narration_chars > 0
    assert fingerprint.duration_sec > 0
    assert sum(fingerprint.visual_type_distribution.values()) == fingerprint.scene_count


def test_manual_analytics_import(tmp_path: Path) -> None:
    json_path = tmp_path / "metrics.json"
    _write_metrics(json_path, "run-1")
    assert ManualAnalyticsProvider().load("run-1", json_path).views == 420

    csv_path = tmp_path / "metrics.csv"
    csv_path.write_text(
        "run_id,platform,collected_at,source,views,ctr\n"
        f"run-1,bilibili,{datetime.now().astimezone().isoformat()},manual,420,0.042\n",
        encoding="utf-8",
    )
    assert ManualAnalyticsProvider().load("run-1", csv_path).ctr == pytest.approx(0.042)


def test_analysis_engine() -> None:
    analysis = _analysis()
    assert "completion_rate=0.31" in analysis.facts
    assert analysis.hypotheses
    assert all(item.confidence == "low" for item in analysis.hypotheses)
    assert "相关性" in analysis.hypotheses[0].caveat


def test_lesson_extractor() -> None:
    metrics = _metrics()
    fingerprint = _fingerprint()
    lessons = LessonExtractor().extract(_analysis(metrics, fingerprint), metrics, fingerprint)
    assert lessons
    assert all("可能" in item.statement or "值得" in item.statement for item in lessons)
    assert all(item.confidence < 0.5 for item in lessons)


def test_memory_persistence(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "memory")
    candidate = LessonCandidate(
        statement="问题型标题可能与点击率相关",
        category="packaging",
        scope="科技",
        supporting_metrics={"ctr": 0.04},
        confidence=0.3,
    )
    lesson = store.upsert_lesson(candidate, "run-1", "manual")
    assert store.show_lesson(lesson.id).statement == candidate.statement
    assert lesson.id in json.loads(store.index_path.read_text(encoding="utf-8"))["lessons"]


def test_memory_confidence_update(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "memory")
    candidate = LessonCandidate(
        statement="问题型标题可能与点击率相关",
        category="packaging",
        scope="科技",
        supporting_metrics={"ctr": 0.04},
        confidence=0.3,
    )
    first = store.upsert_lesson(candidate, "run-1", "manual")
    same = store.upsert_lesson(candidate, "run-1", "manual")
    second = store.upsert_lesson(candidate, "run-2", "manual")
    assert same.confidence == first.confidence
    assert second.confidence > first.confidence
    assert second.status == "supported"
    counter = candidate.model_copy(update={"direction": "contradicts", "supporting_metrics": {"ctr": 0.01}})
    lowered = store.upsert_lesson(counter, "run-3", "manual")
    assert lowered.confidence < second.confidence
    assert lowered.status == "tentative"
    assert lowered.counter_evidence_run_ids == ["run-3"]


def test_strategy_recommendation() -> None:
    metrics = _metrics()
    fingerprint = _fingerprint()
    recommendations = StrategyEngine().recommend(_analysis(metrics, fingerprint), metrics, fingerprint, [])
    assert recommendations
    assert all(item.evidence and item.confidence for item in recommendations)
    assert all("3 条" in item.test_plan for item in recommendations)


def test_next_experiment() -> None:
    metrics = _metrics()
    fingerprint = _fingerprint()
    strategies = StrategyEngine().recommend(_analysis(metrics, fingerprint), metrics, fingerprint, [])
    proposal = NextExperimentPlanner().propose(fingerprint, strategies)
    assert proposal.topic != fingerprint.topic
    assert proposal.variable_to_change
    assert "完播率" in proposal.success_metrics


def test_learning_pipeline_idempotent(tmp_path: Path) -> None:
    orchestrator, state = _review_ready_run(tmp_path)
    metrics_path = tmp_path / "metrics.json"
    _write_metrics(metrics_path, state.run_id)
    pipeline = LearningPipeline(orchestrator.manager, tmp_path / "memory")
    pipeline.import_metrics(state.run_id, metrics_path)
    pipeline.analyze(state.run_id)
    first = pipeline.learn(state.run_id)
    before = (orchestrator.manager.run_dir(state.run_id) / first.artifacts["lessons"]).read_text(encoding="utf-8")
    second = pipeline.learn(state.run_id)
    after = (orchestrator.manager.run_dir(state.run_id) / second.artifacts["lessons"]).read_text(encoding="utf-8")
    assert before == after
    assert second.milestone == "memory_updated"


def test_mock_data_not_promoted_as_real(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "memory")
    candidate = LessonCandidate(
        statement="测试数据只能形成 tentative lesson",
        category="testing",
        scope="科技",
        supporting_metrics={"ctr": 0.9},
        confidence=0.9,
    )
    lesson = store.upsert_lesson(candidate, "mock-1", "mock")
    lesson = store.upsert_lesson(candidate, "mock-2", "mock")
    assert lesson.source == "testing"
    assert lesson.status == "tentative"
    assert lesson.confidence <= 0.2
