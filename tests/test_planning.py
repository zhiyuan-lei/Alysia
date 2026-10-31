from __future__ import annotations

import json
import asyncio
from datetime import date, datetime
from pathlib import Path

import pytest

from alysia.core.config import AlysiaConfig
from alysia.planning import CreatorLoop, PlanningQA, TopicGenerator, TopicScoringEngine
from alysia.planning.board import EditorialBoard
from alysia.planning.novelty import topic_similarity
from alysia.providers.trends import ManualTrendProvider, MockTrendProvider
from alysia.schemas import (
    ContentPlan,
    CreatorProfile,
    PlanSlot,
    RankedTopic,
    TopicCandidate,
    TopicScore,
    TrendItem,
)


def _profile() -> CreatorProfile:
    return CreatorProfile(
        channel_goal="解释 AI 与可靠软件工程",
        primary_domains=["人工智能", "软件工程", "自主智能体"],
        excluded_domains=["医疗诊断"],
        target_audience="中文技术观众",
        preferred_formats=["科普解释", "案例拆解"],
        originality_requirements="必须有独立分析",
        source_quality_requirements="时效事实必须可追溯",
    )


def _config(tmp_path: Path) -> AlysiaConfig:
    profile_path = tmp_path / "creator_profile.yaml"
    profile_path.write_text(
        "\n".join(
            [
                "creator_name: Alysia",
                "channel_goal: 解释 AI 与可靠软件工程",
                "primary_domains: [人工智能, 软件工程, 自主智能体]",
                "excluded_domains: [医疗诊断]",
                "target_audience: 中文技术观众",
                "language: zh-CN",
                "preferred_formats: [科普解释, 案例拆解]",
                "target_duration_sec_range: [120, 300]",
                "publishing_frequency: 每周两条（仅排期）",
                "risk_tolerance: low",
                "originality_requirements: 必须有独立分析",
                "source_quality_requirements: 时效事实必须可追溯",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return AlysiaConfig.model_validate(
        {
            "creator": {"profile_file": str(profile_path), "require_human_approval": True},
            "trends": {"provider": "mock", "workspace_dir": str(tmp_path / "workspace"), "max_items": 50},
            "planning": {"plans_dir": str(tmp_path / "plans"), "candidate_count": 10, "selected_count": 3},
            "creator_loop": {
                "enabled": False,
                "candidate_count": 10,
                "selected_count": 3,
                "horizon_days": 7,
                "require_human_approval": True,
            },
            "learning": {"memory_dir": str(tmp_path / "memory")},
            "runtime": {"runs_dir": str(tmp_path / "runs"), "retries": 0},
        }
    )


def _candidate(topic: str = "AI Agent 的可靠性测试", *, category: str = "人工智能") -> TopicCandidate:
    return TopicCandidate(
        id="topic_test",
        topic=topic,
        angle="用失败案例解释",
        target_audience="中文技术观众",
        why_now="来自可追溯趋势快照",
        source_refs=["trend_test"],
        category=category,
        novelty_score=0.9,
        relevance_score=0.9,
        evidence_score=0.8,
        expected_effort="medium",
        risks=[],
    )


def test_creator_profile_schema() -> None:
    profile = _profile()
    assert profile.creator_name == "Alysia"
    assert profile.target_duration_sec_range == (120, 300)


def test_trend_schema() -> None:
    item = TrendItem(
        id="trend_test",
        topic="AI Agent 可靠性",
        source="公开页面",
        source_kind="manual",
        observed_at=datetime.now().astimezone(),
        popularity_hint=None,
        confidence=0.7,
        freshness_days=None,
    )
    assert item.popularity_hint is None
    assert item.freshness_days is None


def test_manual_trend_import(tmp_path: Path) -> None:
    source = tmp_path / "trends.json"
    source.write_text(
        json.dumps(
            {
                "items": [
                    {
                        "topic": "公开趋势主题",
                        "source": "公开网页",
                        "url": "https://example.com/topic",
                        "keywords": ["AI"],
                        "category": "人工智能",
                    },
                    {
                        "topic": "公开趋势主题",
                        "source": "公开网页",
                        "url": "https://example.com/topic",
                        "confidence": 0.8,
                    },
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    items = ManualTrendProvider(source).gather(max_items=10, freshness_days=7)
    assert len(items) == 1
    assert items[0].source_kind == "manual"
    assert items[0].popularity_hint is None


def test_topic_candidate_generation_mock() -> None:
    trends = MockTrendProvider().gather(max_items=12, freshness_days=7)
    candidates = TopicGenerator().generate(_profile(), trends, [], candidate_count=10)
    assert len(candidates) == 10
    assert all(candidate.source_refs for candidate in candidates)


def test_topic_scoring(tmp_path: Path) -> None:
    config = _config(tmp_path)
    trends = MockTrendProvider().gather(max_items=1, freshness_days=7)
    candidate = TopicGenerator().generate(_profile(), trends, [], candidate_count=1)[0]
    score = TopicScoringEngine(config.planning).score(candidate, _profile(), trends, [])
    assert score.total > 0
    assert set(score.components) >= {"channel_relevance", "freshness", "duplication_penalty"}


def test_duplicate_penalty(tmp_path: Path) -> None:
    config = _config(tmp_path)
    candidate = _candidate()
    engine = TopicScoringEngine(config.planning)
    novel = engine.score(candidate, _profile(), [], [])
    duplicate = engine.score(candidate, _profile(), [], [candidate.topic])
    assert topic_similarity(candidate.topic, candidate.topic) == 1
    assert duplicate.total < novel.total
    assert duplicate.disqualify_reason is not None


def test_excluded_domain_rejection(tmp_path: Path) -> None:
    config = _config(tmp_path)
    candidate = _candidate("AI 医疗诊断自动化", category="人工智能")
    score = TopicScoringEngine(config.planning).score(candidate, _profile(), [], [])
    assert score.total == 0
    assert "excluded_domains" in (score.disqualify_reason or "")


def test_editorial_decision() -> None:
    candidates = [
        _candidate("主题一", category="人工智能"),
        _candidate("主题二", category="软件工程").model_copy(update={"id": "topic_2"}),
        _candidate("主题三", category="自主智能体").model_copy(update={"id": "topic_3"}),
    ]
    scores = [
        TopicScore(candidate_id=item.id, total=90 - index, components={}, explanation="规则评分")
        for index, item in enumerate(candidates)
    ]
    decision, selected = EditorialBoard().decide(candidates, scores, selected_count=3)
    assert decision.selected_topic.candidate.topic == "主题一"
    assert len(selected) == 3


def test_content_plan(tmp_path: Path) -> None:
    plan = CreatorLoop(_config(tmp_path)).tick()
    assert plan.status == "waiting_for_approval"
    assert len(plan.slots) == 3
    assert all(slot.status == "proposed" for slot in plan.slots)


def test_planning_qa(tmp_path: Path) -> None:
    config = _config(tmp_path)
    plan = CreatorLoop(config).tick()
    report = CreatorLoop(config).store.load_qa(plan.plan_id)
    assert report.passed
    assert all(report.checks.values())


def test_mock_trend_not_promoted_to_real_plan() -> None:
    with pytest.raises(ValueError, match="testing=true"):
        ContentPlan(
            plan_id="plan_bad",
            created_at=datetime.now().astimezone(),
            horizon_days=7,
            source="mock",
            provider="MockTrendProvider",
            testing=False,
            source_digest="digest",
            profile_name="Alysia",
            slots=[
                PlanSlot(
                    id="slot_01",
                    planned_date=date.today(),
                    topic_candidate_id="topic_test",
                    topic="测试",
                    category="人工智能",
                    priority=1,
                )
            ],
        )


def test_approval_gate(tmp_path: Path) -> None:
    loop = CreatorLoop(_config(tmp_path))
    plan = loop.tick()
    assert not list((tmp_path / "runs").glob("*/run_state.json"))
    approved, run = loop.approve(plan.plan_id, plan.slots[0].id)
    assert approved.slots[0].status == "approved"
    assert run.current_stage.value == "created"


def test_approved_slot_creates_traceable_run(tmp_path: Path) -> None:
    loop = CreatorLoop(_config(tmp_path))
    plan = loop.tick()
    _, run = loop.approve(plan.plan_id, "slot_01")
    payload = loop.run_manager.read_json(run.run_id, "input.json")
    provenance = payload["planning_provenance"]
    assert provenance["plan_id"] == plan.plan_id
    assert provenance["slot_id"] == "slot_01"
    assert provenance["testing"] is True
    assert "Research" in provenance["research_handoff"]
    assert run.creator_job_id
    assert provenance["creator_job_id"] == run.creator_job_id
    creator_job = loop.creator_jobs.load(run.creator_job_id)
    assert creator_job.run_id == run.run_id
    assert creator_job.testing is True


def test_creator_loop_tick_idempotent(tmp_path: Path) -> None:
    loop = CreatorLoop(_config(tmp_path))
    first = loop.tick()
    loop.approve(first.plan_id, "slot_01")
    second = loop.tick()
    assert second.plan_id == first.plan_id
    assert len(list((tmp_path / "plans").glob("plan_*/content_plan.json"))) == 1


def test_creator_loop_run_requires_approval(tmp_path: Path) -> None:
    loop = CreatorLoop(_config(tmp_path))
    plan = loop.tick()
    with pytest.raises(RuntimeError, match="已批准"):
        asyncio.run(loop.start(plan.plan_id, "slot_01"))
