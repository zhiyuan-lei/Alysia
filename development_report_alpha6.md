# Alysia v0.1-alpha.6 开发报告

生成日期：2026-08-07（Asia/Shanghai）

## 结果

仓库路径：`D:\Alysia`

本阶段已完成离线学习闭环：

```text
review_ready
  → analytics_imported
  → analyzed
  → memory_updated
  → strategy_ready
```

它不会登录 B 站、拉取账号数据、投稿、评论、修改账号资料、修改自身源码或自动启动下一条创作任务。

## 前阶段状态

- alpha6 开始前全量基线：`43 passed in 13.37s`。
- `python -m alysia doctor` 可运行；Python、Git、Node、npm、FFmpeg、FFprobe、RTX 4060 Ti 与 Windows SAPI 可用。
- 未发现独立的 alpha5.1 / recovery 开发报告；当前 demo artifact 使用 SAPI 音频，`audio_qa_report.json`、视频 QA 与发布前 QA 均存在。
- demo run：`20260807_175616_cb2fbe40`，开始时为 `pipeline_phase=review_ready`。
- alpha3-alpha5 的既有未提交改动全部保留；本轮没有回退或重建前序流水线。

## 新增能力

- `VideoMetrics` 与 `RetentionPoint` 支持部分字段为空，比例统一使用 `0..1`。
- `DerivedMetrics` 为每个指标保存 `value`、`formula`、`inputs` 与 `missing_inputs`；缺失输入或无效分母时返回 `null`。
- `BaseAnalyticsProvider`、`ManualAnalyticsProvider`、`MockAnalyticsProvider` 与只保留 contract 的 `BilibiliAnalyticsProvider`。
- 手工 JSON/CSV 导入，以及不会填造数据的 `metrics_template.json`。
- 从现有 Script、Storyboard、Subtitle、Audio、Video QA 和 Publish artifacts 确定性提取 `ContentFingerprint`，不调用 LLM。
- Performance Analyzer 明确输出事实、强项、弱项、异常、低置信度假设、证据与缺失数据。
- 可审计 JSON Memory：`episodes/`、`lessons/`、`strategies/` 与 `index.json`。
- 单 run lesson 默认为 `tentative`；至少两个独立真实 run 支持且达到置信度阈值后才升级 `supported`。
- `LessonCandidate.direction=contradicts` 可让相反证据降低置信度；多个相反证据可将 lesson 标为 `rejected`。
- Mock/testing 数据永久标记为测试来源，置信度上限 0.2，不能升级为正式 `supported` lesson。
- Strategy Recommendation 包含 objective、change、rationale、evidence、confidence、risk 与可验证 test plan。
- Next Experiment 只基于历史 artifact/lesson/strategy 生成实验方向，不联网找热点，不自动 create。
- Learning QA 阻止缺失数据变成事实、单视频高置信度规律、mock 晋升及无证据推荐。
- `learn` 对已完成 run 幂等；重复运行不会重复添加证据或提高置信度。

## 主要修改文件

- Schema：`alysia/schemas/analytics.py`、`learning.py`、`__init__.py`
- Analytics：`alysia/analytics/derived.py`、`fingerprint.py`、`analyzer.py`
- Provider：`alysia/providers/analytics/base.py`、`manual.py`、`mock.py`、`bilibili.py`
- Learning：`alysia/learning/memory.py`、`lessons.py`、`strategy.py`、`planner.py`、`qa.py`、`pipeline.py`
- 状态/配置：`alysia/core/state.py`、`run.py`、`config.py`
- CLI：`alysia/cli.py`
- 测试：`tests/test_analytics_learning.py`、`tests/test_state.py`
- 配置/文档：`config.example.yaml`、`pyproject.toml`、`README.md`
- Mock 指标：`evaluation/mock_metrics_alpha6.json`

## 测试

- alpha6 最终全量测试：`55 passed in 18.94s`。
- 新增 12 项离线覆盖：metrics schema、derived metrics、content fingerprint、manual JSON/CSV import、analysis、lesson extraction、memory persistence、confidence/counter-evidence update、strategy、next experiment、learning idempotency、mock isolation。
- 测试无网络、无 B 站账号、无 API key、不依赖 Ollama。
- `python -m compileall -q alysia` 通过。
- `git diff --check` 通过。

## Demo 验收

- run_id：`20260807_175616_cb2fbe40`
- 模板：`runs/20260807_175616_cb2fbe40/analytics/metrics_template.json`
- Mock 输入：`evaluation/mock_metrics_alpha6.json`
- Metrics 摘要：10,000 impressions、420 views、CTR 4.2%、平均观看比例 38%、完播率 31%。
- 派生指标：互动率 13.8095%、点赞率 6.6667%、收藏率 4.5238%、评论率 1.6667%、分享率 0.9524%、关注转化率 0.7143%、标准化观看分 34.5%。
- Content Fingerprint：82.23 秒、3 scenes、约 9.3 秒 hook、叙事速度约 4.09 字/秒。
- Lesson：2 条，均为 `tentative`、`source=testing`、`confidence=0.2`。
- Strategy：2 条，分别针对 30 秒留存与完播率，均为 `confidence=low`，并要求未来连续 3 条视频做受控比较。
- Next Experiment：`AI Agent 失败时，暴露了哪些 AGI 差距？`
- Learning QA：通过，4/4 检查为 true；警告 mock 数据仅可形成测试记忆、独立 run 样本不足。
- 第二次 `learn`：Memory 目录 7 个文件的 SHA-256 全部不变，`idempotent=True`。

## Memory 路径

```text
D:\Alysia\memory\episodes
D:\Alysia\memory\lessons
D:\Alysia\memory\strategies
D:\Alysia\memory\index.json
```

本轮 demo 写入的是明确标记 `testing` 的长期记忆，不会与正式经验混淆。

## 已知限制

- 不自动访问 B 站 Analytics；`BilibiliAnalyticsProvider` 仅有接口契约。
- 阈值与 normalized watch score 是 alpha6 的可审计启发式，不是平台官方评分。
- 单条 demo 的所有假设置信度均为 low，不能据此证明因果关系。
- 目前只支持单条视频指标导入，不处理账号级时间序列、分区基线或统计显著性。
- Retention 使用离散点，不执行曲线插值、变化点检测或受众分群。
- `rejected` 机制已支持相反证据降级，但自动反证提取仍采用保守的确定性规则。
- 不自动修改全局配置、Prompt、源码或现有创作流水线。

## 下一阶段建议

建议 alpha7 再进入真正的自主选题 + Trend Research + Scheduled Creator Loop，但仍保留人工审核门：

1. 建立账号定位、内容支柱与受众假设的显式配置。
2. 接入可追溯的 Trend Research / RSS / 搜索来源，并保存热点快照。
3. 用历史 topic 去重、来源质量和 lesson/strategy 生成候选选题。
4. 先只做 scheduled proposal，不自动投稿；由人确认候选后再进入现有 Topic → Video 流程。
5. 累积足够真实 run 后再做分区基线、时间窗口和实验对照，避免用 mock 阈值驱动账号决策。
