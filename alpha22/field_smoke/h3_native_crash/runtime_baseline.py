from __future__ import annotations

import ctypes.util
import hashlib
import importlib
import importlib.metadata
import json
import os
import platform
import struct
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "runtime_baseline.json"


def pe_machine(path: Path) -> str:
    names = {0x8664: "AMD64", 0x14C: "I386", 0xAA64: "ARM64"}
    with path.open("rb") as stream:
        stream.seek(0x3C)
        pe_offset = struct.unpack("<I", stream.read(4))[0]
        stream.seek(pe_offset + 4)
        machine = struct.unpack("<H", stream.read(2))[0]
    return names.get(machine, hex(machine))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def package_state(name: str, import_name: str | None = None) -> dict[str, object]:
    try:
        version = importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return {"installed": False}
    payload: dict[str, object] = {"installed": True, "version": version}
    try:
        module = importlib.import_module(import_name or name)
        payload["import"] = "PASS"
        payload["path"] = str(Path(module.__file__).resolve()) if module.__file__ else None
    except BaseException as exc:
        payload["import"] = "FAIL"
        payload["error_type"] = type(exc).__name__
        payload["error"] = str(exc)
    return payload


def sanitize(value: str | None) -> str | None:
    if value is None:
        return None
    home = str(Path.home())
    return value.replace(home, "<USERPROFILE>")


def main() -> None:
    import torch

    torch_dir = Path(torch.__file__).resolve().parent
    torch_cpu = torch_dir / "lib" / "torch_cpu.dll"
    loaded_candidates: list[str] = []
    try:
        import psutil

        loaded_candidates = sorted(
            {
                str(Path(item.path).resolve())
                for item in psutil.Process().memory_maps()
                if Path(item.path).name.lower() == "torch_cpu.dll"
            }
        )
    except BaseException:
        pass

    cpu_capability = None
    try:
        cpu_capability = torch.backends.cpu.get_cpu_capability()
    except (AttributeError, RuntimeError):
        pass

    relevant_path = [
        sanitize(entry)
        for entry in os.environ.get("PATH", "").split(os.pathsep)
        if any(token in entry.lower() for token in ("python", "cuda", "torch", "comfy", "uv"))
    ]
    payload = {
        "windows": {
            "platform": platform.platform(),
            "release": platform.release(),
            "version": platform.version(),
        },
        "python": {
            "version": sys.version,
            "implementation": platform.python_implementation(),
            "architecture_bits": struct.calcsize("P") * 8,
            "machine": platform.machine(),
            "sys_executable": str(Path(sys.executable).resolve()),
            "base_executable": str(Path(getattr(sys, "_base_executable", sys.executable)).resolve()),
            "prefix": str(Path(sys.prefix).resolve()),
            "base_prefix": str(Path(sys.base_prefix).resolve()),
            "executable_pe_machine": pe_machine(Path(sys.executable)),
        },
        "cpu": {
            "processor": platform.processor(),
            "identifier": os.environ.get("PROCESSOR_IDENTIFIER"),
            "architecture": os.environ.get("PROCESSOR_ARCHITECTURE"),
            "logical_count": os.cpu_count(),
            "torch_cpu_capability": cpu_capability,
        },
        "torch": {
            "version": torch.__version__,
            "path": str(Path(torch.__file__).resolve()),
            "build_cuda": torch.version.cuda,
            "cuda_available": torch.cuda.is_available(),
            "architecture_bits": struct.calcsize("P") * 8,
            "thread_count": torch.get_num_threads(),
            "interop_thread_count": torch.get_num_interop_threads(),
            "build_config": torch.__config__.show(),
        },
        "torch_cpu_dll": {
            "expected_path": str(torch_cpu),
            "exists": torch_cpu.is_file(),
            "size_bytes": torch_cpu.stat().st_size if torch_cpu.is_file() else None,
            "sha256": sha256(torch_cpu) if torch_cpu.is_file() else None,
            "pe_machine": pe_machine(torch_cpu) if torch_cpu.is_file() else None,
            "loaded_paths": loaded_candidates,
        },
        "packages": {
            "numpy": package_state("numpy"),
            "torchvision": package_state("torchvision"),
            "torchaudio": package_state("torchaudio"),
            "safetensors": package_state("safetensors"),
            "comfyui": package_state("comfyui", "comfy"),
            "comfy-aimdo": package_state("comfy-aimdo", "comfy_aimdo"),
            "comfy-kitchen": package_state("comfy-kitchen", "comfy_kitchen"),
        },
        "native_environment": {
            "pythonhome": sanitize(os.environ.get("PYTHONHOME")),
            "pythonpath": sanitize(os.environ.get("PYTHONPATH")),
            "cuda_path": sanitize(os.environ.get("CUDA_PATH")),
            "relevant_path_entries": relevant_path,
            "vcruntime140_visible": ctypes.util.find_library("vcruntime140"),
            "omp_num_threads": os.environ.get("OMP_NUM_THREADS"),
            "mkl_num_threads": os.environ.get("MKL_NUM_THREADS"),
            "kmp_duplicate_lib_ok": os.environ.get("KMP_DUPLICATE_LIB_OK"),
            "kmp_init_at_fork": os.environ.get("KMP_INIT_AT_FORK"),
        },
        "sys_path": [sanitize(str(Path(item).resolve())) if item else "" for item in sys.path],
    }
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
