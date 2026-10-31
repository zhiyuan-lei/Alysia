# Alpha22 Step 8.2 — GPU Availability Recovery + H3 Retry

Date: 2026-08-09

## Status

```text
ALPHA22_STEP_8_2_STATUS = BLOCKED
H3_RETRY = NOT_EXECUTED
PHYSICAL_MACHINE_H3 = BLOCKED
H3_24G_ENVELOPE = NOT_VERIFIED
STEP_8_STATUS = KEEP_BLOCKED
```

## GPU inventory

- GPU: RTX 4060 Ti, 8,188 MiB total.
- Final measurement: 1,313 MiB used / 6,637 MiB free / 37% utilization.
- Five samples: 1,317–1,337 MiB used and 6,613–6,633 MiB free.
- Historical minimal H3 peak: 7,678 MiB.
- Raw shortfall before driver/desktop headroom: 1,041 MiB.
- WDDM reports per-process VRAM as `N/A` through `nvidia-smi`; Windows dedicated-allocation counters were used only as estimates.

The largest estimated allocations were desktop composition, Microsoft Edge, Word, Windows Widgets, and the current Codex desktop application. No process was closed or terminated.

## Alysia leak check

No Python, Pythonw, pytest, ffmpeg, ComfyUI, H3, Torch, or Alysia worker process was found after correlating process names with command lines, executable paths, and parent processes. No cleanup action was eligible or performed.

## Ready gate

The generic `ResourceGuard` thresholds are 768 MiB minimum and 1,536 MiB warning free VRAM, but those thresholds do not reserve the measured 7,678 MiB H3 profile. Workload-specific evidence therefore controls this decision.

Current free VRAM is already 1,041 MiB below the historical H3 peak, before allowing any WDDM driver and desktop headroom. The ready gate failed and H3 was not invoked.

## User action required

The user may close ordinary applications they recognize and do not need: Microsoft Edge, Word, Weixin/WeChat, Outline, Edge Game Assist, and Phone Link. The current Codex task, Windows desktop/system processes, and Windows Widgets were preserved. Actual free VRAM must be remeasured after user action; dedicated-allocation estimates are not guarantees of reclaimed resident VRAM.

## H3 retry and verdict

- Real `H3ProductionAdapter`: NOT INVOKED.
- Real H3 runtime: NOT INVOKED.
- Artifact and resource profile: NOT MEASURED.
- `PHYSICAL_MACHINE_H3 = BLOCKED`.
- `H3_24G_ENVELOPE = NOT_VERIFIED`.
- `STEP_8_STATUS = KEEP_BLOCKED`.

## Safety

- No process termination, application closure, driver change, reboot, CUDA reinstall, H3/ComfyUI modification, pagefile change, or Alpha22 architecture change.
- No reset, clean, restore, checkout, stage, or commit.

## Evidence

- `alpha22/field_smoke/gpu_availability/gpu_process_inventory.json`
- Previous Step 8 and Step 8.1 BLOCKED evidence remains unchanged.
