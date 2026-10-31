# Alpha22 Gap Analysis

| Requirement | Existing coverage | Gap | Minimal Alpha22 action | Verification |
|---|---|---|---|---|
| Stable CreatorJob trace | RunState, PublishJob, planning provenance | No single aggregate/job ID across all stages | Add immutable CreatorJob model/store; bind run_id, publish job, revisions, metrics, reflection, memory refs | schema/state-transition/store tests |
| Required lifecycle | RunState + PublishJob stages | Required DRAFT→REVIEW→APPROVED→PUBLISH_READY→PUBLISHED not represented centrally | Enforce explicit CreatorJob transitions and invariants | invalid transition and approval bypass tests |
| Topic scoring | Existing nine-component score | Production cost is indirect; duplication too narrow | Add explicit cost/safety fields and multi-field duplicate report | topic score and duplicate fixture tests |
| Research trace | Source + KnowledgeClaim + GroundingReport | CreatorJob lacks claim classification vocabulary and INSUFFICIENT_EVIDENCE | Add claim trace with VERIFIED_FACT/INFERENCE/OPINION/CREATIVE_CONTENT/UNKNOWN and evidence status | unsupported/stale claim gate tests |
| CreatorPlan | Existing script/storyboard/publish artifacts | No normalized plan summary bound to CreatorJob | Add CreatorPlan references/summary without duplicating media | aggregate serialization test |
| H3/ComfyUI production | Real adapter, resource policy, old smoke evidence | Live service stopped at baseline; no Alpha22 per-job resource snapshot | Record job resource evidence, keep heavy stages serial, reuse existing adapter | doctor/live integration when service is available |
| CreatorQA | Separate grounding/video/publish QA | No single publish-blocking report; black/freeze checks split from final QA | Aggregate required QA inputs and duplicate/safety checks | QA missing/failed input tests |
| Human approval | Hash-bound publish approval; approve/reject UI | No REQUEST_REVISION in approval API; central status absent | Add revision request endpoint/store and CreatorJob transition | approval/reject/revision history tests |
| Bilibili adapter | Safe-fail placeholder | No real publish/status/metrics implementation | Implement prepare/validate/status/fetch contract plus real manual-handoff receipt path; retain official API safe-fail until authenticated contract is supplied | BV ID/proof validation, no premature PUBLISHED, duplicate receipt tests |
| Publish failure handling | bounded RecoveryPolicy and deterministic job IDs | Publish job lacks retry counters, next retry, terminal/manual states | Add attempt ledger and bounded/idempotent publish recovery metadata | F3/F4 and retry-budget tests |
| Metrics snapshots | VideoMetrics/FeedbackRecord | Bilibili provider placeholder; unavailable implicit only | Add ContentObservation with observed_at, source, availability map, evidence ref | unavailable and platform/manual-real provenance tests |
| Reflection | PerformanceAnalysis | Required seven-question CreatorReflection not persisted as one artifact | Add structured reflection with facts/interpretations/uncertainties | causal-boundary validation test |
| Memory integration | episodes/lessons/strategies/raw artifacts | CreatorJob refs and promotion gate not explicit | Write compact episodic summary; require multiple real runs before semantic promotion | mock/single-run promotion tests |
| 10-run evidence | None | No CSV schema/validator | Add CSV ledger service and evidence validator; count only real Bilibili published jobs | fake/test/dry-run rejection tests |
| F1–F7 | Many generic recovery tests | No exact Alpha22 phase matrix/evidence | Add deterministic Alpha22 fault harness mapped to F1–F7 | seven named tests and report |
| Regression | Historical reports and matrix | Current results not yet rerun | Run full pytest, focused historical gates, frontend tests/build | command evidence with exit codes |
| Phase ledger | Existing ledger through Alpha21 | No Alpha22 rows | Append every requirement/result/limitation; never remove failures | ledger completeness test/review |
| Resource reporting | execution metrics, resource guard, old H3 measurement | No Alpha22 disk/cache delta and job peaks summary | Capture baseline/end snapshots and live H3 peaks when run | report fields explicit, unknown if unavailable |

## External dependency boundary

The public Bilibili Open Platform confirms video publication/query and data-return capabilities, but detailed contracts are available after identity verification, application setup, and UP authorization. Until those prerequisites are supplied, Alpha22 can safely complete a real manual-handoff workflow:

1. Alysia prepares and validates the immutable Bilibili upload package.
2. A human approves the exact package.
3. The human publishes it on Bilibili.
4. The human records the returned BV identifier, publication URL/time, and evidence path.
5. Alysia validates the receipt and only then transitions the CreatorJob to PUBLISHED.
6. Metrics are imported as real observations with timestamps and unavailable fields; no synthetic value is accepted.

This path is real, auditable, and human-supervised, but it does not claim automated platform API submission.

