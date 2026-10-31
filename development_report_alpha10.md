# Alysia v0.1-alpha.10 开发报告

生成日期：2026-08-07（Asia/Shanghai）

## 结果

alpha.10 已将 Alysia 从长期内容战略 Agent 扩展为具有稳定、可配置、可审计创作身份的 AI UP 主系统：

```text
Creator Identity v1
  + Brand Voice
  + Visual Identity
  + Narrative Framework Library
  → PromptContextBuilder
  → Writer / Director context artifacts
  → Style Consistency QA
  → Identity Change Proposal
  → Human Approval
  → New Identity Version
```

Alysia 的身份明确为 AI 视频创作系统，不是真人创作者。系统不生成个人背景或现实经历，不会自动修改人格、频道方向、内容或发布状态。

## Alpha.9 稳定性确认

开发前已完整读取并审计：

- `development_report_alpha9.md` 与 `README.md`。
- `memory/channels/main/channel_memory.json`、`dashboard.json` 和 Strategy JSON。
- `alysia/operations` 的 Channel Memory、Experiment Manager、Strategy Evidence Chain 与 Dashboard。
- `alysia/planning/loop.py` 的 Creator Loop 和 Human Approval Gate。
- 对应 schema、store、CLI 和 `tests/test_operations.py`。

基线结果：`83 passed`。`python -m alysia doctor` 正常完成；发布、反馈、学习、实验审批、多频道隔离和 Creator Loop 幂等测试均通过。工作树已有 alpha.2-alpha.9 未提交成果，本轮保留且未重置。

## 新增能力

### 1. Creator Identity Model 与版本历史

- 当前身份：`identity/creator_identity.yaml`。
- 不可覆盖历史：`identity/history/creator_identity.vNNNN.yaml`。
- 包含使命、频道用途、内容哲学、观众、专业领域、排除主题、沟通风格、视觉身份、叙事模式、价值、披露政策和版本时间。
- 每次人工批准的修改创建新版本；历史版本内容不同则拒绝覆盖。

当前 identity 版本：`v1`。

### 2. Brand Voice 与 Visual Identity

Brand Voice 配置包括 tone、句式、词汇偏好、禁用表达、解释深度、幽默程度、技术深度、开场和结尾风格。默认是理性、清晰、克制、少营销词、强调证据，但 schema 不写死单一频道风格。

Visual Identity 包含颜色主题、字体、封面布局、缩略图规则和 scene 偏好。alpha5 模板封面现在记录 `visual_identity.template_version` 与 `cover_layout` metadata；第一版不接入 AI 图片生成，也不强制重绘旧封面。

### 3. Content Style Memory

新增 `memory/channels/<channel_id>/content_style_memory.json`：

- 只从 alpha9 已识别的非测试 success case 读取风格特征。
- 每项观察关联 run、可选 experiment、metrics 和 source。
- 记录标题、开场、结构、视觉、字幕和节奏。
- 单一 run 只能形成 `tentative` 风格规则；至少两个独立 run 且存在受控实验关联才可能成为 `supported`。
- mock/testing 内容永不进入正式风格记忆。

当前 demo 没有非测试成功样本，因此 Style Memory 正确保持空观察，没有生成永久规则。

### 4. Style Consistency QA

`style check` 读取 Script、Storyboard、主标题、封面/投稿 metadata 与 Creator Identity，输出 matched elements、violations、suggestions、score、confidence 和输入 SHA-256。

检查频道领域、排除主题、目标观众、禁用表达、技术深度、开场/结尾和视觉偏好。报告是确定性的旁路建议，不会修改内容或推进 pipeline 状态。

### 5. Narrative Framework Library

`skills/narrative/` 新增五个可验证 YAML 模板：

- `problem_solution`
- `myth_breaking`
- `deep_explanation`
- `technology_evolution`
- `experiment_report`

每个模板包含 purpose、structure、suitable_topics、examples 和 limitations。它们可供 Writer 引用，但不强制套用。

### 6. Prompt Assembly Layer

`PromptContextBuilder` 统一组合：

```text
Base Task Prompt
+ Creator Identity
+ Brand Voice
+ Relevant Strategy（保留 tentative/supported 状态）
+ 已人工批准或运行中的 Content Experiment
```

Writer 与 Director 不包含各自硬编码的人格文本。Orchestrator 在调用它们前统一构建最终 prompt，并记录：

```text
runs/<run_id>/identity/prompt_context.writer.json
runs/<run_id>/identity/prompt_context.director.json
```

`identity check` 另写 `prompt_context.check.json` 和检查报告，便于查看、调试与复现。

### 7. Identity Card 与受控演进

`identity_card.md` 只渲染配置化使命、领域、观众、价值和披露政策，并明确 Alysia 是 AI 视频创作系统、不是人类创作者、没有现实身份或个人经历。

`IdentityChangeProposal` 保存 proposed change、reason、evidence、expected effect、risk 和 approval requirement。proposal 默认 pending，不改变当前身份；automation、agent、system 或 Alysia 不能批准提案。proposal 基于旧版本时也不能应用。

## CLI

```powershell
python -m alysia identity show
python -m alysia identity history
python -m alysia identity check RUN_ID
python -m alysia style check RUN_ID
python -m alysia identity propose
python -m alysia identity approve PROPOSAL_ID --approved-by HUMAN
```

## 主要修改文件

- Schema：`alysia/schemas/identity.py`、`alysia/schemas/__init__.py`
- Identity：`alysia/identity/store.py`、`card.py`、`style.py`、`prompts.py`、`narrative.py`、`evolution.py`、`service.py`
- Prompt 接入：`alysia/core/orchestrator.py`、`alysia/agents/writer.py`、`director.py`
- Cover 对接：`alysia/providers/cover/template.py`、`alysia/workers/publish_package.py`
- Memory：`alysia/operations/store.py`
- CLI/配置：`alysia/cli.py`、`alysia/core/config.py`、`config.example.yaml`
- 叙事模板：`skills/narrative/*.yaml`
- 测试：`tests/test_identity.py`、`tests/test_orchestrator_text_pipeline.py`、`tests/helpers.py`
- 文档/版本：`README.md`、`pyproject.toml`、`alysia/__init__.py`

## 离线测试

alpha.10 新增 10 个指定测试，覆盖 Creator Identity schema、版本化、Brand Voice、Style QA、Narrative Library、Prompt Context Builder、人工审批门、Visual Identity、Identity Card 安全边界和幂等检查。

最终全量结果：`93 passed`。

## Demo

使用已有完整 run：

```text
run_id: 20260807_175616_cb2fbe40
topic: 为什么AI Agent还不是AGI？
```

执行 `identity show`：

- 生成 `creator_identity.yaml`、历史 `v0001` 和 `identity_card.md`。
- 当前 identity version：`1`。

执行 `identity check`：

- valid：`true`。
- errors：`0`。
- warning：频道当前没有 supported 策略，tentative 项只作为带状态审计上下文。

执行 `style check`：

- violations：`0`。
- score：`0.972`；confidence：`0.9`。
- 已匹配频道领域、目标观众、禁用表达、技术深度、开场、结论、scene 偏好和封面 metadata。
- 因只有 mock/testing 样本，报告提示缺少非测试成功案例，不将该 run 升级为长期风格规则。

执行 `identity propose`：

- proposal 状态：`pending`。
- `approval_required: true`。
- 当前 identity 仍为 v1，未发生自动修改。

## 当前限制

- 当前只有 mock/testing 运营样本，无法验证跨视频品牌一致性与表现之间的关系。
- Style QA 是透明启发式规则，不是语义模型或审美评审，不声称证明内容质量。
- Visual Identity v1 主要是配置和模板 metadata；颜色、字体与 scene 偏好尚未成为强制渲染约束。
- Narrative Library 已验证结构，但不会自动为每个选题选择最佳模板。
- Identity 变更应用仅支持经 schema 验证的顶层字段更新；复杂嵌套修改应提交完整嵌套配置。
- Human Approval Gate、发布门和实验审批逻辑保持不变。

## Alpha.11 建议

建议 alpha.11 聚焦 **Brand-aware Editorial Review + Controlled Identity Evaluation**：

1. 在人工审核界面并列展示内容、Style QA、Identity version 和 Prompt Context digest。
2. 用至少 3-5 条非测试内容验证风格特征稳定性，再讨论 supported brand rules。
3. 为叙事模板增加人工选择与实验关联，比较结构对留存的影响，但不自动改变频道方向。
4. 给 Visual Identity 模板加入可回滚 token 版本，并对旧封面保持兼容。
5. 在任何半自主运营扩展前，继续保留身份、内容和发布三道人工审批门。
