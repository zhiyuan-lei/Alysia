from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any


def find_media_executable(name: str, configured: Path | None = None) -> Path | None:
    """查找 FFmpeg 工具，兼容当前终端尚未刷新 winget PATH 的情况。"""
    if configured is not None:
        candidate = configured.expanduser().resolve()
        return candidate if candidate.is_file() else None

    discovered = shutil.which(name)
    if discovered:
        return Path(discovered).resolve()

    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        packages = Path(local_app_data) / "Microsoft" / "WinGet" / "Packages"
        pattern = f"Gyan.FFmpeg_*/*/bin/{name}.exe"
        candidates = sorted(packages.glob(pattern), reverse=True)
        if candidates:
            return candidates[0].resolve()
    return None


def require_media_executable(name: str, configured: Path | None = None) -> Path:
    path = find_media_executable(name, configured)
    if path is None:
        raise FileNotFoundError(f"找不到 {name}；请安装 FFmpeg 或在 render 配置中指定路径")
    return path


def run_command(
    command: list[str],
    *,
    cwd: Path | None = None,
    timeout_sec: int = 600,
    heartbeat: Callable[[], None] | None = None,
    poll_interval_sec: float = 1.0,
) -> subprocess.CompletedProcess[str]:
    if heartbeat is None:
        result = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_sec,
            check=False,
        )
    else:
        with tempfile.TemporaryFile(mode="w+", encoding="utf-8", errors="replace") as stdout_file, tempfile.TemporaryFile(
            mode="w+", encoding="utf-8", errors="replace"
        ) as stderr_file:
            process = subprocess.Popen(command, cwd=cwd, stdout=stdout_file, stderr=stderr_file, text=True)
            started = time.monotonic()
            while process.poll() is None:
                heartbeat()
                if time.monotonic() - started > timeout_sec:
                    process.kill()
                    process.wait()
                    stdout_file.seek(0)
                    stderr_file.seek(0)
                    raise subprocess.TimeoutExpired(
                        command, timeout_sec, output=stdout_file.read(), stderr=stderr_file.read()
                    )
                time.sleep(max(0.05, poll_interval_sec))
            stdout_file.seek(0)
            stderr_file.seek(0)
            result = subprocess.CompletedProcess(
                command, process.returncode, stdout_file.read(), stderr_file.read()
            )
    if result.returncode != 0:
        details = (result.stderr or result.stdout).strip()
        raise RuntimeError(f"命令失败（{result.returncode}）：{' '.join(command[:3])}\n{details[-3000:]}")
    return result


def probe_media(path: Path, ffprobe_path: Path) -> dict[str, Any]:
    result = run_command(
        [
            str(ffprobe_path),
            "-v",
            "error",
            "-show_streams",
            "-show_format",
            "-of",
            "json",
            str(path),
        ],
        timeout_sec=60,
    )
    return json.loads(result.stdout)
