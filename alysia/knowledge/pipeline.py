from __future__ import annotations

import hashlib
from urllib.parse import urlparse

from alysia.knowledge.conflicts import ConflictDetector
from alysia.knowledge.extraction import ClaimExtractor
from alysia.knowledge.models import EvidenceSource, ResearchKnowledgeResult
from alysia.knowledge.store import KnowledgeStore
from alysia.knowledge.verification import ClaimVerifier
from alysia.schemas.research import ResearchResult, Source


class SourceNormalizer:
    def normalize(self, source: Source) -> EvidenceSource:
        content_hash = source.content_hash or hashlib.sha256(
            f"{source.title}\x1f{source.url}\x1f{source.note}".encode("utf-8")
        ).hexdigest()
        return EvidenceSource(
            source_id=source.id,
            url=source.url,
            title=source.title,
            publisher=source.publisher,
            domain=source.domain or urlparse(source.url).netloc,
            author=source.author,
            published_at=source.published_at,
            retrieved_at=source.retrieved_at,
            source_type=source.source_type,
            freshness_class="dated" if source.published_at else "unknown",
            content_hash=content_hash,
            access_note=source.access_note or source.note,
            citation_note=source.citation_note,
            reliability_notes=[source.note] if source.note else [],
            evidence_origin=source.evidence_origin,
            observation_scope=source.observation_scope,
        )


class ResearchKnowledgePipeline:
    def __init__(self, store: KnowledgeStore) -> None:
        self.store = store
        self.normalizer = SourceNormalizer()
        self.extractor = ClaimExtractor()
        self.verifier = ClaimVerifier(store)
        self.conflicts = ConflictDetector(store)

    def ingest(self, research: ResearchResult, *, domain: str = "general") -> ResearchKnowledgeResult:
        source_ids = []
        for raw_source in research.sources:
            source = self.store.add_source(self.normalizer.normalize(raw_source))
            source_ids.append(source.source_id)

        claim_ids: list[str] = []
        unsupported = []
        verification_results = []
        conflict_ids: list[str] = []
        for candidate in self.extractor.extract(research, domain=domain):
            claim, verification = self.verifier.verify_candidate(candidate)
            verification_results.append(verification)
            if claim is None:
                unsupported.append(candidate)
                continue
            self.store.add_claim(claim)
            claim_ids.append(claim.claim_id)
            conflict_ids.extend(item.conflict_id for item in self.conflicts.detect_for(claim))
        return ResearchKnowledgeResult(
            topic=research.topic,
            source_ids=source_ids,
            claim_ids=claim_ids,
            unsupported_claims=unsupported,
            verification_results=verification_results,
            conflict_ids=sorted(set(conflict_ids)),
        )

