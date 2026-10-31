from __future__ import annotations

import hashlib
import re
from datetime import datetime
from pathlib import Path

from alysia.capabilities import CapabilityService
from alysia.capabilities.gaps import CapabilityGapStore
from alysia.core.config import AlysiaConfig
from alysia.schemas import CapabilityGap, ProductionConstraints, WorkflowPlan, WorkflowTask

from .contracts import RegistryView
from .evaluation import WorkflowEvaluator
from .executors import WorkflowExecutorRegistry
from .matcher import CapabilityMatcher
from .planner import WorkflowPlanner
from .policy import CompositionPolicy
from .qa import WorkflowQA
from .recipes import WorkflowRecipeStore
from .repair import WorkflowRepairPlanner
from .runtime import WorkflowRuntime
from .store import WorkflowStore
from .validator import WorkflowValidator


class WorkflowService:
    def __init__(self, config: AlysiaConfig, *, runs_dir: Path | None = None) -> None:
        self.config = config
        self.capability_service = CapabilityService(config)
        self.registry = RegistryView(
            self.capability_service.registry,
            self.capability_service.skills.registry,
        )
        self.store = WorkflowStore(runs_dir or config.runtime.runs_dir)
        self.recipes = WorkflowRecipeStore(
            config.workflow.recipe_dir,
            validation_successes=config.workflow.recipe_validation_successes,
        )
        self.policy = CompositionPolicy(
            max_skill_hops=config.workflow.max_skill_hops,
            allow_unapproved_skills=config.workflow.allow_unapproved_skills,
        )
        self.validator = WorkflowValidator(self.policy, max_steps=config.workflow.max_steps)

    def plan(self, task: WorkflowTask) -> WorkflowPlan:
        if not self.config.workflow.enabled:
            raise RuntimeError("workflow.enabled=false")
        self.store.save_task(task)
        run_id = self._new_run_id(task)
        recipe = self.recipes.retrieve(task, self.registry)
        if recipe is not None:
            plan = self.recipes.clone(task, recipe, self.registry, run_id=run_id)
        else:
            constraints = ProductionConstraints(
                quality_target=task.quality_target,
                max_local_vram_mb=task.budget_policy.max_local_vram_mb,
                max_cloud_cost=task.budget_policy.max_cloud_cost,
                max_wall_time_sec=task.budget_policy.max_wall_time_sec,
                sequential_gpu_required=self.config.production.sequential_gpu_required,
                prefer_local=self.config.production.prefer_local,
                allow_cloud=self.config.production.allow_cloud,
                offline_mode=self.config.production.offline_mode,
            )
            candidates = CapabilityMatcher().match(task, self.registry, constraints)
            plan = WorkflowPlanner(max_steps=self.config.workflow.max_steps).plan(
                task, candidates, self.registry, run_id=run_id,
            )
        if plan.unresolved_gaps:
            plan.gap_links = self._link_capability_gaps(task, plan)
        self.store.save_plan(plan)
        self.store.initialize_state(plan)
        self.store.append_trace(plan, {
            "event": "workflow_planned", "recipe_id": plan.recipe_id,
            "unresolved_gaps": plan.unresolved_gaps, "layering": {
                "supervisor": "objective owner", "workflow": "approved capability composition",
                "studio": "single content run", "production": "provider/resource owner",
            },
        })
        return plan

    def validate(self, workflow_id: str):
        plan = self.store.load_plan(workflow_id)
        task = self.store.load_task(plan.task_id)
        report = self.validator.validate(task, plan, self.registry)
        self.store.save_validation(plan, report)
        plan.status = "validated" if report.passed else (
            "blocked_waiting_capability" if plan.unresolved_gaps else "blocked"
        )
        self.store.save_plan(plan)
        state = self.store.load_state(plan)
        state.status = plan.status
        state.blocked_reason = "; ".join(report.errors) if report.errors else None
        self.store.save_state(plan, state)
        return report

    def run(self, workflow_id: str, *, executors: WorkflowExecutorRegistry | None = None):
        plan = self.store.load_plan(workflow_id)
        task = self.store.load_task(plan.task_id)
        if self.config.workflow.require_validation and plan.status != "validated":
            validation = self.validate(workflow_id)
            plan = self.store.load_plan(workflow_id)
            if not validation.passed:
                return self.store.load_state(plan)
        runtime = WorkflowRuntime(
            self.store, self.registry, executors or WorkflowExecutorRegistry.controlled_defaults(),
            WorkflowRepairPlanner(max_repair_rounds=self.config.workflow.max_repair_rounds),
            max_repair_rounds=self.config.workflow.max_repair_rounds,
            security=self.capability_service.security,
        )
        state = runtime.run(task, plan)
        evaluation = WorkflowEvaluator().evaluate(task, plan, state, self.store)
        self.store.save_evaluation(plan, evaluation)
        validation = self.validator.validate(task, plan, self.registry)
        qa = WorkflowQA().run(
            task, plan, state, validation, self.registry,
            max_repair_rounds=self.config.workflow.max_repair_rounds,
        )
        self.store.save_qa(plan, qa)
        if self.config.workflow.auto_recipe_candidate and (evaluation.task_success or plan.recipe_id):
            self.recipes.record(task, plan, evaluation)
        return state

    def resume(self, workflow_id: str, *, executors: WorkflowExecutorRegistry | None = None):
        plan = self.store.load_plan(workflow_id)
        state = self.store.load_state(plan)
        if state.status in {"blocked", "failed"}:
            for step_state in state.steps.values():
                if step_state.status == "blocked":
                    step_state.status = "failed"
            state.status = "failed"
            state.blocked_reason = None
            self.store.save_state(plan, state)
            plan.status = "failed"
            self.store.save_plan(plan)
        return self.run(workflow_id, executors=executors)

    def status(self, workflow_id: str) -> dict:
        plan = self.store.load_plan(workflow_id)
        return {"plan": plan.model_dump(mode="json"), "state": self.store.load_state(plan).model_dump(mode="json")}

    def report(self, workflow_id: str) -> dict:
        plan = self.store.load_plan(workflow_id)
        result = {"plan": plan.model_dump(mode="json"), "state": self.store.load_state(plan).model_dump(mode="json")}
        for filename, key in [
            ("workflow_evaluation_report.json", "evaluation"),
            ("workflow_qa_report.json", "qa"),
            ("workflow_validation_report.json", "validation"),
        ]:
            path = self.store.workflow_dir(plan) / filename
            if path.is_file():
                import json
                result[key] = json.loads(path.read_text(encoding="utf-8"))
        return result

    def qa(self, workflow_id: str):
        plan = self.store.load_plan(workflow_id)
        task = self.store.load_task(plan.task_id)
        state = self.store.load_state(plan)
        validation = self.validator.validate(task, plan, self.registry)
        report = WorkflowQA().run(
            task, plan, state, validation, self.registry,
            max_repair_rounds=self.config.workflow.max_repair_rounds,
        )
        self.store.save_qa(plan, report)
        return report

    def _link_capability_gaps(self, task: WorkflowTask, plan: WorkflowPlan) -> list[str]:
        links: list[str] = []
        gap_store = CapabilityGapStore(self.config.capability.root_dir)
        for missing in plan.unresolved_gaps:
            digest = hashlib.sha256(f"{task.task_id}:{missing}".encode()).hexdigest()[:12]
            safe = re.sub(r"[^a-zA-Z0-9_]+", "_", missing).strip("_").lower() or "unknown"
            gap = CapabilityGap(
                gap_id=f"gap_{digest}", description=f"WorkflowTask 需要 registry 不存在的产物 contract：{missing}",
                evidence_runs=[plan.run_id], evidence_ids=[f"workflow:{plan.workflow_id}"],
                affected_agents=["workflow_planner"], severity="high", frequency=1,
                current_workaround="workflow blocked_waiting_capability；不执行未知实现",
                proposed_capability=f"missing_{safe}", confidence=0.9,
            )
            gap_store.save(gap)
            proposal = self.capability_service.skills.propose(gap.gap_id)
            links.extend([gap.gap_id, f"skill:{proposal.skill_id}:{proposal.state}"])
        return links

    @staticmethod
    def _new_run_id(task: WorkflowTask) -> str:
        now = datetime.now().astimezone()
        digest = hashlib.sha256(f"{task.task_id}:{now.isoformat()}".encode()).hexdigest()[:12]
        return f"workflow_{now.strftime('%Y%m%d_%H%M%S')}_{digest}"
