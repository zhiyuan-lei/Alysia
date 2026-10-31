from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from alysia.cli import app
from alysia.core.config import load_config
from alysia.evaluation.engine import EvaluationGate, RegressionEngine
from alysia.evaluation.fingerprint import environment_snapshot, fixture_manifest_hash, worktree_fingerprint
from alysia.evaluation.matrix import REGRESSION_MATRIX, matrix_invariant_ids
from alysia.evaluation.registry import BenchmarkRegistry
from alysia.evaluation.service import EvaluationService
from alysia.evaluation.scorers import VisualArtifactScorer
from alysia.evaluation.store import EvaluationStore
from alysia.schemas import (
    BaselineSnapshot,
    BenchmarkCase,
    EvaluationMetric,
    EvaluationRun,
    RegressionTolerance,
    RubricDimension,
)


ROOT = Path(__file__).parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "evaluation"
runner = CliRunner()


def _case(*, severity: str = "major", tolerance: RegressionTolerance | None = None) -> BenchmarkCase:
    return BenchmarkCase(
        case_id="test.metric",
        category="test",
        name="Test metric",
        description="Deterministic test case",
        scorer_id="unused",
        tolerance=tolerance or RegressionTolerance(),
        severity_if_regressed=severity,
        version="1.0",
    )


def _metric(value: float | None, *, direction: str = "higher_is_better", tolerance: RegressionTolerance | None = None) -> EvaluationMetric:
    return EvaluationMetric(
        metric_id="test.metric.value",
        benchmark_case_id="test.metric",
        value=value,
        unit="score",
        direction=direction,
        tolerance=tolerance or RegressionTolerance(),
        source="test",
        confidence=0.0 if value is None else 1.0,
        measurement_type="unknown" if value is None else "observed",
    )


def _evaluation(metric: EvaluationMetric, evaluation_id: str = "candidate") -> EvaluationRun:
    config = load_config()
    return EvaluationRun(
        evaluation_id=evaluation_id,
        created_at=datetime.now().astimezone(),
        code_worktree_fingerprint="fingerprint",
        benchmark_registry_version="test-v1",
        metrics=[metric],
        environment_snapshot=environment_snapshot(config),
        status="completed",
        case_ids=["test.metric"],
        fixture_manifest_hash="fixtures",
    )


def _baseline(metric: EvaluationMetric) -> BaselineSnapshot:
    config = load_config()
    return BaselineSnapshot(
        baseline_id="baseline",
        version="test",
        created_at=datetime.now().astimezone(),
        evaluation_id="base-eval",
        worktree_fingerprint="fingerprint",
        benchmark_registry_version="test-v1",
        environment_snapshot=environment_snapshot(config),
        metrics=[metric],
    )


def _service(tmp_path: Path) -> EvaluationService:
    return EvaluationService(load_config(), project_root=ROOT, store=EvaluationStore(tmp_path / "evaluation"))


def test_benchmark_case_schema() -> None:
    case = _case()
    assert case.version == "1.0"
    assert case.fixture_refs == []
    with pytest.raises(ValidationError):
        BenchmarkCase(case_id="BAD ID", category="x", name="x", description="x", scorer_id="x", version="1")


def test_metric_schema() -> None:
    metric = _metric(1)
    assert metric.direction == "higher_is_better"
    with pytest.raises(ValidationError):
        EvaluationMetric(metric_id="m", benchmark_case_id="c", value=0.5, unit="ratio", direction="higher_is_better", source="x", confidence=1, measurement_type="unknown")


def test_registry_versioning() -> None:
    registry = BenchmarkRegistry()
    assert registry.version == "alpha20.1"
    assert len(registry.list()) == 15
    assert len(registry.default_cases()) == 14
    assert all(case.version for case in registry.list())
    assert len({case.case_id for case in registry.list()}) == len(registry.list())


def test_golden_fixture_stability() -> None:
    paths = [path for path in FIXTURES.iterdir() if path.is_file()]
    first = fixture_manifest_hash(ROOT, paths)
    second = fixture_manifest_hash(ROOT, list(reversed(paths)))
    assert first == second
    assert (FIXTURES / "speech.wav").stat().st_size > 10000
    assert (FIXTURES / "visual_corrupt.mp4").is_file()


def test_visual_golden_valid_and_corrupt() -> None:
    case = BenchmarkRegistry().get("visual_h3_artifact_validity.offline")
    scorer = VisualArtifactScorer()
    assert scorer.score(case, [FIXTURES / "visual_valid.mp4"])[0].value == 1
    assert scorer.score(case, [FIXTURES / "visual_corrupt.mp4"])[0].value == 0


def test_baseline_snapshot(tmp_path: Path) -> None:
    service = _service(tmp_path)
    baseline = service.create_baseline()
    assert baseline.metrics
    assert service.store.get_baseline(baseline.baseline_id) == baseline
    assert baseline.worktree_fingerprint == service.store.get_run(baseline.evaluation_id).code_worktree_fingerprint


def test_worktree_fingerprint_stable(tmp_path: Path) -> None:
    first = worktree_fingerprint(ROOT)
    (tmp_path / "unrelated-evaluation-output.json").write_text("{}", encoding="utf-8")
    second = worktree_fingerprint(ROOT)
    assert first == second


def test_regression_absolute_threshold() -> None:
    tolerance = RegressionTolerance(absolute=1)
    registry = BenchmarkRegistry([_case(tolerance=tolerance)], version="test-v1")
    comparison = RegressionEngine(registry).compare(_baseline(_metric(10, tolerance=tolerance)), _evaluation(_metric(8, tolerance=tolerance)))
    assert comparison.overall_gate_status == "BLOCKED"
    assert comparison.findings[0].delta == -2


def test_regression_relative_threshold() -> None:
    tolerance = RegressionTolerance(relative=0.1)
    registry = BenchmarkRegistry([_case(tolerance=tolerance)], version="test-v1")
    comparison = RegressionEngine(registry).compare(_baseline(_metric(100, tolerance=tolerance)), _evaluation(_metric(89, tolerance=tolerance)))
    assert comparison.findings[0].threshold["effective"] == 10


def test_regression_directionality() -> None:
    registry = BenchmarkRegistry([_case()], version="test-v1")
    lower = RegressionEngine(registry).compare(_baseline(_metric(1, direction="lower_is_better")), _evaluation(_metric(2, direction="lower_is_better")))
    higher = RegressionEngine(registry).compare(_baseline(_metric(1)), _evaluation(_metric(2)))
    assert lower.findings
    assert higher.improvements == ["test.metric.value"]


def test_critical_regression_blocks_gate(tmp_path: Path) -> None:
    service = _service(tmp_path)
    baseline = service.create_baseline()
    candidate = service.run(label="regression", regression_injection="subtitle_timing")
    comparison = service.compare(baseline.baseline_id, candidate.evaluation_id)
    gate = service.gate(candidate.evaluation_id, baseline_id=baseline.baseline_id)
    assert comparison.overall_gate_status == "BLOCKED"
    assert gate.status == "BLOCKED"
    assert not gate.promotion_allowed
    assert any("subtitle" in item.metric_id for item in gate.blocking_findings)
    with pytest.raises(PermissionError, match="BLOCKED capability/version promotion"):
        EvaluationGate.require_promotion_allowed(gate)


def test_warning_does_not_block_gate() -> None:
    case = _case(severity="warning")
    registry = BenchmarkRegistry([case], version="test-v1")
    comparison = RegressionEngine(registry).compare(_baseline(_metric(2)), _evaluation(_metric(1)))
    assert comparison.overall_gate_status == "PASS_WITH_WARNINGS"
    assert comparison.findings[0].gate_effect == "warn"


def test_no_fabricated_unknown_metric(tmp_path: Path) -> None:
    metric = _metric(None)
    assert metric.value is None and metric.confidence == 0
    service_metric = next(item for item in _service(tmp_path).run(label="unknown-check").metrics if item.metric_id.endswith("asr_text_similarity"))
    assert service_metric.measurement_type == "unknown"
    assert service_metric.value is None


def test_rubric_has_dimension_breakdown(tmp_path: Path) -> None:
    run = _service(tmp_path).run(label="rubric")
    rubric = next(item for item in run.metrics if item.measurement_type == "rubric")
    assert rubric.rubric_dimensions
    assert all(isinstance(item, RubricDimension) and item.reason for item in rubric.rubric_dimensions)


def test_h3_integration_marker_isolated() -> None:
    registry = BenchmarkRegistry()
    assert not any(case.integration for case in registry.default_cases())
    integration = registry.integration_cases()
    assert len(integration) == 1
    assert {"integration", "h3_local", "explicit_only"} <= set(integration[0].tags)


def test_evaluation_run_idempotent(tmp_path: Path) -> None:
    service = _service(tmp_path)
    first = service.run(label="idempotent")
    second = service.run(label="idempotent")
    assert first.evaluation_id == second.evaluation_id
    assert first.created_at == second.created_at


def test_regression_matrix_core_invariants() -> None:
    registry = BenchmarkRegistry()
    registered = {case.case_id for case in registry.list()}
    assert len(REGRESSION_MATRIX) == 26
    assert len(matrix_invariant_ids()) == 26
    for row in REGRESSION_MATRIX:
        assert row["tests"] and row["evaluation_cases"]
        assert all((ROOT / ref.split("::", 1)[0]).is_file() for ref in row["tests"])
        assert set(row["evaluation_cases"]) <= registered


def test_cli_eval_list_and_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(ROOT)
    listed = runner.invoke(app, ["eval", "list", "--offline-only"])
    assert listed.exit_code == 0
    assert "research_grounding.core" in listed.stdout


def test_normal_candidate_passes_gate(tmp_path: Path) -> None:
    service = _service(tmp_path)
    baseline = service.create_baseline()
    candidate = service.run(label="normal-candidate")
    gate = service.gate(candidate.evaluation_id, baseline_id=baseline.baseline_id)
    assert gate.status == "PASS"
    assert gate.promotion_allowed
    EvaluationGate.require_promotion_allowed(gate)
