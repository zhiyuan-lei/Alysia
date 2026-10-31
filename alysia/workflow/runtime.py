from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path

from alysia.schemas import StepExecutionResult, WorkflowPlan, WorkflowState, WorkflowTask
from alysia.core.io import atomic_write_json
from alysia.reliability import CheckpointManager, FailureClassifier, FailureStore, RecoveryPolicyEngine

from .contracts import RegistryView
from .executors import ExecutionContext, WorkflowExecutionError, WorkflowExecutorRegistry
from .repair import WorkflowRepairPlanner
from .store import WorkflowStore


class WorkflowRuntime:
    def __init__(
        self,
        store: WorkflowStore,
        registry: RegistryView,
        executors: WorkflowExecutorRegistry,
        repair: WorkflowRepairPlanner,
        *,
        max_repair_rounds: int = 2,
        recovery_policy: RecoveryPolicyEngine | None = None,
        security=None,
    ) -> None:
        self.store = store
        self.registry = registry
        self.executors = executors
        self.repair = repair
        self.max_repair_rounds = max_repair_rounds
        self.recovery_policy = recovery_policy or RecoveryPolicyEngine(max_recovery_rounds=max_repair_rounds + 1)
        self.security = security

    def run(self, task: WorkflowTask, plan: WorkflowPlan, state: WorkflowState | None = None) -> WorkflowState:
        if plan.status not in {"validated", "running", "failed"}:
            raise WorkflowExecutionError("Workflow 必须先通过 validation")
        state = state or self.store.load_state(plan)
        if state.status == "completed":
            return state
        state.artifacts.update(self.store.materialize_inputs(plan, task))
        state.status = "running"
        self.store.save_state(plan, state)
        self.store.append_trace(plan, {"event": "workflow_started", "status": state.status})
        while True:
            pending = [step for step in plan.steps if state.steps[step.step_id].status in {"pending", "failed"}]
            if not pending:
                state.status = "completed" if all(
                    item.status in {"completed", "skipped"} for item in state.steps.values()
                ) else "failed"
                break
            progressed = False
            for step in pending:
                step_state = state.steps[step.step_id]
                if not all(state.steps[item].status in {"completed", "skipped"} for item in step.depends_on):
                    continue
                if self._artifacts_reusable(plan, step, state):
                    step_state.status = "completed"
                    self.store.append_trace(plan, {"event": "artifact_reused", "step_id": step.step_id})
                    progressed = True
                    continue
                progressed = True
                if not self._execute_with_repair(task, plan, state, step):
                    self.store.save_state(plan, state)
                    return state
            if not progressed:
                state.status = "blocked"
                state.blocked_reason = "没有依赖已满足的可执行 step"
                break
            self.store.save_state(plan, state)
        self.store.save_state(plan, state)
        self.store.append_trace(plan, {"event": "workflow_finished", "status": state.status})
        return state

    def _execute_with_repair(self, task: WorkflowTask, plan: WorkflowPlan, state: WorkflowState, step) -> bool:
        implementation = step.implementation_id
        fallback_used = False
        while True:
            result = self._execute_once(task, plan, state, step, implementation, fallback_used)
            self.store.append_result(plan, result)
            if result.status == "completed":
                return True
            repair_plan = self.repair.propose(plan, state, step, result.error or "unknown failure", self.registry)
            state.repair_rounds += 1
            state.steps[step.step_id].repair_rounds += 1
            self.store.append_trace(plan, {"event": "repair_planned", **repair_plan.model_dump(mode="json")})
            if repair_plan.action == "retry_same_step" and state.repair_rounds <= self.max_repair_rounds:
                continue
            if repair_plan.action == "use_approved_fallback" and repair_plan.selected_implementation:
                implementation = repair_plan.selected_implementation
                fallback_used = True
                continue
            if repair_plan.action == "skip_optional_step":
                state.steps[step.step_id].status = "skipped"
                return True
            state.steps[step.step_id].status = "blocked" if repair_plan.approval_required else "failed"
            state.status = "blocked" if repair_plan.approval_required else "failed"
            state.blocked_reason = repair_plan.reason
            return False

    def _execute_once(self, task, plan, state, step, implementation: str, fallback_used: bool) -> StepExecutionResult:
        source_type = "skill" if any(
            item.implementation_id == implementation and item.source_type == "skill" for item in self.registry.all()
        ) else "capability"
        step_state = state.steps[step.step_id]
        step_state.status = "running"
        step_state.attempts += 1
        step_state.selected_implementation = implementation
        step_state.started_at = datetime.now().astimezone()
        checkpoint_manager = CheckpointManager(self.store.workflow_dir(plan) / "reliability" / "checkpoints")
        checkpoint_manager.create(
            run_id=state.run_id, workflow_id=state.workflow_id, stage=step.step_id, status="started",
            state_payload=state.model_dump(mode="json"),
        )
        output_paths = {artifact: self.store.artifact_path(plan, step.step_id, artifact) for artifact in step.outputs}
        context = ExecutionContext(
            task=task, plan=plan, step=step, state=state, implementation_id=implementation,
            input_artifacts={name: state.artifacts[name] for name in step.inputs if name in state.artifacts},
            output_paths=output_paths,
        )
        start = time.monotonic()
        try:
            contract = self.registry.get(implementation, source_type=source_type)
            if source_type == "skill" and contract.status != "active":
                raise PermissionError(f"policy_violation: unapproved skill cannot execute: {implementation}")
            if self.security is not None:
                decision = self.security.policy.authorize_tool(
                    actor="WorkflowRuntime", executable="python", approved_context=True,
                    action="workflow.execute", correlation_id=state.workflow_id,
                )
                if decision.decision != "allow":
                    raise PermissionError(f"policy_violation: {decision.reason}")
            spec = self.executors.get(source_type, implementation)
            if spec.execution_layer != step.execution_layer:
                raise WorkflowExecutionError(
                    f"Runtime adapter layer mismatch：{implementation} {spec.execution_layer}!={step.execution_layer}"
                )
            outputs, observations = spec.execute(context)
            missing = set(step.outputs) - set(outputs)
            if missing or any(not self._path_exists(outputs[item]) for item in step.outputs if item in outputs):
                raise WorkflowExecutionError(f"missing artifact outputs：{sorted(missing)}")
            state.artifacts.update(outputs)
            step_state.artifact_refs = outputs
            step_state.status = "completed"
            step_state.error = None
            step_state.completed_at = datetime.now().astimezone()
            result = StepExecutionResult(
                step_id=step.step_id, implementation_id=implementation, status="completed",
                outputs=outputs, elapsed_sec=time.monotonic() - start,
                retry_count=max(0, step_state.attempts - 1), fallback_used=fallback_used,
                resource_observations=observations,
                qa_outcomes={key: True for key in outputs if key.endswith("qa_report")},
                created_at=datetime.now().astimezone(),
            )
            checkpoint_manager.create(
                run_id=state.run_id, workflow_id=state.workflow_id, stage=step.step_id, status="succeeded",
                state_payload=state.model_dump(mode="json"),
                artifact_paths=[Path(path) for path in outputs.values()],
                producer=implementation,
            )
        except Exception as exc:
            safe_error = self.security.redactor.redact(str(exc)) if self.security is not None else str(exc)
            step_state.status = "failed"
            step_state.error = safe_error
            result = StepExecutionResult(
                step_id=step.step_id, implementation_id=implementation, status="failed",
                elapsed_sec=time.monotonic() - start, retry_count=max(0, step_state.attempts - 1),
                fallback_used=fallback_used, error=safe_error, created_at=datetime.now().astimezone(),
            )
            failure = FailureClassifier.record(
                RuntimeError(safe_error), run_id=state.run_id, workflow_id=state.workflow_id, stage=step.step_id,
                provider=implementation, retry_count=max(0, step_state.attempts - 1),
                max_retries=self.max_repair_rounds,
                fallback_refs=list(step.fallback),
            )
            failure.recovery_round = state.repair_rounds
            failure_store = FailureStore(self.store.workflow_dir(plan) / "reliability" / "failures")
            failure_store.save(failure)
            checkpoint = checkpoint_manager.create(
                run_id=state.run_id, workflow_id=state.workflow_id, stage=step.step_id, status="failed",
                state_payload=state.model_dump(mode="json"),
            )
            decision = self.recovery_policy.decide(
                failure,
                current_state=state,
                approved_fallbacks=list(step.fallback),
                checkpoint_id=checkpoint.checkpoint_id,
                artifact_owner=step.step_id,
            )
            atomic_write_json(
                self.store.workflow_dir(plan) / "reliability" / "decisions" / f"{failure.failure_id}.json",
                decision.model_dump(mode="json"), backup_count=2,
            )
        self.store.append_trace(plan, {
            "event": "step_finished", "step_id": step.step_id, "implementation_id": implementation,
            "status": result.status, "execution_layer": step.execution_layer, "fallback_used": fallback_used,
        })
        return result

    @staticmethod
    def _path_exists(value: str) -> bool:
        from pathlib import Path
        return Path(value).is_file()

    @staticmethod
    def _artifacts_reusable(plan, step, state) -> bool:
        from alysia.reliability.artifacts import ArtifactIntegrityChecker

        step_state = state.steps[step.step_id]
        return step_state.status == "completed" and bool(step_state.artifact_refs) and all(
            ArtifactIntegrityChecker().check(Path(path), producer=step.step_id).validity == "valid"
            for path in step_state.artifact_refs.values()
        )
