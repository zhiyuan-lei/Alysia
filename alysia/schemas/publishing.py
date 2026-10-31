from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator


PublishJobStatus = Literal["draft", "approved", "submitting", "submitted", "failed", "cancelled"]


class ApprovalRecord(BaseModel):
    approval_id: str = Field(default_factory=lambda: f"approval_{uuid4().hex[:16]}", min_length=1)
    action_type: str = Field(default="publish", min_length=1)
    subject_id: str | None = None
    run_id: str = Field(min_length=1)
    approved_by: str = Field(default="human", min_length=1)
    approved_at: datetime
    expires_at: datetime | None = None
    package_hash: str = Field(min_length=64, max_length=64)
    scope: list[str] = Field(default_factory=lambda: ["publish:submit"])
    nonce: str = Field(default_factory=lambda: uuid4().hex)
    version: int = Field(default=1, ge=1)
    consumed_at: datetime | None = None
    consumed_by: str | None = None
    accepted_warnings: list[str] = Field(default_factory=list)
    note: str | None = None

    @model_validator(mode="after")
    def approval_binding_is_consistent(self) -> "ApprovalRecord":
        if self.subject_id is None:
            self.subject_id = self.run_id
        if self.consumed_at is not None and not self.consumed_by:
            raise ValueError("consumed approval 必须记录 consumed_by")
        if self.expires_at is not None and self.expires_at <= self.approved_at:
            raise ValueError("expires_at 必须晚于 approved_at")
        return self


class PublishJob(BaseModel):
    job_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    provider: Literal["mock", "bilibili"]
    status: PublishJobStatus = "draft"
    package_path: Path
    package_hash: str = Field(min_length=64, max_length=64)
    external_id: str | None = None
    error: str | None = None
    approval_record: ApprovalRecord | None = None
    created_at: datetime
    updated_at: datetime
    submitted_at: datetime | None = None

    @model_validator(mode="after")
    def submitted_job_has_receipt(self) -> "PublishJob":
        if self.status == "submitted" and (not self.external_id or self.submitted_at is None):
            raise ValueError("submitted PublishJob 必须包含 external_id 与 submitted_at")
        return self


class PublishValidationReport(BaseModel):
    run_id: str
    provider: Literal["mock", "bilibili"]
    passed: bool
    package_hash: str
    approval_required: bool
    approval_present: bool
    checks: dict[str, bool]
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    mock_artifacts: list[str] = Field(default_factory=list)
    generated_at: datetime
