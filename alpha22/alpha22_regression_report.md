# Alpha22 Step 7 Regression Report

Date: 2026-08-09  
Status: PASS  
Repository baseline: `main` at `55da6463f0ff50e5c7e51fb1b9496aca5c8481fa`

## Stage results

| Stage | Repository-defined entrypoint | Tests | Result | Evidence |
|---|---|---:|---|---|
| Alpha18 | `tests/test_evaluation.py` | 19 | PASS | Alpha18–21 JUnit |
| Alpha19 | `tests/fault_injection/test_reliability.py` | 23 | PASS | Alpha18–21 JUnit |
| Alpha20 | `tests/test_security.py` | 33 | PASS | Alpha18–21 and required-subsystem JUnit |
| Alpha21 | `tests/test_control_api.py` | 14 | PASS | Alpha18–21 JUnit |
| Alpha22 Step 1 | creator model + compatibility tests | 18 | PASS | Step 1–7 JUnit |
| Alpha22 Step 2 | `tests/test_topic_research.py` | 23 | PASS | Step 1–7 JUnit |
| Alpha22 Step 3 | `tests/test_creator_production.py` | 17 | PASS | Step 1–7 JUnit |
| Alpha22 Step 4 | `tests/test_creator_qa_review.py` | 22 | PASS | Step 1–7 JUnit |
| Alpha22 Step 5 | `tests/test_creator_publisher.py` | 27 | PASS | Step 1–7 JUnit |
| Alpha22 Step 6 | `tests/test_creator_observation_memory.py` | 15 | PASS | Step 1–7 JUnit |
| Alpha22 Step 7 | recovery tests + legacy F1–F7 tests | 26 | PASS | Step 1–7 JUnit |

The historical entrypoints were identified from `development_report_alpha18.md` through `development_report_alpha21.md` and confirmed by current test collection. They were not guessed from memory.

## Historical compatibility finding and fix

The first Alpha18–21 run produced one Alpha21 failure: the Control API historically returns `REVISION_REQUESTED`, while the Alpha22 internal approval state is `REVISION_REQUIRED`. No historical test or assertion was changed. A narrow API serialization compatibility mapping was added in `alysia/control/service.py`; the internal Alpha22 state and safety transitions remain unchanged. The affected Control API suite and the complete safe-local suite then passed.

## Test commands

```text
uv run pytest --collect-only -q
uv run pytest -q tests/test_alpha22_creator.py tests/test_creator_job.py tests/test_topic_research.py tests/test_creator_production.py tests/test_creator_qa_review.py tests/test_creator_publisher.py tests/test_creator_observation_memory.py tests/test_creator_recovery.py tests/fault_injection/test_alpha22_creator_loop.py --junitxml=evaluation/alpha22/alpha22_step7_steps_1_7.junit.xml
uv run pytest -q tests/test_evaluation.py tests/fault_injection/test_reliability.py tests/test_security.py tests/test_control_api.py --junitxml=evaluation/alpha22/alpha22_step7_alpha18_21.junit.xml
uv run pytest -q tests/test_production.py tests/test_visual_generation.py tests/test_security.py tests/test_analytics_learning.py --junitxml=evaluation/alpha22/alpha22_step7_required_subsystems.junit.xml
uv run pytest -q --ignore=tests/test_h3_local_integration.py --junitxml=evaluation/alpha22/alpha22_step7_full_regression.junit.xml
uv run python -m py_compile alysia/creator/recovery.py alysia/creator/production.py alysia/creator/memory.py alysia/creator/__init__.py alysia/control/service.py tests/test_creator_recovery.py
```

## Results

| Suite | Passed | Failed | Errors | Skipped |
|---|---:|---:|---:|---:|
| Alpha22 Steps 1–7 | 148 | 0 | 0 | 0 |
| Alpha18–21 acceptance entrypoints | 89 | 0 | 0 | 0 |
| Required Production/Visual/Security/Analytics | 75 | 0 | 0 | 0 |
| Complete safe-local repository regression | 484 | 0 | 0 | 0 |

The rows overlap; the full-suite row is the repository-wide total and must not be added to the targeted rows.

## Collection and exclusions

Collection found 485 tests after Step 7. The complete safe-local command ran 484 and explicitly excluded only `tests/test_h3_local_integration.py` (1 test), which requires opt-in through `ALYSIA_RUN_H3_LOCAL=1` and loads the 42.5 GB local H3/ComfyUI stack.

- GPU heavy: excluded H3 local integration; deterministic resource-lock tests ran without model load.
- Real network: no opt-in real-network test was run; providers/transports were fake or local fixtures.
- Manual integration: no manual platform or credential flow was run.
- Bilibili LIVE: no real account, login, upload, or submit occurred; LIVE-mode tests used an injected TEST_ONLY transport.
- Real metrics/comments: not collected.

## Evidence integrity

All required Step 1–6 checkpoints exist and are non-empty:

- `alpha22/checkpoints/00_baseline.md`
- `alpha22/checkpoints/01_creator_job.md`
- `alpha22/checkpoints/02_topic_research.md`
- `alpha22/checkpoints/03_creator_production.md`
- `alpha22/checkpoints/04_creator_qa_review.md`
- `alpha22/checkpoints/05_bilibili_publisher.md`
- `alpha22/checkpoints/06_observation_reflection_memory.md`

Their primary test paths exist, and the current full-suite JUnit revalidates those paths. Baseline evidence directories `evaluation/control_center`, `evaluation/reliability_demos`, and `evaluation/security_demos` also remain present.

## Durable evidence

- `evaluation/alpha22/alpha22_step7_steps_1_7.junit.xml`
- `evaluation/alpha22/alpha22_step7_alpha18_21.junit.xml`
- `evaluation/alpha22/alpha22_step7_required_subsystems.junit.xml`
- `evaluation/alpha22/alpha22_step7_full_regression.junit.xml`

## Secret scan

The repository SecretScanner scanned `alpha22/` after reports/checkpoint generation. Final result is recorded in checkpoint 07; no credential-value finding is accepted as clean unless the final scan reports zero.

## Known limitations

- Real H3/ComfyUI health and output quality remain unverified in this step.
- Real Bilibili reconciliation behavior remains dependent on a future verified transport contract.
- TEST_ONLY published records intentionally do not update real field-run CreatorJob publication evidence.
- Multiple orphan outputs are classified for manual selection rather than guessed automatically.
- The recovery helper coordinates persisted Production and Publisher state; QA, Review, Observation, Reflection, and Memory recovery uses their atomic stores and idempotent domain APIs.
