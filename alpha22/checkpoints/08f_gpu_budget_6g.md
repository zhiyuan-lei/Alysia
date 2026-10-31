# Alpha22 — 6 GiB GPU admission boundary

Date: 2026-10-01

## User requirement and interpretation

Limit one submitted GPU workload to 6 GiB (6,144 MiB), keep GPU-heavy work serial, and preserve room for the agent and desktop. RAM planning remains 24 GiB. This change does not complete Step 8 or resolve the native H3 crash.

## Implemented boundary

- Production, workflow, and simulation budget defaults: 6,144 MiB.
- Local GPU provider routing rejects unknown peaks and peaks above the effective budget. Legacy higher production budgets are clamped to 6,144 MiB for routing.
- The real ComfyUI/H3 `submit` entry point checks resources before any queue/prompt request. Direct H3 adapter calls and the visual queue both reach this entry point.
- Missing/invalid peak data or incomplete GPU telemetry blocks submission.
- Admission requires current GPU used memory plus declared task peak to stay at or below 6,144 MiB, and available memory after that peak to retain the existing minimum headroom. Existing allocations are conservatively counted even if a profile measurement already includes them.
- A nonempty or unrecognizable ComfyUI queue blocks submission. The check-and-submit sequence is serialized across provider instances in the same Python process.
- Budget rejection is a non-retryable resource failure (`GPU_BUDGET_BLOCKED`) in Creator Production.
- Existing successful-workload peak measurements are preserved. Lowering resolution or task count does not manufacture a lower model-loading peak.

## Scope and limits

This is an application admission policy, not a driver-enforced memory partition or allocator hard cap. Estimates can be inaccurate and unrelated programs can allocate GPU memory after the check. The Python submission lock does not coordinate unrelated clients/processes. No claim is made that all programs or every instantaneous allocation on this machine are capped, or that agent responsiveness is guaranteed.

No runtime, driver, model, pagefile, or ComfyUI deployment change was made. No external process was stopped. No model download, model inference, Bilibili LIVE, or end-to-end creator run was initiated.

## Live read-only gate

At 2026-10-01T22:04:36+08:00:

- Current H3 declared historical peak: 7,678 MiB.
- Effective submission budget: 6,144 MiB.
- Available GPU memory: 6,681 MiB.
- Projected current used plus historical peak: 8,947 MiB.
- ResourceGuard result: BLOCKED.
- H3 invocation count in this change: 0.

The historical H3 profile cannot be admitted under the new budget. The missing INT8 bypass component and unresolved native crash remain separate blockers; no <=6 GiB successful H3 profile has been established.

## Verification

Regression evidence: `evaluation/alpha22/gpu_budget_6g_regression.junit.xml`.

Command: `.venv/Scripts/python.exe -m pytest -m 'not integration and not h3_local' --tb=short --junitxml=evaluation/alpha22/gpu_budget_6g_regression.junit.xml`

Result: 503 passed, 1 integration test deselected, 0 failures in 160.33 seconds. One dependency deprecation warning (FastAPI/Starlette test client) was reported. Checkpoint secret scan: 1 file, 0 findings. Git diff whitespace check: PASS; staged files: 0; ComfyUI/H3 Python processes after checks: none.

The added tests cover exact admission boundaries, missing/invalid estimates, unavailable telemetry, current GPU occupancy, headroom, legacy budget overrides, queue occupancy, no-network rejection through the real H3 adapter, and non-retryable resource classification. GPU inference integration tests are excluded.

## Git safety

Existing worktree changes were preserved. No reset, clean, restore, checkout, stage, or commit.

## Project status

```text
GPU_TASK_BUDGET_MIB = 6144
ALPHA22_STEP_8 = BLOCKED
H3_REAL_SMOKE = NOT_EXECUTED
H3_6G_ENVELOPE = NOT_VERIFIED
H3_24G_ENVELOPE = NOT_VERIFIED
```
