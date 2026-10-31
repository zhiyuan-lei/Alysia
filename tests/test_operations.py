from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from alysia.core.config import AlysiaConfig
from alysia.core.run import RunManager
from alysia.learning.memory import MemoryStore
from alysia.operations import ChannelStore, ExperimentManager, ExperimentManagerError, MultiVideoAnalyzer, OperationsService
from alysia.planning import CreatorLoop
from alysia.schemas import (
    ContentFingerprint,
    ExperimentMetric,
    StrategyMemory,
    VideoMetrics,
    VideoPerformanceSnapshot,
)


def _config(tmp_path: Path, *, minimum_group_size: int = 1) -> AlysiaConfig:
    profile = tmp_path / "creator_profile.yaml"
    profile.write_text(
        "\n".join(
            [
                "creator_name: Alysia",
                "channel_goal: 解释 AI 与可靠软件工程",
                "primary_domains: [人工智能, 软件工程, 自主智能体]",
                "target_audience: 中文技术观众",
                "preferred_formats: [科普解释]",
                "originality_requirements: 必须有独立分析",
                "source_quality_requirements: 时效事实必须可追溯",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return AlysiaConfig.model_validate(
        {
            "creator": {"profile_file": str(profile), "require_human_approval": True},
            "trends": {"provider": "mock", "workspace_dir": str(tmp_path / "trends")},
            "planning": {"plans_dir": str(tmp_path / "plans")},
            "learning": {"memory_dir": str(tmp_path / "memory")},
            "operations": {
                "default_channel_id": "main",
                "minimum_experiment_group_size": minimum_group_size,
            },
            "runtime": {"runs_dir": str(tmp_path / "runs"), "retries": 0},
        }
    )


def _snapshot(
    run_id: str,
    *,
    channel_id: str = "main",
    category: str = "人工智能",
    completion: float = 0.5,
    ctr: float = 0.05,
    avg_view: float = 0.55,
    day: int = 0,
    source: str = "manual",
) -> VideoPerformanceSnapshot:
    return VideoPerformanceSnapshot(
        channel_id=channel_id,
        run_id=run_id,
        topic=f"主题 {run_id}",
        category=category,
        published_at=datetime(2026, 1, 1).astimezone() + timedelta(days=day),
        source=source,
        metrics={
            "views": 100 + day,
            "ctr": ctr,
            "completion_rate": completion,
            "avg_view_percentage": avg_view,
            "likes": 10,
            "favorites": 5,
            "comments": 2,
            "followers_gained": 1,
        },
        fingerprint={"title_style": "问题型", "hook_length_sec": 8.0},
    )


def _write_analytics_run(
    config: AlysiaConfig,
    run_id_hint: str,
    *,
    channel_id: str,
    day: int,
    completion: float,
) -> str:
    manager = RunManager(config.runtime.runs_dir)
    state = manager.create(
        f"{channel_id} 主题 {run_id_hint}",
        config.model_dump(mode="json"),
        planning_provenance={"channel_id": channel_id},
    )
    metrics = VideoMetrics(
        run_id=state.run_id,
        collected_at=datetime(2026, 1, 1).astimezone() + timedelta(days=day),
        source="manual",
        views=100 + day,
        likes=10,
        comments=2,
        favorites=5,
        followers_gained=1,
        ctr=0.04 + day * 0.001,
        completion_rate=completion,
        avg_view_percentage=completion,
    )
    fingerprint = ContentFingerprint(
        run_id=state.run_id,
        topic=state.topic,
        title=state.topic,
        title_style="问题型",
        duration_sec=120,
        hook_length_sec=8,
        scene_count=6,
        subtitle_density=1,
        average_subtitle_chars=14,
        narration_chars=500,
        narration_speed_chars_per_sec=4,
        visual_type_distribution={"text": 6},
        number_of_sources=2,
        cover_template="default",
        cover_text_length=8,
        tags=["AI"],
        category="人工智能",
    )
    manager.write_json(state.run_id, "analytics/metrics.json", metrics.model_dump(mode="json"))
    manager.write_json(state.run_id, "analytics/content_fingerprint.json", fingerprint.model_dump(mode="json"))
    state.artifacts.update(
        {
            "analytics_metrics": "analytics/metrics.json",
            "content_fingerprint": "analytics/content_fingerprint.json",
        }
    )
    manager.save(state)
    return state.run_id


def test_multi_video_analysis_detects_trend_fatigue_and_lifecycle() -> None:
    snapshots = [
        _snapshot(f"run_{index}", completion=value, ctr=value / 10, avg_view=value, day=index)
        for index, value in enumerate((0.75, 0.65, 0.55, 0.4))
    ]
    analysis = MultiVideoAnalyzer().analyze("main", snapshots)
    assert analysis.sample_size == 4
    assert analysis.non_testing_sample_size == 4
    assert next(item for item in analysis.trend_changes if item.metric == "completion_rate").direction == "declining"
    assert analysis.fatigue_signals[0].status == "possible"
    assert analysis.topic_lifecycles[0].stage == "declining"
    assert analysis.evidence == [f"run_{index}:manual:{snapshots[index].published_at.isoformat()}" for index in range(4)]


def test_channel_memory_isolated_by_channel_and_refresh_is_idempotent(tmp_path: Path) -> None:
    config = _config(tmp_path)
    _write_analytics_run(config, "a", channel_id="main", day=0, completion=0.6)
    _write_analytics_run(config, "b", channel_id="secondary", day=1, completion=0.4)
    service = OperationsService(config)

    first = service.refresh("main")
    repeated = service.refresh("main")
    secondary = service.refresh("secondary")

    assert first.model_dump(mode="json") == repeated.model_dump(mode="json")
    assert first.channel_state.revision == 1
    assert first.recent_performance.sample_size == 1
    assert secondary.recent_performance.sample_size == 1
    assert first.channel_state.published_topics[0].run_id != secondary.channel_state.published_topics[0].run_id
    assert ChannelStore(config.learning.memory_dir).load_memory("main") is not None


def test_experiment_requires_human_approval_and_assignment_is_idempotent(tmp_path: Path) -> None:
    config = _config(tmp_path)
    manager = ExperimentManager(
        ChannelStore(config.learning.memory_dir),
        MemoryStore(config.learning.memory_dir),
        minimum_group_size=1,
    )
    experiment = manager.create(
        "main",
        hypothesis="缩短开场能提升完播率",
        variable_changed="hook_length_sec",
        control_variables=["topic", "title_style"],
        success_metrics=[ExperimentMetric(metric="completion_rate", minimum_relative_change=0.1)],
    )
    with pytest.raises(ExperimentManagerError, match="已人工批准"):
        manager.assign("main", experiment.id, run_id="run_c", experiment_group="control", source="manual")
    with pytest.raises(ExperimentManagerError, match="人类审核者"):
        manager.approve("main", experiment.id, approved_by="automation")

    manager.approve("main", experiment.id, approved_by="owner")
    first = manager.assign("main", experiment.id, run_id="run_c", experiment_group="control", source="manual")
    repeated = manager.assign("main", experiment.id, run_id="run_c", experiment_group="control", source="manual")
    manager.assign("main", experiment.id, run_id="run_t", experiment_group="treatment", source="manual")
    assert len(first.assignments) == len(repeated.assignments) == 1

    with pytest.raises(ExperimentManagerError, match="source 与实际"):
        manager.evaluate(
            "main",
            experiment.id,
            [_snapshot("run_c", completion=0.4), _snapshot("run_t", completion=0.6, source="mock")],
        )

    result = manager.evaluate(
        "main",
        experiment.id,
        [_snapshot("run_c", completion=0.4), _snapshot("run_t", completion=0.6)],
    )
    assert result.status == "completed"
    assert result.result and result.result.outcome == "positive"
    assert manager.evaluate("main", experiment.id, []).result == result.result


def test_strategy_needs_two_real_experiments_and_mock_does_not_promote(tmp_path: Path) -> None:
    config = _config(tmp_path)
    memory = MemoryStore(config.learning.memory_dir)
    store = ChannelStore(config.learning.memory_dir)
    manager = ExperimentManager(store, memory, minimum_group_size=1)
    now = datetime.now().astimezone()
    strategy = StrategyMemory(
        id="strategy_hook",
        channel_id="main",
        rule="将 hook 控制在 8 秒以内",
        rationale="待实验验证",
        evidence_run_ids=[],
        confidence=0.3,
        applies_to="人工智能",
        source="manual",
        created_at=now,
        updated_at=now,
    )
    memory.save_strategy(strategy)

    for index, source in enumerate(("manual", "manual"), start=1):
        experiment = manager.create(
            "main",
            hypothesis=f"hook 实验 {index}",
            variable_changed="hook_length_sec",
            control_variables=["topic"],
            success_metrics=[ExperimentMetric(metric="completion_rate", minimum_relative_change=0.1)],
            linked_strategy_id=strategy.id,
        )
        manager.approve("main", experiment.id, approved_by="owner")
        manager.assign("main", experiment.id, run_id=f"c{index}", experiment_group="control", source=source)
        manager.assign("main", experiment.id, run_id=f"t{index}", experiment_group="treatment", source=source)
        manager.evaluate(
            "main",
            experiment.id,
            [_snapshot(f"c{index}", completion=0.4), _snapshot(f"t{index}", completion=0.6)],
        )
        current = memory.show_strategy(strategy.id)
        assert current.status == ("supported" if index == 2 else "tentative")
    assert memory.show_strategy(strategy.id).evidence_experiment_ids == [
        item.id for item in store.list_experiments("main")
    ]

    testing = manager.create(
        "main",
        hypothesis="mock 实验",
        variable_changed="hook_length_sec",
        control_variables=["topic"],
        success_metrics=[ExperimentMetric(metric="completion_rate")],
        linked_strategy_id=strategy.id,
    )
    manager.approve("main", testing.id, approved_by="owner")
    manager.assign("main", testing.id, run_id="mock_c", experiment_group="control", source="mock")
    manager.assign("main", testing.id, run_id="mock_t", experiment_group="treatment", source="mock")
    manager.evaluate(
        "main",
        testing.id,
        [_snapshot("mock_c", completion=0.4, source="mock"), _snapshot("mock_t", completion=0.7, source="mock")],
    )
    assert testing.id not in memory.show_strategy(strategy.id).evidence_experiment_ids


def test_dashboard_and_creator_loop_operating_cycle_are_idempotent(tmp_path: Path) -> None:
    config = _config(tmp_path)
    dashboard = OperationsService(config).refresh("main")
    assert dashboard.channel_id == "main"
    assert dashboard.next_recommendations
    assert (tmp_path / "memory" / "channels" / "main" / "dashboard.json").is_file()

    experiments = ExperimentManager(
        ChannelStore(config.learning.memory_dir),
        MemoryStore(config.learning.memory_dir),
        minimum_group_size=1,
    )
    experiment = experiments.create(
        "main",
        hypothesis="缩短开场是否提升前 30 秒留存",
        variable_changed="hook_length_sec",
        control_variables=["topic", "title_style"],
        success_metrics=[ExperimentMetric(metric="completion_rate")],
    )
    experiments.approve("main", experiment.id, approved_by="owner")

    loop = CreatorLoop(config, channel_id="main")
    first = loop.tick()
    state_before = loop.status()
    dashboard_before = (tmp_path / "memory" / "channels" / "main" / "dashboard.json").read_text(encoding="utf-8")
    second = loop.tick()
    dashboard_after = (tmp_path / "memory" / "channels" / "main" / "dashboard.json").read_text(encoding="utf-8")
    assert second.plan_id == first.plan_id
    assert any(slot.linked_experiment == f"experiment:{experiment.id}" for slot in first.slots)
    assert state_before.cycle_phase == "create"
    assert state_before.channel_id == "main"
    assert dashboard_before == dashboard_after

    secondary_loop = CreatorLoop(config, channel_id="secondary")
    secondary_plan = secondary_loop.tick()
    assert secondary_plan.channel_id == "secondary"
    assert secondary_plan.plan_id != first.plan_id
    assert (tmp_path / "plans" / "creator_loop_state.secondary.json").is_file()
