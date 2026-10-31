# Alysia v0.1-alpha.3 开发报告

生成日期：2026-08-07（Asia/Shanghai）

## 结果

本阶段已完成：

```text
已有 Script / Storyboard
  → scene PCM16 WAV
  → narration.wav + audio_manifest.json
  → deterministic subtitles.srt / subtitles.json
  → 基础 Audio QA
  → milestone: audio_ready
```

实际仓库路径：`D:\Alysia`

`final.mp4` 尚未生成，任务没有标记为 `completed`；run 仅通过 `pipeline_phase=audio_ready`、`milestone=audio_ready` 和 `audio_pipeline_completed=true` 表示第三阶段完成。

## alpha.2 审计结论

开始前基线为 `14 passed in 0.69s`。仓库中的 alpha.2 并非只有空骨架：Research、Script、Storyboard、Text QA、Run 持久化以及 create/status/resume 已经可工作，历史 demo 也完整存在。本轮没有重建或重构这些模块，只做了第三阶段必需的最小扩展：

- 旧 config snapshot 缺少音频配置时使用安全默认值。
- `create` 继续停在 `text_ready`，保持 alpha.2 语义。
- `resume` 在幂等跳过已有文本阶段后继续到 `audio_ready`。
- RunState 增加 `audio_pipeline_completed`，并将新 phase 使用明确的 `text_ready` / `audio_ready` 值。

Web Research、Cloud LLM 和真实事实核查仍未完成，但它们不阻塞已有 Storyboard 的音频闭环。

## 新增能力

- `BaseTTSProvider`、`MockTTSProvider`、`CosyVoiceProvider`。
- MockTTS 生成真正可由 Python `wave` 解码的确定性 PCM16 mono WAV，不是空文件占位。
- CosyVoice 使用惰性适配器，只读取已存在的本地模型目录，不自动安装或下载。
- scene 级 TTS hash 缓存；原始与规范化 narration 同时保存在 manifest。
- Voice 重做会使下游字幕与 Audio QA 状态失效，避免真实 TTS 时长变化后误用旧时间轴；只移除状态引用，不删除文件。
- 轻量中文口播预处理：Markdown、URL、代码块、空白与常用中英文标点的安全规范化。
- WAV 拼接、可配置 scene pause，以及下一阶段可直接消费的 scene 边界。
- deterministic 字幕按句子和字符上限切分，按真实 scene 时长分配，保证单调且不越过旁白。
- `BaseASRProvider`、`FasterWhisperProvider`、`MockASRProvider`；ASR 只做可选边界校准，不覆盖脚本文字。
- faster-whisper CUDA RuntimeError 时尝试 CPU/int8；任何可选 ASR 失败都会回退 deterministic 主路径。
- 最小 ResourceManager 串行记录 TTS/ASR phase，退出时卸载 provider 并在可用时清理 CUDA cache。
- Audio QA 检查 WAV 解码、scene 数量与时间、静音、clipping、字幕覆盖/越界/重叠和文本缺失。
- CLI 新增 `voice`、`subtitle`、`audio-status`；`resume` 支持 `--tts-provider`、`--asr-provider`、`--force`。

## 音频规范

- 容器：WAV
- 编码：PCM signed 16-bit little-endian
- 声道：mono
- 默认采样率：24000Hz；同一 narration 的所有 scene 必须一致
- FFmpeg 不承担 TTS；alpha.3 核心拼接与探测使用 Python 标准库 `wave`

## 修改文件

- 配置与状态：`alysia/core/config.py`、`resources.py`、`run.py`、`orchestrator.py`
- Schema：`alysia/schemas/audio.py`、`alysia/schemas/__init__.py`
- TTS：`alysia/providers/tts/*`
- ASR：`alysia/providers/asr/*`
- Worker：`alysia/workers/text.py`、`wav.py`、`voice.py`、`subtitle.py`、`audio_qa.py`
- CLI：`alysia/cli.py`
- 配置/包：`config.example.yaml`、`pyproject.toml`
- 测试：`tests/test_audio_pipeline.py`
- 文档：`README.md`、`development_report_alpha3.md`

本轮保留了开始前用户已有的 `setup_report.md` 修改，没有覆盖或回退。

## Provider 与环境状态

| 项目 | 实时结果 |
|---|---|
| MockTTS | 可用，已完成 demo 与正式离线测试 |
| CosyVoice Python 包 | 未安装；真实 smoke test 跳过 |
| CosyVoice 本地模型 | 未配置；未下载 |
| faster-whisper | 未安装；真实 smoke test 跳过 |
| torch | 未安装；无法声明 Python CUDA 推理已就绪 |
| NVIDIA GPU | RTX 4060 Ti，8188 MiB，驱动 596.21，可由 nvidia-smi 读取 |
| CUDA Toolkit / nvcc | 当前 PATH 不可用；alpha.3 不需要本地 CUDA 编译 |
| FFmpeg / ffprobe | 当前终端 PATH 不可见；核心 demo 使用 Python wave 验证 |

没有修改代理、驱动、Windows Update、全局 CUDA 或系统网络配置，也没有安装大型模型。

## 测试

- 修改前基线：`14 passed in 0.69s`
- alpha.3 最终完整离线测试：`23 passed in 5.95s`
- 覆盖 Mock WAV、manifest、scene 缓存、deterministic 字幕、时间单调、Audio QA、orchestrator resume 和 CLI audio mock。

## Demo

- 复用 run_id：`20260807_175616_cb2fbe40`
- 目录：`D:\Alysia\runs\20260807_175616_cb2fbe40`
- milestone / pipeline_phase：`audio_ready`
- scene WAV 数：3
- narration.wav：66.138458 秒，24000Hz，mono，PCM16
- subtitle segment 数：24
- Audio QA：通过，无 errors / warnings
- RMS：0.067402
- peak：0.128143
- clipping ratio：0
- 字幕语音覆盖：0.999993
- 字幕文本相似度：1.0

第二次 resume 后，scene WAV、narration.wav、manifest、SRT/JSON 与 QA 报告的修改时间均未变化，缓存与恢复幂等性通过。

另行执行 `voice --force` 后，状态正确降为 `voice_ready`，`audio_pipeline_completed=false`，字幕与 QA artifact 失效；随后 resume 成功重建并恢复 `audio_ready`。

## 已知问题

- MockTTS 是可听测试 tone，不代表真实中文语音质量；demo 时长也不代表最终节目时长。
- CosyVoice 适配器需要用户提供兼容包和本地模型；当前机器未进行真实 API smoke test。
- faster-whisper 未安装，ASR 校准路径只有接口与降级逻辑，未在本机做真实模型 smoke test。
- deterministic 字幕按句子/字符分配时间，尚无词级时间戳。
- 当前终端找不到 FFmpeg/ffprobe，与早期 setup_report 的安装记录不一致；第四阶段前必须解决可执行文件发现问题。
- Audio QA 是基础工程检查，不含 LUFS、True Peak、噪声门或广播规范验收。
- Windows 终端偶尔显示中文代码页乱码，但所有 artifact 均按 UTF-8 写入并由测试正常解析。

## 第四阶段建议：Remotion + FFmpeg Video Render

1. 先解决并固定 FFmpeg/ffprobe 二进制发现方式，doctor 应显示实际路径和版本。
2. 让 Remotion 只消费现有 `storyboard.json`、`audio_manifest.json`、`subtitles.json` 和 scene 边界，不重复推断时间轴。
3. 先实现少量确定性 scene 组件（Title/Text/Diagram），用占位背景完成 1080p/30fps 渲染闭环。
4. FFmpeg 只用于探测、最终 mux/编码和基础视频 QA，不承担 TTS 或业务编排。
5. 新增 video manifest 与 video QA，验证 MP4 可解码、分辨率、FPS、音轨、总时长、黑帧和字幕安全区。
6. 保持 GPU 串行；Remotion/编码阶段开始前确保 TTS/ASR provider 已卸载。
7. 在稳定输出可播放 MP4 前，继续延后 ComfyUI、Bilibili 投稿和浏览器登录。
