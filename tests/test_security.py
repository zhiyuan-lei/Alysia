from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from alysia.capabilities.sandbox import SkillSandbox
from alysia.core.config import CoverConfig, VideoConfig
from alysia.core.io import atomic_write_json
from alysia.core.orchestrator import AlysiaOrchestrator
from alysia.publishing import PublishingService, PublishingValidationError
from alysia.reliability import FailureClassifier, RecoveryPolicyEngine
from alysia.schemas import ApprovalBoundAction, ApprovalRecord
from alysia.schemas.reliability import FailureCategory
from alysia.schemas.security import Permission, SecurityActionError
from alysia.security import PathGuard, SecurityService, ToolAllowlist
from tests.helpers import make_config


ROOT = Path(__file__).resolve().parents[1]


def _service(tmp_path: Path) -> SecurityService:
    config = make_config(tmp_path / "runs")
    config.security.audit_log_path = tmp_path / "audit" / "audit_log.jsonl"
    config.security.policy_file = ROOT / "config" / "security_policy.yaml"
    config.security.credential_reference_file = ROOT / "config" / "credential_references.yaml"
    return SecurityService(config)


def _approval(
    *, action: str = "publish", subject: str = "run-1", package_hash: str = "a" * 64,
    scope: str = "publish:mock", approved_by: str = "human:test",
    approved_at: datetime | None = None, expires_at: datetime | None = None,
) -> ApprovalRecord:
    return ApprovalRecord(
        action_type=action, subject_id=subject, run_id=subject, approved_by=approved_by,
        approved_at=approved_at or datetime.now().astimezone(), expires_at=expires_at,
        package_hash=package_hash, scope=[scope],
    )


def _bound(
    *, action: str = "publish", subject: str = "run-1", package_hash: str = "a" * 64,
    scope: str = "publish:mock", consumption_ref: str = "job-1",
) -> ApprovalBoundAction:
    return ApprovalBoundAction(
        action_type=action, subject_id=subject, artifact_hash=package_hash,
        required_scope=scope, consumption_ref=consumption_ref,
    )


def test_permission_default_deny(tmp_path: Path) -> None:
    decision = _service(tmp_path).policy.authorize(
        actor="UnknownAgent", permission=Permission.READ_ARTIFACT,
        resource="run:x", action="artifact.read",
    )
    assert decision.decision == "deny"
    assert decision.reason == "default_deny"


def test_writer_cannot_publish(tmp_path: Path) -> None:
    service = _service(tmp_path)
    decision = service.policy.authorize(
        actor="WriterAgent", permission=Permission.PUBLISH,
        resource="publish-job:x", action="publish.submit",
    )
    assert decision.decision == "deny"


def test_publisher_cannot_modify_identity(tmp_path: Path) -> None:
    decision = _service(tmp_path).policy.authorize(
        actor="PublisherAgent", permission=Permission.MODIFY_IDENTITY,
        resource="identity:v2", action="identity.apply",
    )
    assert decision.decision == "deny"


def test_researcher_network_allowed_public_only(tmp_path: Path) -> None:
    policy = _service(tmp_path).policy
    assert policy.authorize_network(
        actor="ResearcherAgent", url="https://example.com/public.json", action="research.network",
    ).decision == "allow"
    assert policy.authorize_network(
        actor="ResearcherAgent", url="http://192.168.1.10/private", action="research.network",
    ).decision == "deny"


def test_skill_sandbox_cannot_read_credentials(tmp_path: Path) -> None:
    service = _service(tmp_path)
    with pytest.raises(SecurityActionError):
        service.credentials.resolve("bilibili.official", actor="SkillSandbox")


def test_unapproved_skill_cannot_execute(tmp_path: Path) -> None:
    service = _service(tmp_path)
    sandbox = SkillSandbox(ROOT, tmp_path / "sandbox", security=service)
    with pytest.raises(PermissionError, match="unapproved"):
        sandbox.assert_execute("ffmpeg", approved_skill=False)


def test_skill_cannot_write_outside_sandbox(tmp_path: Path) -> None:
    sandbox = SkillSandbox(ROOT, tmp_path / "sandbox")
    with pytest.raises(PermissionError, match="outside_allowlist"):
        sandbox.path_for("skill-a", str(tmp_path / "outside.txt"))


def test_path_traversal_rejected(tmp_path: Path) -> None:
    sandbox = SkillSandbox(ROOT, tmp_path / "sandbox")
    with pytest.raises(PermissionError, match="path_traversal"):
        sandbox.path_for("skill-a", "../secret.txt")
    guard = PathGuard([tmp_path / "sandbox"])
    with pytest.raises(PermissionError, match="path_traversal"):
        guard.safe_resolve("../secret.txt", base=tmp_path / "sandbox", for_write=True)


def test_local_tool_allowlist() -> None:
    tools = ToolAllowlist(["ffmpeg", "python", "node"])
    assert tools.check("WorkflowRuntime", "C:/tools/ffmpeg.exe").allowed
    assert not tools.check("WorkflowRuntime", "cmd.exe").allowed


def test_secret_redaction(tmp_path: Path) -> None:
    redactor = _service(tmp_path).redactor
    value = "Authorization: Bearer TEST_SECRET_ABC123; api_key=TEST_SECRET_ABC123"
    redacted = redactor.redact(value)
    assert "TEST_SECRET_ABC123" not in redacted
    assert "[REDACTED]" in redacted


def test_secret_not_written_to_artifacts(tmp_path: Path) -> None:
    service = _service(tmp_path)
    secret = "TEST_SECRET_ABC123"
    output = tmp_path / "artifact.json"
    atomic_write_json(output, service.redactor.redact_value({"error": f"token={secret}"}))
    text = output.read_text(encoding="utf-8")
    assert secret not in text
    assert "[REDACTED]" in text


def test_audit_event_on_deny(tmp_path: Path) -> None:
    service = _service(tmp_path)
    service.policy.authorize(
        actor="WriterAgent", permission=Permission.PUBLISH,
        resource="publish-job:x", action="publish.submit",
    )
    assert service.audit.list()[-1].decision == "deny"


def test_audit_event_on_allow(tmp_path: Path) -> None:
    service = _service(tmp_path)
    service.policy.authorize(
        actor="ResearcherAgent", permission=Permission.READ_ARTIFACT,
        resource="run:x", action="artifact.read",
    )
    assert service.audit.list()[-1].decision == "allow"


def test_approval_action_scope(tmp_path: Path) -> None:
    result = _service(tmp_path).policy.approvals.validate(
        _approval(action="identity_change", scope="identity:p1:v1"), _bound(),
    )
    assert not result.valid
    assert "approval_action_mismatch" in result.errors


def test_approval_package_hash_mismatch(tmp_path: Path) -> None:
    result = _service(tmp_path).policy.approvals.validate(
        _approval(package_hash="b" * 64), _bound(package_hash="a" * 64),
    )
    assert "approval_artifact_hash_mismatch" in result.errors


def test_approval_replay_rejected(tmp_path: Path) -> None:
    validator = _service(tmp_path).policy.approvals
    approval = _approval()
    validator.consume(approval, _bound(consumption_ref="job-1"))
    result = validator.validate(approval, _bound(consumption_ref="job-2"))
    assert not result.valid and result.replay


def test_expired_approval_rejected(tmp_path: Path) -> None:
    now = datetime.now().astimezone()
    approval = _approval(approved_at=now - timedelta(hours=2), expires_at=now - timedelta(hours=1))
    assert "approval_expired" in _service(tmp_path).policy.approvals.validate(approval, _bound()).errors


def test_publish_requires_valid_approval(tmp_path: Path) -> None:
    decision = _service(tmp_path).policy.authorize(
        actor="PublisherAgent", permission=Permission.PUBLISH,
        resource="publish-job:x", action="publish.submit",
        approval=_approval(package_hash="b" * 64), approval_action=_bound(),
    )
    assert decision.decision == "require_approval"


@pytest.fixture(scope="module")
def secure_publish_run(tmp_path_factory):
    root = tmp_path_factory.mktemp("alpha20-publish")
    config = make_config(root / "runs")
    config.video = VideoConfig(renderer="mock", width=640, height=360, fps=30)
    config.publish.cover = CoverConfig(width=640, height=360, format="png")
    config.security.audit_log_path = root / "audit" / "audit_log.jsonl"
    config.security.policy_file = ROOT / "config" / "security_policy.yaml"
    config.security.credential_reference_file = ROOT / "config" / "credential_references.yaml"
    orchestrator = AlysiaOrchestrator(config)
    state = asyncio.run(orchestrator.create("Alpha20 安全发布测试"))
    state = asyncio.run(orchestrator.resume(state.run_id))
    state = asyncio.run(orchestrator.render(state.run_id))
    state = asyncio.run(orchestrator.package(state.run_id))
    state = asyncio.run(orchestrator.publish_check(state.run_id))
    return config, state


def test_publish_mock_also_uses_policy_gate(secure_publish_run) -> None:
    config, state = secure_publish_run
    service = PublishingService(config)
    with pytest.raises(PublishingValidationError):
        service.submit(state.run_id, provider="mock")
    service.approve(state.run_id, approved_by="human:test")
    job = service.submit(state.run_id, provider="mock")
    assert job.status == "submitted"
    assert any(event.action == "publish.submit" and event.decision == "allow" for event in service.security.audit.list())


def test_identity_change_requires_approval(tmp_path: Path) -> None:
    service = _service(tmp_path)
    decision = service.policy.authorize(
        actor="Supervisor", permission=Permission.MODIFY_IDENTITY,
        resource="identity:p1", action="identity_change.apply",
    )
    assert decision.decision == "require_approval"
    with pytest.raises(SecurityActionError):
        service.authorize_governed_change(
            actor="Supervisor", permission=Permission.MODIFY_IDENTITY,
            action_type="identity_change", subject_id="p1", payload={"x": 1},
            approved_by="system", scope="identity:p1:v1",
        )


def test_budget_change_requires_approval(tmp_path: Path) -> None:
    service = _service(tmp_path)
    decision = service.policy.authorize(
        actor="Supervisor", permission=Permission.MODIFY_BUDGET,
        resource="budget:channel", action="budget_change.apply",
    )
    assert decision.decision == "require_approval"


def test_skill_approval_requires_correct_scope(tmp_path: Path) -> None:
    service = _service(tmp_path)
    approval = _approval(action="skill_approval", subject="skill-a", scope="skill:skill-b:eval-1")
    action = _bound(action="skill_approval", subject="skill-a", scope="skill:skill-a:eval-1")
    assert "approval_scope_mismatch" in service.policy.approvals.validate(approval, action).errors


@pytest.mark.parametrize("actor", [
    "Supervisor", "StudioDirector", "ResearcherAgent", "WriterAgent", "PublisherAgent",
    "SkillSandbox", "WorkflowRuntime", "ComfyUI/H3 provider adapter",
])
def test_system_config_denied_for_agents(tmp_path: Path, actor: str) -> None:
    decision = _service(tmp_path).policy.authorize(
        actor=actor, permission=Permission.SYSTEM_CONFIG,
        resource="system:config", action="system.configure",
    )
    assert decision.decision == "deny"


def test_policy_violation_not_retried_forever() -> None:
    failure = FailureClassifier.record(
        RuntimeError("policy_violation: denied"), run_id="run-1", stage="security",
    )
    assert failure.category == FailureCategory.POLICY_VIOLATION
    assert not failure.retryable
    assert RecoveryPolicyEngine().decide(failure).action == "terminal_fail"


def test_security_audit_redacts_credentials(tmp_path: Path) -> None:
    service = _service(tmp_path)
    secret = "TEST_SECRET_ABC123"
    service.audit.record(
        actor="PublisherAgent", action="credential.test", resource="credential-ref:test",
        permission=Permission.READ_CREDENTIAL_REF, decision="allow", result="test",
        context={"Authorization": f"Bearer {secret}", "cookie": secret, "message": f"token={secret}"},
    )
    text = service.audit.path.read_text(encoding="utf-8")
    assert secret not in text
    assert "[REDACTED]" in text


def test_security_scan_fixture_redacts_findings(tmp_path: Path) -> None:
    target = tmp_path / "fixture"
    target.mkdir()
    (target / ".env").write_text("API_KEY=TEST_SECRET_ABC123\n", encoding="utf-8")
    (target / "app.log").write_text("Authorization: Bearer TEST_SECRET_ABC123\n", encoding="utf-8")
    report = _service(tmp_path).scanner.scan(target)
    assert report.findings
    encoded = json.dumps(report.model_dump(mode="json"), default=str)
    assert "TEST_SECRET_ABC123" not in encoded
