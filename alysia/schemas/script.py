from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class ScriptSection(BaseModel):
    id: str = Field(min_length=1)
    purpose: str = Field(min_length=1)
    narration: str = Field(min_length=1)
    key_visual_hint: str = Field(min_length=1)
    source_refs: list[str] = Field(default_factory=list)
    claim_refs: list[str] = Field(default_factory=list)


class Script(BaseModel):
    title: str = Field(min_length=1)
    hook: str = Field(min_length=1)
    thesis: str = Field(min_length=1)
    target_audience: str = Field(min_length=1)
    target_duration_sec: int = Field(ge=30, le=3600)
    sections: list[ScriptSection] = Field(min_length=1)
    conclusion: str = Field(min_length=1)
    source_refs: list[str] = Field(default_factory=list)

    @field_validator("sections")
    @classmethod
    def section_ids_are_unique(cls, sections: list[ScriptSection]) -> list[ScriptSection]:
        identifiers = [section.id for section in sections]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("script section id 必须唯一")
        return sections

    def to_markdown(self) -> str:
        sections = "\n\n".join(
            f"## {section.id} · {section.purpose}\n\n{section.narration}\n\n"
            f"画面提示：{section.key_visual_hint}\n\n"
            f"来源引用：{', '.join(section.source_refs) or '无'}\n\n"
            f"事实引用：{', '.join(section.claim_refs) or '无'}"
            for section in self.sections
        )
        return (
            f"# {self.title}\n\n"
            f"> 目标观众：{self.target_audience}  \n"
            f"> 目标时长：{self.target_duration_sec} 秒\n\n"
            f"## Hook\n\n{self.hook}\n\n"
            f"## 核心论点\n\n{self.thesis}\n\n"
            f"{sections}\n\n"
            f"## 结论\n\n{self.conclusion}\n"
        )
