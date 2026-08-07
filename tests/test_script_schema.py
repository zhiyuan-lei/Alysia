import pytest
from pydantic import ValidationError

from alysia.schemas.script import Script, ScriptSection


def make_section(identifier: str) -> ScriptSection:
    return ScriptSection(
        id=identifier,
        purpose="说明",
        narration="这是可口播的中文内容。",
        key_visual_hint="文字画面",
    )


def test_script_schema_renders_markdown() -> None:
    script = Script(
        title="标题",
        hook="开场问题",
        thesis="核心论点",
        target_audience="中文观众",
        target_duration_sec=180,
        sections=[make_section("section-1")],
        conclusion="明确结论",
    )

    assert "## Hook" in script.to_markdown()
    assert "明确结论" in script.to_markdown()


def test_script_section_ids_must_be_unique() -> None:
    with pytest.raises(ValidationError):
        Script(
            title="标题",
            hook="开场问题",
            thesis="核心论点",
            target_audience="中文观众",
            target_duration_sec=180,
            sections=[make_section("same"), make_section("same")],
            conclusion="明确结论",
        )
