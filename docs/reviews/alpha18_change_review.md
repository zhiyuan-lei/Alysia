# Alpha18 Change Review

## Goal

Add one unified, evidence-backed evaluation and regression layer. Do not enter Alpha19 and do not rewrite existing creator business logic.

## Actual Alpha18 files

New production code:

- `alysia/schemas/evaluation.py`
- `alysia/evaluation/{__init__,registry,scorers,fingerprint,store,engine,service,matrix}.py`

Incremental integration:

- `alysia/schemas/__init__.py`
- `alysia/cli.py`
- `alysia/__init__.py`
- `pyproject.toml`, `uv.lock`
- `README.md`

Tests and evidence:

- `tests/test_evaluation.py`
- `tests/fixtures/evaluation/*`
- `evaluation/{runs,baselines,comparisons,gates}/`
- `evaluation/h3_integration_health.json`
- `docs/baseline_alpha17_inventory.md`
- `docs/regression_matrix.md`
- `docs/roadmap_alpha18_23.md`
- `docs/phase_execution_ledger.md`
- `development_report_alpha18.md`

Planning files were appended with Alpha18 progress; historical content was retained.

## Unrelated changes

0. Existing Alpha1-Alpha17 dirty files were not cleaned, reformatted or attributed to Alpha18. The tracked diff still contains historical work, so whole-worktree diff size is not an Alpha18-only change count.

## Dependencies

No new Python or Node dependency. Golden media was generated once with existing Windows SAPI and FFmpeg and is now static/offline.

## Schema / config / CLI

- Added versioned `BenchmarkCase`, `EvaluationMetric`, `EvaluationRun`, `RegressionFinding`, baseline/comparison/gate and rubric models.
- No new runtime config section and no system configuration change.
- Added `eval list/run/baseline-create/compare/report/gate`.
- Public `skill approve` now requires baseline/evaluation IDs and invokes the Alpha18 promotion gate before registering a capability version.

## Regression risk review

- Worktree fingerprint intentionally excludes generated evaluation outputs and includes evaluation source/tests/golden fixtures.
- Existing CLI business commands and orchestrators are unchanged except the explicit Skill promotion gate.
- Default suite never loads H3; explicit integration was run successfully.
- Binary media fixtures make repository size slightly larger but keep tests deterministic and network-free.

## Uncovered risks

- Offline voice scoring verifies decode, dynamics and non-tone behavior. ASR text similarity stays `unknown` until an explicit ASR integration environment exists.
- One H3 smoke run is an engineering health observation, not a visual-aesthetic score or long-term latency baseline.
- Future promotion entry points must call `EvaluationGate.require_promotion_allowed`; the current public Skill registration CLI does so.
- Alpha18 does not retry, recover or roll back failed work; those concerns belong to Alpha19 and were not implemented.

## Alpha19 prerequisites

Alpha19 may consume Alpha18 findings and gate artifacts for fault injection/recovery decisions, but it must preserve benchmark determinism and must not rewrite baselines to hide failures.

## Review conclusion

No out-of-scope implementation was found. Alpha19 was not started.
