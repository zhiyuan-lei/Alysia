# Alpha22 Existing Architecture Inspection

## Scope
Inspected Alpha18–21 planning, knowledge, production, QA, security, approval, Control Center, publishing, feedback, analytics, learning, reliability, and regression surfaces before Alpha22 code changes.

## Existing end-to-end flow

```text
Trend providers
  -> CreatorLoop / TopicGenerator / TopicScoringEngine / EditorialBoard
  -> human-approved PlanSlot
  -> RunManager / AlysiaOrchestrator
  -> Research + Knowledge grounding
  -> ProductionPlan / serial GPU providers / H3-ComfyUI
  -> text/audio/video/publish QA
  -> REVIEW_READY
  -> PublishingService package-hash-bound approval
  -> publishing provider
  -> feedback / analytics import
  -> PerformanceAnalysis
  -> EpisodeMemory / lessons / strategy / next experiment
```

## Reusable mechanisms

### Planning and research
- Topic candidates already score relevance, freshness, audience fit, novelty, evidence quality, feasibility, experiment value, duplication, and risk.
- CreatorLoop is explicit and approval-gated; mock/testing provenance is carried into the run.
- Knowledge models preserve source retrieval time, type, origin, claim confidence/status, conflicts, freshness, grounding, and unresolved research status.
- Verified claims require evidence and opinions cannot become verified facts.

### Production and resources
- Production planning, provider routing, fallback recording, caching, execution metrics, and quality gates already exist.
- H3/ComfyUI uses a loopback adapter, low-VRAM profile, serial-GPU requirement, unload behavior, timeout, cancellation, and bounded retry configuration.
- The existing real H3 profile is near the 8 GB VRAM ceiling and therefore cannot run concurrently with another heavy GPU workload.

### QA and approval
- Video QA checks existence, streams, duration, resolution, codecs, sample rate, complete decode, and AV duration alignment.
- Publish QA checks final video, video QA, title/topic consistency, title risk, description/source section, tags, cover readability, and configured dimensions.
- Publishing approval is bound to action, run, provider scope, immutable package hash, version/nonce, and one-time consumption.
- Control Center exposes run artifacts, QA, risk/recovery, approve, and reject. Rejection has a reason and is audited.
- Studio artifact ownership and revision requests already preserve versions internally, but the publish approval UI/API does not expose REQUEST_REVISION.

### Publishing, observation, and learning
- PublishingService separates package validation from provider submission, derives deterministic job IDs, prevents duplicate submission after success, blocks real publish when mock artifacts exist, and redacts provider errors.
- Metrics schemas timestamp collection and keep unavailable numeric fields as null.
- PerformanceAnalysis separates observed facts from low-confidence hypotheses and explicitly denies causal proof from one video.
- Memory is already layered into per-run episodes, multi-run lessons, strategies, and raw run artifacts; mock/testing evidence cannot promote real lessons.

### Reliability and historical gates
- Atomic state writes, backups, checkpoints, bounded retry/backoff, human escalation, resource guards, and idempotent publish recovery are present.
- Existing tests cover ComfyUI unavailable, H3 OOM fallback, state recovery, publish deduplication, policy failures, stale knowledge, human approval, and mock-to-real boundaries.
- Alpha18–21 reports record passing historical gates; Alpha22 must rerun current regression rather than rely only on those reports.

## Confirmed limitations
- No unified CreatorJob aggregate or single Alpha22 job_id spans every artifact.
- Bilibili publish/analytics/feedback providers are safe-fail placeholders and currently make no network requests.
- Detailed Bilibili Open Platform endpoint contracts require authenticated developer/application/UP authorization; public pages only confirm that video management and data-return capabilities exist.
- Current duplicate detection only compares topic text.
- Current Control Center has approve/reject but no publish REQUEST_REVISION action.
- Current schemas do not provide an explicit field-level unavailable map for metrics.
- No Alpha22 Beta CSV/evidence validator or F1–F7 phase-specific harness exists.

