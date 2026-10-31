# Alpha22 Step 8 — Field Readiness + Real Local Smoke Test

Date: 2026-08-09

## Status

```text
ALPHA22_STEP_8_STATUS = BLOCKED
LOCAL_SMOKE = BLOCKED_RESOURCE_LIMIT
COMFYUI_REAL_SMOKE = PASS
H3_REAL_SMOKE = BLOCKED_RESOURCE_LIMIT
END_TO_END_LOCAL_SMOKE = NOT_EXECUTED
REAL_BETA_READINESS = BLOCKED
BILIBILI_LIVE = NOT_EXECUTED / NOT_VERIFIED
HARDWARE_VERDICT = YES_WITH_LIMITATIONS
```

## Preflight

- Physical RAM detected: 31.85 GiB; configured operating budget remains 24 GiB.
- GPU: RTX 4060 Ti, 8,188 MiB VRAM.
- Current pre-smoke free VRAM: 2,278 MiB.
- Existing minimum H3 profile peak: 7,678 MiB VRAM / 25,919 MiB RAM.
- Model tree: 42,470,615,823 bytes (39.554 GiB); this is disk footprint, not simultaneous resident memory.
- H3 deployment/model/workflow checks: ready.
- Resource gate: blocked H3 before prompt submission; no user process was terminated.

## Real ComfyUI Stage A

- Real Alysia provider and real ComfyUI service invoked.
- Built-in no-model 64×64 workflow completed.
- Artifact: `alpha22/field_smoke/comfyui/TEST_ONLY_comfyui_stage_a.png`.
- 434 bytes; SHA-256 `fb2b62bf9a61f0a6d81175fba73fe1657cf4929e8d9886205cd1a8a39f6fe83b`.
- Validation: VALID; `mock=false`.
- GPU lock released; `/free` called.

## H3 and end-to-end

H3 was not invoked because current free VRAM was materially below the already measured minimum profile. The Step 8 hard-stop rule therefore prevented end-to-end Production, real-artifact QA, human review, and PREPARE_ONLY. No fake evidence was substituted.

## Resume

- ProductionOrchestrator resume: PASS.
- Real ComfyUI artifact regenerated: NO.
- Hash unchanged: yes.
- Modification time unchanged: yes.
- ComfyUI invocation history: 1 before / 1 after.

## Cleanup

- Step 8 ComfyUI process: stopped.
- Orphan H3/ComfyUI process: none.
- Stale GPU lock: none.
- Stale `RUNNING` field-smoke task: none.
- Stale TEST_ONLY publish state: none.

## Regression

- Direct Step 1–8 affected suite: 156 passed, 0 failed, 0 errors, 0 skipped.
- JUnit: `evaluation/alpha22/alpha22_step8_direct_regression.junit.xml`.
- Full 484 suite not repeated because no shared public code changed.

## Publishing safety

- PREPARE_ONLY: NOT EXECUTED because end-to-end prerequisites were blocked.
- Upload calls: 0.
- Submit calls: 0.
- Bilibili LIVE: NOT EXECUTED / NOT VERIFIED.

## Secret scan

- `alpha22/field_smoke/`: 8 scanned files, 0 findings.
- `alpha22/checkpoints/`: 9 scanned files, 0 findings.
- Supplemental sensitive-assignment findings: 0.
- Result: PASS.

## Files created in Step 8

- `alpha22/hardware_preflight.md`
- `alpha22/field_smoke/smoke_manifest.json`
- `alpha22/field_smoke/comfyui/TEST_ONLY_comfyui_stage_a.png`
- `alpha22/field_smoke/comfyui/stage_a_result.json`
- `alpha22/field_smoke/resume/resume_result.json`
- `alpha22/field_smoke/run_comfyui_stage_a.py`
- `alpha22/field_smoke/run_resume_check.py`
- `alpha22/alpha22_field_readiness_report.md`
- `alpha22/checkpoints/08_field_readiness.md`
- `evaluation/alpha22/alpha22_step8_direct_regression.junit.xml`

## Known limitations

- Fresh real H3 inference is not verified by Step 8.
- Real video composition, CreatorQA, human review, and PREPARE_ONLY were not run.
- Current hardware can run the historical minimal H3 profile only with significant limitations and an otherwise available GPU.
- A strict 24 GiB RAM envelope remains unverified.

## Git safety

- No reset, clean, restore, checkout, stage, commit, or bulk deletion was performed.
- Final worktree: 28 tracked modified, 163 untracked entries, 0 staged.
- Branch `main`; HEAD remains `55da6463f0ff50e5c7e51fb1b9496aca5c8481fa`.

## Next safe step

No Step 9 recommendation while status and Real Beta readiness remain BLOCKED.
