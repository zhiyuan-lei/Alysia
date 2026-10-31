from __future__ import annotations

from datetime import datetime
from pathlib import Path

from alysia.core.config import AlysiaConfig
from alysia.core.resources import ResourceManager
from alysia.core.run import RunManager, RunState
from alysia.creator.duplicates import CreatorDuplicateDetector
from alysia.creator.models import (
    ClaimClassification,
    CreatorClaimTrace,
    CreatorPlan,
    ResearchEvidenceStatus,
    ResearchSourceTrace,
    ResourceUsageSnapshot,
)
from alysia.creator.qa import CreatorQAGate
from alysia.creator.service import CreatorJobService
from alysia.creator.store import CreatorJobStore
from alysia.knowledge.models import GroundingReport
from alysia.schemas import PublishPackage, PublishQAReport, ResearchResult, Script, VideoQAReport


class CreatorRunBridge:
    """Maps existing Alpha18–21 run artifacts into the Alpha22 aggregate."""

    def __init__(self, config: AlysiaConfig) -> None:
        self.config = config
        self.manager = RunManager(config.runtime.runs_dir)
        root = config.creator_loop.jobs_dir or (config.runtime.runs_dir.parent / "creator_jobs")
        self.store = CreatorJobStore(root)
        self.service = CreatorJobService(self.store)

    def sync_review_ready(self, state: RunState) -> None:
        if not state.creator_job_id:
            return
        job = self.store.load(state.creator_job_id)
        research = self._load(state, "research", ResearchResult)
        script = self._load(state, "script", Script)
        package = self._load(state, "publish_package", PublishPackage)
        video_qa = self._load(state, "video_qa_report", VideoQAReport)
        publish_qa = self._load(state, "publish_qa_report", PublishQAReport)
        grounding = self._optional(state, "grounding_report", GroundingReport)

        run_dir = self.manager.run_dir(state.run_id)
        job.research_sources = [
            ResearchSourceTrace(
                source_id=source.id,
                source=source.url,
                retrieved_at=source.retrieved_at,
                claim=source.note or research.summary,
                confidence=0.5,
                source_type=source.source_type,
                evidence_path=run_dir / state.artifacts["research"],
            )
            for source in research.sources
        ]
        job.claims = self._claims(state)
        job.research_status = (
            ResearchEvidenceStatus.SUFFICIENT
            if grounding is not None and grounding.passed
            else ResearchEvidenceStatus.INSUFFICIENT_EVIDENCE
        )
        job.uncertainties = list(research.open_questions)
        job.script = script.to_markdown()
        job.selected_title = package.title
        job.title_candidates = self._title_candidates(state, package.title)
        job.description = package.description
        job.tags = list(package.tags)
        job.video_path = (run_dir / package.video_path).resolve()
        job.thumbnail_path = (run_dir / package.cover_path).resolve()
        job.creator_plan = CreatorPlan(
            plan_id=f"legacy_{job.job_id}_{job.current_revision}",
            job_id=job.job_id,
            revision=job.current_revision,
            hook=script.hook,
            core_message=script.thesis,
            structure=[section.purpose for section in script.sections],
            script_ref=state.artifacts.get("script"),
            visuals={"artifact_refs": [state.artifacts[key] for key in state.artifacts if "visual" in key]},
            voice={"audio_manifest": state.artifacts.get("audio_manifest")},
            music={},
            thumbnail_ref=str(package.cover_path),
            title=package.title,
            description=package.description,
            tags=package.tags,
        )
        job.visual_plan = dict(job.creator_plan.visuals)
        job.audio_plan = dict(job.creator_plan.voice)

        duplicate_report = CreatorDuplicateDetector(
            threshold=self.config.planning.duplicate_threshold
        ).check(job, self.store.list())
        evidence_refs = [
            state.artifacts[key]
            for key in ("grounding_report", "knowledge_qa_report", "video_qa_report", "publish_qa_report")
            if key in state.artifacts
        ]
        job.qa_report = CreatorQAGate().evaluate(
            claims=job.claims,
            research_status=job.research_status,
            video_passed=video_qa.passed,
            copy_passed=publish_qa.passed,
            safety_passed=bool(self.config.security.enabled and self.config.publishing.require_approval),
            duplicate_report=duplicate_report,
            evidence_refs=evidence_refs,
        )
        resources = ResourceManager()
        vram = resources.probe_vram()
        ram = resources.probe_ram()
        job.resource_usage.append(
            ResourceUsageSnapshot(
                observed_at=datetime.now().astimezone(),
                gpu_vram_used_mb=vram.get("used_mb") if vram else None,
                system_ram_used_mb=ram.get("used_mb") if ram else None,
                evidence_ref="review_ready_resource_snapshot",
            )
        )
        job.evidence_paths = list(
            dict.fromkeys(
                job.evidence_paths
                + [
                    (run_dir / relative).resolve()
                    for relative in evidence_refs
                    if (run_dir / relative).is_file()
                ]
            )
        )
        self.store.save(job)
        if job.qa_report.passed and job.status == "DRAFT":
            self.service.submit_for_review(job.job_id)

    def _claims(self, state: RunState) -> list[CreatorClaimTrace]:
        relative = state.artifacts.get("claims_used")
        if not relative or not (self.manager.run_dir(state.run_id) / relative).is_file():
            return []
        payload = self.manager.read_json(state.run_id, relative)
        output: list[CreatorClaimTrace] = []
        for item in payload:
            status = item.get("status")
            claim_type = item.get("claim_type")
            if claim_type == "opinion":
                classification = ClaimClassification.OPINION
            elif status == "verified":
                classification = ClaimClassification.VERIFIED_FACT
            elif status == "provisional" or claim_type == "estimate":
                classification = ClaimClassification.INFERENCE
            else:
                classification = ClaimClassification.UNKNOWN
            output.append(
                CreatorClaimTrace(
                    claim=item.get("statement") or "unknown claim",
                    classification=classification,
                    confidence=float(item.get("confidence", 0.0)),
                    source_refs=list(item.get("evidence_refs") or []),
                    presented_as_fact=classification == ClaimClassification.VERIFIED_FACT,
                    stale=status == "stale",
                    conflicted=status == "conflicted",
                    note=f"knowledge_claim_id={item.get('claim_id')}",
                )
            )
        return output

    def _title_candidates(self, state: RunState, selected: str) -> list[str]:
        relative = state.artifacts.get("title_candidates")
        if not relative or not (self.manager.run_dir(state.run_id) / relative).is_file():
            return [selected]
        payload = self.manager.read_json(state.run_id, relative)
        values = payload.get("candidates", payload) if isinstance(payload, dict) else payload
        titles = [
            item.get("title") if isinstance(item, dict) else str(item)
            for item in values
        ]
        return list(dict.fromkeys([selected] + [value for value in titles if value]))

    def _load(self, state: RunState, key: str, model: type):
        relative = state.artifacts.get(key)
        if not relative:
            raise FileNotFoundError(f"run missing artifact: {key}")
        return model.model_validate(self.manager.read_json(state.run_id, relative))

    def _optional(self, state: RunState, key: str, model: type):
        relative = state.artifacts.get(key)
        if not relative or not (self.manager.run_dir(state.run_id) / relative).is_file():
            return None
        return model.model_validate(self.manager.read_json(state.run_id, relative))
