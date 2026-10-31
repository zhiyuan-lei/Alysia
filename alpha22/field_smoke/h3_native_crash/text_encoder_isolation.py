from __future__ import annotations

import faulthandler
import json
import os
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / (
    "text_encoder_post_fix_child_result.json"
    if os.environ.get("ALYSIA_84_PHASE") == "post_fix"
    else "text_encoder_isolation_child_result.json"
)
COMFY_DIR = Path(r"D:\ComfyUI")
MODEL_NAME = "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors"


def checkpoint(name: str, **values: object) -> None:
    print(json.dumps({"checkpoint": name, **values}, ensure_ascii=False), flush=True)


def main() -> None:
    faulthandler.enable(all_threads=True)
    os.chdir(COMFY_DIR)
    sys.path.insert(0, str(COMFY_DIR))
    checkpoint("python_ready", executable=sys.executable, bits=64 if sys.maxsize > 2**32 else 32)

    import torch

    checkpoint(
        "torch_ready",
        version=torch.__version__,
        torch_path=str(Path(torch.__file__).resolve()),
        threads=torch.get_num_threads(),
        interop_threads=torch.get_num_interop_threads(),
    )

    import folder_paths
    import nodes

    model_path = Path(folder_paths.get_full_path_or_raise("text_encoders", MODEL_NAME)).resolve()
    checkpoint(
        "model_resolved",
        model_path=str(model_path),
        model_size_bytes=model_path.stat().st_size,
        loader="nodes.CLIPLoader(type=minimax, device=cpu)",
    )

    started = time.monotonic()
    clip = nodes.CLIPLoader().load_clip(MODEL_NAME, type="minimax", device="cpu")[0]
    checkpoint("clip_loaded", elapsed_seconds=round(time.monotonic() - started, 3))

    tokens = clip.tokenize("TEST_ONLY blue circle")
    checkpoint("tokenized", token_type=type(tokens).__name__)
    conditioning = clip.encode_from_tokens_scheduled(tokens)
    checkpoint("encoded", output_type=type(conditioning).__name__)

    payload = {
        "result": "PASS",
        "model": str(model_path),
        "model_size_bytes": model_path.stat().st_size,
        "device": "cpu",
        "dtype_quantization": "deployed NVFP4-AWQ component",
        "tokenizer_config_loaded": True,
        "short_encode_completed": True,
        "elapsed_seconds": round(time.monotonic() - started, 3),
    }
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
