# Alpha22 Step 8.4 — H3 Native Runtime Crash Triage

Date: 2026-08-09

## Status

```text
ALPHA22_STEP_8_4_STATUS = BLOCKED
ROOT_CAUSE_CLASS = UNKNOWN_NATIVE_CRASH
H3_NATIVE_CRASH = UNRESOLVED
PHYSICAL_MACHINE_H3 = BLOCKED
H3_8GB_VRAM_ENVELOPE = NOT_VERIFIED
H3_24G_ENVELOPE = NOT_VERIFIED
RECOMMENDATION = H3_DEPLOYMENT_CHANGE_REQUIRED
```

## Runtime baseline

- Windows 11, build 10.0.22631.
- ComfyUI interpreter: CPython 3.12.12, AMD64, `D:\ComfyUI\.venv\Scripts\python.exe`.
- Base interpreter used by the venv launcher: uv-managed CPython 3.12.12 AMD64.
- PyTorch: 2.13.0+cu130, AMD64; build CUDA 13.0; CUDA available.
- CPU: Intel Core i5-14600KF, AMD64, AVX2, 14 cores / 20 logical processors.
- Torch threads / interop threads: 14 / 14; no OMP/MKL thread override was present.
- Actual loaded DLL: `D:\ComfyUI\.venv\Lib\site-packages\torch\lib\torch_cpu.dll`, AMD64, 305,204,224 bytes, SHA-256 `9a046ce316519c0d51c5a1a8e5e732aeb3716973edfdc9ffd29805b69b7ac36c`.
- numpy 2.4.4, torchvision 0.28.0+cu130, torchaudio 2.11.0+cu130, and safetensors 0.8.0 imported successfully from the same venv.

No foreign Torch DLL was loaded. `PYTHONHOME` and `PYTHONPATH` were unset. Old Python entries existed in process PATH but were absent from the running interpreter's `sys.path` and did not replace Python or Torch modules; a DLL environment conflict is not supported by current evidence.

## Native crash evidence

Original event, 20:55:26 local:

- Windows Application Error event 1000; WER event 1001.
- Faulting application: Python 3.12.12 AMD64 base interpreter behind the ComfyUI venv launcher.
- Faulting module: ComfyUI venv `torch_cpu.dll`.
- Exception: `0xc0000005`.
- Fault offset: `0x0000000008e4a279`.
- Python path: `torch.storage.__getitem__` → ComfyUI `load_torch_file` → `load_clip`.

Post-fix reproduction, 21:16:44 local, produced the same module, exception code, and exact fault offset. Both failures occurred without CUDA OOM or Windows/system memory exhaustion.

## Minimal feedback loops

| Layer | Pre-fix | Post-fix | Scope |
|---|---|---|---|
| Tiny PyTorch CPU tensor/matmul/dtype | PASS | PASS | Same ComfyUI interpreter; CPU only |
| Real H3 text encoder load/tokenize/short encode | PASS | PASS | Same 15,687,142,551-byte NVFP4-AWQ component; no VAE/diffusion/video |
| Full Alysia H3 adapter smoke | Step 8.3 native crash | Native crash | 320×256, 5 frames, 1 step; one post-fix run only |

## One minimal runtime fix

Pre-fix evidence justified testing `ONE_MINIMAL_RUNTIME_FIX = REMOVE_CPU_VAE`: Step 8.3 forced the 5.2 GB VAE to CPU/FP32 before CLIP load, while the text encoder alone passed and the historical successful profile had not used `--cpu-vae`.

The prediction was falsified. Without `--cpu-vae`, ComfyUI used VAE `cuda:0`, CPU offload, FP16, but still crashed during CLIP loading at the exact same native offset. The fix is therefore ineffective and is not adopted. No second fix, package change, thread change, or additional full H3 run was attempted.

## Resource evidence and corrected hardware verdict

Post-fix failed run:

- VRAM baseline / observed peak / after service exit: 1,101 / 1,103 / 997 MiB.
- RAM baseline / observed peak / after service exit: 9,198 / 19,016 / 8,750 MiB.
- Minimum physical RAM available: 13,594 MiB.
- Minimum commit availability: 4,154 MiB.

These are incomplete failure-path values, not successful workload peaks. The native crash does not prove the 8 GB VRAM envelope failed. The corrected classifications are `PHYSICAL_MACHINE_H3 = BLOCKED`, `H3_8GB_VRAM_ENVELOPE = NOT_VERIFIED`, and `H3_24G_ENVELOPE = NOT_VERIFIED`.

## Cleanup and scope

- Provider unload requested; CUDA cache release path called; GPU lock released.
- Owned ComfyUI process exited; orphan ComfyUI/H3: NO.
- Artifact: NONE.
- End-to-End, CreatorQA, Review, PREPARE_ONLY, Bilibili, Step 9, Real Beta, and Alpha23: NOT EXECUTED.
- No model, package, runtime, driver, pagefile, public provider code, or Alpha22 architecture was changed.

## Secret scan

- `alpha22/field_smoke/h3_native_crash`: 23 files, 0 findings.
- This checkpoint: 1 file, 0 findings.
- Result: PASS.

## Git safety

- No reset, clean, restore, checkout, stage, or commit.
- No unknown/system/desktop process termination.
- Final worktree counts: 28 tracked modified, 163 untracked status entries, 0 staged.

## Recommendation

`H3_DEPLOYMENT_CHANGE_REQUIRED`

The evidence supports escalation of the current H3/ComfyUI native deployment rather than a GPU replacement conclusion. A dump/symbol-level investigation or a separately validated H3 deployment would be the next boundary; neither is executed here.
