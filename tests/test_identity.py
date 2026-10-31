from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from alysia.core.config import AlysiaConfig
from alysia.core.run import RunManager
from alysia.identity import (
    ContentStyleMemoryBuilder,
    IdentityCardGenerator,
    IdentityEvolutionService,
    IdentityStore,
    NarrativeLibrary,
    PromptContextBuilder,
    StyleConsistencyChecker,
)
from alysia.schemas import (
    BrandVoiceProfile,
    CreatorIdentity,
    IdentityChangeProposal,
    Script,
    Storyboard,
    VisualIdentity,
)


def _identity(now: datetime | None = None) -> CreatorIdentity:
    timestamp = now or datetime(2026, 8, 7, 21, 30).astimezone()
    return CreatorIdentity(
        creator_name="Alysia",
        mission_statement="用清晰、可验证的方法解释复杂技术",
        channel_purpose="制作面向中文技术观众的 AI 与软件工程内容",
        content_philosophy="证据优先，明确区分事实与推断",
        target_audience="对 AI 与工程实践感兴趣的中文观众",
        expertise_domains=["人工智能", "软件工程", "自主智能体"],
        excluded_topics=["违法活动", "侵犯隐私"],
        communication_style=BrandVoiceProfile(
            tone=["理性", "清晰", "克制"],
            sentence_style="短句为主，复杂概念分步解释",
            vocabulary_preferences=["证据", "验证", "边界"],
            forbidden_phrases=["震惊", "颠覆一切", "百分百"],
            explanation_depth="medium",
            humor_level="low",
            technical_level="medium",
            opening_style="问题驱动",
            conclusion_style="总结证据、边界与下一步",
        ),
        visual_identity=VisualIdentity(
            color_theme={"background": "#0A1126", "accent": "#5BECFF"},
            typography={"heading": "Microsoft YaHei Bold", "body": "Microsoft YaHei"},
            cover_layout="left_accent_v1",
            thumbnail_rules=["标题不超过三行", "保持高对比度"],
            scene_preferences=["title", "diagram", "text", "chart", "code"],
        ),
        narrative_patterns=["problem_solution", "deep_explanation"],
        values=["准确", "透明", "尊重观众"],
        disclosure_policy="明确披露 Alysia 是 AI 视频创作系统，不是真人创作者。",
        version=1,
        created_at=timestamp,
        updated_at=timestamp,
    )


def _script() -> Script:
    return Script.model_validate(
        {
            "title": "为什么 AI Agent 还不是 AGI？",
            "hook": "Agent 会调用工具，就已经是 AGI 了吗？",
            "thesis": "需要用可验证标准区分任务系统与通用智能。",
            "target_audience": "对 AI 与工程实践感兴趣的中文观众",
            "target_duration_sec": 120,
            "sections": [
                {
                    "id": "section-1",
                    "purpose": "解释差异",
                    "narration": "先看证据，再解释能力边界。Agent 能执行任务，但可靠迁移仍需验证。",
                    "key_visual_hint": "Agent 与 AGI 对比图",
                    "source_refs": ["source-1"],
                }
            ],
            "conclusion": "结论是：先验证可靠性，再讨论更通用的能力。",
            "source_refs": ["source-1"],
        }
    )


def _storyboard() -> Storyboard:
    return Storyboard.model_validate(
        {
            "title": "为什么 AI Agent 还不是 AGI？",
            "target_duration_sec": 120,
            "scenes": [
                {
                    "id": "scene-1",
                    "section_id": "section-1",
                    "duration_sec": 120,
                    "narration": "先看证据，再解释能力边界。",
                    "visual_type": "diagram",
                    "visual_prompt": "Agent 与 AGI 对比图",
                    "screen_text": "能力边界",
                    "transition": "fade",
                    "source_refs": ["source-1"],
                }
            ],
        }
    )


def test_creator_identity_schema() -> None:
    identity = _identity()
    assert identity.creator_name == "Alysia"
    assert identity.version == 1
    assert identity.disclosure_policy


def test_identity_versioning(tmp_path: Path) -> None:
    store = IdentityStore(tmp_path / "identity", version_control=True)
    first = store.save_initial(_identity())
    changed = first.model_copy(update={"mission_statement": "解释复杂技术并公开证据边界"})
    second = store.save_new_version(changed)

    assert second.version == 2
    assert store.load_current().version == 2
    assert [item.version for item in store.list_history()] == [1, 2]
    assert (tmp_path / "identity" / "history" / "creator_identity.v0001.yaml").is_file()


def test_brand_voice_schema() -> None:
    voice = _identity().communication_style
    assert voice.technical_level == "medium"
    assert "震惊" in voice.forbidden_phrases


def test_style_consistency_checker() -> None:
    report = StyleConsistencyChecker().check(
        run_id="run_demo",
        script=_script(),
        storyboard=_storyboard(),
        title="为什么 AI Agent 还不是 AGI？",
        cover_metadata={"primary_title": "为什么 AI Agent 还不是 AGI？", "category": "科技"},
        identity=_identity(),
    )
    assert report.score >= 0.8
    assert not report.violations
    assert report.confidence > 0


def test_narrative_library() -> None:
    root = Path(__file__).parents[1] / "skills" / "narrative"
    frameworks = NarrativeLibrary(root).load_all()
    assert {item.id for item in frameworks} == {
        "deep_explanation",
        "experiment_report",
        "myth_breaking",
        "problem_solution",
        "technology_evolution",
    }
    assert all(item.structure and item.limitations for item in frameworks)


def test_prompt_context_builder() -> None:
    artifact = PromptContextBuilder().build(
        base_task_prompt="撰写技术解释脚本",
        identity=_identity(),
        relevant_strategies=[{"rule": "开场八秒内提出核心问题", "status": "tentative"}],
        experiment={"id": "experiment_1", "status": "approved", "variable_changed": "hook_length_sec"},
    )
    assert artifact.identity_version == 1
    assert "Creator Identity" in artifact.rendered_context
    assert "tentative" in artifact.rendered_context
    assert len(artifact.input_digest) == 64


def test_identity_change_requires_approval(tmp_path: Path) -> None:
    store = IdentityStore(tmp_path / "identity", version_control=True)
    store.save_initial(_identity())
    service = IdentityEvolutionService(store, require_approval=True)
    proposal = service.propose(
        proposed_change={"mission_statement": "更强调工程验证"},
        reason="候选风格调整",
        evidence=["run:demo"],
        expected_effect="提升定位清晰度",
        risk="可能缩窄选题范围",
    )
    assert isinstance(proposal, IdentityChangeProposal)
    assert proposal.status == "pending"
    assert store.load_current().version == 1
    with pytest.raises(ValueError, match="人工"):
        service.approve(proposal.id, approved_by="automation")


def test_visual_identity_config() -> None:
    config = AlysiaConfig.model_validate(
        {"visual_identity": {"template_version": "v2"}, "identity": {"enabled": True}}
    )
    assert config.visual_identity.template_version == "v2"
    assert config.identity.require_approval is True


def test_identity_card_no_false_identity() -> None:
    card = IdentityCardGenerator().render(_identity())
    assert "AI 视频创作系统" in card
    assert "不是真人" in card
    assert "我的童年" not in card
    assert "我出生于" not in card


def test_style_check_idempotent(tmp_path: Path) -> None:
    config = AlysiaConfig.model_validate(
        {
            "runtime": {"runs_dir": str(tmp_path / "runs")},
            "learning": {"memory_dir": str(tmp_path / "memory")},
            "identity": {"directory": str(tmp_path / "identity")},
        }
    )
    manager = RunManager(config.runtime.runs_dir)
    state = manager.create("为什么 AI Agent 还不是 AGI？", config.model_dump(mode="json"))
    manager.write_json(state.run_id, "script.json", _script().model_dump(mode="json"))
    manager.write_json(state.run_id, "storyboard.json", _storyboard().model_dump(mode="json"))
    manager.write_json(
        state.run_id,
        "publish/metadata.json",
        {"primary_title": "为什么 AI Agent 还不是 AGI？", "category": "科技"},
    )
    state.artifacts.update(
        {"script": "script.json", "storyboard": "storyboard.json", "publish_metadata": "publish/metadata.json"}
    )
    manager.save(state)
    store = IdentityStore(config.identity.directory, version_control=True)
    store.save_initial(_identity())
    builder = ContentStyleMemoryBuilder(config)
    checker = StyleConsistencyChecker()

    first = checker.check_run(config, state.run_id, identity=store.load_current(), style_memory=builder.refresh("main"))
    path = manager.run_dir(state.run_id) / "qa" / "style_consistency_report.json"
    before = path.read_bytes()
    second = checker.check_run(config, state.run_id, identity=store.load_current(), style_memory=builder.refresh("main"))

    assert first == second
    assert before == path.read_bytes()
    assert json.loads(before)["run_id"] == state.run_id
