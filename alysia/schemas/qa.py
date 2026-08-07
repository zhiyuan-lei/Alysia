from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class QAIssue(BaseModel):
    code: str = Field(min_length=1)
    severity: Literal["error", "warning"]
    message: str = Field(min_length=1)


class TextQAReport(BaseModel):
    passed: bool
    topic_consistent: bool
    has_hook: bool
    has_conclusion: bool
    storyboard_covers_sections: bool
    duration_in_range: bool
    issues: list[QAIssue] = Field(default_factory=list)
    disclaimer: str = "启发式文本检查不等同于事实核查。"

    @property
    def errors(self) -> list[QAIssue]:
        return [issue for issue in self.issues if issue.severity == "error"]

    @property
    def warnings(self) -> list[QAIssue]:
        return [issue for issue in self.issues if issue.severity == "warning"]
