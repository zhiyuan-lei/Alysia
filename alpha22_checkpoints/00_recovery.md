# Alpha22 Checkpoint 00 — Recovery

Captured: `2026-08-09T13:35:47+08:00`

## Decision

```text
ALPHA22_RECOVERY_POINT = AFTER_M_MEMORY_INTEGRATION__BEFORE_N_RECOVERY_AND_RESOURCE_ACCEPTANCE
REAL_PUBLICATION_ALLOWED = NO
REAL_BETA_COUNT = 0/10
```

## Evidence summary

- Git: `main` at `55da6463f0ff50e5c7e51fb1b9496aca5c8481fa`; no staged changes; dirty Alpha3-22 work preserved.
- Creator engineering: aggregate, bridge, QA, approval/revision, manual Bilibili handoff, observation, reflection, memory, and evidence ledger exist.
- Regression: Python JUnit has 356 tests, 0 failures, 1 intentional H3 skip; the H3 test later passed separately.
- H3/ComfyUI smoke: real, non-mock, Visual QA PASS; VRAM 7,708/8,192 MB; RAM 26,933/24,576 MB, therefore resource gate FAIL.
- F1-F7 JUnit: 7/7 pass, but F1/F2 are state-level simulations rather than real service fault injection.
- CreatorJob store: empty. Beta CSV: header only. No real BV receipt or real publication audit evidence.
- Runtime: ComfyUI and Control Center stopped; Ollama healthy; no Alysia/ComfyUI worker, active visual queue item, stale application lock, or transaction temp file found.
- Historical residue: one ready-for-review mock run and one approved mock publish job predate Alpha22; neither is a real publication.

## Do not do from this checkpoint

- Do not reset, clean, restore, delete, or reinitialize the worktree.
- Do not open or depend on the failed Alpha22 Codex thread.
- Do not resume historical mock publish jobs as Alpha22 field evidence.
- Do not record a BV receipt without a specific approved CreatorJob and external-account reconciliation.
- Do not claim `PASS` or `READY_FOR_FIELD_RUN`.
- Do not start Alpha23.

## Next checkpoint boundary (not executed here)

Checkpoint 01 should begin only after explicitly resuming Alpha22 development. It must address bounded publish retry/backoff, real F1/F2 runtime fault injection, 24 GB RAM compliance, and durable frontend/regression reporting before field publication.

Full inventory: `alpha22_recovery_inventory.md`.
