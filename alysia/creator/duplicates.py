from __future__ import annotations

import json
import re

from alysia.creator.models import CreatorJob, DuplicateCheckReport, DuplicateMatch


def _tokens(value: str) -> set[str]:
    normalized = re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", value.casefold())
    ascii_words = set(re.findall(r"[a-z0-9]+", value.casefold()))
    chinese = "".join(re.findall(r"[\u4e00-\u9fff]", normalized))
    return ascii_words | {chinese[index : index + 2] for index in range(max(0, len(chinese) - 1))}


def _similarity(left: str, right: str) -> float:
    left_normalized = re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", left.casefold())
    right_normalized = re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", right.casefold())
    if not left_normalized or not right_normalized:
        return 0.0
    if left_normalized == right_normalized:
        return 1.0
    left_tokens = _tokens(left)
    right_tokens = _tokens(right)
    union = left_tokens | right_tokens
    return len(left_tokens & right_tokens) / len(union) if union else 0.0


class CreatorDuplicateDetector:
    def __init__(self, *, threshold: float = 0.72) -> None:
        if not 0 <= threshold <= 1:
            raise ValueError("threshold must be between 0 and 1")
        self.threshold = threshold

    def check(self, candidate: CreatorJob, history: list[CreatorJob]) -> DuplicateCheckReport:
        matches: list[DuplicateMatch] = []
        candidate_values = self._dimensions(candidate)
        for existing in history:
            if existing.job_id == candidate.job_id:
                continue
            existing_values = self._dimensions(existing)
            for dimension, value in candidate_values.items():
                other = existing_values[dimension]
                if not value or not other:
                    continue
                similarity = _similarity(value, other)
                if similarity >= self.threshold:
                    matches.append(
                        DuplicateMatch(
                            existing_job_id=existing.job_id,
                            dimension=dimension,
                            similarity=similarity,
                            method="normalized_token_jaccard",
                            reference=other[:240],
                        )
                    )
        matches.sort(key=lambda item: (item.existing_job_id, item.dimension, -item.similarity))
        return DuplicateCheckReport(
            passed=not matches,
            matches=matches,
            threshold=self.threshold,
        )

    @staticmethod
    def _dimensions(job: CreatorJob) -> dict[str, str]:
        claims = " ".join(item.claim for item in job.claims)
        visual = json.dumps(job.visual_plan, ensure_ascii=False, sort_keys=True, default=str)
        structure = CreatorDuplicateDetector._script_structure(job.script)
        return {
            "topic": job.topic,
            "title": job.selected_title,
            "core_claim": claims,
            "visual_plan": visual,
            "script_structure": structure,
        }

    @staticmethod
    def _script_structure(script: str) -> str:
        lines = [line.strip() for line in script.splitlines() if line.strip()]
        if not lines:
            return ""
        headings = [
            re.sub(r"[0-9]+", "#", line.casefold())
            for line in lines
            if len(line) <= 32 or re.match(r"^(#{1,6}|第.+[章节]|[一二三四五六七八九十]+[、.])", line)
        ]
        if headings:
            return " | ".join(headings)
        buckets = ["short" if len(line) < 24 else "medium" if len(line) < 80 else "long" for line in lines]
        return " | ".join(buckets)
