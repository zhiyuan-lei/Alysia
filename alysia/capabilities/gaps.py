from __future__ import annotations

import hashlib
from collections import defaultdict
from pathlib import Path

from alysia.capabilities.store import atomic_json, load_models
from alysia.schemas import CapabilityGap, EvaluationEvidence, SelfEvaluationReport


class CapabilityGapDetector:
    def __init__(self, *, minimum_evidence_count: int = 1) -> None:
        self.minimum_evidence_count = minimum_evidence_count

    def detect(self, report: SelfEvaluationReport) -> list[CapabilityGap]:
        grouped: dict[str, list[EvaluationEvidence]] = defaultdict(list)
        for item in report.evidence:
            if item.capability_id and item.kind in {"observed_failure", "qa_report", "trace", "metric"}:
                grouped[item.capability_id].append(item)
        gaps: list[CapabilityGap] = []
        for capability_id, evidence in grouped.items():
            occurrences = sum(int(item.data.get("occurrences", 1)) for item in evidence)
            if len(evidence) < self.minimum_evidence_count and occurrences < self.minimum_evidence_count:
                continue
            digest = hashlib.sha256(
                ":".join(sorted(item.evidence_id for item in evidence)).encode("utf-8")
            ).hexdigest()[:12]
            audio = capability_id in {"tts", "audio_qa", "subtitle_alignment"}
            visual = capability_id == "visual_h3_local"
            proposed = "real_tts_speech_validation" if audio else "verified_h3_local_generation" if visual else f"reliable_{capability_id}"
            description = (
                "真实中文旁白与语音可识别性门禁不足" if audio else
                "本地 H3 视觉能力尚缺真实模型 smoke test 与资源基线" if visual else
                f"{capability_id} 存在有证据的可靠性缺口"
            )
            agents = ["voice"] if audio else ["designer", "editor"] if visual else ["supervisor"]
            gaps.append(CapabilityGap(
                gap_id=f"gap_{digest}", description=description,
                evidence_runs=sorted({item.run_id or item.source for item in evidence}),
                evidence_ids=sorted(item.evidence_id for item in evidence), affected_agents=agents,
                severity=max((item.severity for item in evidence), key=lambda value: ["low", "medium", "high", "critical"].index(value)),
                frequency=max(1, occurrences),
                current_workaround="保留人工审核并禁止不合格或 mock artifact 提升",
                proposed_capability=proposed, confidence=min(0.95, 0.45 + 0.1 * occurrences),
            ))
        return gaps


class CapabilityGapStore:
    def __init__(self, root: Path) -> None:
        self.directory = root.resolve() / "gaps"

    def save(self, gap: CapabilityGap) -> CapabilityGap:
        path = self.directory / f"{gap.gap_id}.json"
        if path.is_file():
            existing = CapabilityGap.model_validate_json(path.read_text(encoding="utf-8"))
            if gap.status == "open" and existing.status != "open":
                gap = gap.model_copy(update={"status": existing.status})
        atomic_json(path, gap.model_dump(mode="json"))
        return gap

    def get(self, gap_id: str) -> CapabilityGap:
        path = self.directory / f"{gap_id}.json"
        if not path.is_file():
            raise KeyError(f"Capability gap 不存在：{gap_id}")
        return CapabilityGap.model_validate_json(path.read_text(encoding="utf-8"))

    def list(self) -> list[CapabilityGap]:
        return load_models(self.directory, CapabilityGap)
