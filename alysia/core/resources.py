from __future__ import annotations

import gc
import importlib.util
import os
import shutil
import subprocess
import threading
import ctypes
from contextlib import contextmanager
from typing import Any, Iterator

from loguru import logger


class ResourceManager:
    """记录并串行化 GPU-heavy 阶段；不伪造精确显存分配。"""

    def __init__(self, *, sequential_gpu: bool = True) -> None:
        self.sequential_gpu = sequential_gpu
        self.current_gpu_phase: str | None = None
        self.current_stage: str | None = None
        self._gpu_mutex = threading.Lock()
        self._gpu_providers: dict[str, Any] = {}

    def register_gpu_provider(self, name: str, provider: Any) -> None:
        self._gpu_providers[name] = provider

    def unload_gpu_providers(self, *, except_name: str | None = None) -> list[str]:
        """尽力卸载已注册 GPU provider；只调用其公开 unload/cleanup 接口。"""
        unloaded: list[str] = []
        for name, provider in self._gpu_providers.items():
            if name == except_name:
                continue
            cleanup = getattr(provider, "unload", None) or getattr(provider, "cleanup", None)
            if callable(cleanup):
                cleanup()
                unloaded.append(name)
        self._release_cuda_cache()
        return unloaded

    def acquire(self, name: str, *, gpu_heavy: bool = False, timeout_sec: float | None = None) -> None:
        if self.current_stage is not None:
            raise RuntimeError(f"资源阶段冲突：{self.current_stage} 尚未释放，不能进入 {name}")
        if gpu_heavy:
            timeout = timeout_sec if timeout_sec is not None else -1
            acquired = self._gpu_mutex.acquire(timeout=timeout)
            if not acquired:
                raise TimeoutError(f"等待 GPU-heavy stage 超时：{name}")
            if self.sequential_gpu and self.current_gpu_phase is not None:
                self._gpu_mutex.release()
                raise RuntimeError(f"GPU 阶段冲突：{self.current_gpu_phase} 尚未释放，不能进入 {name}")
            self.current_gpu_phase = name
        self.current_stage = name

    def release(self, name: str, *, provider: Any | None = None, gpu_heavy: bool = False) -> None:
        try:
            if provider is not None:
                cleanup = getattr(provider, "unload", None) or getattr(provider, "cleanup", None)
                if callable(cleanup):
                    cleanup()
            self._release_cuda_cache()
        finally:
            self.current_stage = None
            if gpu_heavy:
                self.current_gpu_phase = None
                if self._gpu_mutex.locked():
                    self._gpu_mutex.release()

    @contextmanager
    def phase(
        self,
        name: str,
        *,
        provider: Any | None = None,
        gpu_heavy: bool = False,
        timeout_sec: float | None = None,
    ) -> Iterator[None]:
        self.acquire(name, gpu_heavy=gpu_heavy, timeout_sec=timeout_sec)
        logger.info("resource phase acquired: {} (gpu_heavy={})", name, gpu_heavy)
        try:
            yield
        finally:
            self.release(name, provider=provider, gpu_heavy=gpu_heavy)
            logger.info("resource phase released: {}", name)

    @staticmethod
    def probe_vram() -> dict[str, int] | None:
        executable = shutil.which("nvidia-smi")
        if executable is None:
            return None
        try:
            result = subprocess.run(
                [
                    executable,
                    "--query-gpu=memory.total,memory.used,memory.free",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=5,
                check=False,
            )
            if result.returncode != 0 or not result.stdout.strip():
                return None
            total, used, free = [int(value.strip()) for value in result.stdout.splitlines()[0].split(",")]
            return {"total_mb": total, "used_mb": used, "free_mb": free}
        except (OSError, subprocess.TimeoutExpired, ValueError):
            return None

    @staticmethod
    def probe_ram() -> dict[str, int] | None:
        """读取真实物理内存快照；不把配置预算冒充检测值。"""
        if os.name != "nt":
            return None

        class MemoryStatus(ctypes.Structure):
            _fields_ = [
                ("length", ctypes.c_ulong),
                ("memory_load", ctypes.c_ulong),
                ("total_phys", ctypes.c_ulonglong),
                ("avail_phys", ctypes.c_ulonglong),
                ("total_page_file", ctypes.c_ulonglong),
                ("avail_page_file", ctypes.c_ulonglong),
                ("total_virtual", ctypes.c_ulonglong),
                ("avail_virtual", ctypes.c_ulonglong),
                ("avail_extended_virtual", ctypes.c_ulonglong),
            ]

        status = MemoryStatus()
        status.length = ctypes.sizeof(MemoryStatus)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return None
        return {
            "total_mb": round(status.total_phys / (1024 * 1024)),
            "used_mb": round((status.total_phys - status.avail_phys) / (1024 * 1024)),
            "available_mb": round(status.avail_phys / (1024 * 1024)),
            "commit_limit_mb": round(status.total_page_file / (1024 * 1024)),
            "commit_available_mb": round(status.avail_page_file / (1024 * 1024)),
        }

    @staticmethod
    def is_oom_error(error: BaseException) -> bool:
        message = str(error).lower()
        return any(
            token in message
            for token in ("out of memory", "cuda oom", "cublas_status_alloc_failed", "not enough memory")
        )

    @staticmethod
    def _release_cuda_cache() -> None:
        gc.collect()
        if importlib.util.find_spec("torch") is None:
            return
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except (ImportError, RuntimeError):
            return
