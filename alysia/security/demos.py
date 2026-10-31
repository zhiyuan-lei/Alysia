from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from alysia.capabilities.sandbox import SkillSandbox
from alysia.core.config import AlysiaConfig
from alysia.core.io import atomic_write_json, atomic_write_text
from alysia.providers.publishing import MockPublishingProvider
from alysia.schemas import ApprovalBoundAction, ApprovalRecord, PublishJob, PublishPackage
from alysia.schemas.security import Permission

from .service import SecurityService


def run_security_demos(config: AlysiaConfig, evidence_dir: Path | None = None) -> dict[str, object]:
    root = (evidence_dir or Path("evaluation/security_demos/alpha20_gate")).resolve()
    root.mkdir(parents=True, exist_ok=True)
    demo_config = config.model_copy(deep=True)
    demo_config.security.audit_log_path = root / "audit_log.jsonl"
    security = SecurityService(demo_config)

    writer_called = False
    writer = security.policy.authorize(
        actor="WriterAgent", permission=Permission.PUBLISH,
        resource="publish-job:demo-a", action="publish.submit", correlation_id="demo-a",
    )
    demo_a = {
        "status": "PASS" if writer.decision == "deny" and not writer_called else "FAIL",
        "decision": writer.model_dump(mode="json"), "provider_called": writer_called,
    }

    sandbox_root = root / "sandbox"
    sandbox = SkillSandbox(Path.cwd(), sandbox_root, security=security)
    credential_denied = False
    traversal_denied = False
    try:
        security.credentials.resolve("bilibili.official", actor="SkillSandbox", correlation_id="demo-b")
    except (PermissionError, KeyError):
        credential_denied = True
    try:
        sandbox.path_for("demo_skill", "../credential_references.yaml")
    except PermissionError:
        traversal_denied = True
    demo_b = {
        "status": "PASS" if credential_denied and traversal_denied else "FAIL",
        "credential_denied": credential_denied, "path_traversal_denied": traversal_denied,
    }

    correct_hash = "a" * 64
    old_approval = ApprovalRecord(
        action_type="publish", subject_id="demo-run", run_id="demo-run",
        approved_by="human:demo", approved_at=datetime.now().astimezone(),
        package_hash="b" * 64, scope=["publish:mock"],
    )
    invalid_action = ApprovalBoundAction(
        action_type="publish", subject_id="demo-run", artifact_hash=correct_hash,
        required_scope="publish:mock", consumption_ref="demo-c-job",
    )
    invalid = security.policy.authorize(
        actor="PublisherAgent", permission=Permission.PUBLISH,
        resource="publish-job:demo-c", action="publish.submit",
        approval=old_approval, approval_action=invalid_action, correlation_id="demo-c",
    )
    demo_c = {
        "status": "PASS" if invalid.decision == "require_approval" and "hash" in invalid.reason else "FAIL",
        "decision": invalid.model_dump(mode="json"), "provider_called": False,
    }

    video = root / "demo_d.mp4"
    cover = root / "demo_d.png"
    atomic_write_text(video, "mock-video-evidence")
    atomic_write_text(cover, "mock-cover-evidence")
    package = PublishPackage(
        title="Alpha20 安全演示", description="仅用于离线 Mock Gate 演示。", tags=["Alpha20"],
        category="测试", cover_path=cover, video_path=video, duration_sec=1,
        language="zh-CN", generated_at=datetime.now().astimezone(), qa_status="passed",
    )
    approval = ApprovalRecord(
        action_type="publish", subject_id="demo-run-d", run_id="demo-run-d",
        approved_by="human:demo", approved_at=datetime.now().astimezone(),
        package_hash=correct_hash, scope=["publish:mock"],
    )
    job = PublishJob(
        job_id="demo-d-job", run_id="demo-run-d", provider="mock", status="approved",
        package_path=root / "package.json", package_hash=correct_hash,
        approval_record=approval, created_at=datetime.now().astimezone(),
        updated_at=datetime.now().astimezone(),
    )
    valid_action = ApprovalBoundAction(
        action_type="publish", subject_id="demo-run-d", artifact_hash=correct_hash,
        required_scope="publish:mock", consumption_ref=job.job_id,
    )
    allowed = security.policy.enforce(
        actor="PublisherAgent", permission=Permission.PUBLISH,
        resource=f"publish-job:{job.job_id}", action="publish.submit",
        approval=approval, approval_action=valid_action, correlation_id="demo-d",
    )
    security.policy.approvals.consume(approval, valid_action)
    external_id = MockPublishingProvider().submit(job, package, video_path=video, cover_path=cover)
    security.audit.record(
        actor="PublisherAgent", action="publish.provider", resource=f"publish-job:{job.job_id}",
        permission=Permission.PUBLISH, decision="allow", result="submitted",
        approval_ref=approval.approval_id, correlation_id="demo-d",
        context={"external_id": external_id},
    )
    demo_d = {
        "status": "PASS" if allowed.decision == "allow" and external_id.startswith("mock_bv_") else "FAIL",
        "decision": allowed.model_dump(mode="json"), "provider_called": True,
        "external_id": external_id,
    }

    fake_secret = "TEST_SECRET_ABC123"
    raw_message = f"Authorization: Bearer {fake_secret}; api_key={fake_secret}"
    redacted = security.redactor.redact(raw_message)
    leakage_path = root / "fake_secret_redaction.json"
    atomic_write_json(leakage_path, {"message": redacted, "raw_secret_present": fake_secret in redacted})
    leakage = {
        "status": "PASS" if fake_secret not in redacted and "[REDACTED]" in redacted else "FAIL",
        "evidence": str(leakage_path),
    }

    summary = {
        "status": "PASS" if all(item["status"] == "PASS" for item in (demo_a, demo_b, demo_c, demo_d, leakage)) else "FAIL",
        "demo_a_writer_publish_denied": demo_a,
        "demo_b_sandbox_denied": demo_b,
        "demo_c_invalid_approval_denied": demo_c,
        "demo_d_valid_mock_publish_allowed": demo_d,
        "fake_secret_redaction": leakage,
        "audit_log": str(security.audit.path),
        "audit_events": len(security.audit.list()),
    }
    atomic_write_json(root / "summary.json", summary, backup_count=2)
    return summary
