# Alpha22 Step 8 Hardware Preflight

Date: 2026-08-09  
Result: `BLOCKED_RESOURCE_LIMIT` for real H3 invocation

## Measured hardware and current resources

| Item | Measured value | Source |
|---|---:|---|
| Physical RAM total | 34,193,965,056 bytes / 31.85 GiB | Windows `Win32_OperatingSystem` and ComfyUI `/system_stats` |
| Configured Alysia RAM operating budget | 24 GiB | `config/current_machine_profile.yaml` |
| RAM available immediately before Stage A | 17,228,431,360 bytes | Windows `GlobalMemoryStatusEx` |
| GPU | NVIDIA GeForce RTX 4060 Ti | `nvidia-smi` |
| VRAM total | 8,188 MiB | `nvidia-smi` |
| VRAM free immediately before Stage A | 2,278 MiB | `nvidia-smi` |
| VRAM used immediately before Stage A | 5,672 MiB | `nvidia-smi` |
| Disk C free | 54.66 GiB | Windows logical disk query |
| Disk D free | 243.55 GiB | Windows logical disk query |
| ComfyUI state before Step 8 launch | Not running; loopback health refused connection | HTTP health check/process inventory |
| H3 process state before load | Not running | Windows process inventory |

The prompt describes 24 GB RAM. Windows reports 31.85 GiB of installed physical memory; the project deliberately retains a conservative 24 GiB operating budget. These are different facts and neither is overwritten.

At preflight, a user game process was active on the NVIDIA GPU. It was not terminated or modified. System-level `nvidia-smi` showed only about 2.3 GiB free VRAM, so the real H3 prompt was not submitted.

## Deployment

- ComfyUI: `D:\ComfyUI`
- Runtime: `D:\ComfyUI\.venv\Scripts\python.exe`
- Python: 3.12.12
- ComfyUI: 0.31.0
- PyTorch: 2.13.0+cu130; CUDA device detected
- H3 workflow: `D:\Alysia\workflows\comfyui\h3\t2v.json`
- H3 diffusion model: `D:\ComfyUI\models\diffusion_models\minimax_h3_fl2va_pruned_int8_convrot.safetensors`
- Low-memory launch mode: `--lowvram --disable-pinned-memory --disable-async-offload --reserve-vram 1`
- Text encoder device in workflow: CPU
- GPU-heavy concurrency: 1; sequential execution required
- Cleanup: ComfyUI `/free`, followed by termination of only the service processes launched by Step 8

No component, model, runtime, or dependency was downloaded or reinstalled.

## What the 42.5 GB stack means

The four required model files occupy exactly 42,470,585,471 bytes in their verified manifest; the whole local model tree measured 42,470,615,823 bytes (39.554 GiB). Therefore “42.5 GB” is decimal disk footprint, not a claim that all 42.5 GB must reside simultaneously in RAM or VRAM.

| Model | Bytes |
|---|---:|
| FL2VA pruned INT8 ConvRot | 20,970,379,616 |
| Qwen3-VL 32B NVFP4 AWQ encoder | 15,687,142,551 |
| Video VAE FP16 | 5,207,808,496 |
| Audio VAE FP32 | 605,254,808 |

The verified deployment supports CPU placement for the text encoder, low-VRAM execution, sequential loading, and explicit unload. However, the existing real 608×352 / 73-frame / 6-step smoke evidence measured 7,678 MiB peak VRAM and 25,919 MiB peak RAM. The latter exceeds the configured 24 GiB operating budget.

## Hard-stop decision

Current free VRAM (about 2.3 GiB) is materially below the existing minimum-profile peak (7.678 GiB). Launching H3 would rely on forcing eviction/oversubscription while an unrelated user workload is active. Step 8 forbids that behavior and permits at most one safe profile adjustment; the existing profile is already the deployed low-resolution, low-step profile.

```text
LOCAL_SMOKE = BLOCKED_RESOURCE_LIMIT
H3_REAL_SMOKE = BLOCKED_RESOURCE_LIMIT
```

The ComfyUI runtime itself was still tested with a 64×64 no-model built-in workflow. That result does not count as an H3 invocation.
