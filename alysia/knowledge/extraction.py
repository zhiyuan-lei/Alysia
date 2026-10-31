from __future__ import annotations

from alysia.knowledge.models import ClaimCandidate, normalize_claim_key
from alysia.schemas.research import ResearchResult


class ClaimExtractor:
    """确定性离线抽取器；未来 LLM 抽取也必须返回同一 schema 和 source refs。"""

    TIME_MARKERS = ("当前", "目前", "最新", "版本", "价格", "支持", "截至", "现任")
    OPINION_MARKERS = ("我认为", "可能更好", "值得", "偏好", "建议")

    def extract(self, research: ResearchResult, *, domain: str = "general") -> list[ClaimCandidate]:
        source_refs = [source.id for source in research.sources]
        output: list[ClaimCandidate] = []
        for statement in research.key_points:
            time_sensitive = any(marker in statement for marker in self.TIME_MARKERS)
            opinion = any(marker in statement for marker in self.OPINION_MARKERS)
            claim_type = "opinion" if opinion else ("time_sensitive" if time_sensitive else "stable")
            output.append(
                ClaimCandidate(
                    statement=statement,
                    normalized_key=normalize_claim_key(statement),
                    topic=research.topic,
                    domain=domain,
                    claim_type=claim_type,
                    source_refs=source_refs,
                    time_sensitive=time_sensitive,
                    supported=bool(source_refs),
                    unsupported_reason=None if source_refs else "research key point 没有绑定 source refs",
                )
            )
        return output

