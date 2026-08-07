from __future__ import annotations

from pathlib import Path

from alysia.core.config import AlysiaConfig


def make_config(runs_dir: Path, *, retries: int = 0) -> AlysiaConfig:
    return AlysiaConfig.model_validate(
        {
            "llm": {"provider": "mock"},
            "content": {
                "language": "zh-CN",
                "min_duration_sec": 120,
                "max_duration_sec": 300,
                "default_duration_sec": 180,
            },
            "research": {"provider": "mock", "max_sources": 3},
            "runtime": {"retries": retries, "runs_dir": str(runs_dir)},
        }
    )


def write_config(path: Path, runs_dir: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "llm:",
                "  provider: mock",
                "content:",
                "  language: zh-CN",
                "  min_duration_sec: 120",
                "  max_duration_sec: 300",
                "  default_duration_sec: 180",
                "research:",
                "  provider: mock",
                "  max_sources: 3",
                "runtime:",
                "  retries: 0",
                f"  runs_dir: '{runs_dir.as_posix()}'",
                "",
            ]
        ),
        encoding="utf-8",
    )
