# Alysia

Alysia 是面向 B 站的自主创作者系统。本仓库当前处于 `v0.1-alpha.2` 文本创作闭环阶段。

本机实际项目路径：`D:\Alysia`

## 当前能力

当前已打通可恢复的离线文本流水线：

```text
中文 Topic
  → ResearchResult
  → Script
  → Storyboard
  → Text QA
  → milestone: text_ready
```

- 每一步均使用 Pydantic schema 校验结构化输出。
- 每一步完成后写入 `run_state.json` 和对应 artifact。
- `resume` 默认跳过已完成且产物仍存在的阶段；`--force` 可重新执行。
- Mock provider 完全离线，可用于测试和演示。
- Ollama provider 支持结构化输出，但不会自动安装 Ollama 或下载模型。
- Text QA 只做主题、结构、引用、重复和时长的启发式检查，不声称替代事实核查。

## 快速开始

```powershell
Set-Location D:\Alysia
uv sync --extra dev --python 3.11
uv run python -m alysia --help
uv run python -m alysia doctor
uv run python -m alysia create "为什么AI Agent还不是AGI？" --provider mock
uv run pytest
```

也可以直接使用虚拟环境中的解释器：

```powershell
.\.venv\Scripts\python.exe -m alysia doctor
.\.venv\Scripts\python.exe -m alysia create "为什么AI Agent还不是AGI？" --provider mock
.\.venv\Scripts\python.exe -m pytest
```

## CLI

```powershell
# 创建并运行到 text_ready
python -m alysia create "主题" --provider mock

# 查看状态
python -m alysia status RUN_ID

# 幂等恢复；已完成阶段默认跳过
python -m alysia resume RUN_ID

# 明确重跑文本阶段
python -m alysia resume RUN_ID --force

# 列出本地任务
python -m alysia runs
```

单次任务保存在 `runs/<run_id>/`，主要产物包括：

```text
input.json
run_state.json
research.md
sources.json
script.md
script.json
storyboard.json
metadata.json
text_qa_report.json
logs/events.jsonl
```

## 配置

按需复制示例文件，真实配置和密钥不会被 Git 跟踪：

```powershell
Copy-Item config.example.yaml config.yaml
Copy-Item .env.example .env
```

`config.example.yaml` 中的文本阶段配置：

```yaml
llm:
  provider: mock           # mock | ollama | cloud（占位）
  model: qwen3.5:4b
  base_url: http://127.0.0.1:11434

content:
  language: zh-CN
  min_duration_sec: 120
  max_duration_sec: 300
  default_duration_sec: 180

research:
  provider: mock           # web 目前只有接口骨架
  max_sources: 5

runtime:
  retries: 1
  runs_dir: runs
```

使用本地 Ollama 时，将 `llm.provider` 改为 `ollama`，或为单次创建传入 `--provider ollama`。必须先自行确认 Ollama 服务和指定模型已经存在；Alysia 不会自动下载模型。正式发布内容前还需要真实的 Research provider，Mock 来源只用于离线验收。

## 当前明确不支持

- TTS 与真实旁白音频
- 字幕生成及音频时间轴对齐
- Whisper / faster-whisper
- Remotion / FFmpeg 视频渲染
- AI 图片生成
- Bilibili 自动投稿或账号登录
- 真实 Web Research 与事实核查
- Cloud LLM 实际 API 接入

## 待补齐的外部工具

环境诊断以 `python -m alysia doctor` 的实时结果为准。

- 安装 FFmpeg 后运行 `ffmpeg -version` 验证。
- 安装并启动 Ollama 后运行 `ollama list` 验证。
- 后续需要本地文本模型时，再按需运行 `ollama pull qwen3.5:4b`；本轮不会自动下载模型。
- Remotion 当前只有最小 Node 项目骨架，尚未安装依赖或建立视频模板。

## 目录说明

- `alysia/core`：配置、Run 持久化、状态与编排
- `alysia/agents`：Researcher、Writer、Director、TextCritic
- `alysia/workers`：后续工具执行器
- `alysia/providers`：Mock/Ollama LLM、Mock/Web Research 接口及后续适配器
- `alysia/schemas`：Research、Script、Storyboard 与 QA 结构化模型
- `alysia/prompts`：各角色独立 prompt
- `video/remotion`：程序化视频最小 Node 骨架
- `skills`、`memory`、`evaluation`：技能、长期记忆与评测
- `assets`、`runs`：静态素材与运行产物

第一阶段环境检测见 `setup_report.md`；alpha.2 实现与验收结果见 `development_report_alpha2.md`。
