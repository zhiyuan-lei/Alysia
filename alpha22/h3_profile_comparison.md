# Alpha22 Step 8.3 — H3 Profile Comparison

Date: 2026-08-09

Only one candidate is authorized and selected: `ONE_LOW_VRAM_PROFILE`.

| Setting | Historical Profile | Low-VRAM Candidate |
|---|---|---|
| ComfyUI VRAM mode | `--lowvram` | `--novram` |
| text encoder device | CPU, from the existing T2V workflow | CPU, unchanged |
| VAE device | Default ComfyUI placement/dynamic offload | CPU via existing `--cpu-vae` option |
| model offload | Default dynamic offload under `--lowvram` | Maximum existing offload policy under `--novram` |
| sequential load | Required; GPU-heavy concurrency = 1 | Required; `ResourceManager(sequential_gpu=True)` |
| cache policy | RAM-pressure cache plus provider `/free` after task | No new cache implementation; `--novram` plus provider `/free` and CUDA cache release |
| attention mode | ComfyUI/PyTorch default; no explicit override | Unchanged; no unverified attention flag added |
| pinned / async offload | `--disable-pinned-memory --disable-async-offload` | Unchanged |
| driver/desktop reserve | `--reserve-vram 1` | Unchanged |
| deployed weights | Existing INT8 diffusion model, NVFP4-AWQ text encoder, FP16 video VAE | Same verified local files; no download or replacement |
| smoke canvas | 608×352 | 320×256, supported by `H3VisualConfig` and the existing node's 32-pixel grid |
| smoke frames | 73 | 5, the existing node's minimum valid 17k+5 frame count |
| smoke steps | 6 | 1, supported by `H3VisualConfig` |
| component unloading | Provider `/free`, model unload, CUDA cache release | Same, mandatory after the single run |
| expected quality impact | Existing minimal smoke quality, previously VisualQA PASS | Large smoke-only quality reduction from smaller canvas, five frames, and one step; only structural validity is evaluated |
| expected speed impact | Historical provider time about 105–171 seconds | Offload and CPU VAE may be materially slower; the smaller workload may partially offset this |

## Selection basis

The historical 7,678 MiB profile already used low-VRAM mode, CPU text encoding, quantized deployed components, sequential GPU execution, and explicit unload. Repeating it would not validate a new lower-memory profile. The installed ComfyUI 0.31 CLI explicitly provides `--novram` for cases where `--lowvram` is insufficient and also provides `--cpu-vae`; Alysia already supports 320×256, one preview step, five-frame duration binding, serial GPU locking, and cleanup. This candidate therefore uses only current code, current runtime, and current model files.

Stability is prioritized by avoiding experimental `--fast` attention options, disabling pinned/async offload as in the verified deployment, retaining 1 GiB OS reservation, and allowing exactly one real invocation.
