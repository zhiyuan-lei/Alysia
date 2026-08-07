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
| FFmpeg | 未找到 |
| Ollama | 未找到 |
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

## 缺失或有意延后的依赖

- FFmpeg：未安装或不在 PATH。后续视频/音频处理前必须补齐。
- Ollama：未安装或不在 PATH。
- `qwen3.5:4b`：由于 Ollama 不可用，本轮跳过模型检测；没有自动下载大模型。
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
- `python -m alysia doctor`：通过，退出码 0；7 项可用，4 项缺失或未就绪。
- `pytest`：通过，`3 passed in 0.51s`。
- `npm run check --prefix video/remotion`：通过，最小 Node 骨架可调用。
- `git status`：仓库已初始化在 `main` 分支，尚无提交；本轮文件均为待跟踪文件，未擅自创建提交。

## 下一步建议

1. 优先安装并验证 FFmpeg，因为它是后续任何可播放 MP4 流程的硬依赖。
2. 再安装并启动 Ollama；确认服务正常后，按需执行 `ollama pull qwen3.5:4b`，不要与其他 GPU 模型同时常驻。
3. 下一开发轮先补充可持久化的 Run/状态文件和配置加载测试，再接一个确定性的“无 AI 占位视频”渲染闭环。
4. 在 FFmpeg 与状态持久化稳定前，不引入 TTS、Whisper、ComfyUI、LangChain 或 LangGraph。
