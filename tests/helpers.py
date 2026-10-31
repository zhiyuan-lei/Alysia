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
            "tts": {"provider": "mock", "allow_test_tone": True},
            "publishing": {
                "provider": "mock",
                "require_approval": True,
                "save_credentials": False,
                "workspace_dir": str(runs_dir.parent / "publishing"),
            },
            "feedback": {"provider": "manual"},
            "learning": {"memory_dir": str(runs_dir.parent / "memory")},
            "identity": {"directory": str(runs_dir.parent / "identity")},
            "knowledge": {"root_dir": str(runs_dir.parent / "knowledge")},
            "planning": {"plans_dir": str(runs_dir.parent / "plans")},
            "workflow": {"recipe_dir": str(runs_dir.parent / "memory" / "workflows")},
            # 视觉任务队列与生产缓存默认落在仓库 workspace/ 下。测试必须和本机
            # 真实队列隔离，否则并发跑两个 pytest 会互相抢占用中的 GPU job。
            "visual_generation": {
                "cache_dir": str(runs_dir.parent / "visual_cache"),
                "queue_dir": str(runs_dir.parent / "visual_queue"),
            },
            "production": {"cache_dir": str(runs_dir.parent / "production_cache")},
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
                "tts:",
                "  provider: mock",
                "  allow_test_tone: true",
                "publishing:",
                "  provider: mock",
                "  require_approval: true",
                "  save_credentials: false",
                f"  workspace_dir: '{(runs_dir.parent / 'publishing').as_posix()}'",
                "feedback:",
                "  provider: manual",
                "learning:",
                f"  memory_dir: '{(runs_dir.parent / 'memory').as_posix()}'",
                "identity:",
                f"  directory: '{(runs_dir.parent / 'identity').as_posix()}'",
                "knowledge:",
                f"  root_dir: '{(runs_dir.parent / 'knowledge').as_posix()}'",
                "planning:",
                f"  plans_dir: '{(runs_dir.parent / 'plans').as_posix()}'",
                "runtime:",
                "  retries: 0",
                f"  runs_dir: '{runs_dir.as_posix()}'",
                "",
            ]
        ),
        encoding="utf-8",
    )
