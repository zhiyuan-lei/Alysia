# Alpha22 — Real staged H3 loading with a 6 GiB GPU budget

Date: 2026-10-01

The user clarified that the goal is to split and run H3, not merely reject its historical full-workflow peak. Two real component tests were executed, using the installed model files and ComfyUI node implementations. No model was downloaded or replaced.

## Execution strategy

TEST_ONLY harness: `alpha22/field_smoke/h3_staged_6g/`.

The prepared sequence is CPU text encoding -> persist conditioning -> process exit -> diffusion layer offload and one-step sampling -> process exit -> CPU VAE decode. Only one owned worker runs at a time. Process exit releases model references between stages. This is a component-level experiment, not an end-to-end Alysia H3ProductionAdapter acceptance result.

The GPU stage uses installed `--novram`, `--reserve-vram 2`, disabled asynchronous offload/pinned memory/smart-memory caching, plus PyTorch's CUDA caching-allocator fraction. Its allocator allowance is calculated as 6,144 MiB minus current device occupancy minus 512 MiB of non-allocator headroom (also capped at 5,632 MiB). Whole-device GPU and machine RAM are sampled externally. CPU-only stages do not create a CUDA allocator.

This does not impose a driver-wide memory partition. Monitoring and cooperative interruption cannot prevent every instantaneous memory allocation. A RAM-stop request does not instantly cancel an in-flight native operation.

## Actual results

| Test | Outcome | Observed whole-device VRAM peak | Observed machine RAM peak | Elapsed |
|---|---|---:|---:|---:|
| CPU NVFP4 text encoder load and encode | Load completed; encode cooperatively interrupted for RAM pressure | 1,301 MiB | 32,595 MiB | 79.156 s including startup/exit |
| INT8 diffusion model load, independent of encoding | Native access violation before sampling | 1,290 MiB | 9,534 MiB | 12.938 s |

### Text encoder

Evidence: `alpha22/field_smoke/h3_staged_6g/run_20261001_221422/`.

- `text_encoder_loaded` confirms the real deployed NVFP4 encoder loaded on CPU.
- At 22:15:29, sampled machine RAM first exceeded 24 GiB: 24,801 MiB. The monitor requested a cooperative stop.
- During the interval until the next ComfyUI interruption checkpoint, observed machine RAM reached 32,595 MiB; minimum commit availability was 477 MiB.
- The worker exited with `InterruptProcessingException`; no force termination was used.
- Short encoding did not complete and no reusable conditioning artifact was produced. The initial result JSON lacks exception detail because this ComfyUI interruption inherits outside ordinary `Exception`; the stderr traceback provides the evidence. The harness now explicitly records that interruption type.
- This CPU-only profile must not be represented as satisfying the 24 GiB RAM envelope or as a successful text-encoding test.

### Diffusion model

Evidence: `alpha22/field_smoke/h3_staged_6g/run_20261001_221705/`.

- Tested independently after the CPU encoder process exited; no failed conditioning was reused.
- Actual CUDA allocator allowance: 4,425 MiB.
- Exit code: 3,221,225,477 (`0xc0000005`).
- Trace: `torch.storage.__getitem__ -> comfy.utils.load_torch_file` at `safetensors.get_tensor` -> `comfy.sd.load_diffusion_model -> nodes.UNETLoader.load_unet`.
- No `diffusion_model_loaded` event was reached. Model offload readiness, sampling, and VAE decoding were not executed.
- This failure occurred with only 1,290 MiB observed GPU use and 9,534 MiB machine RAM use. It is not evidence of exceeding the 6 GiB GPU budget.
- The failing file is the existing INT8 ConvRot diffusion model, not the NVFP4 text encoder. The evidence broadens the loader investigation; it does not establish the underlying native root cause.

## Cleanup and verification

- Both owned Python workers exited; no Python/ComfyUI/H3 process remained at final inspection.
- Final snapshot: total VRAM 8,188 MiB, used 1,177 MiB, free 6,773 MiB.
- Both new scripts compile successfully. No inference was repeated for compilation checks.
- No forced process termination, model/runtime/driver change, or manual pagefile change.
- No production architecture or default encoder change in this turn.
- No reset, clean, restore, checkout, stage, or commit; staged files remain zero.
- Previous blocked evidence remains intact.

## Verdict

```text
REAL_STAGED_LOADING_TEST = EXECUTED
TEXT_ENCODER_LOAD = PASS
TEXT_ENCODER_ENCODE = INTERRUPTED_RAM_PRESSURE
DIFFUSION_MODEL_LOAD = FAIL_NATIVE_ACCESS_VIOLATION
H3_FULL_LOAD = NOT_COMPLETED
H3_SAMPLING = NOT_EXECUTED
VIDEO_ARTIFACT = NONE
H3_6G_ENVELOPE = NOT_VERIFIED
H3_24G_ENVELOPE = NOT_VERIFIED
ALPHA22_STEP_8 = BLOCKED
```

Next technical blocker: investigate the native safetensors/PyTorch loading failure at low GPU usage. Separately, CPU text encoding needs a lower-RAM profile before retry. Splitting the process lifetime alone has not solved these two failures.
