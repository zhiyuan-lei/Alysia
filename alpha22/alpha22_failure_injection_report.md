# Alpha22 Step 7 Failure Injection Report

Date: 2026-08-09  
Status: PASS  
Environment: isolated local tests and injected transports only

## Summary

| Failure | Result | Primary evidence |
|---|---|---|
| F1 ComfyUI | PASS | `tests/test_creator_recovery.py`; Step 1–7 JUnit |
| F2 H3 | PASS | `tests/test_creator_recovery.py`; Step 1–7 JUnit |
| F3 Publisher | PASS | `tests/test_creator_recovery.py`, `tests/test_creator_publisher.py` |
| F4 Runtime/network interruption | PASS | `tests/test_creator_recovery.py` |
| F5 Mid-process exit | PASS | recovery, QA/review, observation, and memory persistence tests |
| F6 Approval/revision | PASS | recovery, QA/review, publisher, and legacy fault tests |
| F7 Grounding | PASS | recovery, topic/research, QA/review, and legacy fault tests |

## F1 — ComfyUI failure

- Fault: injected connection failure, timeout, and provider error at the image task.
- Expected: bounded failure, preserved job/plan/upstream task, released GPU lock, partial output not valid, resumable failed branch.
- Actual: the visual task exhausted two task attempts and persisted `FAILED/retryable`; the voice task remained `SUCCEEDED`; composite stayed blocked; the partial manifest was `PARTIAL`; the resource phase was empty after failure.
- Recovery: startup reset only the recoverable visual branch and its blocked dependent. Resume ran visual and composite once; voice call count remained one.
- Test: `test_f1_f2_bounded_failure_restart_resumes_only_failed_task` with three ComfyUI fault points.
- Result: PASS.

## F2 — H3 failure

- Fault: injected timeout, process failure, and `RESOURCE_EXHAUSTED`.
- Expected: persisted task state, bounded retry, released resource lock, failed-task resume rather than whole-plan restart.
- Actual: each injected fault stopped after the configured task budget; repeated startup recovery is also bounded to one cycle and then classified `MANUAL_INTERVENTION`.
- Recovery: the first startup recovery resumed the failed branch; a second exhausted recovery cycle remained failed and required a human.
- Tests: the parameterized F1/F2 test and `test_startup_retry_budget_is_bounded_across_restarts`.
- Result: PASS.

## F3 — Publisher uncertainty

- Fault: pre-submit transient upload failure; remote-accepted/local-timeout after submit.
- Expected: bounded pre-submit retry; post-submit `UNKNOWN`; no blind submit; reconcile into published, not-published, or still unknown.
- Actual: upload retry stayed bounded with one PublishRecord and stable idempotency key. Post-submit timeout persisted `UNKNOWN`; restarted publisher called reconcile, while submit call count stayed one.
- Recovery: remote `PUBLISHED` produced a reliable TEST_ONLY content ID; `NOT_FOUND` produced retryable `FAILED`; unresolved state remained `UNKNOWN`.
- Tests: `test_process_lock_and_safe_pre_submit_retry`, `test_post_submit_timeout_becomes_unknown_and_never_blind_retries`, and `test_f3_unknown_restart_reconciles_without_second_submit`.
- Result: PASS; NO DUPLICATE SUBMIT proven.

## F4 — Runtime/network interruption

- Fault: persisted production `RUNNING`; publisher `SUBMITTING`/`PROCESSING`/`UNKNOWN`; service objects reconstructed over the same stores.
- Expected: classify by side-effect risk instead of converting every state to generic failure.
- Actual: local generation used artifact integrity to choose complete vs retry. Submit-risk states became/remained `UNKNOWN` and emitted reconciliation-required audit events. Completed QA/review and TEST_ONLY learning artifacts reloaded from disk.
- Recovery: `CreatorRecoveryService.recover()` plus idempotent domain-store retries.
- Tests: orphan/missing artifact, submitting restart, publisher reconciliation, QA/review restart, observation/memory tests.
- Result: PASS.

## F5 — Mid-process exit and crash consistency

- Fault: task state before success; artifact before manifest; manifest before artifact loss; QA/review persisted before the next transition; candidate before Reflection link.
- Expected: no false success and no duplicate human or learning artifact.
- Actual: complete orphan artifact was registered without regeneration; stale manifest forced rebuild; persisted QA/review resumed with one review; repeated candidate creation repaired the interrupted Reflection link without creating a second candidate.
- Recovery: atomic stores remain authoritative; transition APIs revalidate current revision and evidence.
- Tests: `test_f4_f5_orphan_artifact_is_registered_then_missing_file_is_rebuilt`, `test_f5_qa_and_review_survive_restart_without_duplicate_human_action`, and `test_memory_candidate_retry_repairs_interrupted_reflection_link`.
- Result: PASS.

## F6 — Rejection, revision, and stale UI action

- Fault: QA pass followed by reject; revision request/content change; duplicate approve/confirm; browser request from an old revision.
- Expected: rejected content cannot prepare or publish; old QA/review/request becomes stale; human duplicates do not duplicate side effects.
- Actual: reject blocked both publisher operations and submit count stayed zero. Grounding/content changes incremented revision, returned approval to draft/not-ready, and rejected old review/request. Duplicate review was idempotent; duplicate confirmation was explicitly blocked with one persisted confirmation.
- Recovery: reload current job revision and revalidate all approval and request references.
- Tests: `test_f6_reject_blocks_prepared_publish_and_stale_request`, `test_f6_revision_and_grounding_change_invalidate_old_approval`, QA/review stale tests, and legacy F6.
- Result: PASS.

## F7 — Bad, stale, conflicting, or missing grounding

- Fault: unsupported/missing/stale/conflicting evidence and grounding changed after approval.
- Expected: evidence classification remains honest; unsupported factual content fails QA; downstream approval cannot survive grounding revision.
- Actual: topic/research tests preserve conflicting and insufficient states; QA blocked a conflicting claim presented as fact; changed claims invalidated old approval, QA, review, and publisher request.
- Recovery: repeat research/plan/QA on the new revision; old artifacts remain evidence history only.
- Tests: `test_f7_conflicting_research_cannot_pass_qa`, topic/research negative tests, QA grounding tests, legacy F7.
- Result: PASS.

## Additional injected boundaries

- Corrupt or missing artifacts are rehashed by Production, QA, and Publisher rather than trusted from a stale manifest.
- Wrong observation content identity/revision and TEST_ONLY-as-real evidence are rejected.
- TEST fixture memory cannot enter production storage; repeated snapshots from one CreatorJob keep semantic support count at one.
- Cross-subsystem success is exercised by the Step 6 TEST_ONLY fixture through artifacts, QA, human review, publish record, observation, reflection, and memory candidate with a stable job/revision evidence chain.
- Cross-subsystem failure is exercised by approved content mutation followed by stale QA/review/publisher validation failure.

## Evidence

- `evaluation/alpha22/alpha22_step7_steps_1_7.junit.xml`
- `evaluation/alpha22/alpha22_step7_full_regression.junit.xml`
- `alpha22/recovery_state_matrix.md`
