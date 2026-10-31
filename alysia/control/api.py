from __future__ import annotations

import secrets
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from alysia.core.config import AlysiaConfig, load_config
from alysia.local_creator import LocalCreationSpec
from alysia.schemas.security import SecurityActionError

from .service import ControlCenterError, ControlCenterService


class ConfirmedAction(BaseModel):
    confirmed: bool
    failure_id: str | None = None


class ApprovalAction(BaseModel):
    confirmed: bool
    expected_hash: str = Field(min_length=64, max_length=64)
    expected_scope: str = Field(min_length=1)
    expected_version: str = Field(min_length=1)
    actor: str = Field(default="human:control-center", pattern=r"^human:[A-Za-z0-9_.-]+$")
    reason: str = ""


class CreatorRevisionAction(BaseModel):
    confirmed: bool
    actor: str = Field(default="human:control-center", pattern=r"^human:[A-Za-z0-9_.-]+$")
    reason: str = Field(min_length=1)


class PublicationReceiptAction(BaseModel):
    confirmed: bool
    actor: str = Field(default="human:control-center", pattern=r"^human:[A-Za-z0-9_.-]+$")
    content_id: str = Field(pattern=r"^BV[0-9A-Za-z]{10}$")
    publication_url: str = Field(min_length=1)
    published_at: datetime
    recorded_at: datetime
    evidence_path: Path


class ObservationAction(BaseModel):
    confirmed: bool
    actor: str = Field(default="human:control-center", pattern=r"^human:[A-Za-z0-9_.-]+$")
    observed_at: datetime
    views: int | None = Field(default=None, ge=0)
    likes: int | None = Field(default=None, ge=0)
    comments: int | None = Field(default=None, ge=0)
    favorites: int | None = Field(default=None, ge=0)
    shares: int | None = Field(default=None, ge=0)
    followers_delta: int | None = None
    availability: dict[str, str]
    evidence_path: Path


class ReflectionAction(BaseModel):
    confirmed: bool
    actor: str = Field(default="human:control-center", pattern=r"^human:[A-Za-z0-9_.-]+$")
    attempted: str = Field(min_length=1)
    actual: str = Field(min_length=1)
    worked: list[str] = Field(default_factory=list)
    likely_failed: list[str] = Field(default_factory=list)
    supporting_evidence: list[str] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)
    next_changes: list[str] = Field(default_factory=list)
    facts: list[str] = Field(default_factory=list)
    interpretations: list[str] = Field(default_factory=list)
    created_at: datetime


class EvidenceAction(BaseModel):
    confirmed: bool
    actor: str = Field(default="human:control-center", pattern=r"^human:[A-Za-z0-9_.-]+$")
    evidence_path: Path


class LocalCreationAction(BaseModel):
    confirmed: bool
    spec: LocalCreationSpec


def create_control_app(
    config: AlysiaConfig | None = None,
    *,
    service: ControlCenterService | None = None,
    static_dir: Path | None = None,
) -> FastAPI:
    resolved_config = config or load_config()
    control = service or ControlCenterService(resolved_config)
    app = FastAPI(title="Alysia Control Center", version="0.1-alpha.22", docs_url=None, redoc_url=None)
    app.state.control = control
    app.state.csrf_sessions = {}
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"])

    @app.middleware("http")
    async def local_origin_guard(request: Request, call_next):
        origin = request.headers.get("origin")
        if origin and origin.rstrip("/") not in {"http://127.0.0.1:8765", "http://localhost:8765"}:
            return JSONResponse(status_code=403, content={"detail": "origin_not_allowed"})
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store" if request.url.path.startswith("/api/") else "private, max-age=0"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = "default-src 'self'; img-src 'self' data: blob:; media-src 'self' blob:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'"
        return response

    @app.exception_handler(FileNotFoundError)
    async def not_found_handler(_request: Request, exc: FileNotFoundError):
        return JSONResponse(status_code=404, content={"detail": str(exc) or "not_found"})

    async def controlled_error_handler(_request: Request, exc: Exception):
        status = 403 if isinstance(exc, (PermissionError, SecurityActionError)) else 409 if isinstance(exc, ControlCenterError) else 400
        return JSONResponse(status_code=status, content={"detail": control.security.redactor.redact(str(exc))})

    for error_type in (ValueError, PermissionError, ControlCenterError, SecurityActionError):
        app.add_exception_handler(error_type, controlled_error_handler)

    def protected_payload(payload: Any) -> Any:
        return control.security.redactor.redact_value(payload)

    def require_csrf(
        request: Request,
        x_alysia_csrf: str | None = Header(default=None),
    ) -> None:
        session_id = request.cookies.get("alysia_control_session")
        expected = app.state.csrf_sessions.get(session_id)
        if not session_id or not expected or not x_alysia_csrf or not secrets.compare_digest(expected, x_alysia_csrf):
            raise HTTPException(status_code=403, detail="csrf_validation_failed")

    @app.get("/api/health")
    def health(request: Request, response: Response):
        session_id = request.cookies.get("alysia_control_session")
        if not session_id or session_id not in app.state.csrf_sessions:
            session_id = secrets.token_urlsafe(24)
            app.state.csrf_sessions[session_id] = secrets.token_urlsafe(32)
        response.set_cookie("alysia_control_session", session_id, httponly=True, samesite="strict", secure=False, path="/")
        payload = protected_payload(control.health())
        payload["csrf_token"] = app.state.csrf_sessions[session_id]
        return payload

    @app.get("/api/dashboard")
    def dashboard():
        return protected_payload({
            "health": control.health(), "resources": control.resources(), "providers": control.providers(),
            "runs": control.list_runs()[:10], "approvals": control.approvals(), "errors": control.errors()[-10:],
        })

    @app.get("/api/system/resources")
    def resources():
        return protected_payload(control.resources())

    @app.get("/api/system/providers")
    def providers():
        return protected_payload(control.providers())

    @app.get("/api/runs")
    def runs():
        return protected_payload(control.list_runs())

    @app.get("/api/runs/{run_id}")
    def run_detail(run_id: str):
        return protected_payload(control.run_detail(run_id))

    @app.get("/api/runs/{run_id}/artifacts")
    def run_artifacts(run_id: str):
        return protected_payload(control.run_artifacts(run_id))

    @app.get("/api/runs/{run_id}/artifacts/{artifact_key}")
    def artifact(run_id: str, artifact_key: str):
        path, media_type = control.artifact(run_id, artifact_key)
        return FileResponse(path, media_type=media_type, filename=path.name if media_type == "application/octet-stream" else None)

    @app.post("/api/runs/{run_id}/resume", dependencies=[Depends(require_csrf)])
    async def resume(run_id: str, action: ConfirmedAction):
        if not action.confirmed:
            raise HTTPException(status_code=409, detail="confirmation_required")
        return protected_payload(await control.resume(run_id))

    @app.post("/api/runs/{run_id}/recover", dependencies=[Depends(require_csrf)])
    async def recover(run_id: str, action: ConfirmedAction):
        if not action.confirmed:
            raise HTTPException(status_code=409, detail="confirmation_required")
        return protected_payload(await control.recover(run_id, action.failure_id))

    @app.get("/api/runs/{run_id}/diagnose")
    def diagnose(run_id: str):
        return protected_payload(control.diagnose(run_id))

    @app.get("/api/supervisor/goals")
    def supervisor_goals(): return protected_payload(control.supervisor("goals"))
    @app.get("/api/supervisor/plans")
    def supervisor_plans(): return protected_payload(control.supervisor("plans"))
    @app.get("/api/supervisor/blockers")
    def supervisor_blockers(): return protected_payload(control.supervisor("blockers"))

    @app.get("/api/studio/{run_id}/agents")
    def studio_agents(run_id: str): return protected_payload(control.studio(run_id, "agents"))
    @app.get("/api/studio/{run_id}/trace")
    def studio_trace(run_id: str): return protected_payload(control.studio(run_id, "trace"))

    @app.get("/api/production/{run_id}/plan")
    def production_plan(run_id: str): return protected_payload(control.production(run_id, "plan"))
    @app.get("/api/production/{run_id}/resources")
    def production_resources(run_id: str): return protected_payload(control.production(run_id, "resources"))

    @app.get("/api/visual/jobs")
    def visual_jobs(): return protected_payload(control.visual_jobs())
    @app.get("/api/visual/jobs/{job_id}")
    def visual_job(job_id: str): return protected_payload(control.visual_job(job_id))
    @app.get("/api/visual/{run_id}/plan")
    def visual_plan(run_id: str): return protected_payload(control.visual_plan(run_id))

    @app.get("/api/local-create/jobs")
    def local_creation_jobs(): return protected_payload(control.local_creation_jobs())
    @app.get("/api/local-create/jobs/{run_id}")
    def local_creation_job(run_id: str): return protected_payload(control.local_creation_job(run_id))
    @app.post("/api/local-create/jobs", dependencies=[Depends(require_csrf)])
    def submit_local_creation(action: LocalCreationAction):
        if not action.confirmed:
            raise HTTPException(status_code=409, detail="confirmation_required")
        return protected_payload(control.submit_local_creation(action.spec))
    @app.post("/api/local-create/jobs/{run_id}/resume", dependencies=[Depends(require_csrf)])
    def resume_local_creation(run_id: str, action: ConfirmedAction):
        if not action.confirmed:
            raise HTTPException(status_code=409, detail="confirmation_required")
        return protected_payload(control.resume_local_creation(run_id))
    @app.get("/api/local-create/jobs/{run_id}/video")
    def local_creation_video(run_id: str):
        return FileResponse(control.local_creation_video(run_id), media_type="video/mp4")

    @app.get("/api/knowledge/status")
    def knowledge_status(): return protected_payload(control.knowledge("status"))
    @app.get("/api/knowledge/claims")
    def knowledge_claims(): return protected_payload(control.knowledge("claims"))
    @app.get("/api/knowledge/conflicts")
    def knowledge_conflicts(): return protected_payload(control.knowledge("conflicts"))
    @app.get("/api/knowledge/stale")
    def knowledge_stale(): return protected_payload(control.knowledge("stale"))

    @app.get("/api/analytics/{run_id}")
    def analytics(run_id: str): return protected_payload(control.analytics(run_id))
    @app.get("/api/memory/lessons")
    def lessons(): return protected_payload(control.lessons())
    @app.get("/api/experiments")
    def experiments(): return protected_payload(control.experiments())

    @app.get("/api/creator-jobs")
    def creator_jobs(): return protected_payload(control.list_creator_jobs())
    @app.get("/api/creator-jobs/{job_id}")
    def creator_job(job_id: str): return protected_payload(control.creator_job(job_id))
    @app.post("/api/creator-jobs/{job_id}/request-revision", dependencies=[Depends(require_csrf)])
    def request_creator_revision(job_id: str, action: CreatorRevisionAction):
        if not action.confirmed:
            raise HTTPException(status_code=409, detail="confirmation_required")
        return protected_payload(control.request_creator_revision(job_id, actor=action.actor, reason=action.reason))
    @app.post("/api/creator-jobs/{job_id}/record-publication", dependencies=[Depends(require_csrf)])
    def record_creator_publication(job_id: str, action: PublicationReceiptAction):
        if not action.confirmed:
            raise HTTPException(status_code=409, detail="confirmation_required")
        return protected_payload(control.record_creator_publication(
            job_id, content_id=action.content_id, publication_url=action.publication_url,
            published_at=action.published_at, recorded_at=action.recorded_at,
            actor=action.actor, evidence_path=action.evidence_path,
        ))
    @app.post("/api/creator-jobs/{job_id}/observations", dependencies=[Depends(require_csrf)])
    def record_creator_observation(job_id: str, action: ObservationAction):
        if not action.confirmed:
            raise HTTPException(status_code=409, detail="confirmation_required")
        values = {name: getattr(action, name) for name in ("views", "likes", "comments", "favorites", "shares", "followers_delta")}
        return protected_payload(control.record_creator_observation(
            job_id, observed_at=action.observed_at, values=values,
            availability=action.availability, evidence_path=action.evidence_path, actor=action.actor,
        ))
    @app.post("/api/creator-jobs/{job_id}/reflection", dependencies=[Depends(require_csrf)])
    def record_creator_reflection(job_id: str, action: ReflectionAction):
        if not action.confirmed:
            raise HTTPException(status_code=409, detail="confirmation_required")
        payload = action.model_dump(exclude={"confirmed", "actor"})
        return protected_payload(control.record_creator_reflection(job_id, actor=action.actor, payload=payload))
    @app.post("/api/creator-jobs/{job_id}/memory", dependencies=[Depends(require_csrf)])
    def integrate_creator_memory(job_id: str, action: ConfirmedAction):
        if not action.confirmed:
            raise HTTPException(status_code=409, detail="confirmation_required")
        return protected_payload(control.integrate_creator_memory(job_id, actor="human:control-center"))
    @app.post("/api/creator-jobs/{job_id}/beta-evidence", dependencies=[Depends(require_csrf)])
    def upsert_creator_beta_evidence(job_id: str, action: EvidenceAction):
        if not action.confirmed:
            raise HTTPException(status_code=409, detail="confirmation_required")
        return protected_payload(control.upsert_creator_beta_evidence(
            job_id, evidence_path=action.evidence_path, actor=action.actor,
        ))

    @app.get("/api/approvals")
    def approvals(): return protected_payload(control.approvals())
    @app.get("/api/approvals/{approval_id:path}")
    def approval(approval_id: str): return protected_payload(control.approval(approval_id))
    @app.post("/api/approvals/{approval_id:path}/approve", dependencies=[Depends(require_csrf)])
    def approve(approval_id: str, action: ApprovalAction):
        if not action.confirmed:
            raise HTTPException(status_code=409, detail="confirmation_required")
        return protected_payload(control.approve(approval_id, expected_hash=action.expected_hash, expected_scope=action.expected_scope, expected_version=action.expected_version, approved_by=action.actor))
    @app.post("/api/approvals/{approval_id:path}/reject", dependencies=[Depends(require_csrf)])
    def reject(approval_id: str, action: ApprovalAction):
        if not action.confirmed:
            raise HTTPException(status_code=409, detail="confirmation_required")
        return protected_payload(control.reject(approval_id, expected_hash=action.expected_hash, expected_scope=action.expected_scope, expected_version=action.expected_version, rejected_by=action.actor, reason=action.reason))

    @app.get("/api/capabilities")
    def capabilities(): return protected_payload(control.capabilities())
    @app.get("/api/skills")
    def skills(): return protected_payload(control.skills())
    @app.get("/api/workflows")
    def workflows(): return protected_payload(control.workflows())
    @app.get("/api/workflow-recipes")
    def workflow_recipes(): return protected_payload(control.workflow_recipes())

    @app.get("/api/audit")
    def audit(): return protected_payload(control.audit())
    @app.get("/api/errors")
    def errors(): return protected_payload(control.errors())
    @app.get("/api/evaluation")
    def evaluation():
        gate = control.evaluation.gate(control.alpha20_evaluation_id, baseline_id=control.baseline_id)
        return protected_payload({"baseline_id": control.baseline_id, "evaluation_id": control.alpha20_evaluation_id, "gate": gate.model_dump(mode="json")})

    resolved_static = (static_dir or Path("control-center/dist")).resolve()
    if resolved_static.is_dir():
        app.mount("/", StaticFiles(directory=resolved_static, html=True), name="control-ui")

    return app
