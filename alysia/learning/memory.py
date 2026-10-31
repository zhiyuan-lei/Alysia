from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

from alysia.schemas import EpisodeMemory, LessonCandidate, LessonMemory, PublishEpisodeMemory, StrategyMemory


class MemoryStore:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.episodes_dir = self.root / "episodes"
        self.lessons_dir = self.root / "lessons"
        self.strategies_dir = self.root / "strategies"
        self.publish_episodes_dir = self.root / "publish_episodes"
        for directory in (self.episodes_dir, self.lessons_dir, self.strategies_dir, self.publish_episodes_dir):
            directory.mkdir(parents=True, exist_ok=True)
        if not self.index_path.is_file():
            self._write_json(
                self.index_path,
                {"episodes": [], "publish_episodes": [], "lessons": [], "strategies": [], "updated_at": None},
            )
        else:
            index = json.loads(self.index_path.read_text(encoding="utf-8"))
            if "publish_episodes" not in index:
                index["publish_episodes"] = []
                self._write_json(self.index_path, index)

    @property
    def index_path(self) -> Path:
        return self.root / "index.json"

    def record_episode(self, episode: EpisodeMemory) -> Path:
        path = self.episodes_dir / f"{episode.run_id}.json"
        self._write_json(path, episode.model_dump(mode="json"))
        self._index_add("episodes", episode.run_id)
        return path

    def record_publish_episode(self, episode: PublishEpisodeMemory) -> Path:
        path = self.publish_episodes_dir / f"{episode.run_id}.json"
        if path.is_file():
            existing = PublishEpisodeMemory.model_validate_json(path.read_text(encoding="utf-8"))
            if existing.feedback_digest == episode.feedback_digest:
                return path
        self._write_json(path, episode.model_dump(mode="json"))
        self._index_add("publish_episodes", episode.run_id)
        return path

    def list_publish_episodes(self) -> list[PublishEpisodeMemory]:
        return [
            PublishEpisodeMemory.model_validate_json(path.read_text(encoding="utf-8"))
            for path in sorted(self.publish_episodes_dir.glob("*.json"))
        ]

    def upsert_lesson(self, candidate: LessonCandidate, run_id: str, source: str) -> LessonMemory:
        lesson_id = self._stable_id("lesson", candidate.category, candidate.scope, candidate.statement)
        path = self.lessons_dir / f"{lesson_id}.json"
        now = datetime.now().astimezone()
        is_testing = source in {"mock", "testing"}
        if path.is_file():
            lesson = LessonMemory.model_validate_json(path.read_text(encoding="utf-8"))
            if run_id not in lesson.evidence_run_ids:
                lesson.evidence_run_ids.append(run_id)
                lesson.supporting_metrics[run_id] = candidate.supporting_metrics
                if candidate.direction == "contradicts":
                    lesson.counter_evidence_run_ids.append(run_id)
                    if not is_testing and lesson.source not in {"mock", "testing"}:
                        lesson.confidence = max(0.05, round(lesson.confidence - 0.2, 2))
                elif not is_testing and lesson.source not in {"mock", "testing"}:
                    lesson.confidence = min(0.85, round(lesson.confidence + 0.2, 2))
            lesson.updated_at = now
        else:
            lesson = LessonMemory(
                id=lesson_id,
                statement=candidate.statement,
                evidence_run_ids=[run_id],
                counter_evidence_run_ids=[run_id] if candidate.direction == "contradicts" else [],
                supporting_metrics={run_id: candidate.supporting_metrics},
                confidence=min(candidate.confidence, 0.2) if is_testing else min(candidate.confidence, 0.49),
                status="tentative",
                category=candidate.category,
                scope=candidate.scope,
                source="testing" if is_testing else source,
                created_at=now,
                updated_at=now,
            )
        supporting_runs = [
            value for value in lesson.evidence_run_ids if value not in lesson.counter_evidence_run_ids
        ] if lesson.source not in {"mock", "testing"} else []
        if len(lesson.counter_evidence_run_ids) >= 2 and lesson.confidence <= 0.2:
            lesson.status = "rejected"
        else:
            lesson.status = "supported" if len(supporting_runs) >= 2 and lesson.confidence >= 0.5 else "tentative"
        if is_testing:
            lesson.source = "testing"
            lesson.status = "tentative"
            lesson.confidence = min(lesson.confidence, 0.2)
        self._write_json(path, lesson.model_dump(mode="json"))
        self._index_add("lessons", lesson.id)
        return lesson

    def save_strategy(self, strategy: StrategyMemory) -> Path:
        path = self.strategies_dir / f"{strategy.id}.json"
        if path.is_file():
            existing = StrategyMemory.model_validate_json(path.read_text(encoding="utf-8"))
            strategy.created_at = existing.created_at
            strategy.evidence_run_ids = list(dict.fromkeys(existing.evidence_run_ids + strategy.evidence_run_ids))
        self._write_json(path, strategy.model_dump(mode="json"))
        self._index_add("strategies", strategy.id)
        return path

    def list_lessons(self) -> list[LessonMemory]:
        return [
            LessonMemory.model_validate_json(path.read_text(encoding="utf-8"))
            for path in sorted(self.lessons_dir.glob("*.json"))
        ]

    def list_strategies(self, channel_id: str | None = None) -> list[StrategyMemory]:
        strategies = [
            StrategyMemory.model_validate_json(path.read_text(encoding="utf-8"))
            for path in sorted(self.strategies_dir.glob("*.json"))
        ]
        return [item for item in strategies if channel_id is None or item.channel_id == channel_id]

    def list_episodes(self) -> list[EpisodeMemory]:
        return [
            EpisodeMemory.model_validate_json(path.read_text(encoding="utf-8"))
            for path in sorted(self.episodes_dir.glob("*.json"))
        ]

    def show_lesson(self, lesson_id: str) -> LessonMemory:
        path = self.lessons_dir / f"{lesson_id}.json"
        if not path.is_file():
            raise FileNotFoundError(f"找不到 lesson：{lesson_id}")
        return LessonMemory.model_validate_json(path.read_text(encoding="utf-8"))

    def show_strategy(self, strategy_id: str) -> StrategyMemory:
        path = self.strategies_dir / f"{strategy_id}.json"
        if not path.is_file():
            raise FileNotFoundError(f"找不到 strategy：{strategy_id}")
        return StrategyMemory.model_validate_json(path.read_text(encoding="utf-8"))

    @staticmethod
    def _stable_id(prefix: str, *parts: str) -> str:
        digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:12]
        return f"{prefix}_{digest}"

    def _index_add(self, section: str, value: str) -> None:
        index = json.loads(self.index_path.read_text(encoding="utf-8"))
        index.setdefault(section, [])
        if value not in index[section]:
            index[section].append(value)
            index[section].sort()
        index["updated_at"] = datetime.now().astimezone().isoformat()
        self._write_json(self.index_path, index)

    @staticmethod
    def _write_json(path: Path, payload: object) -> None:
        encoded = json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n"
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(encoded, encoding="utf-8", newline="\n")
        temporary.replace(path)
