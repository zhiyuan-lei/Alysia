# Task Plan: Alysia v0.1-alpha.18 Autonomous Evaluation Benchmarking + Regression Intelligence

## Goal
在完整保留 Alpha1-Alpha17 既有未提交成果的前提下，建立可离线复现的统一 benchmark、baseline snapshot、regression comparison 与 promotion gate；严重回归必须提供证据并阻止 capability/version promotion。本轮不进入 Alpha19。

## Current Phase
Phase 6 (complete)

## Phases

### Phase 1: Alpha17 Baseline Inventory
- [x] 记录开工前 git status/diff stat/diff name-only
- [x] 读取 README、Alpha 报告、配置、CLI、tests、QA 与 Alpha17 关键子系统
- [x] 运行全量 pytest、doctor 与历史 stub audit
- [x] 生成 docs/baseline_alpha17_inventory.md
- **Status:** complete

### Phase 2: Evaluation Domain Core
- [x] 实现 schema、registry、scorers、fixtures、fingerprint 与 EvaluationRun store
- [x] 默认 benchmark 离线且可重复；主观 rubric 提供维度与理由
- [x] 保存 Alpha17 baseline snapshot
- **Status:** complete

### Phase 3: Regression Intelligence and Gate
- [x] 实现 absolute/relative/direction-aware RegressionEngine
- [x] 实现 PASS/PASS_WITH_WARNINGS/BLOCKED EvaluationGate
- [x] 接入 capability/version promotion 决策但不自动回滚
- [x] 增加显式 H3/ComfyUI integration benchmark，默认隔离
- **Status:** complete

### Phase 4: CLI, Fixtures, Tests and Demo
- [x] 实现 eval list/run/baseline-create/compare/report/gate CLI
- [x] 建立 golden fixtures 与完整离线测试
- [x] 实演 baseline PASS、故意 regression BLOCKED、正常 candidate 恢复
- [x] 建立 docs/regression_matrix.md 并执行核心 invariants
- **Status:** complete

### Phase 5: Full Verification and Audits
- [x] 全量 pytest、doctor、CLI 实演、integration health/status
- [x] 检查新增 skip，执行阶段结束 stub audit
- [x] 对比结束 git snapshot，证明 Alpha1-Alpha17 历史成果未丢失
- **Status:** complete

### Phase 6: Documentation and Final Gate
- [x] 更新 README、roadmap、phase ledger、change review
- [x] 生成 development_report_alpha18.md，逐项附 evidence path
- [x] 仅在全部 gate 满足且无 production stub/blocker 时标记 Alpha18 DONE
- [x] 明确确认未进入 Alpha19
- **Status:** complete

## Alpha18 Constraints
- 禁止 reset/clean/checkout/restore/stash/rebase/commit/squash/amend 或清理历史未提交成果。
- 不进入 Alpha19，不大规模重写现有业务逻辑，不引入大型 Agent 框架。
- 默认测试完全离线；H3/ComfyUI 仅显式 integration 模式运行。
- mock/test 数据不得进入真实 Analytics/Memory；未知指标保持 unknown。
- production path 新增未实现 stub 时 Alpha18 必须 BLOCKED。

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
| 并行基线命令中的 `rg development_report_alpha*.md` 在 Windows 把通配符当作非法路径，导致聚合调用退出 1，pytest/doctor 输出未返回 | 1 | 改用 `--glob 'development_report_alpha*.md' .`，并将 pytest、doctor、stub audit 分开执行以保留证据 |
| 查询 skill approve 命令时使用了未闭合的 `rg` 正则 | 1 | 改用简单安全模式 `rg 'skill.*approve|command\("approve"'` 并成功定位；未修改业务文件 |

---

# Previous Plan: Alysia v0.1-alpha.12 Multi-Agent Creator Studio

## Goal
在不重写现有 Topic to Video to Publish 流水线、不降低 ProductionPlan 和 Human Approval Gate 的前提下，增加单一 StudioDirector、受控共享上下文、标准 handoff/result contract、artifact ownership、规则路由、可恢复 trace 与 Studio QA。

## Current Phase
Phase 5 (complete)

## Phases

### Phase 1: Alpha11 Baseline Audit
- [x] 阅读 alpha11 报告、README、orchestrator、production planner/router、agents、workers、providers、memory、identity、analytics、creator loop 与 tests
- [x] 执行基线 pytest 与 doctor，确认生产优化和完整闭环稳定
- [x] 记录 dirty worktree，保留全部 alpha1-alpha11 既有成果
- **Status:** complete

### Phase 2: Studio Domain Core
- [x] 实现 protocol、registry、context/context policy、handoff、trace、ownership、failure 与统一 AgentResult
- [x] 实现规则化 StudioDirector、review 上限、hop 上限和显式 escalation
- [x] 保证默认串行，禁止 agent 递归自治或绕过 ProductionPlanner
- **Status:** complete

### Phase 3: Existing Pipeline Integration
- [x] 封装现有 agents/workers/providers，明确九个角色职责边界
- [x] 复用现有阶段和 artifact，不复制 Research/Writer/Voice/Render/Publish/Analytics 逻辑
- [x] 按角色裁剪 Identity/Brand/Strategy/Experiment/Memory context
- **Status:** complete

### Phase 4: CLI, QA & Simulations
- [x] 实现 studio agents/status/trace/run/resume CLI
- [x] 实现 StudioQA 与测试内完整离线协作 demo
- [x] 验证恢复从 Voice revision 继续到 Editor，不从头重跑
- [x] 在仓库 runs 中生成最终 demo 与 failure recovery 证据
- **Status:** complete

### Phase 5: Tests & Documentation
- [x] 新增用户指定的 alpha12 离线测试并跑全量 pytest
- [x] 更新 README、版本与 development_report_alpha12.md
- [x] 执行 doctor、studio CLI demo、trace、failure recovery、Studio QA、git status、diff check
- **Status:** complete

## Alpha12 Decisions
| Decision | Rationale |
|----------|-----------|
| Studio 是现有 orchestrator 的兼容包装层 | 避免重写已验证的生产闭环 |
| Agent 是职责角色，worker/provider 仍执行工具 | 保持现有依赖注入与 ProductionPlan 路由 |
| 默认严格串行、单 Director、有限 review/hops | 适配 RTX 4060 Ti 8GB 并防止无限自治 |
| 交接、结果、revision、ownership 和 trace 都结构化持久化 | 满足审计、恢复和越权检测 |

## Alpha12 Constraints
- 不清理或覆盖 alpha1-alpha11 未提交成果。
- 不引入大型 Agent 框架、自由聊天、多 Agent 默认并发或无限反思。
- 不允许 Agent 自选昂贵 provider、修改自身源码或绕过任何人工审批。
- 所有新增测试和 demo 离线运行，不依赖真实网络、凭证、Ollama 或 Bilibili。

---

# Previous Plan: Alysia v0.1-alpha.11 Autonomous Production Optimization

## Goal
在完整保留 alpha1-alpha10 既有能力、审批门槛和用户未提交工作成果的前提下，为每次内容生产增加可解释、可审计、资源受限、可安全降级的生产规划与执行优化层。

## Current Phase
Phase 6 (complete)

## Phases

### Phase 1: Repository Baseline & Alpha.10 Audit
- [x] 阅读 alpha10 报告、README、identity/brand voice、creator loop、resource manager、providers、config、tests
- [x] 执行基线 pytest 与 doctor，确认 alpha10 闭环稳定
- [x] 审计工作树与兼容边界，记录现有用户改动
- **Status:** complete

### Phase 2: Production Domain & Planning Core
- [x] 实现 constraints/profile、capability registry、plan、metrics、fallback、cache、cost schemas
- [x] 实现配置化 router、planner、optimizer 与 explainable alternatives
- [x] 保证 offline/credentials/VRAM/cloud budget 等硬约束
- **Status:** complete

### Phase 3: Resource, Execution & Quality Integration
- [x] 升级 ResourceManager 的 stage acquire/release、GPU mutex、VRAM probe、unload、timeout/OOM 处理
- [x] 实现 metrics/fallback/cache/cost 记录与 ProductionQualityGate
- [x] 保持已有 QA，不允许无限重试或静默降级
- **Status:** complete

### Phase 4: CLI & Creator Loop Integration
- [x] 实现 production plan/status/report CLI
- [x] approved content run 在 create pipeline 前通过 plan/policy gate
- [x] cloud cost 可能超限时阻止并要求人工确认，保留既有 Human Approval Gate
- **Status:** complete

### Phase 5: Offline Tests & Demo
- [x] 补齐要求的 alpha11 离线测试
- [x] 对已有 approved/review-ready run 生成 draft/standard/high plans
- [x] 使用 mock providers 验证串行 GPU、fallback、cache、metrics、QA gate
- **Status:** complete

### Phase 6: Documentation & Final Verification
- [x] 更新 README 与 development_report_alpha11.md
- [x] 执行 pytest、doctor、三种 plan、production/fallback/cache simulation、report、git status
- [x] 汇总瓶颈与 alpha12 建议
- **Status:** complete

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| 保留现有未提交 alpha1-alpha10 工作 | 当前工作树包含大量既有用户成果，禁止清理或重置 |
| 先验证 alpha10，再写 alpha11 | 用户明确要求生产闭环稳定后再开发 |
| alpha11 采用轻量单总控与规则化排序 | 满足可解释、可审计且避免大型 Agent/复杂并发 |
| unknown 保持 unknown | 禁止伪造成本、VRAM 或 benchmark |

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
| 初次仓库审计耗时超过 10 秒并返回 running cell | 1 | 使用 wait 获取完整输出；无任务失败 |
| Phase 状态更新补丁上下文顺序不匹配 | 1 | 读取 task_plan 当前内容后使用精确上下文更新 |
| alpha11 首轮全量回归超过 120 秒超时且无 pytest 失败输出 | 1 | 改为按测试域并行运行，定位重复健康探测或执行阶段阻塞 |
| resume idempotency 测试中注入的 MockResearchProvider 被计划重建 | 1 | 当当前 provider_id 已匹配计划时保留注入实例，避免破坏调用计数与依赖注入 |
| 新 Creator Loop gate 测试使用了过时 CreatorProfile 字段名 | 1 | 按现有 alpha7 schema 改为 channel_goal/primary_domains/target_audience 等字段 |
| 首次 fallback demo 中 render.mock 被 Registry 误判不可用 | 1 | Registry 改用项目既有 FFmpeg 发现逻辑，兼容 winget Gyan 路径，不只依赖 PATH |
| 最终 CLI 自检脚本的 `$quality:` 触发 PowerShell 变量解析错误 | 1 | 改用 `${quality}` 明确变量边界后重跑 |
| 误用 Python 执行 planning skill 的 `.ps1` 完成检查 | 1 | 改用要求的 PowerShell 7 `pwsh -File` 执行 |

## Constraints
- 不破坏 alpha1-alpha10；不清理用户工作树。
- 不自动购买/充值、修改全局预算、绕过成本或发布审批。
- 不自动修改自身源码、驱动或 CUDA；不引入多 GPU/复杂并发/大型 Agent 框架。
- 所有测试离线，不依赖网络、真实 API 或 Ollama。
