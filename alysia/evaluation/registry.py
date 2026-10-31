from __future__ import annotations

from alysia.schemas import BenchmarkCase, RegressionTolerance


REGISTRY_VERSION = "alpha20.1"


class BenchmarkRegistry:
    def __init__(self, cases: list[BenchmarkCase] | None = None, *, version: str = REGISTRY_VERSION) -> None:
        self.version = version
        self._cases = {case.case_id: case for case in (cases or _default_cases())}
        if len(self._cases) != len(cases or _default_cases()):
            raise ValueError("benchmark case_id 必须唯一")

    def list(self, *, include_integration: bool = True) -> list[BenchmarkCase]:
        cases = sorted(self._cases.values(), key=lambda item: item.case_id)
        return cases if include_integration else [case for case in cases if not case.integration]

    def default_cases(self) -> list[BenchmarkCase]:
        return [case for case in self.list(include_integration=False) if case.default_enabled]

    def integration_cases(self) -> list[BenchmarkCase]:
        return [case for case in self.list() if case.integration]

    def get(self, case_id: str) -> BenchmarkCase:
        try:
            return self._cases[case_id]
        except KeyError as exc:
            raise KeyError(f"未知 benchmark case：{case_id}") from exc

    @property
    def categories(self) -> list[str]:
        return sorted({case.category for case in self._cases.values()})


def _case(
    case_id: str,
    category: str,
    scorer_id: str,
    fixture: str,
    *,
    severity: str = "major",
    absolute: float = 0.0,
    relative: float = 0.0,
    expected: list[str] | None = None,
    capabilities: list[str] | None = None,
    tags: list[str] | None = None,
) -> BenchmarkCase:
    return BenchmarkCase(
        case_id=case_id,
        category=category,
        name=case_id.replace("_", " ").title(),
        description=f"Alpha18 deterministic benchmark for {category}.",
        fixture_refs=[fixture] if fixture else [],
        required_capabilities=capabilities or [category],
        expected_properties=expected or ["deterministic", "offline"],
        scorer_id=scorer_id,
        tolerance=RegressionTolerance(absolute=absolute, relative=relative),
        severity_if_regressed=severity,
        version="1.0",
        tags=tags or ["offline", "alpha18"],
    )


def _default_cases() -> list[BenchmarkCase]:
    cases = [
        _case("research_grounding.core", "research_grounding", "grounding_coverage", "research_grounding.json", severity="critical"),
        _case("knowledge_freshness_conflict.core", "knowledge_freshness_conflict", "knowledge_freshness", "knowledge_freshness_conflict.json", severity="critical"),
        _case("script_quality.core", "script_quality", "script_rubric", "script_quality.json", absolute=1.0),
        _case("storyboard_coverage.core", "storyboard_coverage", "storyboard_coverage", "storyboard_coverage.json", absolute=0.0),
        _case("voice_intelligibility.core", "voice_intelligibility", "audio_validity", "speech.wav", severity="critical"),
        _case("subtitle_sync_semantic_split.core", "subtitle_sync_semantic_split", "subtitle_timing", "subtitle_good.json", severity="critical"),
        _case("visual_h3_artifact_validity.offline", "visual_h3_artifact_validity", "visual_artifact", "visual_valid.mp4", absolute=0.0),
        _case("render_stability.core", "render_stability", "render_media", "render_valid.mp4", severity="critical"),
        _case("brand_style_consistency.core", "brand_style_consistency", "style_consistency", "style_report.json", absolute=1.0),
        _case("publish_package_correctness.core", "publish_package_correctness", "publish_package", "publish_package.json", severity="critical"),
        _case("analytics_learning_correctness.core", "analytics_learning_correctness", "analytics_learning", "analytics_learning.json", severity="critical"),
        _case("supervisor_workflow_reliability.core", "supervisor_workflow_reliability", "workflow_reliability", "workflow_supervisor.json", severity="critical"),
        _case("fault_recovery_reliability.core", "fault_recovery_reliability", "recovery_reliability", "reliability_recovery.json", severity="critical"),
        _case("security_governance.core", "security_governance", "security_governance", "security_governance.json", severity="critical"),
    ]
    cases.append(
        BenchmarkCase(
            case_id="visual_h3_artifact_validity.integration",
            category="visual_h3_artifact_validity",
            name="Local H3 explicit integration smoke",
            description="Runs the fixed local ComfyUI/H3 3-5 second smoke workflow only when explicitly requested.",
            fixture_refs=[],
            required_capabilities=["visual_h3_local", "comfyui_api", "gpu_execute"],
            expected_properties=["real_provider", "decodable", "visual_qa", "fixed_seed"],
            scorer_id="h3_integration",
            tolerance=RegressionTolerance(absolute=30.0, relative=0.25),
            severity_if_regressed="major",
            version="1.0",
            tags=["integration", "h3_local", "explicit_only"],
            default_enabled=False,
            integration=True,
        )
    )
    return cases
