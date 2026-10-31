# Alpha22 Step 8.5 — MiniMax H3 NVFP4 Bypass Validation

Date: 2026-08-09

## Status

```text
ALPHA22_STEP_8_5_STATUS = DOWNLOAD_REQUIRED
INT8_ENCODER = MODEL_COMPONENT_DOWNLOAD_REQUIRED
DIAGNOSTIC_VERDICT = INSUFFICIENT_EVIDENCE
PHYSICAL_MACHINE_H3 = BLOCKED
H3_8GB_VRAM_ENVELOPE = NOT_VERIFIED
H3_24G_ENVELOPE = NOT_VERIFIED
RECOMMENDATION = MODEL_COMPONENT_DOWNLOAD_REQUIRED
```

## Encoder inventory

ComfyUI resolves text encoders from:

- `D:\ComfyUI\models\text_encoders`
- `D:\ComfyUI\models\clip`

No active `extra_model_paths.yaml` exists in the deployed ComfyUI root.

Current NVFP4 encoder:

- Path: `D:\ComfyUI\models\text_encoders\qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors`
- Size: 15,687,142,551 bytes
- Live SHA-256: `35a88d51044231fe332301d7a62aa81e3f2cba62febeb446e2c1e3e0ef76f2c6`
- Provenance manifest: `Comfy-Org/MiniMax-H3`, revision `eb8a16107c595128b3a578f82d2ce2f75920c355`; current size and hash match the verified manifest.

Required INT8 encoder:

- Filename: `qwen3vl_32b_minimax_h3_int8_convrot.safetensors`
- Status: NOT_FOUND in every registered text-encoder directory
- Official target size: approximately 27.1 GB
- Official target SHA-256: `bc2ced0fbea64757fa9acddccfc0b3f4819d1dcf1da6c124d690d368be283923`
- Integrity: NOT_VERIFIED because no local file exists
- Download attempted: NO

## Upstream correlation

Upstream correlation: ComfyUI issue [#15397](https://github.com/Comfy-Org/ComfyUI/issues/15397).

Local symptom correlation:

- MiniMax H3
- NVFP4-AWQ text encoder
- Windows
- `0xc0000005`
- `torch_cpu.dll`
- `torch.storage.__getitem__` -> `load_torch_file` -> `load_clip`
- no CUDA or system RAM OOM

Correlation is HIGH, but the upstream issue is an open potential-bug report. It has not formally confirmed a root cause or fix. Its INT8 ConvRot replacement is a proposed follow-up isolation test, which is exactly the local test blocked by the missing component.

## Stage gates

```text
INT8_LOAD_TORCH_FILE = NOT_EXECUTED
INT8_TEXT_ENCODER = NOT_EXECUTED
REAL_H3_INT8_SMOKE = NOT_EXECUTED
0xc0000005 reproduced? = NOT_EXECUTED
```

The specification forbids starting the approximately 27.1 GB download automatically. Because the model-integrity gate cannot pass, no ComfyUI process, H3 process, or Alysia adapter invocation was started. No artifact or resource measurement exists for this run.

## Hardware verdict

No successful full real workload was executed. Failure-path or historical resource values cannot be used to pass either envelope.

```text
PHYSICAL_MACHINE_H3 = BLOCKED
H3_8GB_VRAM_ENVELOPE = NOT_VERIFIED
H3_24G_ENVELOPE = NOT_VERIFIED
```

## Scope and cleanup

- NVFP4 file: untouched.
- Default production encoder configuration: unchanged.
- Models downloaded or replaced: none.
- ComfyUI/H3/Alysia GPU processes started: none.
- Real H3 invocation count: 0.
- Resume test: NOT_EXECUTED.
- Alpha22 architecture and public provider code: unchanged.
- End-to-End, CreatorQA, Review, PREPARE_ONLY, Bilibili, Step 9, Real Beta, and Alpha23: NOT EXECUTED.

## Secret scan

- Scope: `alpha22/field_smoke/h3_int8_bypass` and this checkpoint.
- Files scanned: 5.
- Findings: 0.
- Result: PASS.

## Git safety

- No reset, clean, restore, checkout, stage, or commit.
- Initial worktree counts: 28 tracked modified, 163 untracked status entries, 0 staged.
- Final worktree counts: 28 tracked modified, 163 untracked status entries, 0 staged.

## Recommendation

`MODEL_COMPONENT_DOWNLOAD_REQUIRED`

Obtain the official INT8 ConvRot encoder component and verify its SHA-256 against `bc2ced0fbea64757fa9acddccfc0b3f4819d1dcf1da6c124d690d368be283923` before rerunning Step 8.5. Do not substitute a third-party quantization, GGUF, or unofficial conversion.
