from __future__ import annotations

from datetime import datetime

from alysia.creator.models import (
    ClaimClassification,
    CreatorClaimTrace,
    CreatorQAReport,
    DuplicateCheckReport,
    ResearchEvidenceStatus,
)


class CreatorQAGate:
    def evaluate(
        self,
        *,
        claims: list[CreatorClaimTrace],
        research_status: ResearchEvidenceStatus,
        video_passed: bool,
        copy_passed: bool,
        safety_passed: bool,
        duplicate_report: DuplicateCheckReport,
        evidence_refs: list[str],
    ) -> CreatorQAReport:
        errors: list[str] = []
        warnings: list[str] = []
        if research_status == ResearchEvidenceStatus.INSUFFICIENT_EVIDENCE:
            errors.append("insufficient_evidence")
        for index, claim in enumerate(claims):
            label = f"claim[{index}]"
            if claim.classification == ClaimClassification.VERIFIED_FACT:
                if claim.stale:
                    errors.append(f"{label}:stale_verified_fact")
                if claim.conflicted:
                    errors.append(f"{label}:conflicted_verified_fact")
            if claim.presented_as_fact and claim.classification in {
                ClaimClassification.INFERENCE,
                ClaimClassification.OPINION,
                ClaimClassification.CREATIVE_CONTENT,
                ClaimClassification.UNKNOWN,
            }:
                errors.append(f"{label}:{claim.classification.value.lower()}_presented_as_fact")
        if not video_passed:
            errors.append("video_qa_failed")
        if not copy_passed:
            errors.append("copy_consistency_failed")
        if not safety_passed:
            errors.append("safety_gate_failed")
        if not duplicate_report.passed:
            errors.append("duplicate_detection_failed")
        if not evidence_refs:
            warnings.append("creator_qa_has_no_evidence_refs")
        content_passed = not any(
            item == "insufficient_evidence" or item.startswith("claim[") for item in errors
        )
        passed = (
            content_passed
            and video_passed
            and copy_passed
            and safety_passed
            and duplicate_report.passed
            and not errors
        )
        return CreatorQAReport(
            passed=passed,
            content_passed=content_passed,
            video_passed=video_passed,
            copy_passed=copy_passed,
            safety_passed=safety_passed,
            duplicate_passed=duplicate_report.passed,
            errors=errors,
            warnings=warnings,
            checked_at=datetime.now().astimezone(),
            evidence_refs=evidence_refs,
        )
