from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from alysia.core.config import AlysiaConfig, load_config
from alysia.evaluation.engine import EvaluationGate, RegressionEngine
from alysia.evaluation.fingerprint import environment_snapshot, fixture_manifest_hash, stable_json_hash, worktree_fingerprint
from alysia.evaluation.registry import BenchmarkRegistry
from alysia.evaluation.scorers import ScorerRegistry
from alysia.evaluation.store import EvaluationStore
from alysia.schemas import BaselineSnapshot, EvaluationMetric, EvaluationRun


class EvaluationService:
    def __init__(
        self,
        config: AlysiaConfig | None = None,
        *,
        project_root: Path | None = None,
        store: EvaluationStore | None = None,
        registry: BenchmarkRegistry | None = None,
    ) -> None:
        self.config = config or load_config()
        self.project_root = (project_root or Path(__file__).resolve().parents[2]).resolve()
        self.fixtures_root = self.project_root / "tests" / "fixtures" / "evaluation"
        self.store = store or EvaluationStore(self.project_root / "evaluation")
        self.registry = registry or BenchmarkRegistry()
        self.scorers = ScorerRegistry()
        self.regression = RegressionEngine(self.registry)
        self.gate_engine = EvaluationGate()

    def list_cases(self, *, include_integration: bool = True) -> list[dict[str, Any]]:
        return [case.model_dump(mode="json") for case in self.registry.list(include_integration=include_integration)]

    def run(
        self,
        *,
        label: str = "candidate",
        integration: bool = False,
        regression_injection: str | None = None,
    ) -> EvaluationRun:
        cases = self.registry.integration_cases() if integration else self.registry.default_cases()
        resolved: dict[str, list[Path]] = {}
        all_fixtures: list[Path] = []
        for case in cases:
            refs = list(case.fixture_refs)
            if regression_injection == "subtitle_timing" and case.case_id == "subtitle_sync_semantic_split.core":
                refs = ["subtitle_bad.json"]
            paths = [(self.fixtures_root / ref).resolve() for ref in refs]
            missing = [str(path) for path in paths if not path.is_file()]
            if missing:
                raise FileNotFoundError(f"benchmark fixtures missing: {missing}")
            resolved[case.case_id] = paths
            all_fixtures.extend(paths)
        fixture_hash = fixture_manifest_hash(self.project_root, all_fixtures)
        fingerprint = worktree_fingerprint(self.project_root)
        identity = stable_json_hash({
            "label": label,
            "suite": "integration" if integration else "offline",
            "registry": self.registry.version,
            "fingerprint": fingerprint,
            "fixtures": fixture_hash,
            "cases": [case.case_id for case in cases],
            "injection": regression_injection,
        })[:20]
        evaluation_id = f"eval_{identity}"
        try:
            existing = self.store.get_run(evaluation_id)
        except FileNotFoundError:
            existing = None
        if existing is not None:
            return existing

        metrics: list[EvaluationMetric] = []
        failures: list[str] = []
        artifacts: list[str] = []
        status = "completed"
        for case in cases:
            try:
                if case.integration:
                    case_metrics, case_artifacts, blocked_reason = self._run_h3_integration(case)
                    metrics.extend(case_metrics)
                    artifacts.extend(case_artifacts)
                    if blocked_reason:
                        failures.append(blocked_reason)
                        status = "blocked"
                else:
                    scorer = self.scorers.get(case.scorer_id)
                    metrics.extend(scorer.score(case, resolved[case.case_id]))
                    artifacts.extend(str(path.relative_to(self.project_root)) for path in resolved[case.case_id])
            except Exception as exc:
                failures.append(f"{case.case_id}: {type(exc).__name__}: {exc}")
                status = "failed"
        run = EvaluationRun(
            evaluation_id=evaluation_id,
            created_at=datetime.now().astimezone(),
            code_worktree_fingerprint=fingerprint,
            benchmark_registry_version=self.registry.version,
            metrics=metrics,
            artifacts=sorted(set(artifacts)),
            environment_snapshot=environment_snapshot(self.config),
            status=status,
            case_ids=[case.case_id for case in cases],
            label=label,
            suite="integration" if integration else "offline",
            failures=failures,
            fixture_manifest_hash=fixture_hash,
        )
        self.store.save_run(run)
        return run

    def create_baseline(self, *, label: str = "alpha17-baseline", version: str = "alpha17") -> BaselineSnapshot:
        evaluation = self.run(label=label)
        if evaluation.status != "completed":
            raise RuntimeError(f"baseline evaluation 未完成：{evaluation.failures}")
        baseline_id = f"baseline_{version}_{stable_json_hash({'evaluation': evaluation.evaluation_id, 'registry': self.registry.version})[:12]}"
        baseline = BaselineSnapshot(
            baseline_id=baseline_id,
            version=version,
            created_at=datetime.now().astimezone(),
            evaluation_id=evaluation.evaluation_id,
            worktree_fingerprint=evaluation.code_worktree_fingerprint,
            benchmark_registry_version=evaluation.benchmark_registry_version,
            environment_snapshot=evaluation.environment_snapshot,
            metrics=evaluation.metrics,
        )
        try:
            return self.store.get_baseline(baseline_id)
        except FileNotFoundError:
            self.store.save_baseline(baseline)
            return baseline

    def compare(self, baseline_id: str, evaluation_id: str):
        baseline = self.store.get_baseline(baseline_id)
        candidate = self.store.get_run(evaluation_id)
        comparison = self.regression.compare(baseline, candidate)
        self.store.save_comparison(comparison)
        return comparison

    def gate(self, evaluation_id: str, *, baseline_id: str | None = None):
        baseline = self.store.get_baseline(baseline_id) if baseline_id else self.store.latest_baseline()
        candidate = self.store.get_run(evaluation_id)
        comparison = self.regression.compare(baseline, candidate)
        self.store.save_comparison(comparison)
        gate = self.gate_engine.evaluate(comparison, candidate)
        self.store.save_gate(gate)
        return gate

    def report(self, evaluation_id: str) -> dict[str, Any]:
        run = self.store.get_run(evaluation_id)
        unknown = [item.metric_id for item in run.metrics if item.measurement_type == "unknown"]
        category_counts: dict[str, int] = {}
        for case_id in run.case_ids:
            category = self.registry.get(case_id).category
            category_counts[category] = category_counts.get(category, 0) + 1
        return {
            "evaluation": run.model_dump(mode="json"),
            "summary": {
                "case_count": len(run.case_ids),
                "metric_count": len(run.metrics),
                "categories": category_counts,
                "unknown_metrics": unknown,
                "unknown_values_are_not_imputed": True,
            },
        }

    def _run_h3_integration(self, case) -> tuple[list[EvaluationMetric], list[str], str | None]:
        from alysia.visual import VisualGenerationService

        service = VisualGenerationService(self.config)
        health = service.h3_setup_status()
        health_path = self.project_root / "evaluation" / "h3_integration_health.json"
        health_path.parent.mkdir(parents=True, exist_ok=True)
        health_path.write_text(json.dumps(health, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        artifacts = [str(health_path.relative_to(self.project_root))]
        if not health.get("ready"):
            metric = EvaluationMetric(
                metric_id=f"{case.case_id}.success",
                benchmark_case_id=case.case_id,
                value=None,
                unit="boolean",
                direction="higher_is_better",
                tolerance=case.tolerance,
                source=str(health_path),
                confidence=0.0,
                measurement_type="unknown",
                reason="H3 health unavailable; integration is blocked rather than passed",
                affected_capability="visual_h3_local",
                evidence_refs=artifacts,
            )
            return [metric], artifacts, "H3/ComfyUI health not ready"
        report = service.h3_smoke_test()
        result = report["result"]
        qa = report["qa"]
        output_files = [str(path) for path in result.get("output_files", [])]
        artifacts.extend(output_files)
        source = "workspace/visual_queue/h3_smoke_result.json"
        metrics = [
            EvaluationMetric(metric_id=f"{case.case_id}.success", benchmark_case_id=case.case_id, value=int(result.get("status") == "completed" and not result.get("mock")), unit="boolean", direction="higher_is_better", tolerance=case.tolerance, source=source, confidence=1.0, measurement_type="observed", reason="Real provider completed", affected_capability="visual_h3_local", evidence_refs=artifacts),
            EvaluationMetric(metric_id=f"{case.case_id}.visual_qa_passed", benchmark_case_id=case.case_id, value=int(bool(qa.get("passed") and qa.get("production_eligible"))), unit="boolean", direction="higher_is_better", tolerance=case.tolerance, source=source, confidence=1.0, measurement_type="observed", reason="Engineering VisualQA only; no aesthetic score", affected_capability="visual_h3_local", evidence_refs=artifacts),
            EvaluationMetric(metric_id=f"{case.case_id}.generation_time", benchmark_case_id=case.case_id, value=float(result["generation_time_sec"]), unit="seconds", direction="lower_is_better", tolerance=case.tolerance, source=source, confidence=1.0, measurement_type="observed", reason="Provider wall time", affected_capability="visual_h3_local", evidence_refs=artifacts),
        ]
        detected_vram = health.get("detected_vram")
        detected_ram = health.get("detected_ram")
        for name, snapshot, unit in (("vram_used_health_snapshot", detected_vram, "MiB"), ("ram_used_health_snapshot", detected_ram, "MiB")):
            numeric = snapshot.get("used_mb") if isinstance(snapshot, dict) and isinstance(snapshot.get("used_mb"), (int, float)) else None
            metrics.append(EvaluationMetric(
                metric_id=f"{case.case_id}.{name}", benchmark_case_id=case.case_id, value=numeric,
                unit=unit, direction="lower_is_better", tolerance=case.tolerance, source=str(health_path),
                confidence=1.0 if numeric is not None else 0.0,
                measurement_type="observed" if numeric is not None else "unknown",
                reason="Observed immediately before the explicit smoke run; not claimed as peak" if numeric is not None else "Resource measurement unavailable; value not fabricated",
                affected_capability="visual_h3_local", evidence_refs=[str(health_path.relative_to(self.project_root))],
            ))
        blocked = None if all(metric.value == 1 for metric in metrics[:2]) else "H3 smoke or VisualQA failed"
        return metrics, artifacts, blocked
