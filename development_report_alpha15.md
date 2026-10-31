# Alysia v0.1-alpha.15 开发报告

## 仓库与工作树保护

- 仓库：`D:\Alysia`
- alpha15 开始前，工作树已有 alpha1-alpha14 大量历史未提交成果；基线 `git status --short` 和 `git diff --stat` 已记录在 `.planning/alpha15/`。
- 开始时 tracked diff 为 22 个文件、3608 insertions / 89 deletions，另有大量 alpha3-alpha14 untracked 文件。
- 本阶段未执行 `git reset`、`git clean`、`git checkout`、`git stash`、`rebase`、`commit`、`squash` 或历史改动清理。

## alpha14 起点

- alpha14 基线：179/179 tests PASS。
- CapabilityRegistry：15 项初始能力；12 stable、3 experimental。
- SkillRegistry：`h3_visual_generation` v1 active、v2 disabled；active 版本由 human review/approve 产生。
- Supervisor、Studio、ProductionPlanner 与发布/身份/预算 Human Approval Gate 均已存在，alpha15 只在其外增加 composition 层。

## alpha15 新增能力

- WorkflowTask：强制明确 inputs、desired outputs、constraints、预算/审批策略和可验证 success criteria。
- CapabilityMatcher：按 tags、contracts、prerequisites、成熟度、资源和 policy 透明打分；最终 eligibility 由规则决定。
- WorkflowPlanner：从 desired outputs 反向组合受信任能力，生成有限 DAG、artifact handoff、approval/quality/resource notes；未知能力显式阻塞。
- CompositionPolicy / WorkflowValidator：检查 active skill、contract、layer、cycle、资源、mock/production、skill hops 和各类审批点。
- WorkflowRuntime：顺序推进、统一 step state、JSONL result/trace、resume、幂等 artifact reuse；production 只能使用注入的 Studio/Production adapter。
- WorkflowRepairPlanner：有限 retry、active fallback、artifact owner 回退、optional skip、human escalation 或 alpha14 gap proposal。
- WorkflowEvaluation / WorkflowQA：只读取可观测时延、重试、fallback、resource notes、artifact 和 QA 结果，不虚构成本/质量。
- WorkflowRecipe：candidate/validated/deprecated 程序性记忆；默认 3 次独立成功后 validated，失败降低 confidence，版本变化使复用失效。
- CLI：`workflow plan/validate/run/resume/status/report/recipes/recipe-show` 及离线 demo 命令。

## 本阶段文件

新增：

- `alysia/schemas/workflow.py`
- `alysia/workflow/*.py`
- `tests/test_workflow.py`
- `development_report_alpha15.md`
- `memory/workflows/` 与 alpha15 demo 的 `runs/*/workflow/` 证据

增量修改：

- `alysia/schemas/capability.py`、`alysia/schemas/__init__.py`
- `alysia/capabilities/registry.py`、`alysia/capabilities/skill_registry.py`
- `alysia/core/config.py`、`config.example.yaml`
- `alysia/cli.py`、`README.md`
- `alysia/__init__.py`、`pyproject.toml`

这些既有文件在 alpha15 前已含历史未提交修改；本报告只归因上述 workflow/contract/config/CLI/version 增量。

## Capability / Skill 状态

- Registry bootstrap 现描述 20 项 capabilities：在原 15 项基础上，为 alpha13.5 已有 SceneSelection、VisualPlanner、VisualQA、EditorIntegration、VideoQA 补充受信任 contract。
- Skill records 仍为 2 个历史 H3 版本；只有 v1 active eligible，v2 disabled 不可组合。
- 没有自动批准 skill，没有改变 H3 v1/v2 审批状态。

## Demo A：视频视觉增强

- Workflow：`wf_4a361107b6e5`
- Run：`workflow_20260808_161321_df084f2a9b74`
- 组合：SceneSelection → VisualPlanner → `h3_visual_generation` v1 → VisualQA → EditorIntegration → VideoQA。
- 6-step DAG validation PASS；H3 继承 alpha11 sequential GPU policy，unknown VRAM 仅在明确 testing/mock demo 中允许。
- artifact handoff、evaluation 与 Workflow QA PASS；Mock 产物标记 testing，不可进入 production。

## Failure / Repair / Resume

- Workflow：`wf_97b27951fcca`
- 首次受控 adapter failure 后状态 blocked；没有删除已完成 artifact。
- 恢复受信任 adapter 后 `resume` 完成；失败 step attempts=2，未从头重跑。

## Demo B：能力缺口回流

- Workflow：`wf_c6c5846416ad`
- 缺失 contract：`editable_vector_infographic`。
- 状态：`blocked_waiting_capability`；未执行未知代码。
- alpha14 linkage：`gap_396c94beb90e` → `missing_editable_vector_infographic` SkillProposal，状态 PROPOSED，未评测/批准/注册。

## Demo C：Recipe Learning

- 三次独立成功：`wf_4666257f8871`、`wf_64a6e3a8335a`、`wf_87c3eb11fe6d`。
- Recipe：`recipe_a06f7ced1b568b65`；第 1 次 candidate，第 3 次达到阈值后 validated。
- 第四次 `wf_f41ae2c8f562` 优先从该 recipe 克隆，并保留 recipe/evidence/adjustments provenance。

## 测试与 QA

- alpha15 专项：22/22 PASS。
- Supervisor/Studio/Publish/Production/Capability 定向回归：全部 PASS。
- 最终全量：201/201 PASS（53.25s）。
- `python -m alysia doctor`：成功；11 项可用、4 项可选组件未就绪；RTX 4060 Ti 为 8188 MiB。
- 最终显式 `workflow plan → validate → run → status → report → qa`：`wf_b3715240be09`，6 steps，completed，Workflow QA 全部 checks PASS。
- 最终 repair/resume：`wf_164950130828`，blocked → completed，未从头重跑。
- 最终 gap demo：`wf_f6a0d31cdcf7`，保持 `blocked_waiting_capability`，仍链接 `gap_396c94beb90e` 与 PROPOSED skill。
- 最终 Recipe：`recipe_a06f7ced1b568b65` 为 validated；重复离线自检后 success_count=8、failure_count=0、confidence=0.9，recipe-show provenance 完整。
- `compileall`、`git diff --check` PASS；仅显示仓库既有 LF/CRLF conversion warnings，无 whitespace error。
- 最终 tracked `git diff --stat`：22 files、3837 insertions / 89 deletions；untracked 中新增 alpha15 workflow/schema/test/report/recipe/demo artifacts，同时 alpha1-alpha14 历史成果仍全部存在。

## 分层与安全结论

- Supervisor 仍拥有长期 objective；Workflow 只组合受信任能力。
- StudioDirector 仍拥有单 content run；ProductionPlanner 仍拥有 provider/resource 决策。
- SkillRegistry 仍是 skill eligibility 真相源；disabled/unapproved/deprecated skill 不可执行。
- 发布、身份、预算和重大策略 Gate 未被绕过。
- 未下载/执行未知代码，未自动安装依赖，未自动修改核心源码，未引入大型 Agent 框架。

## 当前限制

1. 默认内置 runtime adapter 只用于受控 testing；真实 production composition 需为相应步骤注入现有 Studio/Production adapter。
2. Recipe 相似度目前基于 objective keywords + input/output contracts，不是语义模型；保持可解释但召回有限。
3. 资源为 unknown 的 GPU skill 在 production 默认不可计划；需要真实 H3 smoke 与可验证资源基线。
4. OS 级 sandbox 隔离仍不在 alpha15 范围内。

## alpha16 建议

进入 **World Model / Simulation Sandbox + Counterfactual Planning**：在真实执行前，对多个内容/运营方案进行受控模拟、比较假设和资源结果，并明确标记 simulated evidence，绝不把预测当作真实平台反馈或自动绕过审批。
