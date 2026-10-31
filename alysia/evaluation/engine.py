from __future__ import annotations

import hashlib
from numbers import Real

from alysia.evaluation.registry import BenchmarkRegistry
from alysia.schemas import (
    BaselineSnapshot,
    EvaluationComparison,
    EvaluationGateResult,
    EvaluationMetric,
    EvaluationRun,
    RegressionFinding,
)


class RegressionEngine:
    def __init__(self, registry: BenchmarkRegistry | None = None) -> None:
        self.registry = registry or BenchmarkRegistry()

    def compare(self, baseline: BaselineSnapshot, candidate: EvaluationRun) -> EvaluationComparison:
        baseline_metrics = {item.metric_id: item for item in baseline.metrics}
        candidate_metrics = {item.metric_id: item for item in candidate.metrics}
        findings: list[RegressionFinding] = []
        improvements: list[str] = []
        unchanged: list[str] = []
        unknown: list[str] = []
        for metric_id, base in sorted(baseline_metrics.items()):
            current = candidate_metrics.get(metric_id)
            if current is None or base.value is None or current.value is None:
                unknown.append(metric_id)
                if current is None:
                    findings.append(self._missing_finding(base))
                continue
            if not isinstance(base.value, Real) or not isinstance(current.value, Real):
                unchanged.append(metric_id) if base.value == current.value else unknown.append(metric_id)
                continue
            state, delta, threshold, reason = self._numeric_state(base, current)
            if state == "regression":
                case = self.registry.get(base.benchmark_case_id)
                severity = case.severity_if_regressed
                findings.append(
                    RegressionFinding(
                        metric_id=metric_id,
                        baseline=base.value,
                        candidate=current.value,
                        delta=delta,
                        threshold=threshold,
                        severity=severity,
                        affected_capability=current.affected_capability or case.category,
                        evidence_refs=sorted(set(base.evidence_refs + current.evidence_refs)),
                        gate_effect="block" if severity in {"major", "critical"} else "warn" if severity == "warning" else "none",
                        reason=reason,
                    )
                )
            elif state == "improvement":
                improvements.append(metric_id)
            else:
                unchanged.append(metric_id)
        gate = "BLOCKED" if any(item.gate_effect == "block" for item in findings) else "PASS_WITH_WARNINGS" if any(item.gate_effect == "warn" for item in findings) else "PASS"
        digest = hashlib.sha256(f"{baseline.baseline_id}|{candidate.evaluation_id}".encode()).hexdigest()[:16]
        return EvaluationComparison(
            comparison_id=f"cmp_{digest}",
            baseline_id=baseline.baseline_id,
            candidate_evaluation_id=candidate.evaluation_id,
            findings=findings,
            improvements=improvements,
            unchanged=unchanged,
            unknown=unknown,
            overall_gate_status=gate,
        )

    @staticmethod
    def _numeric_state(base: EvaluationMetric, current: EvaluationMetric) -> tuple[str, float, dict[str, float | None], str]:
        baseline = float(base.value)  # type: ignore[arg-type]
        candidate = float(current.value)  # type: ignore[arg-type]
        delta = candidate - baseline
        tolerance = current.tolerance
        allowed = max(tolerance.absolute, abs(baseline) * tolerance.relative)
        threshold = {"absolute": tolerance.absolute, "relative": tolerance.relative, "effective": allowed}
        if current.direction == "higher_is_better":
            if candidate < baseline - allowed:
                return "regression", delta, threshold, f"candidate decreased by {abs(delta):g}, beyond tolerance {allowed:g}"
            if candidate > baseline + allowed:
                return "improvement", delta, threshold, "candidate increased beyond tolerance"
        elif current.direction == "lower_is_better":
            if candidate > baseline + allowed:
                return "regression", delta, threshold, f"candidate increased by {delta:g}, beyond tolerance {allowed:g}"
            if candidate < baseline - allowed:
                return "improvement", delta, threshold, "candidate decreased beyond tolerance"
        else:
            minimum, maximum = tolerance.target_min, tolerance.target_max
            candidate_ok = (minimum is None or candidate >= minimum) and (maximum is None or candidate <= maximum)
            baseline_ok = (minimum is None or baseline >= minimum) and (maximum is None or baseline <= maximum)
            if baseline_ok and not candidate_ok:
                return "regression", delta, threshold, f"candidate {candidate:g} left target range [{minimum}, {maximum}]"
            if not baseline_ok and candidate_ok:
                return "improvement", delta, threshold, "candidate entered target range"
        return "unchanged", delta, threshold, "change is within tolerance"

    def _missing_finding(self, base: EvaluationMetric) -> RegressionFinding:
        case = self.registry.get(base.benchmark_case_id)
        return RegressionFinding(
            metric_id=base.metric_id,
            baseline=base.value if isinstance(base.value, Real) else None,
            candidate=None,
            delta=None,
            threshold={"absolute": base.tolerance.absolute, "relative": base.tolerance.relative, "effective": None},
            severity="critical",
            affected_capability=base.affected_capability or case.category,
            evidence_refs=base.evidence_refs,
            gate_effect="block",
            reason="candidate evaluation omitted a baseline metric",
        )


class EvaluationGate:
    PROTECTED: dict[str, tuple[str, float]] = {
        "research_grounding.core.coverage": ("min", 1.0),
        "knowledge_freshness_conflict.core.blocked_claim_usage": ("max", 0.0),
        "voice_intelligibility.core.audio_valid": ("min", 1.0),
        "voice_intelligibility.core.test_tone_detected": ("max", 0.0),
        "subtitle_sync_semantic_split.core.overlap_count": ("max", 0.0),
        "subtitle_sync_semantic_split.core.out_of_bounds_count": ("max", 0.0),
        "subtitle_sync_semantic_split.core.semantic_split_violations": ("max", 0.0),
        "render_stability.core.render_decodable": ("min", 1.0),
        "publish_package_correctness.core.approval_invariant": ("min", 1.0),
        "supervisor_workflow_reliability.core.approved_skill_only": ("min", 1.0),
        "supervisor_workflow_reliability.core.publish_approval_preserved": ("min", 1.0),
        "supervisor_workflow_reliability.core.budget_respected": ("min", 1.0),
        "supervisor_workflow_reliability.core.action_limit_respected": ("min", 1.0),
        "supervisor_workflow_reliability.core.knowledge_stale_blocked": ("min", 1.0),
        "supervisor_workflow_reliability.core.provider_resource_constraints": ("min", 1.0),
        "fault_recovery_reliability.core.recovery_success_rate": ("min", 1.0),
        "fault_recovery_reliability.core.unnecessary_stage_reexecution_count": ("max", 0.0),
        "fault_recovery_reliability.core.checkpoint_restore_success": ("min", 1.0),
        "fault_recovery_reliability.core.duplicate_publish_job_count": ("max", 0.0),
        "security_governance.core.unauthorized_action_block_rate": ("min", 1.0),
        "security_governance.core.approval_scope_integrity": ("min", 1.0),
        "security_governance.core.secret_redaction_success": ("min", 1.0),
        "security_governance.core.audit_event_coverage": ("min", 1.0),
        "security_governance.core.sandbox_escape_block_rate": ("min", 1.0),
    }

    def evaluate(self, comparison: EvaluationComparison, candidate: EvaluationRun) -> EvaluationGateResult:
        metrics = {item.metric_id: item for item in candidate.metrics}
        failures: list[str] = []
        for metric_id, (operator, threshold) in self.PROTECTED.items():
            metric = metrics.get(metric_id)
            if metric is None or not isinstance(metric.value, Real):
                failures.append(f"protected metric missing/unknown: {metric_id}")
                continue
            value = float(metric.value)
            if (operator == "min" and value < threshold) or (operator == "max" and value > threshold):
                failures.append(f"protected invariant failed: {metric_id}={value:g} ({operator} {threshold:g})")
        blockers = [item for item in comparison.findings if item.gate_effect == "block"]
        warnings = [item for item in comparison.findings if item.gate_effect == "warn"]
        status = "BLOCKED" if blockers or failures or candidate.status != "completed" else "PASS_WITH_WARNINGS" if warnings else "PASS"
        return EvaluationGateResult(
            evaluation_id=candidate.evaluation_id,
            baseline_id=comparison.baseline_id,
            status=status,
            blocking_findings=blockers,
            warnings=warnings,
            invariant_failures=failures,
            evidence_refs=sorted({ref for item in blockers + warnings for ref in item.evidence_refs}),
            promotion_allowed=status != "BLOCKED",
        )

    @staticmethod
    def require_promotion_allowed(result: EvaluationGateResult) -> None:
        """Capability/version promotion 的单一硬门；只阻止，不自动回滚。"""
        if result.status == "BLOCKED" or not result.promotion_allowed:
            details = [item.metric_id for item in result.blocking_findings] + result.invariant_failures
            raise PermissionError(f"EvaluationGate BLOCKED capability/version promotion: {details}")
