from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path

import pytest
from PIL import Image

from alysia.agents import DescriptionAgent, TagAgent, TitleAgent
from alysia.core.config import CoverConfig, VideoConfig
from alysia.core.orchestrator import AlysiaOrchestrator
from alysia.providers.cover import TemplateCoverGenerator
from alysia.schemas import (
    PublishPackage,
    ResearchResult,
    Scene,
    Script,
    ScriptSection,
    Source,
    Storyboard,
)
from tests.helpers import make_config


def _content() -> tuple[ResearchResult, Script, Storyboard]:
    research = ResearchResult(
        topic="为什么AI Agent还不是AGI？",
        summary="现有智能体具备工具使用能力，但仍缺少可靠的长期自主性。",
        key_points=["工具使用不等于通用智能", "可靠性与持续学习仍是关键差距"],
        sources=[
            Source(
                id="source-1",
                title="可信来源",
                url="https://example.com/agent",
                publisher="Example",
                domain="example.com",
                retrieved_at=datetime.now().astimezone(),
            )
        ],
    )
    script = Script(
        title="为什么AI Agent还不是AGI？",
        hook="Agent 已经会调用工具，但这是否等于通用智能？",
        thesis="会执行任务只是起点，可靠规划、验证和持续学习才是关键。",
        target_audience="关注人工智能的科技观众",
        target_duration_sec=120,
        sections=[
            ScriptSection(
                id="section-1",
                purpose="厘清概念",
                narration="AI Agent 可以调用工具完成任务，但能力边界仍然明显。",
                key_visual_hint="Agent 与 AGI 对比",
                source_refs=["source-1"],
            ),
            ScriptSection(
                id="section-2",
                purpose="解释差距",
                narration="长期规划、可靠验证与跨场景迁移仍然是主要差距。",
                key_visual_hint="差距流程图",
                source_refs=["source-1"],
            ),
        ],
        conclusion="判断智能系统不能只看单次演示，还要看长期可靠表现。",
        source_refs=["source-1"],
    )
    storyboard = Storyboard(
        title=script.title,
        target_duration_sec=120,
        scenes=[
            Scene(
                id="scene-1",
                section_id="section-1",
                duration_sec=60,
                narration=script.sections[0].narration,
                visual_type="title",
                screen_text="Agent ≠ AGI",
                source_refs=["source-1"],
            ),
            Scene(
                id="scene-2",
                section_id="section-2",
                duration_sec=60,
                narration=script.sections[1].narration,
                visual_type="diagram",
                screen_text="关键差距",
                source_refs=["source-1"],
            ),
        ],
    )
    return research, script, storyboard


@pytest.fixture(scope="module")
def packaged_run(tmp_path_factory):
    root = tmp_path_factory.mktemp("publish-pipeline")
    config = make_config(root / "runs")
    config.video = VideoConfig(renderer="mock", width=640, height=360, fps=30)
    config.publish.cover = CoverConfig(width=640, height=360, format="png")
    orchestrator = AlysiaOrchestrator(config)
    state = asyncio.run(orchestrator.create("为什么AI Agent还不是AGI？"))
    state = asyncio.run(orchestrator.resume(state.run_id))
    state = asyncio.run(orchestrator.render(state.run_id))
    state = asyncio.run(orchestrator.package(state.run_id))
    return orchestrator, state


def test_publish_schema() -> None:
    package = PublishPackage(
        title="为什么AI Agent还不是AGI",
        description="简介\n\n## 参考资料\n\n- 来源",
        tags=["AI Agent", "AGI"],
        category="科技",
        cover_path=Path("publish/cover.png"),
        video_path=Path("output/final.mp4"),
        duration_sec=120,
        language="zh-CN",
        source_links=["https://example.com/agent"],
        generated_at=datetime.now().astimezone(),
    )
    assert package.qa_status == "pending"
    assert package.tags == ["AI Agent", "AGI"]


def test_title_generation_mock() -> None:
    _, script, storyboard = _content()
    result = TitleAgent(candidate_count=5).run(script.title, script, storyboard)
    assert len(result.candidates) == 5
    assert {candidate.style for candidate in result.candidates} == {"科普型", "问题型", "冲突型", "数字型", "悬念型"}
    assert all(candidate.risk == "无" for candidate in result.candidates)
    assert "AI Agent" in result.primary_title


def test_description_generation() -> None:
    research, script, storyboard = _content()
    description = DescriptionAgent().run(script, storyboard, research, 120, "仅供科普。")
    assert description.splitlines()[0] == script.thesis
    assert "## 章节时间轴" in description
    assert "https://example.com/agent" in description
    assert "## 免责声明" in description


def test_tag_generation() -> None:
    _, script, _ = _content()
    tags = TagAgent(max_count=10).run(script.title, script)
    assert "AI Agent" in tags
    assert "AGI" in tags
    assert len(tags) == len({tag.casefold() for tag in tags})
    assert not {"爆款", "必看", "震惊"} & set(tags)


def test_cover_template(tmp_path) -> None:
    output = tmp_path / "cover.png"
    generator = TemplateCoverGenerator(CoverConfig(width=1280, height=720, format="png"))
    generator.generate(output, title="为什么AI Agent还不是AGI", subtitle="能力与目标之间的差距")
    with Image.open(output) as image:
        assert image.size == (1280, 720)
        assert image.format == "PNG"


def test_publish_package_creation(packaged_run) -> None:
    orchestrator, state = packaged_run
    run_dir = orchestrator.manager.run_dir(state.run_id)
    assert state.milestone == "package_ready"
    for relative in (
        "publish/cover.png",
        "publish/title.txt",
        "publish/description.md",
        "publish/tags.json",
        "publish/metadata.json",
        "publish/publish_package.json",
    ):
        assert (run_dir / relative).is_file()


def test_publish_qa(packaged_run) -> None:
    orchestrator, state = packaged_run
    reviewed = asyncio.run(orchestrator.publish_check(state.run_id))
    report = orchestrator.manager.read_json(reviewed.run_id, reviewed.artifacts["publish_qa_report"])
    assert reviewed.milestone == "review_ready"
    assert reviewed.review_ready is True
    assert report["passed"] is True
    assert report["errors"] == []


def test_resume_package_stage(tmp_path) -> None:
    config = make_config(tmp_path / "runs")
    config.video = VideoConfig(renderer="mock", width=640, height=360, fps=30)
    config.publish.cover = CoverConfig(width=640, height=360, format="png")
    orchestrator = AlysiaOrchestrator(config)
    state = asyncio.run(orchestrator.create("为什么AI Agent还不是AGI？"))
    state = asyncio.run(orchestrator.resume(state.run_id))
    state = asyncio.run(orchestrator.render(state.run_id))
    resumed = asyncio.run(orchestrator.resume(state.run_id))
    assert resumed.milestone == "package_ready"
    assert resumed.package_pipeline_completed is True
    assert orchestrator.manager.artifact_exists(resumed, "publish_package")
