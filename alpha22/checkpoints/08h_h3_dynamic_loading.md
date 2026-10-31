# H3 existing dynamic loader research — 2026-10-01

## Outcome and scope

PASS: one real, sequential, TEST_ONLY H3 video experiment using the existing model files and installed ComfyUI nodes: text encoding -> process exit -> 1-step sampling -> process exit -> tiled video VAE decode -> process exit. No synthetic conditioning or replacement model was used.

This is not an Alysia H3ProductionAdapter acceptance test. Step 8 remains BLOCKED pending integration, complete required artifact/QA/review/resume checks. Audio decoding was not tested. No LIVE publishing.

## Native crash isolation

- Pure installed PyTorch 2.13.0+cu130 / safetensors 0.8.0, no ComfyUI imports: reading the first 32,800-byte F32 tensor `adaln_t_table` from the existing INT8 diffusion file reproduces `0xc0000005` in `torch.storage.__getitem__`.
- Disabling inference mode still reproduces the same native crash.
- An independently generated tiny safetensors fixture with the same shape passes.
- Direct bounded file read -> torch.frombuffer passes for the original first tensor, with finite values.
- NumPy safetensors successfully reads that tensor and the next four tensors, then raises a normal unsupported BF16 TypeError. This is not an all-tensor NumPy PASS.
- Installed `comfy.utils.load_safetensors`, after the normal AIMDO library initialization, maps all 932 diffusion state tensors and validates their shapes successfully. This does not verify every weight's numerical contents or full-file integrity.
- Real UNETLoader then constructs MiniMaxH3 with ModelPatcherDynamic successfully. The existing NVFP4 encoder also constructs successfully with the dynamic patcher.

Supported boundary: the local legacy safetensors/PyTorch storage-reading path on the large diffusion file. Not confirmed: an NVFP4-specific bug, exact upstream root cause, or global runtime fix. Upstream issue #15397 is only a related symptom report, not proof of the same cause: https://github.com/Comfy-Org/ComfyUI/issues/15397

## Why the successful path differs

Installed `comfy.cli_args.enables_dynamic_vram()` disables dynamic VRAM by default when `--novram` or `--cpu` is selected (unless explicitly enabled). Earlier standalone harnesses also imported nodes without main.py's AIMDO initialization. Thus those tests did not exercise the existing newer dynamic loading mechanism.

The TEST_ONLY child reproduces main.py's existing initialization: control.init, control.init_devices, aimdo_enabled, ModelPatcherDynamic. No installed ComfyUI source or dependencies were edited. Model weights remain disk-backed and are read as needed; text encoding is no longer forced to full CPU execution.

Runtime profile: `--enable-dynamic-vram --reserve-vram 2 --vram-headroom 2 --fast-disk --disable-pinned-memory --disable-async-offload`. PyTorch caching allocator fraction = 0.5. This allocator cap does not constrain AIMDO's native allocations; whole-device sampling remains necessary. The profile is experimental, not a promised hard 6 GiB partition.

Cooperative stop requested above 5,900 MiB sampled whole-device GPU usage, 20 GiB sampled system RAM/private process memory, or 180 seconds per compute stage. These conservative experimental thresholds do not change the configured Alysia 24 GiB budget. No stop was triggered. No forced termination occurred.

## Measured results

| Stage | Elapsed, including child startup/exit | Whole-device VRAM sampled peak | Process-tree RSS sampled peak | Process-tree private memory sampled peak | System RAM sampled peak |
|---|---:|---:|---:|---:|---:|
| Real text encode | 10.282 s | 5,457 MiB | 4,444.883 MiB | 9,373.379 MiB | 13,191.422 MiB |
| Real H3 sample, 1 step | 14.000 s | 5,441 MiB | 1,901.555 MiB | 7,964.766 MiB | 9,857.766 MiB |
| Tiled video decode | 8.656 s | 5,433 MiB | 2,269.746 MiB | 8,299.480 MiB | 10,310.066 MiB |

Total measured stage time: 32.938 s, excluding gaps between stages and MP4 encoding. GPU sampled about once per second; process memory nominally every 0.1 s, with GPU query delays. These are observed sample maxima, not estimates and not guarantees about unsampled instants. PyTorch allocator high-water marks in stdout exclude native AIMDO allocations and must not be substituted for total VRAM use.

The initial bare probe mistakenly sampled only the Windows venv launcher, not its child. Its RAM values are invalid for workload interpretation. Subsequent probes and all successful stages sample the owned process tree. No earlier evidence was overwritten.

## Artifact

`alpha22/field_smoke/h3_loader_probe/20261001_223923_dynamic_decode/TEST_ONLY_H3.mp4`

- 320 x 256; 5 frames; 24 fps; H.264; silent; duration 0.208333 s; 8,296 bytes.
- SHA-256: `aff70744402114a46b91955a8ca9f16a15743d9013cacb402f844d0d374789bb`.
- Finite conditioning, sampled latents and decoded frames; expected frame shape asserted.
- ffprobe metadata and ffmpeg full bitstream decoding pass.
- First decoded frame visually checked: blue circular shape on a light background, with visible single-step artifacts. Not a production-quality claim.

## Verdict

```text
H3_STAGED_MINIMAL_VIDEO = PASS
LEGACY_NATIVE_CRASH = REPRODUCED_AND_BYPASSED_IN_TEST_ONLY
SAMPLED_6G_GPU_ENVELOPE_THIS_WORKLOAD = PASS
SAMPLED_24G_RAM_ENVELOPE_THIS_WORKLOAD = PASS
GENERAL_H3_6G_PRODUCTION_ENVELOPE = NOT_VERIFIED
ALYSIA_H3_ADAPTER_ACCEPTANCE = NOT_EXECUTED
ALPHA22_STEP_8 = KEEP_BLOCKED
```

Next: integrate this verified profile and sequential artifact handoff into a TEST_ONLY adapter smoke, without changing production defaults; validate recovery/resume and the required output contract before lifting Step 8's blocked status. Do not automatically increase resolution, frames or steps based on this tiny test.

## Safety

No downloads, model changes, driver changes, pagefile changes, architecture changes, desktop-app closures, or forced process termination. No git reset, clean, restore, checkout, stage or commit. Previous evidence and existing dirty-worktree changes preserved. All owned workers exited. Evidence resource summary is generated by `h3_loader_probe/summarize.py`.

Verification: both diagnostic scripts compile; summary assertions and full video bitstream validation pass. Existing SecretScanner checked 37 text evidence files including this checkpoint, with zero findings. Staged Git file list is empty. Final summary snapshot: VRAM total/used/free = 8,188/1,244/6,706 MiB; system RAM used = 8,048.504 MiB. No Python worker remained at final inspection.
