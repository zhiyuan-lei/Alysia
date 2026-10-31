# Alpha22 Checkpoint 02 — Topic Discovery + Research / Grounding

## Status

PASS

## Architecture

- `TopicDiscoveryService` adapts existing `TrendItem` providers or a human seed into Alpha22 `TopicCandidate` records.
- `TopicRanker` validates bounded factors, applies centralized `TopicScoringWeights`, performs history-aware duplicate checks, and returns accepted/rejected candidates with score contributions and rejection reasons.
- `ResearchSource` represents bounded source metadata and excerpts; `ResearchArtifactStore` keeps redacted, size-limited source content outside CreatorJob.
- `ClaimExtractor` creates stable, source-linked claim IDs; `GroundingService` keeps claim classification separate from evidence status.
- `CreatorJobResearchIntegrator` writes the selected topic, compact source traces, grounded claims, and uncertainties into the existing CreatorJob through versioned `CreatorJobStore.update()`.

## Files changed

- `alysia/creator/models.py`
- `alysia/creator/topics.py`
- `alysia/creator/research.py`
- `alysia/creator/__init__.py`
- `tests/test_topic_research.py`
- `alpha22/checkpoints/02_topic_research.md`

## Duplicate strategy

- Exact case-insensitive title match.
- Normalized title match using existing `planning.novelty.normalize_topic`.
- Recent CreatorJob comparison against topic, selected title, and core claims.
- Lightweight semantic-like similarity using existing normalized token/bigram Jaccard; no embedding model was introduced.
- Duplicate risk, match method/reference, score breakdown, and rejection reason remain inspectable.

## Grounding rules

- `VERIFIED_FACT + SUPPORTED` requires a usable source reference.
- Conflicting sources produce `CONFLICTING`; the service never chooses one silently.
- Missing, unknown, or unavailable evidence can produce `INSUFFICIENT_EVIDENCE`.
- `INFERENCE` remains inference even when supported.
- Source reliability affects confidence but never makes official content 100% certain.
- `CREATIVE_CONTENT` may be supported without factual sources while retaining its explicit classification.
- Unknown-only reliability produces `PARTIALLY_SUPPORTED`.

## Security and size limits

- Research URLs reuse Alpha20 `NetworkPolicy`; file, unsupported scheme, loopback, literal private network, credential URL, and sensitive credential query parameters are rejected.
- Text, metadata, and artifact payloads reuse Alpha20 `Redactor`.
- `ResearchLimits` centralizes max sources, max claims, excerpt length, artifact length, and metadata size.
- CreatorJob stores only bounded traces and artifact paths, not full research text.

## Tests executed

```text
uv run pytest tests/test_topic_research.py -q
uv run pytest tests/test_alpha22_creator.py tests/test_creator_job.py tests/test_topic_research.py -q
```

## Test results

- Step 2 focused: `23 passed`.
- Step 1 + Step 2 combined regression: `41 passed`.
- Exit code 0; no warnings.
- No network retrieval, GPU workload, login, content creation, or publish action executed.

## Evidence paths

- `tests/test_topic_research.py`
- `tests/test_creator_job.py`
- `tests/test_alpha22_creator.py`
- `alpha22/checkpoints/02_topic_research.md`

## Known limitations

- Semantic-like duplicate detection is deterministic lexical similarity, not embeddings.
- Conflicting source stance is supplied explicitly; no automated NLI or truth adjudication is attempted.
- Source reliability is a lightweight grounding input, not a truth score.
- Artifact persistence is bounded local JSON without multi-process locking.
- No real retrieval smoke test or full repository test suite was run in this step.

## Git diff summary

- Tracked baseline remains 28 modified files with 5,129 insertions and 113 deletions.
- `alysia/creator/` and `alpha22/` were already untracked aggregate paths, so ordinary tracked diff cannot isolate their per-step lines; this checkpoint lists every Step 2 file touched.
- `tests/test_topic_research.py` is newly untracked.
- No reset, clean, restore, checkout, stage, commit, or deletion was performed.

## Next safe step

Only recommend: Alpha22 Step 3 — CreatorPlan + Production Orchestration. Stop after this checkpoint; do not execute Step 3 automatically.

