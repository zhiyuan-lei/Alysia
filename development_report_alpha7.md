# Alysia v0.1-alpha.7 开发报告

生成日期：2026-08-07（Asia/Shanghai）

## 结果

仓库路径：`D:\Alysia`

本阶段已完成默认需要人工批准的自主选题与排期闭环：

```text
Creator Profile + Trend Snapshot + Historical Runs + Memory/Strategy
  → 10 Topic Candidates
  → Explicit Weighted Scoring + Duplicate/Risk Rules
  → Scout / Editor / Critic Editorial Decision
  → 7-day Content Plan
  → Planning QA
  → WAITING_FOR_APPROVAL
  → explicit plan approve
  → traceable CREATED run
```

系统不会自动登录 B 站、投稿、评论、私信、修改账号、修改自身源码或在没有人工批准时启动真实创作任务。

## Alpha.6 前置状态

- alpha.7 开始前全量基线：`55 passed in 19.23s`。
- `python -m alysia doctor` 可运行；Python、Git、Node、npm、FFmpeg、FFprobe、RTX 4060 Ti 与 Windows SAPI 可用。
- 历史样本 `20260807_175616_cb2fbe40` 已达到 `strategy_ready`，`pipeline_phase=learning_ready`。
- 该样本包含 testing 来源的 episode、tentative lessons、strategies 与 Next Experiment；alpha.7 保留其测试边界。
- alpha.3-alpha.6 的既有未提交成果全部保留；本轮未回退或重构前序流水线。

## 新增能力

- `config/creator_profile.yaml` 显式记录频道目标、主/排除领域、受众、语言、格式、时长、频率、风险、原创与来源要求。
- `BaseTrendProvider`、`MockTrendProvider`、`ManualTrendProvider` 与 `WebTrendProvider`。
- 手工 JSON/CSV 趋势导入、模板、缺失热度 `null`、来源追溯与主题/URL 去重。
- 结合趋势、历史 runs、lessons/strategies 和 Next Experiment 的确定性 Topic Candidate 生成。
- 明确权重的 Topic Scoring Engine，保存全部正向维度与重复/风险惩罚 breakdown。
- 标题规范化与中文二元组 Jaccard 轻量重复检测；接口可在后续替换为本地 embedding。
- 单进程 Scout/Editor/Critic Editorial Board，带类别分散，未引入多 Agent runtime。
- `ContentPlan`、7 天排期、JSON/Markdown 产物和状态持久化。
- Planning QA 检查 Creator Profile、历史重复、趋势来源、mock 隔离、excluded domain、标题党与策略关联。
- 可恢复 Creator Loop 状态和计划窗口幂等 tick；默认配置 `enabled=false`、`require_human_approval=true`。
- `plan approve/reject` 人工闸门；批准后只创建 `CREATED` run，不自动制作或发布。
- `creator-loop run` 只有在用户显式调用且 slot 已批准时，才推进现有文本创作阶段。
- 新 run 的 `input.json` 与 `run_state.json` 保存 plan、slot、趋势来源、实验/策略关联、testing 与 Research handoff。

## 主要修改文件

- Schema：`alysia/schemas/planning.py`、`alysia/schemas/__init__.py`
- 配置/状态：`alysia/core/config.py`、`alysia/core/run.py`、`alysia/core/orchestrator.py`
- Trend Provider：`alysia/providers/trends/*`
- Planning：`alysia/planning/*`
- CLI：`alysia/cli.py`
- Creator Profile：`config/creator_profile.yaml`
- 配置示例：`config.example.yaml`
- 测试：`tests/test_planning.py`
- 文档：`README.md`、`development_report_alpha7.md`
- 版本：`pyproject.toml`、`alysia/__init__.py`

## 测试

- alpha.7 专项覆盖 15 项，包括用户要求的 13 项：profile、trend schema、manual import、mock candidate generation、scoring、duplicate penalty、excluded domain、editorial decision、content plan、Planning QA、mock isolation、approval gate、traceable run、tick idempotency，以及未审批 run 拒绝。
- 最终全量测试结果在终检后记录于下方“最终自检”。
- 测试全程离线，不需要 B 站账号、网络、API key 或 Ollama。

## 离线 Demo

- plan_id：`plan_20260807_201716_ad8023ca`
- provider：`MockTrendProvider`
- source：`mock`
- testing：`true`
- 候选数量：10
- 排期数量：3
- horizon：7 天

Top 3：

| Slot | Topic | Total | Relevance | Freshness | Novelty | Evidence | Experiment | Duplicate penalty | Risk penalty |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| slot_01 | 8GB 显存如何串行调度多个 AI 工具 | 77.76 | 0.90 | 1.00 | 1.00 | 0.54 | 0.45 | 0.00 | 0.18 |
| slot_02 | AI Agent 为什么仍会在长任务中失控 | 77.76 | 0.90 | 1.00 | 1.00 | 0.54 | 0.45 | 0.00 | 0.18 |
| slot_03 | 从脚本到成片：AI 视频流水线的可测试设计 | 77.76 | 0.90 | 1.00 | 1.00 | 0.54 | 0.45 | 0.00 | 0.18 |

Mock 输入故意不提供虚构热度，所以三个同等质量来源在显式权重下同分；Editorial Board 用确定性排序和类别分散选出人工智能、自主智能体、软件工程三个槽位。

Planning QA：`passed=true`，7/7 checks 通过，errors 为空；警告明确指出 mock/testing 计划不代表真实平台趋势，Trend 只解释选题时机，脚本事实必须重新 Research。

人工批准：

- approved slot：`slot_01`
- 新 run_id：`20260807_201750_f211ca71`
- run 当前阶段：`created`
- planning source：`mock`
- testing：`true`
- Research handoff：已写入 input 与 run state

批准后第二次 `creator-loop tick` 返回同一 `plan_20260807_201716_ad8023ca`，没有重复创建计划。

## Trend Provider 状态

- MockTrendProvider：可用，用于离线测试；强制 testing 隔离。
- ManualTrendProvider：可用，支持 JSON/CSV、去重与 freshness 过滤。
- WebTrendProvider：已实现显式公共 JSON feed 适配，不登录平台；当前未配置 `web_sources`，因此未执行非阻塞联网 smoke test。
- 任何 provider 都不会猜测缺失热度数字，也不会把单一来源描述成“全网趋势”。

## 当前限制

- WebTrend 只支持显式 JSON feed，不包含 B 站登录、站内账号数据或通用网页抽取器。
- 轻量重复检测使用规范化文本与关键词/中文二元组 Jaccard，尚未接入本地 embedding。
- Mock 趋势质量刻意统一，因此 demo 同类候选可能同分；真实来源可通过 freshness、confidence 与 evidence 拉开分数。
- 评分权重与阈值是可审计的 alpha.7 启发式，不代表平台官方推荐模型。
- 当前排期按类别分散和固定日期间隔，不处理节假日、具体发布时间或平台流量窗口。
- `creator-loop run` 只在显式调用后推进已批准 run 的文本阶段；后续音频、渲染、发布包仍沿用现有分阶段命令。
- 本阶段不自动投稿、评论、私信、修改账号资料或访问 B 站账号。

## 最终自检

- `python -m compileall -q alysia`：通过。
- `pytest`：`70 passed in 19.27s`。
- `python -m alysia doctor`：命令通过；10 项可用，5 项可选能力缺失/未就绪。
- `creator-loop tick`（mock）：返回 `plan_20260807_201716_ad8023ca`，`testing=true`。
- `plan show`：显示 3 个槽位，`slot_01` 已 approved 并关联 run。
- `plan approve plan_20260807_201716_ad8023ca slot_01`：幂等返回已有 `20260807_201750_f211ca71`，未重复创建 run。
- provenance 校验：plan_id、slot_id、testing、1 个趋势来源和 Research handoff 均存在。
- 再次 `creator-loop tick`：仍返回同一 plan_id，未重复造计划。
- `creator-loop --help`：tick/plan/run/status 分组命令均可见。
- `git diff --check`：通过。
- `git status --short`：已执行；仓库仍包含 alpha.3-alpha.6 的既有未提交成果和本轮 alpha.7 改动，未覆盖或清理用户工作。

## 下一阶段建议

alpha.8 可进入 Bilibili 官方接口适配 + Human-approved Publishing + Comment/Feedback Ingestion，但默认继续保留人工批准：

1. 先实现官方 OAuth/授权和只读能力检测，不模拟登录、不保存明文凭据。
2. 发布动作必须同时满足 approved slot、review_ready 与显式二次确认。
3. 投稿回执、稿件 ID 和失败原因写入可恢复状态，不因重试重复投稿。
4. 评论与反馈先只读导入，并继续区分事实、推断、骚扰内容与隐私数据。
