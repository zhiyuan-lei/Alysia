# Alysia v0.1-alpha.1 配置报告

生成日期：2026-08-07（Asia/Shanghai）

## 实际项目路径

- 项目根目录：`D:\Alysia`
- Git 分支：`main`
- Python 虚拟环境：`D:\Alysia\.venv`
- Python 3.11 由 uv 隔离管理，未替换本机已有的 Anaconda Python。

## 检测到的软件版本

| 组件 | 结果 |
|---|---|
| 项目 Python | 3.11.14 |
| 本机原有默认 Python | 3.12.7（Anaconda） |
| 本机其他 Python | 3.10（Python Launcher 可见） |
| 项目 pip | 26.2.1 |
| 本机原有 pip | 24.2（Python 3.12） |
| uv | 0.9.5 |
| Git | 2.51.1.windows.1 |
| Node.js | 24.16.0 |
| npm | 11.13.0 |
| FFmpeg | 9.0-full_build-www.gyan.dev（通过 winget 安装） |
| Ollama | 0.32.6（本地 API 已验证） |
| NVIDIA-SMI | 596.21 |
| NVIDIA 驱动 | 596.21 |
| 驱动支持的 CUDA 版本 | 13.2 |
| CUDA Toolkit / nvcc | 未找到或不在 PATH |

## GPU 检测结果

- GPU：NVIDIA GeForce RTX 4060 Ti
- 总显存：8188 MiB
- NVIDIA 驱动可见，`nvidia-smi` 调用成功。
- 驱动报告支持 CUDA 13.2；这不等于本机已经安装 CUDA Toolkit。
- `nvcc` 当前不可调用。Alysia 本轮不依赖本地 CUDA 编译器，因此没有安装或修改 CUDA。
- `config.example.yaml` 已将 GPU 执行方式固定为串行，最大并发 GPU 模型数为 1。

## 已安装依赖

通过 `uv sync --extra dev --python 3.11` 安装到项目 `.venv`：

| 直接依赖 | 版本 |
|---|---|
| typer | 0.27.1 |
| pydantic | 2.13.4 |
| pydantic-settings | 2.15.0 |
| PyYAML | 6.0.3 |
| httpx | 0.28.1 |
| rich | 14.3.4 |
| tenacity | 9.1.4 |
| loguru | 0.7.3 |
| pytest | 9.1.1 |
| pip（环境工具） | 26.2.1 |

完整的直接和传递依赖已锁定在 `uv.lock`。

## 已补齐、缺失或有意延后的依赖

- FFmpeg：已通过 `winget` 安装 `Gyan.FFmpeg 9.0`；`ffmpeg` 与 `ffprobe` 均已验证可调用。
- Ollama：已安装在用户目录，版本 0.32.6；后台进程与 `http://127.0.0.1:11434/api/version` 均验证正常。
- `qwen3.5:4b`：当前模型列表为空，尚未安装；本轮遵守约束，没有自动下载大模型。
- CUDA Toolkit / `nvcc`：未安装或不在 PATH；当前地基阶段不构成阻塞。
- Remotion npm 包：本轮按范围只创建最小 Node 项目骨架，没有安装 Remotion 或实现模板。
- TTS、Whisper、图像模型和大型 Agent 框架：按本轮范围有意不安装。

## 本轮创建的目录与文件

目录骨架：

- `alysia/core`
- `alysia/agents`
- `alysia/workers`
- `alysia/providers/llm`
- `alysia/providers/tts`
- `alysia/providers/search`
- `alysia/providers/image`
- `alysia/schemas`
- `alysia/prompts`
- `video/remotion`
- `skills`
- `memory`
- `evaluation`
- `assets`
- `runs`
- `tests`

项目文件：

- `pyproject.toml`
- `uv.lock`
- `.gitignore`
- `.env.example`
- `config.example.yaml`
- `README.md`
- `setup_report.md`
- `alysia/__init__.py`
- `alysia/__main__.py`
- `alysia/cli.py`
- `alysia/core/__init__.py`
- `alysia/core/config.py`
- `alysia/core/state.py`
- `tests/test_cli.py`
- `tests/test_state.py`
- `video/remotion/package.json`
- `video/remotion/README.md`
- 空目录中的 `.gitkeep` 占位文件

运行时还创建了被 `.gitignore` 排除的 `.venv`、Python 缓存和 pytest 缓存。

## CLI 与测试结果

- `python -m alysia --help`：通过，退出码 0，显示 `doctor` 子命令。
- `python -m alysia doctor`：通过，退出码 0；9 项可用，4 项缺失或未就绪，其中 CosyVoice Python 与 faster-whisper 为可选延后项。
- `pytest`：通过，`15 passed in 2.73s`。
- `npm run check --prefix video/remotion`：通过，最小 Node 骨架可调用。
- `git status`：仓库位于 `main` 分支；检测到已有提交 `55da646 feat: add alpha.2 text creation pipeline`，环境续配前工作区干净。本轮不修改 alpha.2 业务逻辑、不提交代码。

## 下一步建议

1. 确认要启用本地 LLM 后，再执行 `ollama pull qwen3.5:4b`；不要与其他 GPU 模型同时常驻。
2. 模型下载完成后运行 `ollama list` 与 `python -m alysia doctor`，验证模型检测结果。
3. CUDA Toolkit / `nvcc` 对当前运行路径不是硬依赖，不要仅为了消除 doctor 提示而安装。
4. 当前工作区存在进行中的 TTS/ASR/worker 开发文件；本轮保持原样，先完成其自身验证再引入更多运行时组件。
