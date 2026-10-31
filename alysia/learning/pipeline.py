from __future__ import annotations

from datetime import datetime
from pathlib import Path

from alysia.analytics import ContentFingerprintBuilder, PerformanceAnalyzer, derive_metrics
from alysia.core.run import RunManager, RunState
from alysia.core.state import Stage
from alysia.learning.lessons import LessonExtractor
from alysia.learning.memory import MemoryStore
from alysia.learning.planner import NextExperimentPlanner
from alysia.learning.qa import LearningQA
from alysia.learning.strategy import StrategyEngine
from alysia.providers.analytics import ManualAnalyticsProvider, MockAnalyticsProvider
from alysia.schemas import (
    ContentFingerprint,
    DerivedMetrics,
    EpisodeMemory,
    LessonMemory,
    PerformanceAnalysis,
    StrategyRecommendation,
    VideoMetrics,
)


class LearningPipelineError(RuntimeError):
    pass


class LearningPipeline:
    def __init__(self, manager: RunManager, memory_dir: Path) -> None:
        self.manager = manager
        self.memory = MemoryStore(memory_dir)
        self.fingerprint_builder = ContentFingerprintBuilder(manager)
        self.analyzer = PerformanceAnalyzer()
        self.lesson_extractor = LessonExtractor()
        self.strategy_engine = StrategyEngine()
        self.planner = NextExperimentPlanner()
        self.learning_qa = LearningQA()

    def write_template(self, run_id: str) -> Path:
        state = self._require_review_ready(run_id)
        template = {
            "run_id": state.run_id,
            "platform": "bilibili",
            "collected_at": datetime.now().astimezone().isoformat(),
            "source": "manual",
            "impressions": None,
            "views": None,
            "likes": None,
            "comments": None,
            "favorites": None,
            "shares": None,
            "followers_gained": None,
            "avg_view_duration_sec": None,
            "avg_view_percentage": None,
            "completion_rate": None,
            "ctr": None,
            "publish_time": None,
            "retention_points": [],
        }
        return self.manager.write_json(run_id, "analytics/metrics_template.json", template)

    def import_metrics(self, run_id: str, source: Path, *, mock: bool = False) -> RunState:
        provider = MockAnalyticsProvider() if mock else ManualAnalyticsProvider()
        metrics = provider.load(run_id, source if not mock else None)
        return self.import_video_metrics(metrics)

    def import_video_metrics(self, metrics: VideoMetrics) -> RunState:
        """导入已由可信适配器规范化的指标，供 feedback 映射复用。"""
        run_id = metrics.run_id
        state = self._require_review_ready(run_id)
        try:
            state.start_stage(Stage.ANALYTICS_IMPORTED)
            self.manager.save(state)
            fingerprint = self.fingerprint_builder.build(state)
            derived = derive_metrics(metrics)
            self.manager.write_json(run_id, "analytics/metrics.json", metrics.model_dump(mode="json"))
            self.manager.write_json(run_id, "analytics/derived_metrics.json", derived.model_dump(mode="json"))
            self.manager.write_json(run_id, "analytics/content_fingerprint.json", fingerprint.model_dump(mode="json"))
            state.artifacts.update(
                {
                    "analytics_metrics": "analytics/metrics.json",
                    "derived_metrics": "analytics/derived_metrics.json",
                    "content_fingerprint": "analytics/content_fingerprint.json",
                }
            )
            for key in (
                "performance_analysis",
                "lessons",
                "strategy_recommendations",
                "next_experiment",
                "learning_qa_report",
            ):
                state.artifacts.pop(key, None)
            state.completed_stages = [
                stage
                for stage in state.completed_stages
                if stage not in {Stage.ANALYZED, Stage.MEMORY_UPDATED, Stage.STRATEGY_READY}
            ]
            state.analysis_completed = False
            state.learning_completed = False
            state.strategy_ready = False
            state.analytics_imported = True
            state.pipeline_phase = "analytics_ready"
            state.milestone = "analytics_imported"
            state.complete_stage(Stage.ANALYTICS_IMPORTED)
            self.manager.save(state)
            self.manager.append_event(run_id, "analytics_imported", stage=Stage.ANALYTICS_IMPORTED)
            return state
        except Exception as exc:
            self._fail(state, Stage.ANALYTICS_IMPORTED, exc)
            raise

    def analyze(self, run_id: str) -> RunState:
        state = self.manager.load(run_id)
        if not state.analytics_imported:
            raise LearningPipelineError("请先导入 Analytics 指标")
        if state.analysis_completed and self.manager.artifact_exists(state, "performance_analysis"):
            return state
        try:
            state.start_stage(Stage.ANALYZED)
            self.manager.save(state)
            metrics = self._load(state, "analytics_metrics", VideoMetrics)
            derived = self._load(state, "derived_metrics", DerivedMetrics)
            fingerprint = self._load(state, "content_fingerprint", ContentFingerprint)
            qa_reports = {
                key: self.manager.read_json(run_id, relative)
                for key in ("text_qa_report", "audio_qa_report", "video_qa_report", "publish_qa_report")
                if (relative := state.artifacts.get(key)) and self.manager.artifact_exists(state, key)
            }
            analysis = self.analyzer.analyze(metrics, derived, fingerprint, qa_reports)
            self.manager.write_json(run_id, "analytics/performance_analysis.json", analysis.model_dump(mode="json"))
            state.artifacts["performance_analysis"] = "analytics/performance_analysis.json"
            state.analysis_completed = True
            state.milestone = "analyzed"
            state.pipeline_phase = "analytics_ready"
            state.complete_stage(Stage.ANALYZED)
            self.manager.save(state)
            self.manager.append_event(run_id, "performance_analyzed", stage=Stage.ANALYZED)
            return state
        except Exception as exc:
            self._fail(state, Stage.ANALYZED, exc)
            raise

    def learn(self, run_id: str) -> RunState:
        state = self.manager.load(run_id)
        if not state.analysis_completed:
            raise LearningPipelineError("请先运行 analyze")
        if state.learning_completed and self.manager.artifact_exists(state, "lessons"):
            return state
        try:
            state.start_stage(Stage.MEMORY_UPDATED)
            self.manager.save(state)
            metrics = self._load(state, "analytics_metrics", VideoMetrics)
            fingerprint = self._load(state, "content_fingerprint", ContentFingerprint)
            analysis = self._load(state, "performance_analysis", PerformanceAnalysis)
            source = "testing" if metrics.is_mock else metrics.source
            episode = EpisodeMemory(
                run_id=run_id,
                topic=state.topic,
                source=source,
                metrics_summary={
                    "views": metrics.views,
                    "ctr": metrics.ctr,
                    "completion_rate": metrics.completion_rate,
                    "avg_view_percentage": metrics.avg_view_percentage,
                },
                fingerprint_summary={
                    "title_style": fingerprint.title_style,
                    "duration_sec": fingerprint.duration_sec,
                    "hook_length_sec": fingerprint.hook_length_sec,
                    "category": fingerprint.category,
                },
                analysis_summary=analysis.summary,
                created_at=datetime.now().astimezone(),
            )
            self.memory.record_episode(episode)
            candidates = self.lesson_extractor.extract(analysis, metrics, fingerprint)
            lessons = [self.memory.upsert_lesson(item, run_id, source) for item in candidates]
            self.manager.write_json(run_id, "analytics/lessons.json", [item.model_dump(mode="json") for item in lessons])
            report = self.learning_qa.run(metrics, analysis, lessons, [])
            self.manager.write_json(run_id, "analytics/learning_qa_report.json", report.model_dump(mode="json"))
            if not report.passed:
                raise LearningPipelineError("Learning QA 未通过")
            state.artifacts.update(
                {
                    "lessons": "analytics/lessons.json",
                    "learning_qa_report": "analytics/learning_qa_report.json",
                }
            )
            state.learning_completed = True
            state.pipeline_phase = "learning_ready"
            state.milestone = "memory_updated"
            state.complete_stage(Stage.MEMORY_UPDATED)
            self.manager.save(state)
            self.manager.append_event(run_id, "memory_updated", stage=Stage.MEMORY_UPDATED)
            return state
        except Exception as exc:
            self._fail(state, Stage.MEMORY_UPDATED, exc)
            raise

    def strategy(self, run_id: str) -> RunState:
        state = self.manager.load(run_id)
        if not state.learning_completed:
            raise LearningPipelineError("请先运行 learn")
        if state.strategy_ready and all(
            self.manager.artifact_exists(state, key) for key in ("strategy_recommendations", "next_experiment")
        ):
            return state
        try:
            state.start_stage(Stage.STRATEGY_READY)
            self.manager.save(state)
            metrics = self._load(state, "analytics_metrics", VideoMetrics)
            fingerprint = self._load(state, "content_fingerprint", ContentFingerprint)
            analysis = self._load(state, "performance_analysis", PerformanceAnalysis)
            lessons = [
                LessonMemory.model_validate(item)
                for item in self.manager.read_json(run_id, state.artifacts["lessons"])
            ]
            recommendations = self.strategy_engine.recommend(analysis, metrics, fingerprint, lessons)
            proposal = self.planner.propose(fingerprint, recommendations)
            source = "testing" if metrics.is_mock else metrics.source
            channel_id = (
                (state.planning_provenance or {}).get("channel_id")
                or state.config_snapshot.get("operations", {}).get("default_channel_id")
                or "main"
            )
            self.strategy_engine.persist(
                self.memory,
                run_id,
                source,
                recommendations,
                fingerprint.category,
                channel_id=channel_id,
            )
            qa_report = self.learning_qa.run(metrics, analysis, lessons, recommendations)
            if not qa_report.passed:
                raise LearningPipelineError("Learning QA 未通过")
            self.manager.write_json(
                run_id,
                "analytics/strategy_recommendations.json",
                [item.model_dump(mode="json") for item in recommendations],
            )
            self.manager.write_json(run_id, "analytics/next_experiment.json", proposal.model_dump(mode="json"))
            self.manager.write_json(run_id, "analytics/learning_qa_report.json", qa_report.model_dump(mode="json"))
            state.artifacts.update(
                {
                    "strategy_recommendations": "analytics/strategy_recommendations.json",
                    "next_experiment": "analytics/next_experiment.json",
                    "learning_qa_report": "analytics/learning_qa_report.json",
                }
            )
            state.strategy_ready = True
            state.pipeline_phase = "learning_ready"
            state.milestone = "strategy_ready"
            state.complete_stage(Stage.STRATEGY_READY)
            self.manager.save(state)
            self.manager.append_event(run_id, "strategy_ready", stage=Stage.STRATEGY_READY)
            return state
        except Exception as exc:
            self._fail(state, Stage.STRATEGY_READY, exc)
            raise

    def _require_review_ready(self, run_id: str) -> RunState:
        state = self.manager.load(run_id)
        if not state.review_ready:
            raise LearningPipelineError("run 尚未达到 review_ready")
        return state

    def _load(self, state: RunState, key: str, model: type):
        relative = state.artifacts.get(key)
        if not relative or not self.manager.artifact_exists(state, key):
            raise FileNotFoundError(f"学习管线缺少必需产物：{key}")
        return model.model_validate(self.manager.read_json(state.run_id, relative))

    def _fail(self, state: RunState, stage: Stage, error: Exception) -> None:
        state.fail_stage(stage, error)
        self.manager.save(state)
        self.manager.append_event(state.run_id, "stage_failed", stage=stage)
