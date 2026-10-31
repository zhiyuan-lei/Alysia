from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from alysia.capabilities.registry import CapabilityRegistry
from alysia.schemas import EvaluationEvidence, SelfEvaluationReport


class EvidenceCollector:
    def __init__(self, evidence_files: list[Path], runs_dir: Path, supervisor_root: Path | None = None) -> None:
        self.evidence_files = evidence_files
        self.runs_dir = runs_dir
        self.supervisor_root = supervisor_root

    def collect(self) -> list[EvaluationEvidence]:
        evidence: dict[str, EvaluationEvidence] = {}
        for path in self.evidence_files:
            if not path.is_file():
                continue
            payload = json.loads(path.read_text(encoding="utf-8"))
            items = payload if isinstance(payload, list) else payload.get("evidence", [])
            for item in items:
                model = EvaluationEvidence.model_validate(item)
                evidence[model.evidence_id] = model
        if self.runs_dir.is_dir():
            for path in self.runs_dir.glob("*/**/*qa*.json"):
                try:
                    payload = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                if payload.get("passed") is False:
                    relative = path.relative_to(self.runs_dir).as_posix()
                    digest = hashlib.sha256(relative.encode("utf-8")).hexdigest()[:12]
                    capability = _capability_from_text(f"{relative} {payload.get('errors', [])}")
                    model = EvaluationEvidence(
                        evidence_id=f"qa_{digest}", source=relative, run_id=path.parts[-3] if len(path.parts) >= 3 else None,
                        kind="qa_report", summary="; ".join(payload.get("errors") or ["QA failed"]),
                        capability_id=capability, severity="high", data={"observed": True},
                    )
                    evidence[model.evidence_id] = model
            self._collect_studio_failures(evidence)
            self._collect_production_failures(evidence)
            self._collect_manual_reviews(evidence)
        self._collect_supervisor_failures(evidence)
        return list(evidence.values())

    def _collect_studio_failures(self, evidence: dict[str, EvaluationEvidence]) -> None:
        for path in self.runs_dir.glob("*/studio/agent_results.json"):
            try:
                items = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            for index, item in enumerate(items):
                if item.get("status") != "failed":
                    continue
                failure = item.get("failure") or {}
                summary = failure.get("message") or item.get("summary") or "Studio agent failed"
                evidence_id = f"studio_{path.parts[-3]}_{index}"
                evidence[evidence_id] = EvaluationEvidence(
                    evidence_id=evidence_id, source=str(path), run_id=path.parts[-3], kind="trace",
                    summary=summary, capability_id=_capability_from_text(f"{item.get('agent_id')} {summary}"),
                    severity="high", data={"agent_id": item.get("agent_id"), "observed": True},
                )

    def _collect_production_failures(self, evidence: dict[str, EvaluationEvidence]) -> None:
        for path in self.runs_dir.glob("*/production/execution_metrics.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            for index, stage in enumerate(payload.get("stages", [])):
                if stage.get("success") is not False:
                    continue
                summary = stage.get("failure_reason") or f"production stage {stage.get('stage_id')} failed"
                evidence_id = f"metric_{path.parts[-3]}_{index}"
                evidence[evidence_id] = EvaluationEvidence(
                    evidence_id=evidence_id, source=str(path), run_id=path.parts[-3], kind="metric",
                    summary=summary, capability_id=_capability_from_text(f"{stage.get('stage_id')} {summary}"),
                    severity="high", data={"provider": stage.get("provider"), "observed": True},
                )

    def _collect_manual_reviews(self, evidence: dict[str, EvaluationEvidence]) -> None:
        for path in self.runs_dir.glob("*/**/*manual*review*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            rating = payload.get("rating")
            if rating is None:
                continue
            evidence_id = f"review_{hashlib.sha256(str(path).encode()).hexdigest()[:12]}"
            evidence[evidence_id] = EvaluationEvidence(
                evidence_id=evidence_id, source=str(path), run_id=path.parts[-3], kind="manual_rating",
                summary=str(payload.get("summary", f"manual rating={rating}")),
                capability_id=payload.get("capability_id"), severity="medium", data={"rating": rating},
            )

    def _collect_supervisor_failures(self, evidence: dict[str, EvaluationEvidence]) -> None:
        if self.supervisor_root is None:
            return
        path = self.supervisor_root / "supervisor_trace.jsonl"
        if not path.is_file():
            return
        for index, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            text = f"{item.get('event_type', '')} {item.get('summary', '')}"
            if not any(token in text.casefold() for token in ("fail", "block", "escalat", "失败", "阻塞")):
                continue
            evidence_id = f"supervisor_{index}_{hashlib.sha256(text.encode()).hexdigest()[:8]}"
            evidence[evidence_id] = EvaluationEvidence(
                evidence_id=evidence_id, source=str(path), kind="trace", summary=text,
                capability_id=_capability_from_text(text), severity="medium", data={"observed": True},
            )


class SelfEvaluationEngine:
    def evaluate(self, registry: CapabilityRegistry, evidence: list[EvaluationEvidence]) -> SelfEvaluationReport:
        capabilities = registry.bootstrap()
        counts = Counter(item.capability_id for item in evidence if item.capability_id)
        observed = [item for item in evidence if item.kind in {"observed_failure", "qa_report", "trace", "metric"}]
        strengths = [
            item.capability_id for item in capabilities
            if item.maturity == "stable" and counts[item.capability_id] == 0
        ]
        weak = sorted(capability_id for capability_id, count in counts.items() if count > 0)
        missing = sorted(
            {item.capability_id for item in evidence if item.capability_id}
            - {item.capability_id for item in capabilities}
        )
        recurring = [
            f"{capability_id}: {sum(int(item.data.get('occurrences', 1)) for item in observed if item.capability_id == capability_id)} 次观察"
            for capability_id in weak
            if sum(int(item.data.get("occurrences", 1)) for item in observed if item.capability_id == capability_id) >= 2
        ]
        hypotheses = [
            "音频失败可能来自测试 provider 被误用于正式链路；这是原因假设，不等同于观测事实。"
            for item in observed if item.capability_id in {"tts", "audio_qa", "subtitle_alignment"}
        ]
        stable_count = sum(item.maturity == "stable" for item in capabilities)
        payload = json.dumps([item.model_dump(mode="json") for item in evidence], ensure_ascii=False, sort_keys=True, default=str)
        report_id = f"selfeval_{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:16]}"
        confidence = min(0.95, 0.35 + 0.1 * len(observed)) if evidence else 0.1
        return SelfEvaluationReport(
            report_id=report_id, strengths=strengths, recurring_failures=recurring,
            weak_capabilities=weak, missing_capabilities=missing,
            reliability_metrics={
                "capability_count": len(capabilities), "stable_count": stable_count,
                "evidence_count": len(evidence), "observed_failure_count": len(observed),
            },
            evidence=evidence, cause_hypotheses=sorted(set(hypotheses)), confidence=confidence,
            created_at=datetime.now().astimezone(),
        )


def _capability_from_text(value: str) -> str:
    text = value.casefold()
    if any(token in text for token in ("audio", "voice", "tts", "speech", "subtitle")):
        return "audio_qa"
    if any(token in text for token in ("visual", "h3", "image", "video")):
        return "visual_h3_local"
    if "publish" in text:
        return "publish_gate"
    return "unknown_runtime"
