from __future__ import annotations

import json
import platform
import struct
import sys
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / (
    "tiny_torch_cpu_post_fix_result.json"
    if os.environ.get("ALYSIA_84_PHASE") == "post_fix"
    else "tiny_torch_cpu_result.json"
)


def main() -> None:
    import torch

    left = torch.tensor([[1.0, 2.0], [3.0, 4.0]], dtype=torch.float32, device="cpu")
    right = torch.tensor([[2.0, 0.0], [1.0, 2.0]], dtype=torch.float32, device="cpu")
    product = left @ right
    converted = product.to(dtype=torch.float64).to(dtype=torch.float32)
    expected = torch.tensor([[4.0, 4.0], [10.0, 8.0]], dtype=torch.float32)
    passed = bool(torch.equal(converted, expected))
    payload = {
        "result": "PASS" if passed else "FAIL",
        "python": sys.version,
        "python_bits": struct.calcsize("P") * 8,
        "machine": platform.machine(),
        "torch": torch.__version__,
        "device": str(product.device),
        "input_dtype": str(left.dtype),
        "converted_dtype": str(converted.dtype),
        "matmul_result": converted.tolist(),
        "torch_threads": torch.get_num_threads(),
        "torch_interop_threads": torch.get_num_interop_threads(),
        "cuda_api_called": False,
    }
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2), flush=True)
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
