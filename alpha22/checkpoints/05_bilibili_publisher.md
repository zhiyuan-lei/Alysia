# Alpha22 Checkpoint 05 — Bilibili Publisher Adapter + Publish Safety

## Status

PASS

## Publisher architecture

- `Publisher` defines `prepare`, `validate`, `publish`, `status`, and `cancel`.
- `BilibiliPublisher` owns CreatorJob/QA/Review/artifact preflight and delegates network or UI work only to an injected `BilibiliTransport`.
- `PublisherStore` atomically persists redacted requests, packages, confirmations, and platform-layer records. Publisher states remain distinct from CreatorJob domain states.
- The prior `manual_handoff` compatibility surface remains available; no undocumented platform endpoint was introduced.

## Publish modes

- `VALIDATE_ONLY` performs gate checks and writes no package or publish record.
- `PREPARE_ONLY` creates a secret-free immutable package for human inspection and performs no transport call.
- `LIVE` is isolated behind `BILIBILI_LIVE_PUBLISH_ENABLED = False` plus an injected verified transport and ready session provider.

## Publish gate and snapshot

- Requires APPROVED, PUBLISH_READY, current PASS/PASS_WITH_WARNINGS QA, current APPROVE review, matching revision, no blocking QA issue, required metadata, and current VALID video/thumbnail manifests.
- The persisted request/package freezes title, description, tags, video and thumbnail hashes, revision, QA ID, and review ID.
- The full gate is re-run at publish time, then hashes/revision/snapshot are checked again immediately before final submit. Stale snapshots terminate with `STALE_PUBLISH_REQUEST` or a more specific validation issue.
- Bilibili metadata is translated into `BilibiliPublishPayload`; mutable platform limits remain centralized in `BilibiliCapabilityConfig` and unverified limits are `UNKNOWN`.

## Human confirmation and authentication

- Review APPROVE never implies publish. LIVE requires a second persisted `PublishConfirmation` with a non-forbidden `human:<identifier>` actor, timestamp, request ID, and revision.
- System, agent, model, automation, supervisor, and equivalent identities cannot confirm.
- Authentication crosses the adapter boundary only as runtime-only `SessionLease.handle`; it is not a serializable model field.
- Missing, expired, rejected, CAPTCHA/risk/manual-verification states stop for human handling. Authentication failure is never treated as a network retry.
- Existing Alpha20 redaction is reused and extended for Bilibili-specific credential field names. Requests, records, packages, confirmations, audit context, exceptions, and this checkpoint contain no credential values.

## Retry, UNKNOWN, reconciliation, and cancellation

- Only explicitly classified pre-submit transient failures receive a bounded retry (default maximum two upload attempts).
- A timeout or unexpected error after final submit becomes `UNKNOWN`; direct re-publish is blocked.
- `reconcile` can move reliable remote success to `PUBLISHED`, confirmed not-published/failure to `FAILED` with safe retry marked, or retain `UNKNOWN` when the result remains indeterminate.
- `PUBLISHED` requires a reliable platform content ID. Test transport IDs are marked `TEST_ONLY` and never update CreatorJob field-run evidence.
- Cancellation is local and safe before submit; after submission may have started it refuses to claim remote retraction.

## Idempotency and duplicate safety

- The stable idempotency key binds platform, job ID, revision, and video hash.
- A process-local lock binds platform, job ID, and revision.
- Persistent history blocks another publish for the same platform/job/revision/video when an existing record is PROCESSING, PUBLISHED, or UNKNOWN.
- The remote-success/local-timeout test proves resume performs reconciliation without a second submit.

## Platform integration

- Selected strategy: `PREPARE_ONLY + manual final platform action` by default.
- LIVE has an injectable transport contract but no transport is claimed to be an official working API in this step.
- No browser automation, platform login, reachability probe, upload, submit, or real publication was performed.

## Control Center

No changes. The existing Step 4 interface remains unchanged; a LIVE button was not added before a verified field-test boundary exists.

## Tests executed

```text
uv run pytest tests/test_alpha22_creator.py -q
uv run pytest tests/test_creator_publisher.py -q
uv run pytest tests/test_creator_publisher.py tests/test_security.py -q
uv run python -m py_compile alysia/creator/publisher.py alysia/creator/bilibili.py alysia/creator/__init__.py alysia/security/redaction.py tests/test_creator_publisher.py
uv run pytest tests/test_alpha22_creator.py tests/test_creator_job.py tests/test_topic_research.py tests/test_creator_production.py tests/test_creator_qa_review.py tests/test_creator_publisher.py -q
```

## Results

- Legacy Alpha22 compatibility: 12 passed.
- Step 5 focused: 27 passed.
- Step 5 publisher plus security regression: 60 passed.
- Step 1–5 combined targeted regression: 107 passed.
- Exit code 0; no warnings in the final targeted run.

## PREPARE_ONLY smoke

PASS. A local fixture completed CreatorJob → production artifacts → QA → explicit human review → PUBLISH_READY → validation → secret-free package. Transport upload and submit counters remained zero.

## Real publication

NOT_EXECUTED

## Known limitations

- No currently verified Bilibili upload contract or Creator Center automation backend is configured; LIVE remains disabled.
- Platform title/tag/description/media/category/scheduling limits remain `UNKNOWN` until verified against an authorized current platform contract.
- The lock is process-local; persistent JSON state supplies duplicate guarding but is not a distributed transaction lock.
- Reconciliation quality depends on the future transport's reliable status lookup; otherwise records correctly remain UNKNOWN for human inspection.
- Successful TEST_ONLY transport records do not transition CreatorJob to PUBLISHED or enter Beta evidence.
- Control Center integration and full repository tests were not performed.

## Files changed

- `alysia/creator/publisher.py`
- `alysia/creator/bilibili.py`
- `alysia/creator/__init__.py`
- `alysia/security/redaction.py`
- `tests/test_creator_publisher.py`
- `alpha22/checkpoints/05_bilibili_publisher.md`

## Git status

- Baseline/final branch: `main`; HEAD: `55da6463f0ff50e5c7e51fb1b9496aca5c8481fa`.
- Existing tracked baseline remains 28 modified files with 5,129 insertions and 113 deletions.
- Before this checkpoint, untracked aggregate entries were 161; Step 5 files live inside existing untracked creator/security aggregates plus the new test and checkpoint.
- Staged changes: 0.
- No reset, clean, restore, checkout, stage, commit, deletion, H3/ComfyUI/GPU action, or real Bilibili action was performed.

## Next safe step

Alpha22 Step 6 — Observation Metrics + Creator Reflection + Memory Integration. Do not execute it automatically, and do not enable LIVE or publish from this checkpoint.
