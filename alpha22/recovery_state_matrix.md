# Alpha22 Recovery State Matrix

Date: 2026-08-09  
Scope: Step 7 local, deterministic recovery only

| Subsystem | State before interruption | Possible side effect | Safe automatic recovery? | Needs reconciliation? | Needs human? | Expected state |
|---|---|---|---|---|---|---|
| Production | `RUNNING`, valid manifest and artifact | Local artifact complete | Yes; revalidate hash and mark complete | No | No | `SUCCEEDED`, no regeneration |
| Production | `RUNNING`, one complete artifact, manifest missing | Local artifact complete but unregistered | Yes; validate and register | No | No | `SUCCEEDED` with recovered manifest |
| Production | `RUNNING`, no complete artifact | No durable successful output | Yes | No | No | `PENDING`, then resume task |
| Production | `SUCCEEDED`, artifact missing/hash changed | Stale success claim | Yes | No | No | `PENDING`, stale refs cleared |
| Production | Retryable `FAILED`, first startup recovery | No external side effect | Yes, once | No | No | `PENDING`; prior attempts retained in history |
| Production | Retryable `FAILED`, startup budget exhausted | Repeated local failure | No | No | Yes | `FAILED`, `MANUAL_INTERVENTION` |
| Production | Non-retryable `FAILED` | Invalid input/provider contract | No | No | Yes | `FAILED`, `MANUAL_INTERVENTION` |
| Production | Multiple orphan artifact candidates | Ambiguous output selection | No | No | Yes | Preserve state; select manually |
| QA | Report saved before CreatorJob transition | No external side effect | Yes; reload report and re-enter gate | No | No | Persisted QA remains authoritative; job stays conservative |
| Review | Decision saved before publish-ready transition | No external side effect | Yes; reload and revalidate current revision | No | No | Transition only with current QA/review |
| Publisher | `UPLOADING`, submission not started | Upload may be incomplete, no final submit | Yes, with stable idempotency key | No | No | Retryable `FAILED` |
| Publisher | `SUBMITTING` | Remote submit may exist | No blind retry | Yes | Only if reconciliation cannot resolve | `UNKNOWN` |
| Publisher | `PROCESSING` or `UNKNOWN` | Remote publication may exist | No blind retry | Yes | Only if reconciliation remains unknown | `PUBLISHED`, retryable `FAILED`, or `UNKNOWN` |
| Publisher | `PUBLISHED` with reliable content ID | Remote publication exists | No further submit | No | No | Terminal record; TEST_ONLY does not update field-run evidence |
| Observation | Observation saved before compact CreatorJob ref | No external side effect | Yes; idempotent record retry | No | No | One observation file and one job reference |
| Reflection | Reflection saved before compact CreatorJob ref | No external side effect | Yes; stable ID/idempotent reload | No | No | One reflection and compact reference |
| Memory | Candidate saved before Reflection link | No external side effect | Yes; retry repairs missing link | No | No | One candidate and one reflection reference |
| Memory | TEST fixture targets production store | Production-memory pollution | No | No | No | Reject before persistence |

## Recovery classifications

- `SAFE_TO_RETRY`: local or proven pre-submit work can be resumed within a bounded budget.
- `RECONCILE_FIRST`: a remote side effect may exist; query by the persisted idempotency key before any retry.
- `MANUAL_INTERVENTION`: automatic action would be ambiguous or the recovery budget is exhausted.
- `TERMINAL`: evidence proves the completed state; do not repeat the side effect.

## Audit events

Recovery emits `RECOVERY_STARTED`, `RECOVERY_RESUMED`, `RECOVERY_RECONCILIATION_REQUIRED`, `RECOVERY_COMPLETED`, and `RECOVERY_FAILED`. Context is redacted by the existing audit boundary.
