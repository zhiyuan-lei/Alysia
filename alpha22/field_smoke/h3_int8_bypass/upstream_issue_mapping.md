# Upstream issue mapping

- Upstream correlation: ComfyUI issue [#15397](https://github.com/Comfy-Org/ComfyUI/issues/15397).
- Local symptom correlation: MiniMax H3; NVFP4-AWQ text encoder; Windows; `0xc0000005`; `torch_cpu.dll`; `torch.storage.__getitem__` -> `load_torch_file` -> `load_clip`; no CUDA or system RAM OOM.
- Correlation: HIGH.
- Limitation: the issue remains an open potential-bug report and does not confirm a root cause or fix. The issue itself identifies the INT8 ConvRot replacement as a planned isolation test, not a completed validation.

The local INT8 component is absent, so this run cannot determine whether the NVFP4 path is the trigger.
