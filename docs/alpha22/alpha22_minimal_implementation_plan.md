# Alpha22 Minimal Implementation Plan

## Success criteria
- Every Alpha22 artifact traces to one stable CreatorJob ID.
- No transition to PUBLISHED is possible without passed QA, a valid human approval, and a validated Bilibili receipt.
- Mock/testing/dry-run/synthetic evidence never increments the real Beta count.
- F1–F7 and Alpha18–21 regression have command-level evidence.
- Without ten real records, final status is at most READY_FOR_FIELD_RUN; without a usable real publication path, status is BLOCKED.

## Surgical file plan

1. Add `alysia/creator/`:
   - `models.py`: CreatorJob, CreatorPlan, ResearchClaimTrace, CreatorQA, Revision, ContentObservation, CreatorReflection, PublishAttempt, BetaEvidenceRow.
   - `store.py`: atomic aggregate storage, revision snapshots, observation/reflection append semantics.
   - `service.py`: state transitions and bridges to existing RunManager, PublishingService, LearningPipeline.
   - `qa.py`: aggregate existing grounding/video/publish QA plus duplicate/safety results.
   - `evidence.py`: CSV ledger and strict real-run validator.
2. Extend the existing Bilibili provider boundary without guessing private endpoints:
   - prepare/validate/status/fetch_metrics contracts;
   - real manual-handoff receipt validation;
   - official API mode remains fail-closed until authenticated contract settings exist.
3. Extend Control Center API/UI with CreatorJob detail, APPROVE, REJECT, REQUEST_REVISION, and record-publication actions.
4. Reuse existing approval/security/reliability services; do not create an Alpha22 bypass.
5. Add exact F1–F7 tests and Alpha22 integration tests.
6. Append Alpha22 phase ledger and generate regression/resource/Beta reports from actual outputs.

## Implementation sequence and verification
- Models/store first → schema, invariants, atomic persistence tests.
- QA/transitions → bypass, failed QA, revision, receipt tests.
- Bilibili manual-handoff/observation → provenance and idempotency tests.
- Control Center → API tests, frontend component tests/build.
- Fault harness → F1–F7 focused run.
- Regression → full Python suite and frontend suite/build.
- Field evidence → validate actual CSV; never generate rows to satisfy count.

## Non-goals
- No Alpha23.
- No browser-cookie automation or unofficial endpoint scraping.
- No second platform.
- No replacement of H3/ComfyUI or Alpha20 security.
- No refactoring unrelated historical modules.

