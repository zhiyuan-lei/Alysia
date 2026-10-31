# Alysia v0.1-alpha.13 开发报告

生成日期：2026-08-08（Asia/Shanghai）

## 结果

仓库路径：`D:\Alysia`。

alpha13 已在不重写 alpha1-alpha12 内容流水线的前提下，加入 `AutonomousSupervisor + Goal Management + Long-horizon Planning`：

```text
AutonomousSupervisor
  → CreatorLoop
  → StudioDirector
  → Agents / Workers / Providers
```

Supervisor 只管理跨 run 的 Goal、Plan、Project、依赖、优先级、预算、review 和 replan；单个 run 仍由 StudioDirector 管理。发布、身份重大变化、预算超限和重大 replan 的 Human Approval Gate 均保留。

## Alpha12 状态确认

开发前读取了 alpha12 报告、README、Studio Director/Handoff/Context/Trace、Creator Loop、Channel Memory、Experiments、Production Optimizer、Publishing/Feedback 与相关 tests。

实时基线验证：`129 passed in 50.52s`。Multi-Agent Creator Studio 的串行路由、Artifact Ownership、ProductionPlan、Publish Approval 和定点恢复在 alpha13 开发前均稳定。工作树中 alpha1-alpha12 的未提交成果全部保留，没有 reset、clean、checkout 或重建仓库。

## 新增能力

### Goal / Objective

- Goal 类型：`channel_growth|content_series|learning|quality|experiment|operations`。
- 状态：`draft|active|paused|completed|cancelled|blocked`。
- 每个 Goal 包含日期范围、SuccessMetric、约束、BudgetPolicy、ApprovalPolicy、停止条件和父子引用。
- `GoalDecomposer` 生成有 owner、指标和依赖的 Objective；`max_depth` 与 `max_children` 强制限制展开。
- CLI `supervisor goal-status` 可显式暂停、恢复、完成、取消或阻塞 Goal。

### LongHorizonPlan / ContentProject

- LongHorizonPlan 包含 milestones、projects、dependency edges、review points、resource budget、risk register、status 和 version。
- ContentProject 管理系列 planned runs、experiment refs、deadline、依赖和进度。
- 轻量 DependencyGraph 支持循环检测与可解释 blockers，不使用图数据库。

### Priority / Budget / Governance

- PriorityEngine 使用显式权重计算 goal priority、deadline urgency、dependency readiness、expected value、experiment importance、resource cost 和 risk。
- `PriorityDecision` 保存 score breakdown、alternatives 和 rationale；依赖未就绪的候选不能入选。
- GovernancePolicy 检查日/周 run、日/周 cloud cost、失败次数和 active project 数量。
- 成本 unknown 不按 0 处理；达到硬限制时进入 pause/waiting approval，不会自动突破。

### Review / Replan / QA

- Review point 支持完成 run 数、天数、实验完成和预算比例。
- SupervisorReview 输出 progress、metrics、deviations、risks、decisions_needed 和 continue/pause/replan 建议。
- ReplanProposal 保存 `source version → proposed version`，默认 pending/approval_required；原 plan 不被覆盖。
- Supervisor QA 检查目标可测量性、停止条件、目标冲突、循环依赖、预算、审批越界和无限扩张。

### Cross-run Context / Trace

- CrossRunContextSelector 只读取频道定位、supported lessons/strategies、active experiments、identity 摘要和 production health。
- 不向下游传递完整历史、大文件正文或凭证。
- `supervisor_trace.jsonl` 记录 Goal 选择、优先级、blocker、dispatch、预算暂停、review 和 replan；敏感键脱敏。

## Supervisor State Machine 与 Tick

实现状态：

```text
IDLE
→ EVALUATE_GOALS
→ SELECT_PRIORITY
→ CHECK_DEPENDENCIES
→ PLAN_ACTION
→ DISPATCH
→ MONITOR
→ REVIEW
→ WAITING_APPROVAL / PAUSED / IDLE
```

- 单次 `tick`，无后台 daemon。
- `max_actions_per_tick=3`。
- `max_dispatches_per_tick=1`。
- 输入状态未变化时 tick 幂等，不重复派发。
- 真实派发器唯一调用链为 `Supervisor → CreatorLoop.create_supervised_run() → StudioDirector.run()`。
- `create_supervised_run()` 缺少人工 `approved_by` 时拒绝创建 run。
- Supervisor 不直接调用 Researcher、Writer、Voice、Editor、Publisher 或底层 Worker。

## CLI

新增并验证：

```powershell
python -m alysia supervisor tick
python -m alysia supervisor status
python -m alysia supervisor goals
python -m alysia supervisor plan GOAL_ID
python -m alysia supervisor review GOAL_ID
python -m alysia supervisor blockers [GOAL_ID]
python -m alysia supervisor qa
python -m alysia supervisor goal-status GOAL_ID paused
python -m alysia supervisor approve-run PLANNED_RUN_ID --approved-by HUMAN
python -m alysia supervisor replan GOAL_ID --reason REASON
python -m alysia supervisor demo
```

## 离线长期规划 Demo

- goal_id：`demo_goal`
- plan_id：`demo_plan_v1`
- project_id：`demo_project_ai_agent`
- experiment_id：`demo_experiment_hook_8s`
- horizon：30 天
- milestones：4
- planned runs：`demo_run_ep1` 至 `demo_run_ep4`
- review points：4

Milestones：

1. 建立候选选题池。
2. 完成系列内容。
3. 运行核心实验。
4. 完成周期复盘。

Demo 初始状态将 EP1 标记为 mock completed。第一次 Supervisor tick 透明选择 EP2，派发次数为 1；OfflineSupervisorDispatcher 将 EP2 模拟为 blocked，未联网、未发布。

Blocker 结果：

- EP2：mock blocker。
- EP3：依赖 EP2 completed，当前 EP2 blocked。
- EP4：依赖 EP3 completed，且缺少人工内容批准。

Budget pause：模拟 `runs_today=2/2`、`runs_this_week=7/7` 后，状态进入 `waiting_approval`；未发生额外派发。

Review：进度 0.25，发现 blocked planned run，建议 `replan`，要求人工决定。

Replan：从 plan version 1 提出 version 2，状态 `pending`、`approval_required=true`；version 1 仍是当前已保存计划。

Supervisor QA：PASS，七项检查全部通过。

## 测试

新增 `tests/test_supervisor.py`，21 个完全离线测试，覆盖：

- goal schema、decomposition、max depth/children；
- long-horizon plan、project schema、dependency cycle；
- blocked item、priority breakdown；
- budget/failure pause；
- review point、replan versioning；
- tick action limit、dispatcher、approval gate；
- cross-run context、trace、tick idempotency、Supervisor QA；
- Goal lifecycle、人工 planned-run approval、CreatorLoop Supervisor bridge。

最终全量：`150 passed in 56.41s`。`compileall` 和 `git diff --check` 通过。

## Doctor

`python -m alysia doctor`：11 项可用，4 项缺失或未就绪。

可用：Python 3.11.14、pip、uv、Git、Node.js、npm、FFmpeg、FFprobe、Ollama、RTX 4060 Ti 8GB、Windows SAPI TTS。

未就绪：`qwen3.5:4b` Ollama 模型、CUDA Toolkit (`nvcc`)、CosyVoice Python、faster-whisper。它们不影响 alpha13 的完全离线 Supervisor 测试，但仍限制真实内容质量与本地 AI provider 能力。

## 主要修改文件

- Schema：`alysia/schemas/supervisor.py`、`alysia/schemas/__init__.py`
- Supervisor：`alysia/supervisor/*.py`
- CreatorLoop bridge：`alysia/planning/loop.py`
- 配置/CLI：`alysia/core/config.py`、`alysia/cli.py`、`config.example.yaml`
- 测试：`tests/test_supervisor.py`
- 文档/版本：`README.md`、`development_report_alpha13.md`、`pyproject.toml`、`alysia/__init__.py`

## 当前限制与瓶颈

1. alpha13 的长期规划与优先级主要是确定性规则，不使用 LLM 直接覆盖硬治理规则。
2. 默认单机、单进程、文件持久化；不支持分布式调度或并发 Studio run，这是有意限制。
3. 默认 usage 由 Supervisor 项目状态保守估算；正式 cloud cost 仍需 provider 提供可验证的实际成本记录。
4. Trend、experiment、provider health 的变化可以触发 proposal，但不会自动应用重大重规划。
5. 真实内容 run 仍受 Ollama 模型、CosyVoice 和 faster-whisper 未就绪影响。
6. 工作树包含 alpha1-alpha12 大量既有未提交成果；alpha13 没有替用户提交或清理。

## Alpha14 建议

可进入 **Self-Evaluation + Capability Gap Detection + Skill Acquisition Pipeline**：让 Alysia 识别“自己不会什么”，形成 CapabilityGap 和 SkillProposal，在隔离 sandbox 中生成/验证候选技能，并通过可复现评测比较前后能力。任何新技能启用、外部下载、权限扩大或生产接入仍必须经过沙箱验证和人工批准；Supervisor 不能自动修改自身源码。
