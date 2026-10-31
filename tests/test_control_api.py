from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from alysia.control import ControlCenterService, create_control_app
from alysia.control.server import DEFAULT_HOST
from alysia.core.run import RunManager
from alysia.creator import CreatorQAReport
from alysia.publishing import PublishingService
from alysia.schemas.security import Permission
from tests.helpers import make_config


@pytest.fixture()
def control(tmp_path: Path):
    config = make_config(tmp_path / "runs")
    config.security.audit_log_path = tmp_path / "audit" / "audit_log.jsonl"
    config.capability.root_dir = tmp_path / "capabilities"
    config.capability.sandbox_dir = tmp_path / "sandbox"
    config.supervisor.root_dir = tmp_path / "supervisor"
    config.workflow.recipe_dir = tmp_path / "recipes"
    service = ControlCenterService(config)
    client = TestClient(create_control_app(config, service=service, static_dir=tmp_path / "missing-static"))
    health = client.get("/api/health")
    token = health.json()["csrf_token"]
    return config, service, client, {"X-Alysia-CSRF": token}


def create_run(service: ControlCenterService, *, topic: str = "Control Center API test"):
    return service.manager.create(topic, {"llm": {"provider": "mock"}})


def test_control_api_local_bind_default():
    assert DEFAULT_HOST == "127.0.0.1"


def test_api_run_read(control):
    _config, service, client, _headers = control
    state = create_run(service)
    response = client.get(f"/api/runs/{state.run_id}")
    assert response.status_code == 200
    assert response.json()["summary"]["topic"] == "Control Center API test"
    assert response.json()["timeline"][0]["label"] == "Topic"


def test_api_testing_provenance_is_explicit(control):
    _config, service, client, _headers = control
    state = service.manager.create("Testing provenance", {"testing": True, "environment": "MOCK"})
    response = client.get(f"/api/runs/{state.run_id}")
    assert response.status_code == 200
    assert response.json()["summary"]["testing"] is True


def test_api_bad_run_id(control):
    _config, _service, client, _headers = control
    assert client.get("/api/runs/not%2Fa%2Frun").status_code in {404, 400}


def test_api_artifact_path_guard(control, tmp_path: Path):
    _config, service, client, _headers = control
    state = create_run(service)
    (tmp_path / "outside.txt").write_text("private", encoding="utf-8")
    state.artifacts["evil"] = "../outside.txt"
    service.manager.save(state)
    response = client.get(f"/api/runs/{state.run_id}/artifacts")
    assert response.status_code == 403
    assert "越界" in response.json()["detail"]


def test_api_no_secret_fields(control):
    _config, service, client, _headers = control
    service.security.audit.record(
        actor="ControlCenterAdapter", action="test", resource="test",
        permission=Permission.READ_ARTIFACT, decision="allow", result="ok",
        context={"token": "super-secret-token", "safe": "visible"},
    )
    body = client.get("/api/audit").text
    assert "super-secret-token" not in body
    assert "[REDACTED]" in body


def test_api_resume_uses_recovery_service(control, monkeypatch):
    _config, service, client, headers = control
    state = create_run(service)
    calls: list[str] = []
    monkeypatch.setattr(service.reliability, "diagnose", lambda run_id: calls.append(run_id) or {})

    async def fake_resume(_orchestrator, run_id, *, force=False):
        del force
        return service.manager.load(run_id)

    monkeypatch.setattr("alysia.control.service.AlysiaOrchestrator.resume", fake_resume)
    response = client.post(f"/api/runs/{state.run_id}/resume", headers=headers, json={"confirmed": True})
    assert response.status_code == 200
    assert calls == [state.run_id]


def _approval(kind: str = "publish") -> dict:
    return {
        "id": f"{kind}:subject_1", "kind": kind, "action": kind.title(),
        "subject": "subject_1", "subject_id": "subject_1",
        "scope": f"{kind}:subject_1:v1", "hash": "a" * 64, "version": "v1",
        "state": "pending", "risk": "high", "context": "MOCK",
        "requested_at": "2026-08-09T00:00:00+08:00", "expires_at": None, "warnings": [],
    }


def test_api_approval_uses_policy_gate(control, monkeypatch):
    _config, service, client, headers = control
    record = _approval()
    monkeypatch.setattr(service, "approvals", lambda: [record])
    called = []
    monkeypatch.setattr(PublishingService, "approve", lambda _self, run_id, approved_by, note=None: called.append((run_id, approved_by)) or {"status": "approved"})
    response = client.post(
        "/api/approvals/publish:subject_1/approve", headers=headers,
        json={"confirmed": True, "expected_hash": record["hash"], "expected_scope": record["scope"], "expected_version": record["version"], "actor": "human:test"},
    )
    assert response.status_code == 200
    assert called == [("subject_1", "human:test")]
    event = service.security.audit.list()[-1]
    assert event.action == "control.approval.approve"
    assert event.redacted_context["package_hash"] == record["hash"]


def test_api_invalid_approval_rejected(control, monkeypatch):
    _config, service, client, headers = control
    record = _approval()
    monkeypatch.setattr(service, "approvals", lambda: [record])
    response = client.post(
        "/api/approvals/publish:subject_1/approve", headers=headers,
        json={"confirmed": True, "expected_hash": "b" * 64, "expected_scope": record["scope"], "expected_version": record["version"], "actor": "human:test"},
    )
    assert response.status_code == 403
    assert "approval_artifact_hash_mismatch" in response.json()["detail"]


def test_api_publish_cannot_bypass_gate(control):
    _config, _service, client, headers = control
    assert client.post("/api/publish", headers=headers, json={"confirmed": True}).status_code == 404


def test_api_skill_approval_scope(control):
    _config, service, _client, _headers = control
    record = _approval("skill")
    with pytest.raises(PermissionError, match="approval_scope_mismatch"):
        service._validate_approval_request(record, record["hash"], "skill:other:v1", record["version"])


def test_api_identity_approval_scope(control):
    _config, service, _client, _headers = control
    record = _approval("identity")
    with pytest.raises(PermissionError, match="approval_scope_mismatch"):
        service._validate_approval_request(record, record["hash"], "identity:other:v1", record["version"])


def test_api_audit_redacted(control):
    _config, service, client, _headers = control
    service.security.audit.record(
        actor="ControlCenterAdapter", action="approval.inspect", resource="approval:test",
        permission=Permission.READ_ARTIFACT, decision="allow", result="ok",
        context={"authorization": "Bearer should-never-appear"},
    )
    payload = client.get("/api/audit").json()
    assert payload[-1]["redacted_context"]["authorization"] == "[REDACTED]"


def test_api_creator_job_detail_and_request_revision(control):
    _config, service, client, headers = control
    job = service.creator_job_service.create(
        topic="Alpha22 Control Center", topic_source="manual", topic_score=88,
    )
    job.qa_report = CreatorQAReport(
        passed=True, content_passed=True, video_passed=True, copy_passed=True,
        safety_passed=True, duplicate_passed=True, errors=[], warnings=[],
        checked_at=__import__("datetime").datetime.now().astimezone(),
        evidence_refs=["qa.json"],
    )
    service.creator_jobs.save(job)
    service.creator_job_service.submit_for_review(job.job_id)

    detail = client.get(f"/api/creator-jobs/{job.job_id}")
    assert detail.status_code == 200
    assert detail.json()["status"] == "REVIEW"
    assert detail.json()["topic"] == "Alpha22 Control Center"

    response = client.post(
        f"/api/creator-jobs/{job.job_id}/request-revision",
        headers=headers,
        json={"confirmed": True, "actor": "human:reviewer", "reason": "补充来源"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "DRAFT"
    assert response.json()["approval_status"] == "REVISION_REQUESTED"
    assert response.json()["revisions"][-1]["reason"] == "补充来源"
