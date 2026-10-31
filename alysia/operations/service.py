from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import datetime

import yaml

from alysia.core.config import AlysiaConfig
from alysia.core.run import RunManager
from alysia.learning.memory import MemoryStore
from alysia.operations.analyzer import MultiVideoAnalyzer
from alysia.operations.store import ChannelStore
from alysia.schemas import (
    AudienceModel,
    AudiencePreference,
    ChannelCase,
    ChannelMemory,
    CreatorDashboard,
    CreatorProfile,
    MultiVideoPerformanceAnalysis,
    PublishedTopic,
    StrategyEvidenceChain,
    VideoMetrics,
    VideoPerformanceSnapshot,
    ContentFingerprint,
)


class OperationsService:
    """只读汇总已有创作证据，并生成可解释运营状态。"""

    def __init__(self, config: AlysiaConfig) -> None:
        self.config = config
        self.manager = RunManager(config.runtime.runs_dir)
        self.memory = MemoryStore(config.learning.memory_dir)
        self.store = ChannelStore(config.learning.memory_dir)
        self.analyzer = MultiVideoAnalyzer()

    def refresh(self, channel_id: str | None = None) -> CreatorDashboard:
        channel_id = channel_id or self.config.operations.default_channel_id
        profile = self._load_profile()
        snapshots = self.collect_snapshots(channel_id)
        analysis = self.analyzer.analyze(channel_id, snapshots)
        experiments = self.store.list_experiments(channel_id)
        strategies = self.memory.list_strategies(channel_id)
        digest = self._dashboard_digest(analysis, experiments, strategies)
        existing = self.store.load_dashboard(channel_id)
        if existing and existing.source_digest == digest:
            return existing

        audience = self._audience_model(channel_id, snapshots)
        channel_memory = self._channel_memory(channel_id, profile, snapshots, analysis, experiments, strategies)
        chains = [
            StrategyEvidenceChain(
                strategy_id=item.id,
                rule=item.rule,
                status=item.status,
                confidence=item.confidence,
                experiment_ids=item.evidence_experiment_ids,
                metric_evidence=item.evidence_metrics,
            )
            for item in strategies
            if item.status != "supported"
        ]
        dashboard = CreatorDashboard(
            channel_id=channel_id,
            channel_state=channel_memory,
            recent_performance=analysis,
            audience_model=audience,
            current_experiments=[item for item in experiments if item.status not in {"completed", "cancelled"}],
            pending_strategies=chains,
            next_recommendations=self._recommendations(analysis, experiments, chains),
            source_digest=digest,
            generated_at=datetime.now().astimezone(),
        )
        self.store.save_analysis(analysis)
        self.store.save_audience(audience)
        self.store.save_memory(channel_memory)
        self.store.save_dashboard(dashboard)
        return dashboard

    def collect_snapshots(self, channel_id: str) -> list[VideoPerformanceSnapshot]:
        snapshots: list[VideoPerformanceSnapshot] = []
        default_channel = self.config.operations.default_channel_id
        for path in sorted(self.manager.runs_dir.glob("*/run_state.json")):
            try:
                state = self.manager.load(path.parent.name)
            except (OSError, ValueError):
                continue
            run_channel = (state.planning_provenance or {}).get("channel_id")
            if run_channel is None:
                run_channel = default_channel
            if run_channel != channel_id:
                continue
            if not self.manager.artifact_exists(state, "analytics_metrics") or not self.manager.artifact_exists(
                state, "content_fingerprint"
            ):
                continue
            metrics = VideoMetrics.model_validate(
                self.manager.read_json(state.run_id, state.artifacts["analytics_metrics"])
            )
            fingerprint = ContentFingerprint.model_validate(
                self.manager.read_json(state.run_id, state.artifacts["content_fingerprint"])
            )
            snapshots.append(
                VideoPerformanceSnapshot(
                    channel_id=channel_id,
                    run_id=state.run_id,
                    external_id=state.external_id,
                    topic=state.topic,
                    category=fingerprint.category,
                    published_at=metrics.publish_time or metrics.collected_at,
                    source=metrics.source,
                    metrics={
                        name: getattr(metrics, name)
                        for name in (
                            "views",
                            "ctr",
                            "completion_rate",
                            "avg_view_percentage",
                            "likes",
                            "favorites",
                            "comments",
                            "followers_gained",
                        )
                    },
                    fingerprint={
                        "title_style": fingerprint.title_style,
                        "duration_sec": fingerprint.duration_sec,
                        "hook_length_sec": fingerprint.hook_length_sec,
                        "cover_template": fingerprint.cover_template,
                        "narration_speed_chars_per_sec": fingerprint.narration_speed_chars_per_sec,
                    },
                )
            )
        return snapshots

    def _channel_memory(
        self,
        channel_id: str,
        profile: CreatorProfile,
        snapshots: list[VideoPerformanceSnapshot],
        analysis: MultiVideoPerformanceAnalysis,
        experiments: list,
        strategies: list,
    ) -> ChannelMemory:
        now = datetime.now().astimezone()
        existing = self.store.load_memory(channel_id)
        ranked = sorted(
            ((self._quality_score(item), item) for item in snapshots),
            key=lambda pair: pair[0] if pair[0] is not None else -1,
            reverse=True,
        )
        usable = [(score, item) for score, item in ranked if score is not None and not item.is_testing]
        case_count = min(3, len(usable) // 2)
        successes = [
            self._case(item, score, "可比率指标在当前频道样本中相对较高")
            for score, item in usable[:case_count]
        ]
        failures = [
            self._case(item, score, "可比率指标在当前频道样本中相对较低，需实验验证原因")
            for score, item in reversed(usable[-case_count:])
        ] if case_count else []
        supported = [item.rule for item in strategies if item.status == "supported"]
        long_term_strategy = supported or ["保持人工审批；一次只验证一个内容变量，积累跨视频证据后再调整策略。"]
        return ChannelMemory(
            channel_id=channel_id,
            channel_name=profile.creator_name,
            current_positioning=profile.channel_goal,
            content_directions=profile.primary_domains,
            published_topics=[
                PublishedTopic(
                    run_id=item.run_id,
                    topic=item.topic,
                    category=item.category,
                    published_at=item.published_at,
                    source=item.source,
                )
                for item in snapshots
            ],
            audience_hypotheses=[profile.target_audience],
            success_cases=successes,
            failure_cases=failures,
            long_term_strategy=long_term_strategy,
            active_experiment_ids=[item.id for item in experiments if item.status not in {"completed", "cancelled"}],
            strategy_ids=[item.id for item in strategies],
            source_digest=analysis.source_digest,
            revision=(existing.revision + 1) if existing else 1,
            created_at=existing.created_at if existing else now,
            updated_at=now,
        )

    def _audience_model(
        self,
        channel_id: str,
        snapshots: list[VideoPerformanceSnapshot],
    ) -> AudienceModel:
        grouped: dict[str, list[VideoPerformanceSnapshot]] = defaultdict(list)
        for item in snapshots:
            grouped[item.category].append(item)
        all_scores = [score for item in snapshots if (score := self._quality_score(item)) is not None]
        baseline = sum(all_scores) / len(all_scores) if all_scores else None
        liked_topics: list[AudiencePreference] = []
        for category, items in sorted(grouped.items()):
            scored = [(item, self._quality_score(item)) for item in items]
            scored = [(item, score) for item, score in scored if score is not None]
            mean = sum(score for _, score in scored) / len(scored) if scored else None
            if mean is None or baseline is None:
                signal = "unknown"
            elif mean > baseline + 0.02:
                signal = "positive"
            elif mean < baseline - 0.02:
                signal = "negative"
            else:
                signal = "mixed"
            liked_topics.append(
                AudiencePreference(
                    subject=category,
                    signal=signal,
                    confidence=min(0.8, len(scored) * 0.15),
                    evidence_run_ids=[item.run_id for item, _ in scored],
                )
            )
        format_groups: dict[str, list[VideoPerformanceSnapshot]] = defaultdict(list)
        for item in snapshots:
            style = str(item.fingerprint.get("title_style") or "unknown")
            format_groups[style].append(item)
        content_preferences: list[AudiencePreference] = []
        for style, items in sorted(format_groups.items()):
            scored = [(item, self._quality_score(item)) for item in items]
            scored = [(item, score) for item, score in scored if score is not None]
            mean = sum(score for _, score in scored) / len(scored) if scored else None
            if mean is None or baseline is None:
                signal = "unknown"
            elif mean > baseline + 0.02:
                signal = "positive"
            elif mean < baseline - 0.02:
                signal = "negative"
            else:
                signal = "mixed"
            content_preferences.append(
                AudiencePreference(
                    subject=f"title_style:{style}",
                    signal=signal,
                    confidence=min(0.8, len(scored) * 0.15),
                    evidence_run_ids=[item.run_id for item, _ in scored],
                )
            )
        questions: list[str] = []
        run_ids = {item.run_id for item in snapshots}
        for episode in self.memory.list_publish_episodes():
            if episode.run_id in run_ids:
                questions.extend(episode.comment_insight.questions)
                questions.extend(episode.comment_insight.possible_content_requests)
        viewing_behavior = []
        for metric in ("ctr", "completion_rate", "avg_view_percentage"):
            values = [float(value) for item in snapshots if (value := item.metrics.get(metric)) is not None]
            if values:
                viewing_behavior.append(f"{metric} 有 {len(values)} 个样本，均值为 {sum(values) / len(values):.3f}。")
        return AudienceModel(
            channel_id=channel_id,
            liked_topics=liked_topics,
            common_questions=list(dict.fromkeys(questions))[:20],
            content_preferences=content_preferences,
            viewing_behavior=viewing_behavior,
            caveats=["该模型只描述聚合内容反馈，不建立个人画像。", "相关性信号不能替代受控实验。"],
            updated_at=datetime.now().astimezone(),
        )

    def _load_profile(self) -> CreatorProfile:
        path = self.config.creator.profile_file
        if path.is_file():
            return CreatorProfile.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")) or {})
        return CreatorProfile(
            creator_name=self.config.creator.name,
            channel_goal="建立可解释、可验证的中文技术内容频道",
            primary_domains=["人工智能"],
            target_audience="中文技术观众",
            preferred_formats=["科普解释"],
            originality_requirements="必须有独立分析",
            source_quality_requirements="时效事实必须可追溯",
        )

    @staticmethod
    def _case(snapshot: VideoPerformanceSnapshot, score: float, reason: str) -> ChannelCase:
        return ChannelCase(run_id=snapshot.run_id, topic=snapshot.topic, reason=f"{reason}（score={score:.3f}）", metrics=snapshot.metrics)

    @staticmethod
    def _quality_score(snapshot: VideoPerformanceSnapshot) -> float | None:
        values = [
            float(value)
            for metric in ("ctr", "completion_rate", "avg_view_percentage")
            if (value := snapshot.metrics.get(metric)) is not None
        ]
        return sum(values) / len(values) if values else None

    @staticmethod
    def _dashboard_digest(analysis, experiments, strategies) -> str:
        payload = {
            "analysis": analysis.source_digest,
            "experiments": [item.model_dump(mode="json") for item in experiments],
            "strategies": [item.model_dump(mode="json") for item in strategies],
        }
        return hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()

    @staticmethod
    def _recommendations(analysis, experiments, strategies) -> list[str]:
        recommendations: list[str] = []
        if analysis.non_testing_sample_size < 4:
            recommendations.append("继续收集至少 4 条非测试内容数据，再判断跨视频趋势。")
        if any(item.status == "draft" for item in experiments):
            recommendations.append("由人工审核当前 draft 实验，批准后再分配 control/treatment 内容。")
        if any(item.status in {"approved", "running"} for item in experiments):
            recommendations.append("保持实验控制变量，补足两组样本并完成指标回收。")
        if any(item.status == "possible" for item in analysis.fatigue_signals):
            recommendations.append("对可能的内容疲劳信号建立小范围实验，不要直接改变全频道策略。")
        if strategies:
            recommendations.append("待验证策略保持 tentative，直到至少两个合格实验提供一致证据。")
        if not recommendations:
            recommendations.append("当前没有足够证据触发策略变更；继续按人工批准的内容计划运行。")
        return recommendations
