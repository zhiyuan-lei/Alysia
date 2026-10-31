# Alpha22 Step 8 Field Readiness Report

Date: 2026-08-09  
Status: BLOCKED  
Local field readiness: PARTIAL

## Hardware and deployment

Windows measured 31.85 GiB physical RAM on an RTX 4060 Ti with 8,188 MiB VRAM. Alysia retains a conservative 24 GiB configured operating budget. D: had 243.55 GiB free and C: had 54.66 GiB free.

ComfyUI 0.31.0 and Python 3.12.12 are installed at `D:\ComfyUI`; PyTorch 2.13.0+cu130 detected the CUDA device. H3 model paths, hashes, and T2V API workflow were present. The service was launched with the existing low-VRAM/offload-safe arguments and no reinstall or download occurred.

Full measurements and paths are in `alpha22/hardware_preflight.md`.

## 42.5 GB explanation

The model tree measured 42,470,615,823 bytes, or 39.554 GiB. “42.5 GB” is the decimal on-disk total of the four verified weights, not simultaneous required resident memory. Runtime supports CPU text-encoder placement, low-VRAM mode, sequential execution, and explicit unload.

Existing deployment evidence for the smallest H3 profile measured 7,678 MiB VRAM and 25,919 MiB RAM. That RAM peak is above the configured 24 GiB operating budget.

## Resource preflight and hard stop

At the real Stage A boundary, system `nvidia-smi` measured 5,672 MiB VRAM used and only 2,278 MiB free. An unrelated user game workload was active and was preserved. The Step 8 service health endpoint reported the ComfyUI process itself, but this did not override the system-level contention measurement.

Because current free VRAM was materially below the existing minimum-profile peak, H3 submission would have required unsafe oversubscription or terminating an unrelated application. Neither is authorized. The H3 stage was therefore stopped before prompt submission.

## ComfyUI real smoke

Result: PASS.

- Adapter: real `ComfyUIProvider`
- Service: real loopback ComfyUI 0.31.0
- Workflow: built-in `EmptyImage -> SaveImage`; no model loaded
- Output: 64×64 PNG, 434 bytes
- SHA-256: `fb2b62bf9a61f0a6d81175fba73fe1657cf4929e8d9886205cd1a8a39f6fe83b`
- Provider result: `mock=false`, `status=completed`
- ComfyUI history: `status_str=success`, `completed=true`
- Artifact validation: VALID
- Elapsed: 1.235 seconds
- Resource lock released: yes
- `/free` called: yes

Evidence: `alpha22/field_smoke/comfyui/stage_a_result.json`.

## H3 real smoke

Result: BLOCKED_RESOURCE_LIMIT.

The real `H3ProductionAdapter`/MiniMax model runtime was not invoked. Setup status was ready, all four model files existed and were verified, but current free VRAM was insufficient relative to measured minimum-profile demand. No fake provider was substituted.

## Minimal end-to-end smoke

Result: NOT EXECUTED.

The Step 8 sequence explicitly permits CreatorJob → Grounding → CreatorPlan → real Production → QA → Review → PREPARE_ONLY only after both ComfyUI and H3 real smoke pass. H3 did not pass, so no TEST_ONLY end-to-end job, real-artifact QA, human approval, or publish package was fabricated.

## Resume and hash integrity

Result: PASS for the real ComfyUI artifact.

The PNG was registered in `ProductionArtifactRegistry`, attached to a successful GPU-heavy ProductionTask, and resumed through `ProductionOrchestrator` with the real ComfyUI adapter configured. Before/after hash and modification time were identical. Relevant ComfyUI history count remained 1 → 1, proving the successful real task was not regenerated.

Evidence: `alpha22/field_smoke/resume/resume_result.json`.

## Resource metrics

| Metric | Baseline | Peak | After task | After service stop |
|---|---:|---:|---:|---:|
| RAM used | 16,965,533,696 bytes | 17,040,637,952 bytes | 17,015,087,104 bytes | current available RAM 17.0 GiB |
| VRAM used | 5,672 MiB | 5,673 MiB | 5,668 MiB | 5,563 MiB |
| VRAM free | 2,278 MiB | derived 2,277 MiB | 2,282 MiB | 2,387 MiB |
| H3 peak | NOT MEASURED | NOT MEASURED | NOT INVOKED | — |

Stage A did not load a model, so its small VRAM delta is expected and must not be presented as H3 capacity evidence.

## Disk growth and cache

- `alpha22/field_smoke` did not have a measured byte baseline before directory creation; current pre-report size was 22,989 bytes.
- Known new ComfyUI source output: 434 bytes.
- Evidence copy: 434 bytes.
- Runtime logs before reports: 5,449 bytes.
- ComfyUI temp growth: UNAVAILABLE; current temp file total was zero/no measurable files.
- Model cache: not deleted or rewritten; Stage A loaded no model.
- No abnormal multi-GB smoke growth occurred.

## Process cleanup

- Provider unload requested.
- Step 8 ComfyUI parent/child processes were identified by exact command line and stopped.
- Health endpoint refused connection after stop.
- No H3 process was started.
- GPU lock: none.
- Stale `RUNNING` ProductionTask: none under field-smoke evidence.
- Stale TEST_ONLY publish state: none.

The preflight also found four orphaned Step 7 pytest processes from an earlier command timeout. Their exact command lines and parent chain were verified before they were terminated. No unrelated process was terminated.

## QA, review, and publishing

- Real-artifact CreatorQA: NOT EXECUTED; H3 prerequisite blocked.
- Human review: NOT EXECUTED.
- PREPARE_ONLY package: NOT EXECUTED.
- Bilibili upload calls: 0.
- Bilibili submit calls: 0.
- Bilibili LIVE: NOT EXECUTED / NOT VERIFIED.

## Secret scan

- `alpha22/field_smoke/`: 8 scanned text files, 0 findings.
- `alpha22/checkpoints/`: 9 scanned text files, 0 findings.
- Supplemental sensitive-assignment scan across both paths: 0 findings.
- Result: PASS.

## Regression

```text
uv run python -m py_compile alpha22/field_smoke/run_comfyui_stage_a.py alpha22/field_smoke/run_resume_check.py
uv run pytest -q tests/test_alpha22_creator.py tests/test_creator_job.py tests/test_topic_research.py tests/test_creator_production.py tests/test_creator_qa_review.py tests/test_creator_publisher.py tests/test_creator_observation_memory.py tests/test_creator_recovery.py tests/test_visual_generation.py --junitxml=evaluation/alpha22/alpha22_step8_direct_regression.junit.xml
```

Result: 156 passed, 0 failed, 0 errors, 0 skipped.

The full 484-test regression was not repeated because no shared runtime, resource, security, or control code changed in Step 8.

## Field readiness checklist

| Capability | Status |
|---|---|
| CreatorJob | READY from Step 1–7 regression |
| Research/Grounding | READY from Step 1–7 regression |
| Production | READY for validated local/fake paths; real H3 blocked this run |
| ComfyUI real | PASS, no-model adapter/service smoke |
| H3 real | BLOCKED_RESOURCE_LIMIT |
| QA | READY in regression; NOT EXECUTED on Step 8 real H3 artifact |
| Human Review | READY in regression; NOT EXECUTED in blocked field smoke |
| PREPARE_ONLY | READY in regression; NOT EXECUTED in blocked field smoke |
| Recovery | READY; real ComfyUI artifact resume PASS |
| Observation | READY from regression |
| Memory | READY from regression |
| LIVE Publisher | NOT VERIFIED |

## Verdicts

- Hardware verdict: `YES_WITH_LIMITATIONS` for the physically detected 31.85 GiB machine when the GPU is otherwise available and workloads remain minimal/sequential, based on existing real H3 evidence. A true 24 GiB envelope is NOT VERIFIED because the recorded minimal-profile RAM peak exceeded that budget.
- Current Step 8 status: `BLOCKED` because the required fresh H3 invocation could not safely run under current GPU contention.
- Real Beta readiness: `BLOCKED`.

## Limitations

- No fresh H3 artifact was produced in Step 8.
- Heavy-GPU H3/ComfyUI serialization could not be demonstrated with both real model tasks because H3 never started.
- Real-artifact video composition, QA, review, and PREPARE_ONLY were not eligible to run.
- Real Bilibili upload, reconciliation, content ID, metrics, and comments remain unverified.
- The configured 24 GiB operating budget is not supported by the existing minimal H3 RAM measurement.

## Step 8.1 H3 Resource Revalidation — 2026-08-09

Step 8.1 preserved the original BLOCKED record and performed a new read-only GPU ready gate. ComfyUI and H3 were both stopped. No process was terminated.

Initial system-level measurement was 1,434 MiB VRAM used / 6,516 MiB free with 32% GPU utilization. Five samples over approximately nine seconds showed 6,445–6,527 MiB free and 2–37% utilization. WDDM exposed the graphical process contexts but not reliable per-process VRAM allocation.

The historical minimal H3 profile peaked at 7,678 MiB. The initial measurement therefore had a negative 1,162 MiB margin, and every sample remained in the explicitly prohibited 6–7 GiB free range. The GPU ready gate returned:

```text
H3_REVALIDATION = WAITING_FOR_GPU_AVAILABILITY
```

No H3 prompt was submitted, no H3 artifact was created, and no optimization pass was consumed. Optimization is allowed only after an initial real run demonstrates a slight RAM-budget overage; it cannot compensate for a failed GPU availability gate.

Separate classifications remain:

```text
PHYSICAL_MACHINE_H3 = BLOCKED
H3_24G_ENVELOPE = NOT_VERIFIED
ALPHA22_STEP_8_STATUS = BLOCKED
REAL_BETA_READINESS = BLOCKED
```

Evidence: `alpha22/field_smoke/h3_revalidation/revalidation_manifest.json` and `alpha22/checkpoints/08a_h3_resource_revalidation.md`.
