# Alysia v0.1-alpha.4 开发报告

生成日期：2026-08-07（Asia/Shanghai）

## 结果

仓库路径：`D:\Alysia`

本阶段已完成：

```text
audio_ready
  → storyboard + audio_manifest + subtitles
  → deterministic composition.json
  → Mock / Remotion renderer
  → FFmpeg normalize
  → ffprobe + full decode QA
  → milestone: video_ready
```

`final.mp4` 和视频 QA 均通过后才设置 `video_pipeline_completed=true` 与 `milestone=video_ready`；当前仍不设置最终任务 `completed`。

## alpha.3 前置状态

- 开始前全量基线：`23 passed in 5.89s`。
- demo run `20260807_175616_cb2fbe40` 已是 `audio_ready`。
- `narration.wav`：66.138458 秒、24000Hz、mono、PCM16。
- 24 个确定性字幕 segment，Audio QA 通过。
- alpha.3 的 CLI、状态持久化、scene 音频缓存与未提交工作区修改均被保留。

## 新增能力

- `BaseVideoRenderer`、`MockVideoRenderer` 与 `RemotionRenderer`。
- Mock renderer 使用 FFmpeg 生成带真实旁白音轨的有效 MP4，不创建空占位文件。
- `VideoComposition`、`VideoScene`、`VideoSubtitle`、`VideoRenderResult`、`VideoProbe` 与 `VideoQAReport` schema。
- 使用 Decimal half-up 规则把秒稳定转换为帧，默认 1920x1080、30fps，总帧数由真实旁白时长决定。
- 生成 `video/composition.json`、`assets_manifest.json`、`render_config.json` 与 `render_result.json`。
- Remotion React 模板支持 Title/Text/Image/Diagram/Quote/Code/Chart、单轨旁白与中文字幕安全区。
- 本地图片被复制进 run 的 `video/assets`；不存在或不可用时显示 placeholder，不中断渲染。
- FFmpeg 后处理统一输出 H264、AAC、yuv420p、faststart，并限制成片不超过旁白尾部。
- 视频 QA 检查存在性、时长、分辨率、FPS、编码、音轨、ffprobe 可读性与完整解码。
- `python -m alysia render RUN_ID --renderer mock|remotion [--force]`。
- `resume` 从已存在的 `audio_ready` run 直接推进到 `video_ready`；已有通过产物不会重复渲染。
- `doctor` 可在 PATH 未刷新时发现 winget 的 Gyan.FFmpeg，并新增 FFprobe 检查。

## 主要修改文件

- 配置/状态/编排：`alysia/core/config.py`、`state.py`、`run.py`、`orchestrator.py`
- Video provider：`alysia/providers/video/*`
- Schema：`alysia/schemas/video.py`、`alysia/schemas/__init__.py`
- Worker：`alysia/workers/composition.py`、`media.py`、`video.py`、`video_qa.py`
- CLI：`alysia/cli.py`
- Remotion：`video/remotion/package.json`、`package-lock.json`、`src/*`
- 配置/包：`config.example.yaml`、`pyproject.toml`
- 测试：`tests/test_video_pipeline.py`、`tests/test_state.py`
- 文档：`README.md`、`development_report_alpha4.md`

## 环境状态

| 项目 | 实时结果 |
|---|---|
| Node.js | 24.16.0 |
| npm | 11.13.0 |
| Remotion / CLI | 4.0.506，安装成功 |
| React / React DOM | 19.2.8 |
| Chrome Headless Shell | 下载并缓存成功 |
| FFmpeg / ffprobe | Gyan.FFmpeg 9.0，winget 安装目录可发现 |
| NVIDIA GPU | RTX 4060 Ti 8GB；本阶段未启用 AI 视频模型 |

没有修改代理、驱动、CUDA、Windows Update 或平台登录配置。

## 测试

- alpha.3 基线：`23 passed in 5.89s`
- alpha.4 最终全量测试：`30 passed in 6.51s`
- 新增覆盖：video schema、真实 Mock MP4、composition、subtitle frame mapping、ffprobe parser、render/resume 幂等与 video QA。
- `npm run check` 成功识别 `VideoComposition`。

## Demo 验收

- run_id：`20260807_175616_cb2fbe40`
- renderer：先通过 mock，再通过 Remotion 强制重渲染
- final.mp4：`D:\Alysia\runs\20260807_175616_cb2fbe40\output\final.mp4`
- QA：通过，无 errors / warnings
- 分辨率：1920x1080
- FPS：30
- 时长：66.133333 秒（旁白 manifest 66.138458 秒，差 0.005125 秒）
- 视频编码：H264
- 音频编码：AAC
- 文件大小：2,374,727 bytes（最终 Remotion 版本）
- 完整解码：通过
- composition：3 scenes、24 subtitles、1984 frames
- 抽帧检查：中文文字、背景和字幕均正常显示，无首屏黑帧。

## 当前限制

- MockTTS 仍是测试 tone，demo 不代表正式中文配音质量。
- alpha.4 只有稳定模板和 placeholder，不包含 AI 图片、AI 视频或高级动效。
- Video QA 是工程检查，不执行内容事实核查、审美打分、封面 CTR 预测或逐帧黑场扫描。
- Remotion 在新机器第一次运行时需要下载 Headless Shell。
- 当前不自动投稿、不登录 B 站、不自动回复评论。

## 第五阶段建议

进入“素材生成 + 封面系统 + 发布前 QA”，保持人工审核门：

1. 建立素材需求与版权/来源 manifest，优先使用本地图片、授权素材、网页截图和程序化图表。
2. 加入封面 schema、确定性模板与多候选导出，不自动发布。
3. 扩展发布前 QA：来源完整性、画面重复、逐帧黑场/冻结帧、字幕安全区、封面尺寸与 metadata 完整性。
4. AI 图片生成作为可选 provider 串行接入；继续延后 ComfyUI 常驻、AI 长视频生成与平台登录。
