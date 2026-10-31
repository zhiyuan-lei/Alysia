from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from alysia.core.config import AlysiaConfig
from alysia.schemas import (
    CandidateSimulationResult,
    ExperimentProposal,
    SimulationAssumption,
    SimulationScenario,
    SimulationResults,
    WorkflowTask,
)

from .calibration import SimulationCalibration
from .candidates import CounterfactualCandidateGenerator
from .comparator import CounterfactualComparator
from .engines import (
    ContentStructureSimulationEngine,
    PlatformOutcomeEstimator,
    ProductionSimulationEngine,
    RiskSimulationEngine,
    WorkflowSimulationEngine,
)
from .policy import SimulationDecisionPolicy
from .qa import SimulationQA
from .snapshot import WorldStateSnapshotBuilder
from .store import SimulationStore


class SimulationService:
    def __init__(self, config: AlysiaConfig, *, project_root: Path = Path("."), root: Path | None = None) -> None:
        self.config = config
        self.project_root = project_root.resolve()
        self.store = SimulationStore(root or config.simulation.root_dir)
        self.generator = CounterfactualCandidateGenerator(config.simulation.max_candidates)
        self.production = ProductionSimulationEngine(self.project_root)
        self.content = ContentStructureSimulationEngine()
        self.risk = RiskSimulationEngine()
        self.workflow = WorkflowSimulationEngine(config)
        self.platform = PlatformOutcomeEstimator()
        self.comparator = CounterfactualComparator()
        self.decision_policy = SimulationDecisionPolicy(config.simulation)
        self.qa = SimulationQA(config.simulation)

    def create(self, scenario: SimulationScenario) -> SimulationScenario:
        if not self.config.simulation.enabled:
            raise RuntimeError("simulation.enabled=false")
        self.store.save(scenario.scenario_id, "scenario.json", scenario)
        self.store.append_trace(scenario.scenario_id, "scenario_created", {
            "event": "scenario_created", "created_at": datetime.now().astimezone().isoformat(),
            "mode": "dry_run", "simulation_is_not_fact": True,
        })
        return scenario

    def create_from_task(self, task_or_path: str | Path) -> SimulationScenario:
        path = Path(task_or_path)
        if not path.is_file():
            path = Path("workspace/workflows/tasks") / f"{task_or_path}.json"
        if not path.is_file():
            raise FileNotFoundError(f"Simulation task 不存在：{task_or_path}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        if "scenario_id" in payload:
            return self.create(SimulationScenario.model_validate(payload))
        task = WorkflowTask.model_validate(payload)
        now = datetime.now().astimezone()
        digest = hashlib.sha256(f"{task.task_id}:{task.objective}".encode("utf-8")).hexdigest()[:12]
        scenario = SimulationScenario(
            scenario_id=f"sim_{digest}", objective=task.objective,
            baseline_state_refs=task.context_refs,
            assumptions=[SimulationAssumption(
                assumption_id="task_conversion", statement="由 WorkflowTask 生成两个保守 dry-run profile",
                source=str(path), confidence="medium",
            )],
            controllable_variables={"quality_profile": ["draft", task.quality_target]},
            fixed_variables={"inputs": task.inputs, "desired_outputs": task.desired_outputs},
            candidate_actions=[
                {"candidate_id": "draft", "actions": [{"type": "workflow_dry_run"}],
                 "changed_variables": {"quality_profile": "draft"}, "rationale": "低资源内部草案"},
                {"candidate_id": "target", "actions": [{"type": "workflow_dry_run"}],
                 "changed_variables": {"quality_profile": task.quality_target}, "rationale": "任务目标质量档"},
            ],
            horizon="single_run", resource_budget={
                "max_local_vram_mb": task.budget_policy.max_local_vram_mb,
                "max_ram_mb": 24576,
                "max_wall_time_sec": task.budget_policy.max_wall_time_sec,
                "max_cloud_cost": task.budget_policy.max_cloud_cost,
                "allow_unknown_resources": task.budget_policy.allow_unknown_resources,
            },
            approval_policy={
                "required_gates": task.approval_policy.required_gates,
                "allow_auto_select": False,
            },
            evaluation_metrics=["quality", "reliability", "latency", "risk"],
            uncertainty_notes=["WorkflowTask 转换不包含真实平台结果预测"],
            source_task_ref=str(path), created_at=now,
        )
        return self.create(scenario)

    def run(self, scenario_id: str) -> SimulationResults:
        scenario = self.store.load(scenario_id, "scenario.json", SimulationScenario)
        digest = self._digest(scenario)
        try:
            existing = self.store.load(scenario_id, "simulation_results.json", SimulationResults)
            if existing.scenario_digest == digest:
                return existing
        except FileNotFoundError:
            pass
        snapshot = WorldStateSnapshotBuilder(self.config, self.project_root).build()
        candidates = self.generator.generate(scenario)
        self.store.save(scenario_id, "world_state_snapshot.json", snapshot)
        self.store.save(scenario_id, "candidates.json", [item.model_dump(mode="json") for item in candidates])
        result_rows: list[CandidateSimulationResult] = []
        for candidate in candidates:
            production_predictions, production_failures, production_notes = self.production.evaluate(scenario, candidate, snapshot)
            content_predictions, content_notes = self.content.evaluate(scenario, candidate, snapshot)
            risk_predictions, risk_notes = self.risk.evaluate(scenario, candidate, snapshot)
            workflow_predictions, workflow_dry_run, workflow_notes = self.workflow.evaluate(candidate)
            platform_predictions = self.platform.evaluate(candidate, snapshot)
            result_rows.append(CandidateSimulationResult(
                candidate_id=candidate.candidate_id,
                predictions=[
                    *production_predictions, *content_predictions, *risk_predictions,
                    *workflow_predictions, *platform_predictions,
                ],
                failure_paths=[*production_failures, *risk_notes, *workflow_notes],
                approval_gates_preserved=candidate.expected_approvals,
                workflow_dry_run=workflow_dry_run,
                evaluator_notes={
                    "production": production_notes, "content": content_notes,
                    "workflow": workflow_notes,
                },
            ))
        results = SimulationResults(
            scenario_id=scenario_id, scenario_digest=digest, candidates=result_rows,
            real_providers_called=False, real_metrics_written=False,
            generated_at=datetime.now().astimezone(),
        )
        self.store.save(scenario_id, "simulation_results.json", results)
        report = self.qa.run(scenario, results)
        self.store.save(scenario_id, "simulation_qa_report.json", report)
        self.store.append_trace(scenario_id, f"simulation_run_{digest}", {
            "event": "simulation_run", "created_at": results.generated_at.isoformat(),
            "candidate_count": len(candidates), "real_providers_called": False,
            "real_metrics_written": False,
        })
        return results

    def compare(self, scenario_id: str):
        scenario = self.store.load(scenario_id, "scenario.json", SimulationScenario)
        try:
            results = self.store.load(scenario_id, "simulation_results.json", SimulationResults)
        except FileNotFoundError:
            results = self.run(scenario_id)
        comparison = self.comparator.compare(results)
        decision = self.decision_policy.decide(scenario, results, comparison)
        report = self.qa.run(scenario, results, decision)
        self.store.save(scenario_id, "comparison.json", comparison)
        self.store.save(scenario_id, "decision.json", decision)
        self.store.save(scenario_id, "simulation_qa_report.json", report)
        self.store.append_trace(scenario_id, f"comparison_{results.scenario_digest}", {
            "event": "comparison", "created_at": comparison.compared_at.isoformat(),
            "recommendation": comparison.recommendation, "decision_mode": decision.mode,
            "dispatch_performed": False,
        })
        return comparison, decision

    def show(self, scenario_id: str) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for filename in [
            "scenario.json", "world_state_snapshot.json", "candidates.json",
            "simulation_results.json", "comparison.json", "decision.json",
            "simulation_qa_report.json", "calibration.json", "experiment_proposal.json",
        ]:
            try:
                result[filename.removesuffix(".json")] = self.store.load_json(scenario_id, filename)
            except FileNotFoundError:
                continue
        return result

    def calibrate(self, scenario_id: str, actual_file: Path):
        results = self.store.load(scenario_id, "simulation_results.json", SimulationResults)
        record = SimulationCalibration().calibrate(results, actual_file)
        self.store.save(scenario_id, "calibration.json", record)
        self.store.append_trace(scenario_id, f"calibration_{self._file_digest(actual_file)}", {
            "event": "calibration", "created_at": record.created_at.isoformat(),
            "actual_source": record.actual_source, "is_testing": record.is_testing,
            "applies_automatically": False,
        })
        return record

    def experiment_proposal(self, scenario_id: str, *, hypothesis: str) -> ExperimentProposal:
        results = self.store.load(scenario_id, "simulation_results.json", SimulationResults)
        predictions = [item for candidate in results.candidates for item in candidate.predictions if item.metric in {"experiment_value_score", "platform_outcome_relative"}]
        digest = hashlib.sha256(f"{scenario_id}:{hypothesis}".encode("utf-8")).hexdigest()[:12]
        proposal = ExperimentProposal(
            proposal_id=f"simexp_{digest}", scenario_id=scenario_id, hypothesis=hypothesis,
            test_plan={"source": "simulation_recommendation", "requires_real_run": True, "separate_from_prediction": True},
            predicted_metrics=predictions, created_at=datetime.now().astimezone(),
        )
        self.store.save(scenario_id, "experiment_proposal.json", proposal)
        return proposal

    def supervisor_recommendation(self, scenario_id: str):
        """供 Supervisor 调用；只返回建议，不 dispatch 任何 Agent/Provider。"""
        comparison, decision = self.compare(scenario_id)
        if decision.dispatch_allowed:
            decision = decision.model_copy(update={
                "mode": "recommendation_only", "dispatch_allowed": False,
                "reasons": [*decision.reasons, "Supervisor integration 永远只消费 recommendation"],
            })
        return {"comparison": comparison, "decision": decision, "agent_steps_executed": False}

    def history(self) -> list[dict[str, Any]]:
        return self.store.history()

    @staticmethod
    def _digest(scenario: SimulationScenario) -> str:
        payload = scenario.model_dump(mode="json", exclude={"created_at"})
        payload["simulation_engine_version"] = "alpha16.1"
        return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()

    @staticmethod
    def _file_digest(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()[:16]
