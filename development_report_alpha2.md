# Alysia v0.1-alpha.2 开发报告

生成日期：2026-08-07（Asia/Shanghai）

## 结果

已完成本阶段唯一目标：

```text
中文 Topic → Research → Script → Storyboard → Text QA → text_ready
```

流水线支持 CLI 创建、状态查询和幂等恢复；所有正式测试均离线运行，不依赖网络、Ollama 或 API key。视频级 `Stage.COMPLETED` 没有被误用，文本里程碑通过 `milestone=text_ready` 与 `text_pipeline_completed=true` 表示。

## 架构说明

- `alysia/core/run.py`：创建 run_id，持久化 RunState，原子写入 UTF-8 JSON/Markdown，并记录 JSONL 事件。
- `alysia/core/orchestrator.py`：按状态串行执行 Research、Writing、Storyboarding、Text QA；支持重试、失败记录、跳过已完成步骤和 `--force`。
- `alysia/providers/llm`：统一 `BaseLLMProvider.generate_structured` 接口；实现 Mock、Ollama 和 Cloud 占位。
- `alysia/providers/search`：统一 Research provider 接口；实现离线 Mock 和 Web 占位。
- `alysia/schemas`：定义 ResearchResult、Source、Script、ScriptSection、Storyboard、Scene 和 TextQAReport。
- `alysia/agents`：Researcher、Writer、Director 与启发式 TextCritic。
- `alysia/prompts`：Research、Writer、Director、Critic 四份独立 prompt，不在 Python 中硬编码长提示词。
- `alysia/cli.py`：新增 `create`、`status`、`resume`、`runs`，保留并验证原有 `doctor`。

`Stage` 原有枚举值保持不变，第一阶段 CLI、doctor、state 测试保持兼容。

## 主要修改文件

- 核心：`alysia/core/config.py`、`alysia/core/run.py`、`alysia/core/orchestrator.py`
- Agent：`alysia/agents/researcher.py`、`writer.py`、`director.py`、`critic.py`
- Provider：`alysia/providers/llm/*`、`alysia/providers/search/*`
- Schema：`alysia/schemas/*`
- Prompt：`alysia/prompts/*.md`
- CLI/配置：`alysia/cli.py`、`config.example.yaml`、`pyproject.toml`
- 文档：`README.md`、`development_report_alpha2.md`
- 测试：新增持久化、Mock LLM、Research/Script/Storyboard schema、Orchestrator、CLI 和 resume 幂等性测试。

## 测试与自检

- 修改前基线：`3 passed in 0.50s`
- 修改后测试：`14 passed in 0.71s`
- `python -m alysia --help`：通过，显示 create/status/resume/runs/doctor。
- `python -m alysia doctor`：通过；7 项可用，4 项缺失或未就绪。
- Mock demo create：通过。
- Demo status：通过，当前阶段 `qa`，文本里程碑 `text_ready`。
- Demo resume：通过，已完成产物未重做。
- Demo 全部 JSON：通过 PowerShell `ConvertFrom-Json` 解析。
- Demo Markdown：UTF-8 中文可读。

## Demo

- run_id：`20260807_175616_cb2fbe40`
- 目录：`D:\Alysia\runs\20260807_175616_cb2fbe40`
- 主要产物：`input.json`、`run_state.json`、`research.md`、`sources.json`、`script.md`、`script.json`、`storyboard.json`、`metadata.json`、`text_qa_report.json`
- QA 结果：通过；报告同时声明当前检查不等同于事实核查。

Mock demo 中的来源使用 `example.invalid`，仅验证数据结构和恢复机制，不能作为发布内容的真实依据。

## Ollama smoke test

- `doctor` 未找到 Ollama。
- 因 Ollama 不可用，无法检测 `qwen3.5:4b`，也没有运行模型 smoke test。
- 按范围要求未安装 Ollama、未下载模型、未修改全局配置。

## 已知问题

- Web Research 与 Cloud LLM 只有清晰接口，占位实现会显式抛出 `NotImplementedError`。
- Mock 脚本用于验证闭环，不代表达到正式内容质量。
- TextCritic 的无来源事实检测是关键词启发式，不能替代人工或基于来源的事实核查。
- 任务目录由配置中的 `runtime.runs_dir` 定位；相对路径应在项目根目录运行。
- 本机仍未找到 FFmpeg、Ollama 和 CUDA Toolkit；它们不阻塞 alpha.2。
- Git 在本轮开始前尚无提交，alpha.1 文件也处于未跟踪状态。

## v0.1-alpha.3：TTS + Subtitle 建议

1. 先定义 `BaseTTSProvider` 和带 schema 的 `AudioResult`，要求输出 WAV 路径、采样率、声道、总时长和可选句级时间戳。
2. 测试继续使用离线 `MockTTSProvider`，通过 Python 标准库生成确定性 WAV；真实中文 TTS 作为可替换 provider，不进入测试依赖。
3. 优先按脚本 section/scene 分段合成音频，而不是一次生成整条旁白，以便失败恢复、重试和字幕对齐。
4. 若 TTS 能返回时间戳，直接生成 SRT；否则先按句子和实际音频时长分配时间，再将 faster-whisper 作为可选校验/精对齐步骤。
5. 新增 `audio/manifest.json`、`audio/narration.wav`、`subtitles/subtitles.srt` 与 `subtitle_qa_report.json`，并延续现有 RunState、重试和 artifact 跳过机制。
6. 保持 GPU 串行调度；在 Ollama/TTS/Whisper 阶段之间显式释放模型，适配 RTX 4060 Ti 8GB。
7. alpha.3 暂不接 Remotion；先以“音频可解码、时长合理、字幕时间轴单调且不越界”为验收标准。
