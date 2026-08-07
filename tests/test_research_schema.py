from datetime import datetime

import pytest
from pydantic import ValidationError

from alysia.schemas.research import ResearchResult, Source


def test_research_schema_and_markdown() -> None:
    result = ResearchResult(
        topic="测试主题",
        summary="用于测试的摘要。",
        key_points=["关键点"],
        sources=[
            Source(
                id="s1",
                title="示例",
                url="https://example.invalid/source",
                publisher="测试",
                domain="example.invalid",
                retrieved_at=datetime.now().astimezone(),
                note="离线测试",
            )
        ],
    )

    assert "# 调研：测试主题" in result.to_markdown()
    assert "[s1]" in result.to_markdown()


def test_research_source_rejects_non_http_url() -> None:
    with pytest.raises(ValidationError):
        Source(
            id="s1",
            title="错误地址",
            url="not-a-url",
            publisher="测试",
            domain="invalid",
            retrieved_at=datetime.now().astimezone(),
        )
