# Alpha22 Checkpoint 04 — CreatorQA + Human Review Gate

## Status

PASS

## QA architecture

- `QAReport` binds QA, CreatorJob, CreatorPlan, ProductionPlan, and exact job revision.
- Structured `QAIssue` records category, severity, code, evidence/artifact refs, blocking status, and suggested action.
- `CreatorQAService` runs independent grounding, content, media, metadata, and safety checkers; aggregates PASS/PASS_WITH_WARNINGS/FAIL/INCOMPLETE; persists the report; and records QA_STARTED/QA_COMPLETED.
- QA PASS only moves DRAFT to REVIEW eligibility. It never sets APPROVED or PUBLISH_READY.

## Blocking rules

- Missing/empty or manifest-mismatched video/thumbnail, invalid artifacts, unreadable/zero-duration media, required audio loss, severe AV delta, factual claim trace loss, uncertainty presented as fact, empty script/core message, direct contradiction, critical secret/private-network leakage, and unsafe artifact paths block review approval.
- Deterministic lexical title/description/tag mismatches and excessive repetition are explainable non-blocking warnings.

## Human review architecture

- `ReviewDecision` persists APPROVE/REJECT/REQUEST_REVISION, reason, controlled `human:` reviewer, timestamp, QA ID, job revision, requested changes, and redacted metadata.
- APPROVE accepts only fresh PASS/PASS_WITH_WARNINGS QA and stores `approval_ref=review_id`.
- PUBLISH_READY is a separate explicit method that requires the same fresh QA and APPROVE decision; it performs no platform action.
- REJECT and REQUEST_REVISION remain NOT_READY. Repeated identical review requests are idempotent; conflicting requests are rejected.

## Revision invalidation and staleness

- REQUEST_REVISION snapshots revision N, creates N+1, sets REVISION_REQUIRED, and invalidates the old QA.
- `CreatorJobStore.update()` invalidates approval when script, title, description, tags, media, grounding, plan, visual, or audio data changes.
- `CreatorQAService.load_report()` exposes old-revision reports as STALE.
- Review submission and PUBLISH_READY entry reject stale QA/review revisions, preventing approval of A and release of B.
- Approved content mutations through `HumanReviewService.update_content()` emit APPROVAL_INVALIDATED.

## Control Center changes

None. Existing Alpha21 UI is unchanged; Step 4 delivers a domain/service-level gate suitable for later minimal integration without modifying the older publish/run approval surface.

## Persistence and audit

- `QAReviewStore` uses bounded, path-safe atomic JSON files with QA/review history grouped by CreatorJob.
- Existing Alpha20 `AuditLog` records QA_STARTED, QA_COMPLETED, REVIEW_APPROVED, REVIEW_REJECTED, REVISION_REQUESTED, APPROVAL_INVALIDATED, and PUBLISH_READY_ENTERED with redacted compact context.
- Existing `Redactor`, `NetworkPolicy`, approval identity policy, production artifact registry, media tooling, and CreatorJob revision store are reused.

## Tests executed

```text
uv run pytest tests/test_creator_qa_review.py -q
uv run pytest tests/test_alpha22_creator.py tests/test_creator_job.py tests/test_topic_research.py tests/test_creator_production.py tests/test_creator_qa_review.py -q
```

## Results

- Step 4 focused: `22 passed`.
- Step 1–4 combined regression: `80 passed`.
- Exit code 0; no warnings.
- No H3/ComfyUI startup, GPU work, Bilibili request, authentication, upload, or publish action occurred.

## Known limitations

- QA is deterministic and intentionally does not attempt universal aesthetic/content scoring.
- Advanced black-frame, lip-sync, semantic contradiction, and visual-quality AI checks are not implemented.
- Production media QA requires the existing ffprobe tool; unavailable probing produces INCOMPLETE and cannot authorize approval.
- Review persistence is local single-process JSON, and the reused audit log is logically append-only but not tamper-proof.
- No administrator override exists; FAIL/INCOMPLETE cannot be approved.
- Control Center UI/API was not extended in this step.
- Full repository tests were not run.

## Files changed

- `alysia/creator/store.py`
- `alysia/creator/review.py`
- `alysia/creator/__init__.py`
- `tests/test_creator_qa_review.py`
- `alpha22/checkpoints/04_creator_qa_review.md`

## Git diff summary

- Tracked baseline remains 28 modified files with 5,129 insertions and 113 deletions.
- Creator/checkpoint directories remain untracked aggregates; ordinary tracked diff cannot isolate their per-step lines. This checkpoint lists every Step 4 file touched.
- `tests/test_creator_qa_review.py` is newly untracked.
- No reset, clean, restore, checkout, stage, commit, or deletion was performed.

## Next safe step

Only recommend: Alpha22 Step 5 — Bilibili Publisher Adapter + Publish Safety. Stop after this checkpoint; do not execute Step 5 automatically.

