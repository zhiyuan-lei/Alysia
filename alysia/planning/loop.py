from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

import yaml

from alysia.core.config import AlysiaConfig
from alysia.core.run import RunManager, RunState
from alysia.creator.service import CreatorJobService
from alysia.creator.store import CreatorJobStore
from alysia.learning.memory import MemoryStore
from alysia.operations import OperationsService
from alysia.planning.board import EditorialBoard
from alysia.planning.qa import PlanningQA
from alysia.planning.scoring import TopicScoringEngine
from alysia.planning.store import PlanStore
from alysia.planning.topics import TopicGenerator
from alysia.planning.trend_workspace import TrendWorkspace
from alysia.providers.trends import ManualTrendProvider, MockTrendProvider, WebTrendProvider
from alysia.schemas import (
    ContentPlan,
    CreatorLoopState,
    CreatorProfile,
    NextExperimentProposal,
    PlanSlot,
    RankedTopic,
    TrendItem,
)


class CreatorLoop:
    def __init__(self, config: AlysiaConfig, channel_id: str | None = None) -> None:
        self.config = config
        self.channel_id = channel_id or config.operations.default_channel_id
        self.run_manager = RunManager(config.runtime.runs_dir)
        self.memory = MemoryStore(config.learning.memory_dir)
        self.store = PlanStore(config.planning.plans_dir, self.channel_id)
        self.trend_workspace = TrendWorkspace(config.trends.workspace_dir)
        self.generator = TopicGenerator()
        self.scorer = TopicScoringEngine(config.planning)
        self.board = EditorialBoard()
        self.qa = PlanningQA()
        self.operations = OperationsService(config)
        creator_jobs_dir = config.creator_loop.jobs_dir or (config.runtime.runs_dir.parent / "creator_jobs")
        self.creator_jobs = CreatorJobStore(creator_jobs_dir)
        self.creator_job_service = CreatorJobService(self.creator_jobs)

    def tick(self, *, force: bool = False) -> ContentPlan:
        now = datetime.now().astimezone()
        current = self.store.load_loop_state()
        if not force and current and current.active_plan_id and current.last_tick_at:
            valid_until = current.last_tick_at + timedelta(hours=self.config.creator_loop.planning_interval_hours)
            if now < valid_until:
                try:
                    return self.store.load_plan(current.active_plan_id)
                except FileNotFoundError:
                    pass
        return self.create_plan(now=now)

    def create_plan(self, *, now: datetime | None = None) -> ContentPlan:
        now = now or datetime.now().astimezone()
        state = CreatorLoopState(
            stage="gather_trends",
            updated_at=now,
            last_tick_at=now,
            channel_id=self.channel_id,
            cycle_phase="observe",
        )
        self.store.save_loop_state(state)
        try:
            dashboard = self.operations.refresh(self.channel_id)
            state.operations_digest = dashboard.source_digest
            state.cycle_phase = "analyze"
            self.store.save_loop_state(state)
            profile = self.load_profile()
            trends, provider_name, source = self._gather_trends()
            history_states = self._history_states()
            history_topics = [item.topic for item in history_states]
            next_experiment, experiment_ref = self._managed_experiment(profile)
            if next_experiment is None:
                next_experiment, experiment_ref = self._latest_experiment(history_states)
            state.cycle_phase = "experiment"
            self.store.save_loop_state(state)
            source_digest = self._source_digest(
                profile,
                trends,
                history_topics,
                next_experiment,
                dashboard.source_digest,
            )

            self._advance(state, "generate_topics")
            candidate_count = self.config.creator_loop.candidate_count or self.config.planning.candidate_count
            candidates = self.generator.generate(
                profile,
                trends,
                history_topics,
                candidate_count=candidate_count,
                next_experiment=next_experiment,
                experiment_ref=experiment_ref,
            )

            self._advance(state, "score_topics")
            scores = [self.scorer.score(item, profile, trends, history_topics) for item in candidates]

            self._advance(state, "editorial_review")
            selected_count = self.config.creator_loop.selected_count or self.config.planning.selected_count
            decision, selected = self.board.decide(candidates, scores, selected_count=selected_count)
            plan_id = f"plan_{now:%Y%m%d_%H%M%S}_{uuid4().hex[:8]}"
            plan = ContentPlan(
                plan_id=plan_id,
                created_at=now,
                horizon_days=self.config.creator_loop.horizon_days,
                source=source,
                provider=provider_name,
                testing=source in {"mock", "testing"},
                source_digest=source_digest,
                profile_name=profile.creator_name,
                channel_id=self.channel_id,
                status="waiting_for_approval" if self._requires_approval() else "plan_ready",
                slots=self._schedule(selected, now),
            )
            report = self.qa.run(
                plan,
                selected,
                profile,
                trends,
                history_topics,
                duplicate_threshold=self.config.planning.duplicate_threshold,
            )
            if not report.passed:
                raise RuntimeError(f"Planning QA 未通过：{'; '.join(report.errors)}")
            self.store.save_artifact(plan_id, "creator_profile.json", profile)
            self.store.save_artifact(plan_id, "trends.json", trends)
            self.store.save_artifact(plan_id, "topic_candidates.json", candidates)
            self.store.save_artifact(plan_id, "topic_scores.json", scores)
            self.store.save_artifact(plan_id, "editorial_decision.json", decision)
            self.store.save_artifact(plan_id, "planning_qa_report.json", report)
            self.store.save_plan(plan)
            state.active_plan_id = plan_id
            state.last_source_digest = source_digest
            state.cycle_phase = "create"
            self._advance(state, "waiting_for_approval" if self._requires_approval() else "plan_ready")
            return plan
        except Exception as exc:
            state.stage = "failed"
            state.error_message = str(exc)
            state.updated_at = datetime.now().astimezone()
            self.store.save_loop_state(state)
            raise

    def approve(self, plan_id: str, slot_id: str) -> tuple[ContentPlan, RunState]:
        plan = self.store.load_plan(plan_id)
        report = self.store.load_qa(plan_id)
        if not report.passed:
            raise RuntimeError("Planning QA 未通过，不能批准")
        if plan.source in {"mock", "testing"} and not plan.testing:
            raise RuntimeError("Mock trend 不能创建真实内容 run")
        slot = self._find_slot(plan, slot_id)
        if slot.status == "skipped":
            raise RuntimeError("已拒绝的 slot 不能批准")
        if slot.run_id:
            return plan, self.run_manager.load(slot.run_id)
        trends = [TrendItem.model_validate(item) for item in self.store.read_artifact(plan_id, "trends.json")]
        trend_by_id = {trend.id: trend for trend in trends}
        source_refs = [
            {
                "id": ref,
                "source": trend_by_id[ref].source,
                "url": trend_by_id[ref].url,
            }
            for ref in slot.source_refs
            if ref in trend_by_id
        ]
        provenance = {
            "plan_id": plan.plan_id,
            "slot_id": slot.id,
            "channel_id": plan.channel_id,
            "selected_topic": slot.topic,
            "trend_source_refs": source_refs,
            "linked_lesson_or_strategy": slot.linked_experiment,
            "planning_source": plan.source,
            "testing": plan.testing,
            "research_handoff": (
                "趋势来源只用于解释选题时机；正式脚本事实必须由现有 Research 阶段重新取证。"
            ),
        }
        run = self.run_manager.create(
            slot.topic,
            self.config.model_dump(mode="json"),
            planning_provenance=provenance,
        )
        from alysia.production import ProductionService

        ProductionService(self.config).plan(run.run_id, requested_operation="full", select=True)
        run = self.run_manager.load(run.run_id)
        run = self._bind_creator_job(run, plan, slot)
        slot.status = "approved"
        slot.approved_at = datetime.now().astimezone()
        slot.run_id = run.run_id
        plan.status = "queued"
        self.store.save_plan(plan)
        loop_state = self.store.load_loop_state()
        if loop_state:
            loop_state.stage = "queued"
            loop_state.updated_at = datetime.now().astimezone()
            self.store.save_loop_state(loop_state)
        return plan, run

    def reject(self, plan_id: str, slot_id: str) -> ContentPlan:
        plan = self.store.load_plan(plan_id)
        slot = self._find_slot(plan, slot_id)
        if slot.run_id:
            raise RuntimeError("已创建 content run 的 slot 不能拒绝")
        slot.status = "skipped"
        slot.rejected_at = datetime.now().astimezone()
        self.store.save_plan(plan)
        return plan

    async def start(self, plan_id: str, slot_id: str) -> tuple[ContentPlan, RunState]:
        """仅在显式调用后启动 approved slot；不会自动渲染、投稿或互动。"""
        plan = self.store.load_plan(plan_id)
        slot = self._find_slot(plan, slot_id)
        if slot.status not in {"approved", "queued", "started"} or not slot.run_id:
            raise RuntimeError("只有已批准且已创建 run 的 slot 才能启动")
        state = self.run_manager.load(slot.run_id)
        from alysia.core.orchestrator import AlysiaOrchestrator

        orchestrator = AlysiaOrchestrator(AlysiaConfig.model_validate(state.config_snapshot))
        slot.status = "started"
        self.store.save_plan(plan)
        state = await orchestrator.start_planned(slot.run_id)
        return plan, state

    def create_supervised_run(
        self,
        *,
        topic: str,
        goal_id: str,
        project_id: str,
        planned_run_id: str,
        approved_by: str,
        testing: bool = False,
    ) -> tuple[ContentPlan, RunState]:
        """为已显式批准的 Supervisor work item 创建可追溯 run。

        Supervisor 只能调用 CreatorLoop 的这个边界，不能直接创建 run 或调用下游 Agent。
        """
        if not approved_by.strip():
            raise RuntimeError("Supervisor planned run 缺少人工 approved_by")
        for state in self._history_states():
            provenance = state.planning_provenance or {}
            if provenance.get("planned_run_id") == planned_run_id:
                plan_id = str(provenance["plan_id"])
                return self.store.load_plan(plan_id), state
        now = datetime.now().astimezone()
        plan_id = f"supervisor_{hashlib.sha256(planned_run_id.encode('utf-8')).hexdigest()[:16]}"
        slot = PlanSlot(
            id=f"slot_{hashlib.sha256(planned_run_id.encode('utf-8')).hexdigest()[:8]}",
            planned_date=now.date(),
            topic_candidate_id=planned_run_id,
            topic=topic,
            category="Supervisor series",
            status="approved",
            priority=1,
            approved_at=now,
        )
        plan = ContentPlan(
            plan_id=plan_id,
            created_at=now,
            horizon_days=1,
            source="testing" if testing else "manual",
            provider="AutonomousSupervisor",
            testing=testing,
            source_digest=hashlib.sha256(
                json.dumps(
                    {"goal_id": goal_id, "project_id": project_id, "planned_run_id": planned_run_id},
                    sort_keys=True,
                ).encode("utf-8")
            ).hexdigest(),
            profile_name=self.load_profile().creator_name,
            channel_id=self.channel_id,
            status="queued",
            slots=[slot],
        )
        provenance = {
            "plan_id": plan_id,
            "slot_id": slot.id,
            "channel_id": self.channel_id,
            "goal_id": goal_id,
            "project_id": project_id,
            "planned_run_id": planned_run_id,
            "selected_topic": topic,
            "planning_source": "supervisor",
            "testing": testing,
            "approved_by": approved_by,
            "research_handoff": "Supervisor 只提供主题与长期上下文摘要；正式事实仍由 Research 阶段取证。",
        }
        run = self.run_manager.create(topic, self.config.model_dump(mode="json"), planning_provenance=provenance)
        from alysia.production import ProductionService

        ProductionService(self.config).plan(run.run_id, requested_operation="full", select=True)
        run = self.run_manager.load(run.run_id)
        run = self._bind_creator_job(run, plan, slot)
        slot.run_id = run.run_id
        slot.status = "queued"
        self.store.save_plan(plan)
        return plan, run

    def status(self) -> CreatorLoopState:
        state = self.store.load_loop_state()
        return state or CreatorLoopState(stage="idle", updated_at=datetime.now().astimezone())

    def load_profile(self) -> CreatorProfile:
        path = self.config.creator.profile_file
        if not path.is_file():
            raise FileNotFoundError(f"Creator Profile 不存在：{path}")
        return CreatorProfile.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")) or {})

    def _gather_trends(self) -> tuple[list[TrendItem], str, str]:
        provider_name = self.config.trends.provider
        if provider_name == "mock":
            provider = MockTrendProvider()
            source = "mock"
        elif provider_name == "manual":
            provider = ManualTrendProvider(self.trend_workspace.latest_import())
            source = "manual"
        elif provider_name == "web":
            from alysia.security import SecurityService
            provider = WebTrendProvider(self.config.trends.web_sources, security=SecurityService(self.config))
            source = "web"
        else:
            raise ValueError(f"不支持的 trend provider：{provider_name}")
        trends = provider.gather(
            max_items=self.config.trends.max_items,
            freshness_days=self.config.trends.freshness_days,
        )
        if not trends:
            raise RuntimeError("Trend provider 没有返回可用条目")
        return trends, provider.__class__.__name__, source

    def _history_states(self) -> list[RunState]:
        states: list[RunState] = []
        for path in sorted(self.run_manager.runs_dir.glob("*/run_state.json")):
            try:
                states.append(RunState.model_validate_json(path.read_text(encoding="utf-8")))
            except (ValueError, OSError):
                continue
        return states

    def _latest_experiment(
        self, states: list[RunState]
    ) -> tuple[NextExperimentProposal | None, str | None]:
        for state in sorted(states, key=lambda item: item.updated_at, reverse=True):
            relative = state.artifacts.get("next_experiment")
            if state.strategy_ready and relative and self.run_manager.artifact_exists(state, "next_experiment"):
                proposal = NextExperimentProposal.model_validate(self.run_manager.read_json(state.run_id, relative))
                return proposal, f"run:{state.run_id}:next_experiment"
        return None, None

    def _managed_experiment(
        self,
        profile: CreatorProfile,
    ) -> tuple[NextExperimentProposal | None, str | None]:
        active = [
            item
            for item in self.operations.store.list_experiments(self.channel_id)
            if item.status in {"approved", "running"}
        ]
        if not active:
            return None, None
        experiment = sorted(active, key=lambda item: (item.updated_at, item.id), reverse=True)[0]
        proposal = NextExperimentProposal(
            topic=f"{profile.primary_domains[0]}：{experiment.hypothesis}",
            angle=f"只改变 {experiment.variable_changed}，其余控制变量保持一致",
            target_audience=profile.target_audience,
            primary_hypothesis=experiment.hypothesis,
            variable_to_change=experiment.variable_changed,
            variables_to_hold_constant=experiment.control_variables,
            success_metrics=[item.metric for item in experiment.success_metrics],
        )
        return proposal, f"experiment:{experiment.id}"

    def _source_digest(
        self,
        profile: CreatorProfile,
        trends: list[TrendItem],
        history_topics: list[str],
        experiment: NextExperimentProposal | None,
        operations_digest: str,
    ) -> str:
        stable_trends = [
            {
                "id": item.id,
                "topic": item.topic,
                "source": item.source,
                "url": item.url,
                "published_at": item.published_at,
                "freshness_days": item.freshness_days,
            }
            for item in trends
        ]
        payload = {
            "profile": profile.model_dump(mode="json"),
            "trends": stable_trends,
            "history_topics": sorted(history_topics),
            "lessons": [item.id for item in self.memory.list_lessons()],
            "strategies": [item.id for item in self.memory.list_strategies(self.channel_id)],
            "experiment": experiment.model_dump(mode="json") if experiment else None,
            "operations_digest": operations_digest,
        }
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def _schedule(self, selected: list[RankedTopic], now: datetime) -> list[PlanSlot]:
        horizon = self.config.creator_loop.horizon_days
        step = max(1, horizon // max(1, len(selected)))
        return [
            PlanSlot(
                id=f"slot_{index + 1:02d}",
                planned_date=(now + timedelta(days=min(index * step, horizon - 1))).date(),
                topic_candidate_id=item.candidate.id,
                topic=item.candidate.topic,
                category=item.candidate.category,
                priority=index + 1,
                linked_experiment=item.candidate.experiment_link,
                source_refs=item.candidate.source_refs,
            )
            for index, item in enumerate(selected)
        ]

    def _requires_approval(self) -> bool:
        return self.config.creator.require_human_approval or self.config.creator_loop.require_human_approval

    def _bind_creator_job(self, run: RunState, plan: ContentPlan, slot: PlanSlot) -> RunState:
        existing = self.creator_jobs.find_by_run_id(run.run_id)
        if existing is None:
            score = 0.0
            try:
                scores = self.store.read_artifact(plan.plan_id, "topic_scores.json")
                score = next(
                    float(item.get("total", 0.0))
                    for item in scores
                    if item.get("candidate_id") == slot.topic_candidate_id
                )
            except (FileNotFoundError, StopIteration, TypeError, ValueError):
                score = 0.0
            creator_job = self.creator_job_service.create(
                topic=slot.topic,
                topic_source=plan.source,
                topic_score=score,
                testing=plan.testing,
            )
            creator_job = self.creator_job_service.attach_run(creator_job.job_id, run.run_id)
        else:
            creator_job = existing
        provenance = dict(run.planning_provenance or {})
        provenance["creator_job_id"] = creator_job.job_id
        run.creator_job_id = creator_job.job_id
        run.planning_provenance = provenance
        self.run_manager.save(run)
        input_payload = self.run_manager.read_json(run.run_id, "input.json")
        input_payload["creator_job_id"] = creator_job.job_id
        input_payload["planning_provenance"] = provenance
        self.run_manager.write_json(run.run_id, "input.json", input_payload)
        return run

    def _advance(self, state: CreatorLoopState, stage: str) -> None:
        state.stage = stage
        state.updated_at = datetime.now().astimezone()
        state.error_message = None
        self.store.save_loop_state(state)

    @staticmethod
    def _find_slot(plan: ContentPlan, slot_id: str) -> PlanSlot:
        slot = next((item for item in plan.slots if item.id == slot_id), None)
        if slot is None:
            raise KeyError(f"plan 中不存在 slot：{slot_id}")
        return slot
