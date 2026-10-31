# Alysia v0.1-alpha.5 开发报告

生成日期：2026-08-07（Asia/Shanghai）

## 结果

仓库路径：`D:\Alysia`

本阶段已完成：

```text
video_ready
  → 可追溯标题候选 / 简介 / 标签
  → 1280x720 确定性模板封面
  → ffprobe 投稿元数据
  → publish package
  → Pre-Publish QA
  → milestone: review_ready
  → Human Review
```

`review_ready` 只表示投稿前工程检查通过，不会设置 `published`，也不会登录或调用 B 站接口。

## alpha.4 前置状态

- 开始前全量基线：`30 passed in 6.46s`。
- demo run：`20260807_175616_cb2fbe40`，`pipeline_phase=video_ready`。
- `final.mp4`：1920x1080、30 FPS、H264/AAC、66.133333 秒，可完整解码。
- `qa/video_qa_report.json`：通过，无 errors / warnings。
- alpha.3/alpha.4 的未提交工作区改动均被保留，没有重建项目或回退已有流水线。

## 新增能力

- `PublishPackage`、`PublishQAReport`、`TitleCandidate` 与 `TitleResult` schema。
- Title Agent 输出科普型、问题型、冲突型、数字型和悬念型候选，并标注生成理由和风险。
- 数字型标题的数字来自现有脚本章节数；风险规则禁止虚假承诺、绝对化结论和无依据数字。
- Description Agent 生成不超过 100 字的开头、核心内容、按成片时长换算的章节时间轴、参考资料与免责声明。
- 参考链接只来自已有 Research；`.invalid`、`.test` 和 localhost 地址不会进入可发布链接。
- Tag Agent 从主题和脚本派生核心/长尾/分类标签，执行大小写无关去重和营销词过滤。
- `BaseCoverGenerator`、`MockCoverGenerator` 与 `TemplateCoverGenerator`；默认生成 16:9、1280x720 PNG 文字封面。
- 模板封面支持背景图、主标题、副标题、Logo 区域和主题元素，并按字体像素自动缩放与换行。
- Publish Package Worker 使用 ffprobe 自动读取视频时长、分辨率、FPS 和编码信息。
- `publish/metadata.json` 保存候选标题、视频信息、输入 artifact、来源 id 和关键输入 SHA-256。
- Pre-Publish QA 检查视频及 alpha.4 QA、时长、标题、简介来源字段、标签和封面可读性/尺寸。
- 状态机新增 `packaging`、`publish_qa`、`ready_for_review`，pipeline phase 新增 `package_ready` 与 `review_ready`。
- `resume` 可从 `video_ready` 推进到 `package_ready`，再从 `package_ready` 推进到 `review_ready`。
- 新增 CLI：`package RUN_ID --generator mock|template` 与 `publish-check RUN_ID`。

## 主要修改文件

- 配置/状态/编排：`alysia/core/config.py`、`state.py`、`run.py`、`orchestrator.py`
- Agent：`alysia/agents/title.py`、`description.py`、`tags.py`、`__init__.py`
- Cover provider：`alysia/providers/cover/*`
- Schema：`alysia/schemas/publish.py`、`alysia/schemas/__init__.py`
- Worker：`alysia/workers/publish_package.py`、`publish_qa.py`、`__init__.py`
- CLI：`alysia/cli.py`
- 配置/包：`config.example.yaml`、`pyproject.toml`、`uv.lock`
- 测试：`tests/test_publish_pipeline.py`、`tests/test_state.py`、`tests/test_video_pipeline.py`
- 文档：`README.md`、`development_report_alpha5.md`

## 测试

- alpha.4 基线：`30 passed in 6.46s`
- alpha.5 最终全量测试：`38 passed in 11.86s`
- 新增 8 项离线覆盖：publish schema、标题候选、简介、标签、模板封面、投稿包生成、发布前 QA、resume 包装阶段。
- 测试不依赖网络、B 站、API key 或外部账号。

## Demo 验收

- run_id：`20260807_175616_cb2fbe40`
- 命令：`python -m alysia package 20260807_175616_cb2fbe40 --generator template`
- 命令：`python -m alysia publish-check 20260807_175616_cb2fbe40`
- 投稿包：`D:\Alysia\runs\20260807_175616_cb2fbe40\publish\publish_package.json`
- 封面：`D:\Alysia\runs\20260807_175616_cb2fbe40\publish\cover.png`
- 发布前 QA：通过，0 errors，2 warnings。
- warnings：demo 成片 66.133333 秒，短于 120 秒配置目标；Mock Research 没有可发布来源链接，人工审核时必须补充。
- 最终状态：`pipeline_phase=review_ready`、`milestone=review_ready`、`review_ready=true`。

## 当前限制

- demo 仍使用 MockTTS tone，不代表正式中文配音质量。
- Mock Research 的 `.invalid` 链接不会进入投稿包；正式投稿前必须接入真实 Research 并人工核验来源。
- 标题、简介、标签与封面为确定性第一版，未执行平台 CTR 预测或审美评分。
- 发布前 QA 是工程和规则检查，不替代事实核查、版权检查、平台合规审核或人工观看成片。
- 不自动登录、不自动投稿、不自动回复或运营评论。
- 不包含 AI 图片生成、ComfyUI、AI 视频生成或大型 Agent 框架。

## 第六阶段建议

进入“数据反馈 + Analytics + 自主选题”之前，继续保留人工审核门：

1. 定义平台无关的 `ContentPerformance` schema，先支持人工导入播放、曝光、CTR、完播率、互动和关注转化数据。
2. 建立 `AudienceFeedback` 与评论聚类，只做离线分析和敏感信息清洗，不自动回复。
3. 建立 `ContentExperiment`，把标题、封面、Hook、时长等策略假设与结果关联，避免只按播放量单指标优化。
4. 增加 Topic Scout，基于账号定位、历史表现、来源质量和重复度生成候选选题，由人确认后进入现有 Topic → Video 流程。
5. 在数据量和评测标准稳定后，再讨论 B 站只读 Analytics 接入；自动投稿继续延后。
