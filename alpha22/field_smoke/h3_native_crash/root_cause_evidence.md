# Step 8.4 Root Cause Evidence Before Fix

## Observed

- The Step 8.3 process reached the real Alysia `H3ProductionAdapter` and ComfyUI workflow exactly once.
- Under `--cpu-vae`, ComfyUI logged `VAE load device: cpu, offload device: cpu, dtype: torch.float32` before loading the H3 text encoder.
- The deployed video VAE file is 5,207,808,496 bytes. The deployed text encoder file is 15,687,142,551 bytes.
- The process then crashed in `torch_cpu.dll` with Windows exception `0xc0000005` while `safetensors.get_tensor` was loading CLIP state.
- There was no CUDA OOM or system OOM. The failed run still had at least 8,685 MiB physical RAM and 3,518 MiB commit availability.
- Python, Torch, and the loaded `torch_cpu.dll` are all AMD64 and come from the ComfyUI venv/base interpreter chain. No foreign Torch DLL was loaded.

## Reproduced / minimized

- Same-interpreter tiny PyTorch CPU tensor, matmul, and dtype conversion: PASS.
- Same real 15,687,142,551-byte H3 NVFP4-AWQ text encoder, CPU device, tokenizer, and short encode without VAE/diffusion/video: PASS.
- The crash therefore does not reproduce in PyTorch CPU generally or in the real H3 text encoder alone. The smallest currently demonstrated failing boundary is the Step 8.3 combined configuration after forcing the H3 VAE onto CPU and before/during text-encoder state loading.

## Why one fix is justified

`--cpu-vae` is the only Step 8.3 candidate setting that deliberately adds a second large H3 component to CPU residency before text-encoder loading. ComfyUI source confirms that it changes `vae_device()` from the normal Torch device to CPU; without it, the VAE load device is CUDA while CPU remains its offload device. The previously successful historical H3 deployment did not use `--cpu-vae`.

The single minimal runtime fix is therefore:

```text
ONE_MINIMAL_RUNTIME_FIX = REMOVE_CPU_VAE
```

All other settings, model files, versions, resolution, frames, steps, and Alysia adapter path remain unchanged.

## Expected result

The VAE should no longer be forced to load and operate entirely on CPU before the 15.7 GB text encoder is materialized. Tiny Torch and text-encoder-only checks must remain PASS. Only then may one full Step 8.3-equivalent H3 smoke be run. A valid artifact is required to classify the native crash as resolved.

## Fix outcome

- Post-fix tiny Torch: PASS.
- Post-fix real H3 text encoder-only load/tokenize/encode: PASS.
- The one permitted post-fix full H3 smoke: FAIL before artifact creation.
- With `--cpu-vae` removed, ComfyUI logged VAE on `cuda:0`, CPU offload, FP16, yet the process crashed at the same `torch_cpu.dll` module, `0xc0000005` exception, and `0x0000000008e4a279` fault offset while loading CLIP state.
- The post-fix failure had only 1,103 MiB peak VRAM use, at least 13,594 MiB physical RAM available, and at least 4,154 MiB commit availability.

The prediction was falsified. `REMOVE_CPU_VAE` is not adopted as a solution. No second fix or further full H3 attempt is authorized. The smallest established boundary is now: standalone Torch PASS, standalone real H3 text encoder PASS, but the real ComfyUI H3 workflow process deterministically crashes during CLIP state loading after another workflow component has initialized. The available evidence does not isolate the responsible native interaction more narrowly than `UNKNOWN_NATIVE_CRASH`.
