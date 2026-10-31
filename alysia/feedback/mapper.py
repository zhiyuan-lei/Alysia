from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

from alysia.core.run import RunManager, RunState
from alysia.core.state import Stage
from alysia.feedback.comments import analyze_comments
from alysia.learning.memory import MemoryStore
from alysia.learning.pipeline import LearningPipeline
from alysia.planning import PlanStore
from alysia.schemas import FeedbackRecord, PublishEpisodeMemory, VideoMetrics


class FeedbackMapper:
    def __init__(
        self,
        manager: RunManager,
        memory_dir: Path,
        *,
        plans_dir: Path | None = None,
    ) -> None:
        self.manager = manager
        self.pipeline = LearningPipeline(manager, memory_dir)
        self.memory = MemoryStore(memory_dir)
        self.plans_dir = plans_dir

    def apply(self, feedback: FeedbackRecord) -> RunState:
        state = self.manager.load(feedback.run_id)
        if not state.external_id:
            raise RuntimeError("run 尚无已提交的 external_id，不能导入发布反馈")
        if state.external_id != feedback.external_id:
            raise ValueError("feedback external_id 与 PublishJob 映射不一致")
        digest = self._digest(feedback)
        mapping_path = self.manager.run_dir(feedback.run_id) / "feedback" / "mapping.json"
        if mapping_path.is_file():
            existing = json.loads(mapping_path.read_text(encoding="utf-8"))
            if existing.get("feedback_digest") == digest and self.manager.artifact_exists(state, "analytics_metrics"):
                return state

        source = {"real": "platform", "manual": "manual", "mock": "mock"}[feedback.source]
        metrics = VideoMetrics(
            run_id=feedback.run_id,
            platform="bilibili",
            collected_at=feedback.collected_at,
            source=source,
            views=feedback.views,
            likes=feedback.likes,
            comments=feedback.comments,
            favorites=feedback.favorites,
            shares=feedback.shares,
            followers_gained=feedback.followers_gained,
            retention_points=feedback.retention_points,
        )
        state = self.pipeline.import_video_metrics(metrics)
        insight = analyze_comments(feedback.comments_summary)
        self.manager.write_json(feedback.run_id, "feedback/feedback.json", feedback.model_dump(mode="json"))
        self.manager.write_json(feedback.run_id, "feedback/comment_insight.json", insight.model_dump(mode="json"))
        mapping = {
            "run_id": feedback.run_id,
            "external_id": feedback.external_id,
            "feedback_digest": digest,
            "video_metrics": "analytics/metrics.json",
            "source": feedback.source,
            "mapped_at": datetime.now().astimezone(),
        }
        self.manager.write_json(feedback.run_id, "feedback/mapping.json", mapping)
        episode = PublishEpisodeMemory(
            run_id=feedback.run_id,
            external_id=feedback.external_id,
            source=feedback.source,
            collected_at=feedback.collected_at,
            metrics_summary={
                "views": feedback.views,
                "likes": feedback.likes,
                "comments": feedback.comments,
                "favorites": feedback.favorites,
                "shares": feedback.shares,
                "followers_gained": feedback.followers_gained,
            },
            comment_insight=insight,
            feedback_digest=digest,
            updated_at=datetime.now().astimezone(),
        )
        memory_path = self.memory.record_publish_episode(episode)
        state = self.manager.load(feedback.run_id)
        state.artifacts.update(
            {
                "feedback_record": "feedback/feedback.json",
                "comment_insight": "feedback/comment_insight.json",
                "feedback_mapping": "feedback/mapping.json",
                "publish_episode_memory": memory_path.as_posix(),
            }
        )
        state.feedback_imported = True
        state.complete_stage(Stage.LEARNING)
        state.pipeline_phase = "learning"
        state.milestone = "analytics_imported"
        self.manager.save(state)
        self._sync_creator_loop(state)
        return state

    @staticmethod
    def _digest(feedback: FeedbackRecord) -> str:
        payload = feedback.model_dump(mode="json")
        payload.pop("collected_at", None)
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def _sync_creator_loop(self, state: RunState) -> None:
        if self.plans_dir is None or not state.planning_provenance:
            return
        channel_id = (state.planning_provenance or {}).get("channel_id") or "main"
        store = PlanStore(self.plans_dir, channel_id)
        loop_state = store.load_loop_state()
        if loop_state and loop_state.active_plan_id == state.planning_provenance.get("plan_id"):
            loop_state.stage = "learning"
            loop_state.cycle_phase = "learn"
            loop_state.updated_at = datetime.now().astimezone()
            store.save_loop_state(loop_state)
