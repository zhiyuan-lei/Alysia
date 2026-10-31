from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from alysia.capabilities import (
    CapabilityGapDetector,
    CapabilityRegistry,
    CapabilityService,
    SelfEvaluationEngine,
    SkillAcquisitionService,
    SkillRegistry,
    SkillSandbox,
)
from alysia.capabilities.gaps import CapabilityGapStore
from alysia.production import ProductionPlanner
from alysia.production.registry import ProviderCapabilityRegistry
from alysia.schemas import (
    CapabilityGap,
    EvaluationEvidence,
    ProductionProfile,
    ProviderCapability,
    SelfEvaluationReport,
    SkillSecurityPolicy,
)
from alysia.studio.registry import AgentRegistry
from tests.helpers import make_config


def _service(tmp_path: Path) -> CapabilityService:
    config = make_config(tmp_path / "runs")
    config.capability.root_dir = tmp_path / "capabilities"
    config.capability.sandbox_dir = tmp_path / "sandbox"
    config.capability.evidence_files = [Path("evaluation/capability_evidence_alpha14.json").resolve()]
    return CapabilityService(config)


def _gap(root: Path, *, h3: bool = False) -> CapabilityGap:
    gap = CapabilityGap(
        gap_id="gap_h3" if h3 else "gap_audio",
        description="本地 H3 尚未实测" if h3 else "真实中文旁白门禁不足",
        evidence_runs=["demo_alpha13_5" if h3 else "historical_alpha5_video"],
        evidence_ids=["evidence_h3" if h3 else "evidence_audio"],
        affected_agents=["designer", "editor"] if h3 else ["voice"],
        severity="medium" if h3 else "critical", frequency=1 if h3 else 2,
        current_workaround="人工审核", proposed_capability="verified_h3_local_generation" if h3 else "real_tts_speech_validation",
        confidence=0.8,
    )
    CapabilityGapStore(root).save(gap)
    return gap


def _pipeline(tmp_path: Path, *, h3: bool = False) -> tuple[SkillAcquisitionService, CapabilityGap]:
    root = tmp_path / "capabilities"
    gap = _gap(root, h3=h3)
    sandbox = SkillSandbox(tmp_path, tmp_path / "sandbox", SkillSecurityPolicy())
    return SkillAcquisitionService(root, sandbox), gap


def test_capability_registry(tmp_path: Path) -> None:
    registry = CapabilityRegistry(tmp_path)
    capabilities = registry.bootstrap()
    assert len(capabilities) >= 15
    assert registry.get("visual_h3_local").maturity == "experimental"


def test_self_evaluation(tmp_path: Path) -> None:
    registry = CapabilityRegistry(tmp_path)
    evidence = [
        EvaluationEvidence(
            evidence_id="audio1", source="manual", kind="observed_failure",
            summary="噪音", capability_id="audio_qa", severity="critical", data={"occurrences": 2},
        )
    ]
    report = SelfEvaluationEngine().evaluate(registry, evidence)
    assert "audio_qa" in report.weak_capabilities
    assert report.cause_hypotheses
    assert report.evidence[0].kind == "observed_failure"


def test_gap_detection_from_failures(tmp_path: Path) -> None:
    service = _service(tmp_path)
    report = service.evaluate()
    gaps = service.list_gaps()
    assert report.evidence
    assert any("旁白" in gap.description for gap in gaps)


def test_gap_requires_evidence() -> None:
    report = SelfEvaluationReport(
        report_id="empty", confidence=0.1, created_at=datetime.now().astimezone()
    )
    assert CapabilityGapDetector().detect(report) == []


def test_skill_proposal(tmp_path: Path) -> None:
    pipeline, gap = _pipeline(tmp_path)
    proposal = pipeline.propose(gap.gap_id)
    assert proposal.approval_required and proposal.sandbox_required
    assert proposal.state == "PROPOSED"
    assert pipeline.registry.available() == []


def test_skill_sandbox_path_guard(tmp_path: Path) -> None:
    sandbox = SkillSandbox(tmp_path, tmp_path / "sandbox")
    with pytest.raises(PermissionError):
        sandbox.path_for("safe_skill", "../../outside")


def test_skill_cannot_modify_core_without_permission(tmp_path: Path) -> None:
    sandbox = SkillSandbox(tmp_path, tmp_path / "sandbox")
    with pytest.raises(PermissionError, match="核心源码"):
        sandbox.assert_operation(core_write=True)
    with pytest.raises(PermissionError, match="网络"):
        sandbox.assert_operation(network=True)


def test_skill_evaluation(tmp_path: Path) -> None:
    pipeline, gap = _pipeline(tmp_path)
    proposal = pipeline.propose(gap.gap_id)
    report = pipeline.test(proposal.skill_id)
    assert report.passed and report.score == 1
    assert {case.category for case in report.cases} == {"functional", "quality", "regression", "resource", "security"}


def test_skill_requires_approval(tmp_path: Path) -> None:
    pipeline, gap = _pipeline(tmp_path)
    proposal = pipeline.propose(gap.gap_id)
    pipeline.test(proposal.skill_id)
    assert pipeline.registry.available() == []
    with pytest.raises(RuntimeError):
        pipeline.approve(proposal.skill_id, approved_by="human:test")
    pipeline.review(proposal.skill_id)
    record = pipeline.approve(proposal.skill_id, approved_by="human:test")
    assert record.status == "active"


def test_skill_registry_versioning(tmp_path: Path) -> None:
    pipeline, gap = _pipeline(tmp_path)
    first = pipeline.propose(gap.gap_id)
    pipeline.test(first.skill_id)
    pipeline.review(first.skill_id)
    v1 = pipeline.approve(first.skill_id, approved_by="human:v1")
    second = pipeline.propose(gap.gap_id)
    assert second.state == "PROPOSED"
    pipeline.test(second.skill_id)
    pipeline.review(second.skill_id)
    v2 = pipeline.approve(second.skill_id, approved_by="human:v2")
    assert (v1.version, v2.version) == (1, 2)
    assert [item.status for item in pipeline.registry.versions(first.skill_id)] == ["deprecated", "active"]


def test_skill_rollback(tmp_path: Path) -> None:
    pipeline, gap = _pipeline(tmp_path)
    for reviewer in ("human:v1", "human:v2"):
        proposal = pipeline.propose(gap.gap_id)
        pipeline.test(proposal.skill_id)
        pipeline.review(proposal.skill_id)
        pipeline.approve(proposal.skill_id, approved_by=reviewer)
    rolled = pipeline.rollback("real_tts_speech_gate", 1)
    assert rolled.version == 1 and rolled.status == "active"
    assert pipeline.registry.active("real_tts_speech_gate").version == 1


def test_unapproved_skill_not_available_to_agents(tmp_path: Path) -> None:
    pipeline, gap = _pipeline(tmp_path)
    pipeline.propose(gap.gap_id)
    assert AgentRegistry().available_skills("voice", pipeline.registry) == []


def test_production_planner_reads_skill_requirements() -> None:
    providers = ProviderCapabilityRegistry([
        ProviderCapability(provider_id="visual.mock", task_types=["visual_generation"], local_or_cloud="mock", health_status="healthy"),
        ProviderCapability(provider_id="render.mock", task_types=["render"], local_or_cloud="mock", health_status="healthy"),
        ProviderCapability(provider_id="deterministic.video_qa", task_types=["video_qa"], local_or_cloud="local", health_status="healthy"),
    ])
    profile = ProductionProfile(
        required_skills=["h3_visual_generation"],
        skill_resource_requirements={"h3_visual_generation": {"gpu_heavy": True, "peak_vram_mb": "unknown"}},
    )
    planner = ProductionPlanner(
        providers, make_config(Path("runs-test")).optimization,
        approved_skills={"h3_visual_generation": {"status": "active", "resource_requirements": {"gpu_heavy": True}}},
    )
    plan = planner.generate(run_id="run", profile=profile, requested_operation="video")
    assert not plan.policy_blockers
    assert any("h3_visual_generation" in note for note in plan.expected_resource_notes)


def test_supervisor_cannot_self_approve_skill(tmp_path: Path) -> None:
    pipeline, gap = _pipeline(tmp_path)
    proposal = pipeline.propose(gap.gap_id)
    pipeline.test(proposal.skill_id)
    pipeline.review(proposal.skill_id)
    with pytest.raises(PermissionError, match="human"):
        pipeline.approve(proposal.skill_id, approved_by="supervisor")


def test_alpha13_5_h3_skill_evaluation(tmp_path: Path) -> None:
    pipeline, gap = _pipeline(tmp_path, h3=True)
    proposal = pipeline.propose(gap.gap_id)
    report = pipeline.test(proposal.skill_id, observations={"resource_source": "alpha13.5 mock smoke; real peak unknown"})
    assert proposal.skill_id == "h3_visual_generation"
    assert report.passed
    assert report.resource_observations["peak_vram_mb"] == "unknown"


def test_skill_pipeline_idempotent(tmp_path: Path) -> None:
    pipeline, gap = _pipeline(tmp_path)
    first = pipeline.propose(gap.gap_id)
    second = pipeline.propose(gap.gap_id)
    assert first == second
    evaluation1 = pipeline.test(first.skill_id)
    evaluation2 = pipeline.test(first.skill_id)
    assert evaluation1.evaluation_id == evaluation2.evaluation_id
