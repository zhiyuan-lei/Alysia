# Alysia v0.1-alpha.17 开发报告

## 仓库与工作树保护

- 仓库：`D:\Alysia`
- branch：`main`
- alpha17 开始前 tracked diff：22 files、4087 insertions、89 deletions，另有大量 alpha1-alpha16 untracked 成果。
- 本阶段没有执行 `git reset`、`git clean`、`git checkout`、`git stash`、`rebase`、`commit`、`squash` 或历史改动清理。
- `.planning/alpha17/` 独立保存任务计划、发现、错误与进度；没有覆盖根目录的历史 planning 文件。
- 所有 alpha17 修改均在现有工作树上增量完成；历史未提交成果保持原状态。

## alpha16 / H3 起点

- alpha16 的 Simulation 与现实 Analytics/Memory 已隔离，Supervisor 只消费 recommendation。
- ComfyUI + MiniMax H3 已真实部署；alpha17 没有重装或修改 H3/CUDA/驱动。
- 当前运行预算仍为 RTX 4060 Ti 8GB VRAM + 24GB RAM、GPU-heavy 串行。
- alpha17 只读取 `evaluation/capability_evaluation_h3_runtime.json`，把它保存成 scope=`current_machine` 的 system observation。

## alpha17 新增能力

1. `EvidenceSource` 与 `KnowledgeClaim` 分离；来源不再等同于事实。
2. Source metadata：publisher/domain/author、published/retrieved time、类型、hash、访问与引用说明、reliability notes、origin 和 observation scope。
3. Claim metadata：类型、状态、置信度、scope/conditions、时间窗口、证据/反证、版本与 supersession。
4. JSON KnowledgeStore：claims/sources/topics/conflicts/snapshots/tasks/gaps/index，可查询、可审计、原子写入；更新前保留 snapshot。
5. 透明 SourceQualityEvaluator：一手接近度、时效性、领域相关、corroboration、作者、引用质量、冲突历史均输出分项与固定权重。
6. Claim extraction/verification：无 source refs 或只有 mock/trend/simulation/feedback 的候选不进入 claim store；单一普通来源通常只 provisional；官方/一手或独立高质量 corroboration 才可 verified。
7. KnowledgeConflict 与 ConflictDetector：value/date/scope/definition/version 冲突保留证据并要求更高质量来源。
8. FreshnessPolicy：software 14 天、pricing 3 天、current roles 7 天、stable definition 365 天为可覆盖默认值；没有全局统一 TTL。
9. 单次 maintenance tick：扫描 aging/stale/conflicted claim，幂等生成 ReverificationTask，不启后台 daemon，也不自动批量抓网。
10. Research Provider：保留 Mock/Manual/Web 抽象；Web 只接受显式公开 adapter，并捕获 publication/retrieval/type/hash，不登录受限平台。
11. Research-to-Knowledge：normalization → extraction → verification → conflict → store；unsupported 候选只出现在结果中。
12. Writer grounding：`ScriptSection` 支持 `claim_refs`；事实性 section 检查 claim/source、freshness、conflict 和来源 origin/quality。
13. 每个正式 run 可保存 `claims_used.json`、`source_snapshot.json`、`grounding_report.json`、`knowledge_qa_report.json`。
14. KnowledgeContextSelector：按 topic/role 选择 verified/provisional 且未过期的 claim；不把整个知识库放入 StudioContext。
15. KnowledgeGap 与有限 ResearchTask：显式 evidence quality、freshness、max sources、max rounds、deadline 与 stop condition。
16. Supervisor 新增只读 knowledge readiness/gap 入口；Workflow 增加受控 Research→Verification→Writer adapter；Production/Studio/Publish 分层不变。

## 来源边界

- TrendItem：只用于“为什么现在做”，不会升级为事实。
- Simulation：只写 `simulations/`，不会进入 KnowledgeStore。
- Feedback/Comments：只作为 audience/content insight。
- Mock：只验证离线流程；可保存 source metadata，但不产生 verified/provisional claim。
- User input：作为 instruction/context；若要成为事实，仍需 source policy，或明确标记 user_asserted 且不能自动晋升为 verified。
- 本机 H3 benchmark：是 primary local observation，scope=`current_machine`；不是所有机器或所有 H3 版本的全局性能事实。

## CLI

新增：

- `python -m alysia knowledge status`
- `python -m alysia knowledge claims --topic <topic>`
- `python -m alysia knowledge sources --claim <id>`
- `python -m alysia knowledge conflicts`
- `python -m alysia knowledge stale`
- `python -m alysia knowledge verify <claim_id>`
- `python -m alysia knowledge tick`
- `python -m alysia knowledge qa`
- `python -m alysia research task <question>`
- `python -m alysia grounding check <run_id>`
- `knowledge demo-a/demo-b/demo-c/demo-d/demo-grounding`

## Demo A：时效事实更新

- v1 claim：最大时长 10 秒；新官方 fixture 表示 v2 为 15 秒。
- 结果：旧 claim=`superseded`，新 claim=`verified`/version 2，`supersedes_claim_id` 正确。
- 旧 run 的 `claims_used.json` 仍保留当时 v1 statement 和 verified 状态；新版本不会覆盖旧 snapshot。

## Demo B：来源冲突

- 两个来源对同一 normalized parameter 给出 24/32。
- 结果：`conflict_26ea30ddae2e4223`，两个 claim 均为 `conflicted`，resolution=`needs_primary_source`。
- Writer 不得确定性使用；生成 primary quality 的有限 ResearchTask。

## Demo C：知识过期阻塞

- pricing claim 距上次验证 10 天，TTL=3 天。
- Grounding 阻塞并列出 stale claim；maintenance 生成稳定 ReverificationTask ID；KnowledgeGap 标记 critical。
- 恢复点为 `writing`，`restart_full_pipeline=false`，不重跑 Research 之前的全部历史链路。

## Demo D：H3/ComfyUI 本机观测

- 读取真实 runtime evidence：provider=`visual.comfyui-h3`、mock=false、608x352、3.042 秒、6 steps、provider wall time 105.75 秒、peak VRAM 7678 MB。
- Claim status=`verified` 仅表示该本机 observation artifact 被验证存在；scope=`current_machine`、origin=`system_observation`、global_fact=false。
- 原 evidence 报告的峰值 RAM 超过 24GB 配置预算这一约束被保留，没有改写 H3 capability 成 stable。

## Grounding 与知识状态

- Demo grounding run：`20260808_182330_a2345215`。
- factual section：1；supported：1；unsupported：0；citation coverage=1.0；Knowledge QA PASS。
- 主 KnowledgeStore：2 sources、1 claim（verified）、0 conflict、0 stale、0 task、0 gap；全局 Knowledge QA PASS。
- 主库的两个 source origin 分别为 mock（无 claim，仅保留离线管线痕迹）与 system observation；唯一正式 claim 是 H3 本机 observation。
- Demo A/B/C 已隔离到 `workspace/knowledge_demos/alpha17/`：5 sources、5 claims、1 open conflict、1 stale、4 tasks、1 gap；claim 状态为 1 verified、2 conflicted、1 stale、1 superseded。

## 测试与自检

- alpha17 专项：25/25 PASS。
- 全量收集：248 tests。
- 全量 pytest：247 PASS、1 SKIP；skip 为需要外部真实 H3 环境的标记测试，现有离线回归全部通过。
- Supervisor/Studio/Workflow/Production/Publish/Feedback 定向回归通过。
- `python -m alysia doctor`：12 项可用、4 个可选组件未就绪；RTX 4060 Ti 8188 MiB，Alysia budget 8192MB/24GB。
- Demo A/B/C/D 与 demo grounding 均执行成功。
- 主库 `knowledge tick` 连续执行两次：均 scanned=1/fresh=1、task/conflict 为空，只允许 report timestamp 变化；专项测试另验证 stale demo 的 task IDs 与 snapshot count 幂等。
- compileall 通过；最终还执行 `git diff --check`、git status 与 diff stat。
- `git diff --check` PASS；最终 tracked diff stat 为 27 files、4513 insertions、100 deletions（其中绝大部分是 alpha1-alpha16 历史未提交累计差异，不能归因于 alpha17）。

## alpha17 文件

新增核心：

- `alysia/knowledge/*.py`
- `alysia/providers/search/manual.py`
- `tests/test_knowledge.py`
- `knowledge/` 可审计 demo artifacts
- `.planning/alpha17/*`
- `development_report_alpha17.md`

增量修改：

- `alysia/schemas/research.py`、`alysia/schemas/script.py`
- `alysia/providers/search/{__init__,mock,web}.py`
- `alysia/agents/writer.py`、`alysia/core/orchestrator.py`
- `alysia/studio/context.py`、`alysia/supervisor/supervisor.py`
- `alysia/workflow/executors.py`、`alysia/production/{registry,router}.py`
- `alysia/core/config.py`、`alysia/cli.py`
- `config.example.yaml`、`README.md`
- `alysia/__init__.py`、`pyproject.toml`、`uv.lock`
- `tests/helpers.py`

其中多项既有文件在 alpha17 前已有历史未提交改动；上述列表只描述 alpha17 在其上追加的职责，不把整文件 diff 归因于本阶段。

## 当前限制

1. 默认 ClaimExtractor 是确定性离线实现，会把 ResearchResult 的来源集合绑定到 key point；更精细的句级 entailment 需要后续受评测 extractor，但仍必须返回 source refs。
2. WebResearchProvider 需要显式注入公开 adapter；仓库不自带搜索账号、登录或付费墙访问。
3. 当前 JSON store 适合可审计小规模知识；尚无全文/向量检索和大规模并发写入。
4. 冲突检测依赖 normalized key；语义相同但 key 不同的 claim 需要更强 normalization/benchmark。
5. Source-only grounding 仅按可解释质量规则判断；高风险可变事实仍建议使用具 TTL 的 claim refs。
6. maintenance 只有显式单次 tick；没有后台 daemon，也不会无限搜索。
7. Demo A/B/C 的官方/社区条目是离线 fixtures，只验证系统行为，不代表现实 MiniMax 参数或价格声明。

## 分层结论

- Supervisor：决定是否因 KnowledgeGap 暂停，只创建任务，不直接调 Writer/Provider。
- WorkflowPlanner/Runtime：只组合已批准 Research/Verification/Writer 能力。
- StudioDirector：仍负责单 run 角色交接；通过 selector 获得受控知识上下文。
- ProductionPlanner：仍只负责 provider、资源、预算与 fallback。
- KnowledgeStore：只提供事实与 provenance，不替代 Agent。
- Publishing/Identity/Budget/Experiment：既有 Human Approval Gate 均未绕过。

## alpha18 建议

进入 **Autonomous Evaluation Benchmarking + Regression Intelligence**：为 Research extraction、claim verification、grounding、TTS、字幕、视觉、脚本与 workflow 建立版本化 benchmark suite；升级前对候选版本自动跑离线/沙箱回归，对比质量、成本、时延与失败类型，只有证据显示净改善且关键 gate 无回退时才生成升级建议，仍由人工批准。
