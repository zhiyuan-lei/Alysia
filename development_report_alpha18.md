# Alysia v0.1-alpha.18 Development Report

## Status

**Alpha18 DONE. Alpha19 was not started.**

## Repository and worktree protection

- Repository: `D:\Alysia`, branch `main`.
- Start `git status --short`: 27 tracked modified files plus substantial untracked Alpha3-Alpha17 artifacts.
- Start `git diff --stat`: 27 files changed, 4513 insertions, 100 deletions.
- Start `git diff --name-only`: `.gitignore`, `README.md`, existing Alysia core/agent/search/schema files, config, setup report, historical tests, `uv.lock` and Remotion files (27 total).
- Final `git status --short`: 159 entries; zero deletion entries.
- End tracked `git diff --stat`: 27 files changed, 4631 insertions, 100 deletions. The unchanged file count reflects incremental edits on already-dirty files; Alpha18 new files are untracked and therefore absent from this stat.
- End `git diff --name-only`: the same 27 tracked paths as the start snapshot; no start-tracked path is missing.
- `development_report_alpha17.md` and `evaluation/capability_evaluation_h3_runtime.json` still exist.
- No reset, clean, checkout/restore overwrite, stash, rebase, commit, squash or amend was performed.

## Alpha17 baseline

- Baseline full pytest: 247 passed, 1 skipped, 0 failed in 71.57s.
- Baseline skip: existing `tests/test_h3_local_integration.py`, gated by `ALYSIA_RUN_H3_LOCAL=1` so the 42.5 GB stack is not loaded by default.
- Baseline doctor: exit 0; 12 available, 4 optional missing/not ready.
- Inventory: `docs/baseline_alpha17_inventory.md`.

## Evaluation implementation

- Registry version: `alpha18.1`.
- Registered cases: 13 total; 12 default offline and 1 explicit H3 integration.
- Distinct categories: 12 — research grounding, knowledge freshness/conflict, script, storyboard, voice, subtitle, visual/H3, render, brand style, publish package, analytics learning and supervisor/workflow.
- Default offline run produces 23 metrics.
- Script/Style use discrete 0-3 rubric dimensions with reasons.
- Offline ASR similarity is `unknown` with `value=null` and `confidence=0`; it is not imputed.
- Worktree/config/fixture fingerprints use SHA-256 and do not require a Git commit.

## Final baseline and candidate evidence

- Worktree fingerprint: `1667d849374f4ad7c5acaca1e536f8182f93c3d07563ee681bb098269a247d0d`.
- Baseline ID: `baseline_alpha17_75261fe47f27`.
- Baseline evaluation ID: `eval_481c4c48c660ab5f7af9`.
- Normal candidate ID: `eval_44879ac22cf0937ff9ce`.
- Normal comparison ID: `cmp_7cfd71a18a100910`.
- Normal gate: `PASS`, exit 0, promotion allowed.

## Regression injection demo

- Injection is isolated by selecting `subtitle_bad.json`; the golden `subtitle_good.json` is not edited or replaced.
- Regression evaluation ID: `eval_6184e770ede40534c094`.
- Regression comparison ID: `cmp_acf7e90183a3056e`.
- Findings: subtitle overlap count 0 to 1, out-of-bounds count 0 to 1, semantic-split violation count 0 to 1.
- All three are critical/block findings.
- Gate: `BLOCKED`, CLI exit 2, `promotion_allowed=false`.
- Returning to the normal fixture produced the PASS candidate above.
- Public `skill approve` requires baseline/evaluation IDs and calls `EvaluationGate.require_promotion_allowed`, so this BLOCKED result cannot register a capability version through that entry point.

## H3 / ComfyUI explicit integration

- Final integration evaluation ID: `eval_f5dcfc3364068d0b8eff`.
- Fingerprint matches the final offline baseline.
- Status: completed; real provider success=1; engineering VisualQA and production eligibility=1.
- Fixed 3-second prompt/workflow/seed generation time: 127.953 seconds.
- Pre-run health snapshots: 4106 MiB VRAM used and 14465 MiB RAM used. These are explicitly not claimed as peak values.
- No aesthetic precision score was created.
- Default pytest still skips the heavy real model; explicit integration succeeded.

## Tests and checks

- Alpha18 test module: 19 passed.
- Final full pytest: 266 passed, 1 skipped, 0 failed in 65.02s.
- New skips introduced by Alpha18: 0.
- Final doctor: exit 0; 12 available, 4 optional missing/not ready.
- Regression matrix: 14 executable/traceable invariants; focused matrix/block/pass checks all passed.
- `compileall`: PASS.
- `git diff --check`: PASS; only existing LF/CRLF conversion warnings.
- Alpha18 core stub audit: clean after replacing the sole cache-miss control-flow `pass` with explicit state. No TODO, FIXME, `NotImplementedError`, placeholder, mock-only or bare `pass` exists in new Alpha18 production/test code.
- Historical stubs remain documented in `docs/baseline_alpha17_inventory.md` and were not cleaned.

## Golden fixtures

Stable offline fixtures cover grounding, stale/conflicted knowledge, good/bad scripts, missing storyboard section, real SAPI speech WAV, good/bad subtitle timing, valid/corrupt visual media, valid render media, style report, publish package and workflow/supervisor invariants. They require no network, account or API key.

## Evidence paths

- Inventory: `docs/baseline_alpha17_inventory.md`
- Matrix: `docs/regression_matrix.md`
- Ledger: `docs/phase_execution_ledger.md`
- Change review: `docs/reviews/alpha18_change_review.md`
- Baseline: `evaluation/baselines/baseline_alpha17_75261fe47f27.json`
- Normal run/gate: `evaluation/runs/eval_44879ac22cf0937ff9ce.json`, `evaluation/gates/baseline_alpha17_75261fe47f27__eval_44879ac22cf0937ff9ce.json`
- Regression run/gate: `evaluation/runs/eval_6184e770ede40534c094.json`, `evaluation/gates/baseline_alpha17_75261fe47f27__eval_6184e770ede40534c094.json`
- H3 run/health: `evaluation/runs/eval_f5dcfc3364068d0b8eff.json`, `evaluation/h3_integration_health.json`

## Blockers and conclusion

No Alpha18 blocker remains. Optional Ollama model, nvcc, CosyVoice Python and faster-whisper are not ready, but the default Alpha18 suite represents absent measurements as unknown and does not depend on them. Alpha18 is DONE; Alpha19 has not begun.
