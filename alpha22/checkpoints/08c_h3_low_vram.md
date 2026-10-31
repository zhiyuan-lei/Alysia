# Alpha22 Step 8.3 — H3 Low-VRAM Profile Validation

Date: 2026-08-09

## Status

```text
ALPHA22_STEP_8_3_STATUS = FAIL
H3_LOW_VRAM_PROFILE = FAIL
PHYSICAL_MACHINE_H3 = FAIL
H3_8GB_VRAM_ENVELOPE = FAIL
H3_24G_ENVELOPE = NOT_VERIFIED
RECOMMENDATION = HARDWARE_PROFILE_CHANGE_REQUIRED
```

## Existing capability and selected profile

The deployed ComfyUI 0.31 CLI supports `--novram` and `--cpu-vae`; the checked-in Alysia H3 workflow already places the NVFP4-AWQ text encoder on CPU. `H3VisualConfig` supports 320×256 and one step, the existing duration binding produces the H3 node's valid minimum of five frames, and `ResourceManager` provides serial GPU locking and cleanup.

Exactly one configuration was selected:

```text
ONE_LOW_VRAM_PROFILE
--novram
--cpu-vae
--disable-pinned-memory
--disable-async-offload
--reserve-vram 1
CPU text encoder
320x256 / 5 frames / 1 step
GPU-heavy concurrency = 1
```

The same locally verified INT8 diffusion, NVFP4-AWQ text encoder, and FP16 video VAE files were used. No model, quantization, backend, framework, driver, CUDA, pagefile, or public Alpha22 code was changed.

## Preflight and invocation

- Before service launch: 8,188 MiB total / 1,087 MiB used / 6,863 MiB free VRAM; 24,127 MiB RAM available.
- Word was no longer running; other ordinary user applications remained and were not closed.
- ComfyUI and H3 processes before launch: 0.
- ResourceGuard immediately before H3: `safe`; 6,764 MiB free VRAM and 23,195 MiB available RAM.
- Real route: Alysia `H3ProductionAdapter` → `MiniMaxH3LocalProvider` → real ComfyUI/H3.
- Real invocation: YES, exactly once.

## Failure

No artifact was produced. About 15.604 seconds after adapter invocation, the owned ComfyUI process crashed while loading the CPU text encoder. ComfyUI logged a Windows fatal access violation in `torch.storage` → `load_torch_file` → `load_clip`. Windows Application Error event 1000 identified `torch_cpu.dll` and exception code `0xc0000005`; the adapter then received WinError 10054 because the service connection closed.

No CUDA OOM message or system-memory exhaustion event was reported. A second profile was not attempted.

## Measured resources

Sampling interval: 0.25 seconds; 54 samples during the H3 phase.

| Resource | Baseline | Observed peak during failed load | After service exit |
|---|---:|---:|---:|
| RAM used | 9,423 MiB | 23,925 MiB | 8,906 MiB |
| VRAM used | 1,185 MiB | 1,187 MiB | 1,078 MiB |

- Minimum RAM available during the failed load: 8,685 MiB.
- Minimum commit availability: 3,518 MiB.
- These are measured failure-path values, not a complete-workload peak and cannot establish either envelope as passing.

## Cleanup and downstream

- Provider unload requested: YES.
- CUDA cache release path called: YES.
- GPU lock released: YES.
- Owned ComfyUI service exited: YES.
- Orphan ComfyUI/H3: NO.
- Stale GPU lock: NO.
- Stale persisted ProductionTask: NO; no successful plan was persisted.
- Resume: NOT EXECUTED because no successful H3 artifact exists.
- End-to-End: NOT EXECUTED.
- CreatorQA / Human Review: NOT EXECUTED.
- PREPARE_ONLY: NOT EXECUTED.
- Upload calls: 0.
- Submit calls: 0.
- Bilibili LIVE: NOT EXECUTED / NOT VERIFIED.

## Tests

Direct regression only, because no public code changed:

```text
tests/test_creator_production.py
tests/test_creator_recovery.py
tests/test_visual_generation.py
51 passed
```

## Secret scan

- `alpha22/field_smoke/h3_low_vram`: 5 files, 0 findings.
- `alpha22/h3_profile_comparison.md`: 1 file, 0 findings.
- This checkpoint: 1 file, 0 findings.
- Result: PASS.

## Git safety

- No reset, clean, restore, checkout, stage, or commit.
- No unknown, system, other-user, or desktop process was terminated.
- Only the ComfyUI process launched and owned by this smoke was eligible for cleanup; it exited from the recorded native crash before the cleanup stop step.
- Final worktree counts: 28 tracked modified, 163 untracked status entries, 0 staged.

## Evidence

- `alpha22/h3_profile_comparison.md`
- `alpha22/field_smoke/h3_low_vram/result.json`
- `alpha22/field_smoke/h3_low_vram/resource_samples.json`
- `alpha22/field_smoke/h3_low_vram/comfyui_stderr.log`
- `alpha22/field_smoke/h3_low_vram/run_h3_low_vram.py`

Previous Step 8, 8.1, and 8.2 BLOCKED evidence remains unchanged.

## Recommendation

`HARDWARE_PROFILE_CHANGE_REQUIRED`

Report-only candidates, not executed: a larger-VRAM GPU, a separately deployed smaller/more memory-efficient H3 package, or moving H3 execution off this machine.
