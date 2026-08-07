import asyncio

from alysia.providers.llm import MockLLMProvider
from alysia.schemas.script import Script


def test_mock_llm_returns_schema_validated_script() -> None:
    provider = MockLLMProvider()
    result = asyncio.run(
        provider.generate_structured(
            "writer prompt",
            Script,
            context={
                "topic": "为什么AI Agent还不是AGI？",
                "research": {"sources": [{"id": "source-1"}]},
                "target_duration_sec": 180,
            },
        )
    )

    assert isinstance(result, Script)
    assert result.target_duration_sec == 180
    assert provider.calls == ["Script"]
