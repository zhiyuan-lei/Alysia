# Alysia v0.1-alpha.9 开发报告

生成日期：2026-08-07（Asia/Shanghai）

## 结果

alpha.9 已将 Alysia 从单条内容的创作/发布/反馈闭环，扩展为按频道隔离、证据可追溯的长期运营基础层：

```text
Observe
  → Channel Memory
  → Multi-video Analysis
Analyze
  → Trend / Fatigue / Topic Lifecycle
  → Audience Model（仅聚合内容信号）
Experiment
  → Draft
  → Human Approval
  → Control / Treatment Assignment
  → Metric Evaluation
Create
  → Existing Content Plan + Human Approval Gate
Publish
  → Existing alpha.8 PublishJob + ApprovalRecord
Learn
  → Feedback + Analytics + Memory
  → Strategy Evidence Chain
```

系统仍不会自动修改自身代码、自动评论、绕过审核运营或执行真实账号大规模操作。

## Alpha.8 稳定性确认

开发前已按要求读取并审计：

- `development_report_alpha8.md` 与 `README.md`。
- `alysia/publishing`、`alysia/feedback`、`alysia/analytics`、`alysia/learning`、`alysia/planning`。
- 对应 schema、provider、CLI 和测试。

基线验证结果：`78 passed in 38.9s`。现有发布、反馈、Analytics、Memory 与 Creator Loop 人工门均通过，未发现需要先行修复的闭环回归。

工作树在 alpha.9 开始前已包含 alpha.3-alpha.8 的未提交成果；本轮将其视为用户现有改动并保留，没有重置、清理或重建仓库。

## 新增能力

### 1. Channel Memory 与多频道隔离

- 使用 `channel_id` 隔离频道定位、内容方向、发布主题、受众假设、成功/失败案例、长期策略和实验状态。
- 旧 run 没有 `channel_id` 时只归入 `operations.default_channel_id`。
- 新 Content Plan 与 run provenance 显式写入 `channel_id`。
- 默认频道沿用 `plans/creator_loop_state.json`；其他频道使用独立的 `creator_loop_state.<channel_id>.json`。
- 多频道支持是状态与决策空间隔离，不包含账号登录、凭证管理或批量投稿。

### 2. Multi-video Performance Analysis

跨视频输出以下结构化证据：

- 每项指标的样本数、均值、最小值、最大值。
- 最佳/最弱 run 和全部可比 run。
- 前半窗口与后半窗口的相对变化。
- `improving | declining | stable | insufficient` 趋势状态。
- 最近三条可比内容的 `possible | not_observed | insufficient` 疲劳信号。
- 按内容类别生成 `exploring | growing | stable | declining | insufficient` 生命周期。

少于 4 个有效样本时不判断总体趋势；缺失 CTR、完播率等字段保持缺失，不用 views 或其他指标替代。

### 3. Experiment Manager

新增可审计实验生命周期：

```text
draft → approved → running → completed
```

每个实验记录：

- `hypothesis`
- `variable_changed`
- `control_variables`
- control/treatment `experiment_group`
- `success_metrics`
- `result`
- `conclusion`

硬约束：

- 自动化身份不能批准实验，必须记录明确的人类审核者。
- 未批准实验不能分配 run。
- 同一 run 重复分配幂等，不能切换实验组。
- 每组达到配置的最小样本数后才可评估。
- 分配 source 必须与实际 Analytics source 一致。
- run 必须属于实验 channel。
- 评估结果不会自动改动创作配置。

### 4. Strategy Evolution

现有 `StrategyMemory` 向后兼容地扩展为：

```text
status: tentative | supported | deprecated
strategy
  → evidence_experiment_ids
  → evidence_metrics
  → confidence
```

规则：

- 一个合格正向实验仍保持 `tentative`。
- 至少两个非 mock/testing 的一致正向实验且 confidence 达标后才可 `supported`。
- 至少两个合格负向实验且 confidence 降至门槛后才可 `deprecated`。
- mock/testing 实验可以验证管线，但永久排除在正式策略证据链之外。
- Strategy ID 加入 `channel_id`，避免新策略跨频道碰撞。

### 5. Audience Model v1

只保存内容层聚合信号：

- 主题偏好信号。
- 标题风格等内容偏好信号。
- CommentInsight 中的常见问题与内容请求。
- CTR、完播率、平均观看比例等观看行为摘要。

不读取或保存观众身份、人脸、单人行为轨迹或个人画像。所有偏好附证据 run、置信度和相关性边界。

### 6. Long-term Creator Dashboard

Dashboard JSON 包含：

- 当前 Channel Memory。
- 最近跨视频表现。
- Audience Model。
- 当前 draft/approved/running 实验。
- tentative/deprecated 策略证据链。
- 下一步建议。

当 Analytics、实验和策略输入未变化时，重复 refresh 直接复用原 Dashboard，文件内容与 SHA-256 保持不变。

### 7. Creator Loop 升级

`CreatorLoopState` 新增：

- `channel_id`
- `cycle_phase`
- `operations_digest`

阶段记录为：

```text
observe → analyze → experiment → create → publish → learn
```

已人工批准或运行中的 Managed Experiment 会转成下一期候选的实验约束，但不会自动分组、制作或投稿。计划、内容 run 和 PublishJob 原有 Human Approval Gate 保持不变。

## CLI

新增：

```powershell
python -m alysia operations refresh --channel main
python -m alysia operations dashboard --channel main

python -m alysia experiment create `
  "缩短开场是否提升前30秒留存" `
  --variable hook_length_sec `
  --metric completion_rate `
  --controls topic,title_style

python -m alysia experiment approve EXPERIMENT_ID --approved-by HUMAN
python -m alysia experiment assign EXPERIMENT_ID RUN_ID --group control --source manual
python -m alysia experiment evaluate EXPERIMENT_ID

python -m alysia creator-loop tick --channel main
python -m alysia creator-loop status --channel main
```

## 主要修改文件

- Schema：`alysia/schemas/operations.py`、`alysia/schemas/learning.py`、`alysia/schemas/planning.py`
- 长期运营层：`alysia/operations/store.py`、`analyzer.py`、`experiments.py`、`service.py`
- Creator Loop：`alysia/planning/loop.py`、`alysia/planning/store.py`
- 证据/策略：`alysia/learning/memory.py`、`alysia/learning/strategy.py`、`alysia/learning/pipeline.py`
- 发布反馈阶段同步：`alysia/publishing/service.py`、`alysia/feedback/mapper.py`
- CLI/配置：`alysia/cli.py`、`alysia/core/config.py`、`config.example.yaml`
- 测试：`tests/test_operations.py`
- 文档/版本：`README.md`、`pyproject.toml`、`alysia/__init__.py`

## 离线测试

alpha.9 新增 5 个组合测试场景，覆盖：

1. Multi-video 趋势、疲劳和主题生命周期。
2. Channel Memory、多频道隔离与 Dashboard refresh 幂等。
3. Experiment 人工审批、分配幂等、source 校验和完整生命周期。
4. 两次真实实验升级 Strategy、mock 实验不进入证据链。
5. Dashboard 生成、Managed Experiment 进入计划、Creator Loop 与多频道状态幂等。

最终全量结果：`83 passed in 27.8s`。

## 实际离线 Demo

在 alpha.8 的既有 mock 发布反馈 run 上执行：

```powershell
python -m alysia operations refresh --channel main
```

结果：

- channel：`main`
- sample size：1
- non-testing sample size：0
- topic：`为什么AI Agent还不是AGI？`
- source：`mock`
- CTR、完播率、平均观看比例：缺失
- 趋势：全部 `insufficient`
- 内容疲劳：`insufficient`
- 正式成功/失败案例：空
- 待验证策略：2 条，均为 `tentative`、confidence `0.2`
- 下一步建议：继续收集至少 4 条非测试内容数据，不升级策略

这说明系统没有把 alpha.8 mock 反馈误判为真实频道规律。

重复 refresh 前后：

```text
dashboard SHA-256:
237AF121892897167570F1E41B7BA7D13752E35910C07A14F78A121E1205E2DB
idempotent: true
```

运营产物位于：

```text
memory/channels/main/
├── channel_memory.json
├── multi_video_analysis.json
├── audience_model.json
└── dashboard.json
```

## 最终自检

- `python -m compileall -q alysia`：通过。
- `uv run pytest -q`：`83 passed`。
- `python -m alysia operations --help`：通过。
- `python -m alysia experiment --help`：通过。
- `python -m alysia creator-loop --help`：通过。
- 实际 Dashboard refresh：通过。
- 重复 Dashboard refresh 文件哈希不变：通过。
- `runs/`、`workspace/`、`memory/` 凭证关键字扫描：0 个文件命中。
- `git diff --check`：通过，仅有 Windows autocrlf 提示，无 whitespace error。

## 当前限制

- 当前真实样本不足，Demo 只能正确输出 `insufficient`，尚不能验证真实趋势阈值效果。
- 跨视频比较使用透明启发式规则，不做因果推断或统计显著性声明。
- 当前实验是两组均值比较基础版，不处理季节性、推荐流量变化或复杂协变量。
- Audience Model 只使用结构化指标与轻量 CommentInsight，不调用隐式画像模型。
- Strategy Evolution 不自动应用 rule；`supported` 也仍需人工决定是否进入频道长期策略。
- 多频道只隔离本地状态，不管理真实平台账号、授权或凭证。

## 下一阶段建议

建议 alpha.10 聚焦 **Operational Data Quality + Controlled Experiment Readiness**，而不是立即开启全自动优化：

1. 为真实 Analytics 增加采集窗口、口径版本、曝光来源和数据成熟度标记。
2. 在实验开始前生成 pre-registration 快照，冻结变量、样本目标和停止条件。
3. 增加跨频道只读汇总视图，但继续禁止共享策略证据和自动跨账号操作。
4. 为实验分组与发布排期增加人工 review 页面或更清晰的本地报告。
5. 在积累足够真实样本后，再评估置信区间、异常流量剔除和主题季节性；未达到数据质量门槛前不启用自动策略优化。
