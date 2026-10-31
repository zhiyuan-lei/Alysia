from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol

from alysia.schemas import BenchmarkCase, EvaluationMetric, RubricDimension
from alysia.workers.media import find_media_executable, probe_media, run_command
from alysia.workers.wav import inspect_wav, signal_metrics


class Scorer(Protocol):
    def score(self, case: BenchmarkCase, fixture_paths: list[Path]) -> list[EvaluationMetric]: ...


def _payload(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _metric(
    case: BenchmarkCase,
    suffix: str,
    value: float | int | str | bool | None,
    *,
    unit: str,
    direction: str,
    source: str,
    measurement_type: str = "observed",
    confidence: float = 1.0,
    dimensions: list[RubricDimension] | None = None,
    reason: str | None = None,
    evidence_refs: list[str] | None = None,
) -> EvaluationMetric:
    return EvaluationMetric(
        metric_id=f"{case.case_id}.{suffix}",
        benchmark_case_id=case.case_id,
        value=value,
        unit=unit,
        direction=direction,
        tolerance=case.tolerance,
        source=source,
        confidence=confidence,
        measurement_type=measurement_type,
        rubric_dimensions=dimensions or [],
        reason=reason,
        affected_capability=case.required_capabilities[0] if case.required_capabilities else case.category,
        evidence_refs=evidence_refs if evidence_refs is not None else [source],
    )


class GroundingCoverageScorer:
    def score(self, case: BenchmarkCase, fixture_paths: list[Path]) -> list[EvaluationMetric]:
        data = _payload(fixture_paths[0])["good"]
        total = len(data["factual_sections"])
        supported = sum(bool(item["claim_refs"] and item["source_refs"] and not item.get("stale") and not item.get("conflicted")) for item in data["factual_sections"])
        coverage = supported / total if total else 0.0
        return [_metric(case, "coverage", coverage, unit="ratio", direction="higher_is_better", source=str(fixture_paths[0]), measurement_type="derived", reason=f"{supported}/{total} factual sections are grounded")]


class KnowledgeFreshnessScorer:
    def score(self, case: BenchmarkCase, fixture_paths: list[Path]) -> list[EvaluationMetric]:
        data = _payload(fixture_paths[0])["good"]
        used = data["used_claims"]
        blockers = sum(item["status"] in {"stale", "conflicted"} for item in used)
        fresh = sum(item["status"] in {"verified", "provisional"} and not item.get("expired", False) for item in used)
        return [
            _metric(case, "blocked_claim_usage", blockers, unit="count", direction="lower_is_better", source=str(fixture_paths[0]), measurement_type="derived", reason="stale/conflicted claims used by the script"),
            _metric(case, "eligible_claim_ratio", fresh / len(used) if used else 0.0, unit="ratio", direction="higher_is_better", source=str(fixture_paths[0]), measurement_type="derived", reason=f"{fresh}/{len(used)} claims are eligible"),
        ]


class ScriptRubricScorer:
    DIMENSIONS = ("hook", "structure", "evidence", "conclusion")

    def score(self, case: BenchmarkCase, fixture_paths: list[Path]) -> list[EvaluationMetric]:
        script = _payload(fixture_paths[0])["good"]
        levels = {
            "hook": 3 if script.get("hook") and ("？" in script["hook"] or "?" in script["hook"]) else 1,
            "structure": 3 if len(script.get("sections", [])) >= 3 else 1,
            "evidence": 3 if all(section.get("claim_refs") for section in script.get("factual_sections", [])) else 0,
            "conclusion": 3 if script.get("conclusion") else 0,
        }
        reasons = {
            "hook": "Hook is an explicit question" if levels["hook"] == 3 else "Hook lacks a clear question",
            "structure": f"{len(script.get('sections', []))} ordered sections",
            "evidence": "All factual sections retain claim refs" if levels["evidence"] == 3 else "A factual section lacks claim refs",
            "conclusion": "Explicit conclusion present" if levels["conclusion"] == 3 else "Conclusion missing",
        }
        dimensions = [RubricDimension(dimension=name, level=levels[name], reason=reasons[name]) for name in self.DIMENSIONS]
        return [_metric(case, "rubric_total", sum(levels.values()), unit="rubric_points", direction="higher_is_better", source=str(fixture_paths[0]), measurement_type="rubric", dimensions=dimensions, reason="Discrete 0-3 rubric; no LLM score")]


class StoryboardCoverageScorer:
    def score(self, case: BenchmarkCase, fixture_paths: list[Path]) -> list[EvaluationMetric]:
        data = _payload(fixture_paths[0])["good"]
        expected = set(data["expected_sections"])
        covered = {scene["section_id"] for scene in data["scenes"]}
        ratio = len(expected & covered) / len(expected) if expected else 1.0
        return [_metric(case, "section_coverage", ratio, unit="ratio", direction="higher_is_better", source=str(fixture_paths[0]), measurement_type="derived", reason=f"covered={sorted(expected & covered)} missing={sorted(expected - covered)}")]


class AudioValidityIntelligibilityScorer:
    def score(self, case: BenchmarkCase, fixture_paths: list[Path]) -> list[EvaluationMetric]:
        path = fixture_paths[0]
        try:
            info = inspect_wav(path)
            signal = signal_metrics(path)
            speech_like = not (
                signal["active_window_ratio"] > 0.9
                and signal["active_rms_cv"] < 0.35
                and signal["active_zero_crossing_cv"] < 0.05
            )
            valid = info["duration_sec"] > 0 and info["sample_width_bytes"] == 2 and signal["rms"] >= 0.001 and speech_like
            reason = f"PCM16={info['sample_width_bytes'] == 2}; duration={info['duration_sec']:.3f}; speech_like={speech_like}"
        except (OSError, EOFError, ValueError) as exc:
            valid = False
            speech_like = False
            reason = f"WAV decode failed: {exc}"
        return [
            _metric(case, "audio_valid", int(valid), unit="boolean", direction="higher_is_better", source=str(path), reason=reason),
            _metric(case, "test_tone_detected", int(not speech_like), unit="boolean", direction="lower_is_better", source=str(path), reason="Deterministic speech-dynamics guard"),
            _metric(case, "asr_text_similarity", None, unit="ratio", direction="higher_is_better", source="ASR integration not loaded in offline benchmark", measurement_type="unknown", confidence=0.0, reason="Offline suite does not fabricate intelligibility from absent ASR", evidence_refs=[]),
        ]


class SubtitleTimingScorer:
    LEADING_PUNCTUATION = tuple("，。：；！？、,.!?;:")

    def score(self, case: BenchmarkCase, fixture_paths: list[Path]) -> list[EvaluationMetric]:
        data = _payload(fixture_paths[0])
        segments = data["segments"]
        total = float(data["total_duration_sec"])
        overlaps = 0
        out_of_bounds = 0
        semantic_breaks = 0
        previous_end = 0.0
        for segment in segments:
            start, end = float(segment["start_sec"]), float(segment["end_sec"])
            overlaps += int(start < previous_end - 1e-6)
            out_of_bounds += int(start < 0 or end <= start or end > total + 1e-6)
            semantic_breaks += int(str(segment["text"]).startswith(self.LEADING_PUNCTUATION))
            previous_end = max(previous_end, end)
        source = str(fixture_paths[0])
        return [
            _metric(case, "overlap_count", overlaps, unit="count", direction="lower_is_better", source=source),
            _metric(case, "out_of_bounds_count", out_of_bounds, unit="count", direction="lower_is_better", source=source),
            _metric(case, "semantic_split_violations", semantic_breaks, unit="count", direction="lower_is_better", source=source),
        ]


def _probe(path: Path) -> tuple[dict | None, str | None]:
    ffprobe = find_media_executable("ffprobe")
    if ffprobe is None:
        return None, "ffprobe unavailable"
    try:
        return probe_media(path, ffprobe), None
    except (OSError, RuntimeError, ValueError) as exc:
        return None, str(exc)


class VisualArtifactScorer:
    def score(self, case: BenchmarkCase, fixture_paths: list[Path]) -> list[EvaluationMetric]:
        path = fixture_paths[0]
        probe, error = _probe(path)
        video = next((item for item in (probe or {}).get("streams", []) if item.get("codec_type") == "video"), None)
        valid = bool(path.is_file() and path.stat().st_size > 0 and video and int(video.get("width", 0)) > 0)
        return [_metric(case, "artifact_valid", int(valid), unit="boolean", direction="higher_is_better", source=str(path), reason=error or "ffprobe found a decodable video stream")]


class RenderMediaScorer:
    def score(self, case: BenchmarkCase, fixture_paths: list[Path]) -> list[EvaluationMetric]:
        path = fixture_paths[0]
        probe, error = _probe(path)
        streams = (probe or {}).get("streams", [])
        has_video = any(item.get("codec_type") == "video" for item in streams)
        has_audio = any(item.get("codec_type") == "audio" for item in streams)
        decodable = False
        ffmpeg = find_media_executable("ffmpeg")
        if error is None and ffmpeg is not None:
            try:
                run_command([str(ffmpeg), "-v", "error", "-i", str(path), "-f", "null", "-"], timeout_sec=60)
                decodable = True
            except RuntimeError as exc:
                error = str(exc)
        valid = has_video and has_audio and decodable
        return [_metric(case, "render_decodable", int(valid), unit="boolean", direction="higher_is_better", source=str(path), reason=error or "video/audio streams decode completely")]


class StyleConsistencyScorer:
    def score(self, case: BenchmarkCase, fixture_paths: list[Path]) -> list[EvaluationMetric]:
        report = _payload(fixture_paths[0])
        violations = report.get("violations", [])
        suggestions = report.get("suggestions", [])
        level = 3 if not violations and len(suggestions) <= 1 else 2 if not violations else 1 if len(violations) == 1 else 0
        dimensions = [
            RubricDimension(dimension="identity_violations", level=3 if not violations else max(0, 3 - len(violations)), reason=f"violations={violations}"),
            RubricDimension(dimension="style_suggestions", level=3 if not suggestions else max(0, 3 - len(suggestions)), reason=f"suggestions={suggestions}"),
            RubricDimension(dimension="report_traceability", level=3 if report.get("identity_version") and report.get("input_digest") else 0, reason="Alpha10 report identity_version/input_digest presence"),
        ]
        return [_metric(case, "style_level", level, unit="rubric_level", direction="higher_is_better", source=str(fixture_paths[0]), measurement_type="rubric", dimensions=dimensions, reason="Discrete interpretation of Alpha10 StyleConsistencyReport")]


class PublishPackageScorer:
    def score(self, case: BenchmarkCase, fixture_paths: list[Path]) -> list[EvaluationMetric]:
        data = _payload(fixture_paths[0])["good"]
        package = data["package"]
        errors = []
        if not 5 <= len(package.get("title", "")) <= 80:
            errors.append("title")
        if "## 参考资料" not in package.get("description", ""):
            errors.append("description_sources")
        tags = package.get("tags", [])
        if not tags or len({item.casefold() for item in tags}) != len(tags):
            errors.append("tags")
        if not package.get("cover_exists") or not package.get("video_qa_passed"):
            errors.append("artifacts")
        approval_ok = data.get("approval", {}).get("approved_by", "").startswith("human:") and data.get("approval", {}).get("package_hash") == package.get("package_hash")
        source = str(fixture_paths[0])
        return [
            _metric(case, "package_error_count", len(errors), unit="count", direction="lower_is_better", source=source, reason=f"errors={errors}"),
            _metric(case, "approval_invariant", int(approval_ok), unit="boolean", direction="higher_is_better", source=source, reason="Human approval is bound to package hash"),
        ]


class AnalyticsLearningScorer:
    def score(self, case: BenchmarkCase, fixture_paths: list[Path]) -> list[EvaluationMetric]:
        data = _payload(fixture_paths[0])
        violations = 0
        violations += int(data["source"] in {"mock", "testing"} and data.get("lesson_status") not in {"tentative", None})
        violations += int(bool(data.get("fabricated_missing_metrics")))
        violations += int(not data.get("facts_inferences_separated", False))
        return [_metric(case, "isolation_violations", violations, unit="count", direction="lower_is_better", source=str(fixture_paths[0]), reason="Mock/real isolation, missing-value and fact/inference checks")]


class WorkflowReliabilityScorer:
    KEYS = ("approved_skill_only", "publish_approval_preserved", "budget_respected", "action_limit_respected", "knowledge_stale_blocked", "provider_resource_constraints")

    def score(self, case: BenchmarkCase, fixture_paths: list[Path]) -> list[EvaluationMetric]:
        data = _payload(fixture_paths[0])["good"]
        return [
            _metric(case, key, int(bool(data.get(key))), unit="boolean", direction="higher_is_better", source=str(fixture_paths[0]), reason=f"core invariant {key}")
            for key in self.KEYS
        ]


class RecoveryReliabilityScorer:
    def score(self, case: BenchmarkCase, fixture_paths: list[Path]) -> list[EvaluationMetric]:
        data = _payload(fixture_paths[0])["good"]
        source = str(fixture_paths[0])
        evidence = [source, *data.get("evidence_refs", [])]
        definitions = (
            ("recovery_success_rate", "ratio", "higher_is_better"),
            ("unnecessary_stage_reexecution_count", "count", "lower_is_better"),
            ("checkpoint_restore_success", "count", "higher_is_better"),
            ("duplicate_publish_job_count", "count", "lower_is_better"),
            ("recovery_rounds", "count", "lower_is_better"),
        )
        return [
            _metric(
                case, metric, data[metric], unit=unit, direction=direction, source=source,
                measurement_type="observed", reason="Alpha19 deterministic fault recovery evidence",
                evidence_refs=evidence,
            )
            for metric, unit, direction in definitions
        ]


class SecurityGovernanceScorer:
    KEYS = (
        "unauthorized_action_block_rate",
        "approval_scope_integrity",
        "secret_redaction_success",
        "audit_event_coverage",
        "sandbox_escape_block_rate",
    )

    def score(self, case: BenchmarkCase, fixture_paths: list[Path]) -> list[EvaluationMetric]:
        data = _payload(fixture_paths[0])["good"]
        source = str(fixture_paths[0])
        evidence = [source, *data.get("evidence_refs", [])]
        return [
            _metric(
                case, key, data[key], unit="ratio", direction="higher_is_better",
                source=source, reason="Alpha20 deterministic security gate evidence",
                evidence_refs=evidence,
            )
            for key in self.KEYS
        ]


class ScorerRegistry:
    def __init__(self) -> None:
        self._scorers: dict[str, Scorer] = {
            "grounding_coverage": GroundingCoverageScorer(),
            "knowledge_freshness": KnowledgeFreshnessScorer(),
            "script_rubric": ScriptRubricScorer(),
            "storyboard_coverage": StoryboardCoverageScorer(),
            "audio_validity": AudioValidityIntelligibilityScorer(),
            "subtitle_timing": SubtitleTimingScorer(),
            "visual_artifact": VisualArtifactScorer(),
            "render_media": RenderMediaScorer(),
            "style_consistency": StyleConsistencyScorer(),
            "publish_package": PublishPackageScorer(),
            "analytics_learning": AnalyticsLearningScorer(),
            "workflow_reliability": WorkflowReliabilityScorer(),
            "recovery_reliability": RecoveryReliabilityScorer(),
            "security_governance": SecurityGovernanceScorer(),
        }

    def get(self, scorer_id: str) -> Scorer:
        try:
            return self._scorers[scorer_id]
        except KeyError as exc:
            raise KeyError(f"未知 scorer：{scorer_id}") from exc
