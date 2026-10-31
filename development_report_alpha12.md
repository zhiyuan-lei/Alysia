# Alysia v0.1-alpha.12 开发报告

生成日期：2026-08-07（Asia/Shanghai）

## 结果

alpha12 已在不重写 alpha1-alpha11 内容流水线、不引入大型 Agent 框架、不降低 ProductionPlan 与 Human Approval Gate 的前提下，加入默认串行的 Multi-Agent Creator Studio：

```text
Goal / RunState
  → StudioDirector（唯一总控）
  → AgentRegistry + ContextSelector
  → rule-constrained route decision
  → AgentHandoff
  → role Agent adapter
  → existing Orchestrator / Worker / Provider / Service
  → AgentResult + Artifact owner/version
  → Trace + Context snapshot + Studio QA
```

仓库路径：`D:\Alysia`。

## Alpha11 状态确认

开发前读取了 alpha11 报告、README、Orchestrator、Production Planner/Router/Service、agents、workers、providers、Memory、Identity、Analytics、Creator Loop 和 tests。

alpha11 报告基线为 108 tests passed。alpha12 开发前重新执行当前工作树 pytest，退出码为 0；`python -m alysia doctor` 正常完成，10 项可用、5 项可选能力未就绪。工作树中的 alpha1-alpha11 未提交成果全部保留，没有 reset、clean、checkout 或重建仓库。

## Studio 架构

新增 `alysia/studio/`：

- `director.py`：唯一 StudioDirector、规则路由、retry/revision/escalation、run/resume/status/trace。
- `registry.py`：九角色 AgentProfile、能力、输入、产物、上下文、工具/provider 白名单和升级规则。
- `context.py`：StudioContext、ContextPolicy、ContextSelector、按版本持久化 snapshot。
- `handoff.py`：pending → accepted → completed/rejected/escalated 的显式 Handoff Protocol。
- `protocol.py`：AgentHandoff、AgentResult、AgentFailure、ArtifactRef、RevisionRequest、StudioState、Trace、QA contract。
- `trace.py`：handoffs/results/decisions/artifacts/revisions/context/JSONL trace 持久化和凭证字段脱敏。
- `ownership.py`：artifact owner、active version、revision request 和下游失效。
- `agents.py`：九个轻量角色 adapter；不互相调用，只委派现有实现。
- `qa.py`：Studio handoff、owner/version、loop、required artifact、escalation 与 mock-production 检查。

Agent 是职责与推理边界，不是进程。默认没有多 Agent 并发，也没有自由聊天式辩论。所有角色切换都由 Director 发起，Agent 无法递归调用其他 Agent。

## Studio Agent 列表

| Agent | 主要职责 | Owned artifacts |
|---|---|---|
| ResearcherAgent | 资料、来源、事实摘要 | research |
| WriterAgent | 脚本与修订，不做最终事实裁决 | script, metadata |
| StoryboardDirectorAgent | 分镜与节奏 | storyboard |
| DesignerAgent | 低成本视觉计划、模板封面 | design_plan, design_assets, publish_cover |
| VoiceAgent | TTS、字幕、Audio QA | audio, subtitles, audio_qa |
| EditorAgent | composition、render、Video QA | composition, final_video, video_qa |
| CriticAgent | script/text/final 跨阶段审查、revision request | script_review, text_qa, final_review |
| PublisherAgent | package、validation、PublishJob 边界 | publish_package, publish_qa, publish_validation, publish_job |
| AnalystAgent | Analytics、Memory、Strategy、Experiment | analytics, memory, strategy, experiment |

## 现有 Pipeline 集成

- Researcher/Writer/Storyboard/Critic/Voice/Editor/Publisher 复用现有 `AlysiaOrchestrator` 阶段、workers 和 QA。
- Analyst 复用 `LearningPipeline` 与 `OperationsService`；未导入 Analytics 时明确 blocked，不补造数据。
- Designer 新增轻量 `DesignWorker`，只生成确定性视觉计划和模板封面，不触发高成本 AI 图片。`PublishPackageWorker` 复用已存在的 Designer cover，不覆盖 owner。
- Provider 由 alpha11 ProductionPlan 决定。Agent 只能声明任务需求并验证 provider 是否属于角色白名单。
- StudioContext 只保存 artifact 引用和身份/品牌/lesson/strategy/experiment 摘要，不塞入全部历史或大文件全文。
- Artifact 修订通过 RevisionRequest 产生新版本；Audio/Video/Script revision 会使依赖的 active downstream artifact 失效，但历史 trace 不删除。

## CLI

新增并验证：

```powershell
python -m alysia studio agents
python -m alysia studio run RUN_ID
python -m alysia studio status RUN_ID
python -m alysia studio trace RUN_ID
python -m alysia studio resume RUN_ID
```

现有 create/resume/render/package/publish/feedback/production CLI 未改名或移除。

## Trace 与产物

每个 Studio run 写入：

```text
runs/<run_id>/studio/
├── studio_state.json
├── studio_trace.jsonl
├── handoffs.json
├── decisions.json
├── agent_results.json
├── artifacts.json
├── revision_requests.json
├── studio_qa_report.json
├── design_plan.json
├── reviews/
└── context_snapshots/context.vNNNN.json
```

Trace 记录路由原因、角色、handoff、结果、artifact、QA 返工和 escalation。token、secret、password、cookie、authorization 与 API key 字段会脱敏。

## 测试

alpha12 新增 `tests/test_studio.py`，共 21 个离线测试，覆盖：

- registry、context snapshot、handoff schema/acceptance、AgentResult contract；
- rule routing、role boundary、artifact ownership/version/revision；
- review/hop limit、context selector、failure escalation、trace redaction；
- Audio QA fail → Voice 路由；
- publish approval gate；
- ProductionPlan provider control；
- Studio resume idempotency、Studio QA；
- 人工批准 + mock 发布/反馈后的 Analyst 集成；
- Audio failure 后 Voice/Editor/Critic 定点恢复，不重跑 Researcher/Writer。

最终测试集合：129 tests。最终全量 pytest 退出码为 0；Remotion `npm run check` 通过并发现 1920x1080 / 30fps `VideoComposition`；`compileall` 通过。

## 完整 Multi-Agent Demo

demo run：`20260807_225658_1596ed8c`

主题：`Alysia 的多角色协作为什么默认串行？`

执行结果：

- 首次 Studio run：到 Publisher 后停在 `waiting_for_approval`。
- 显式人工 mock 审核者：`human:alpha12-offline-demo`。
- 之后执行 mock PublishJob、mock feedback，最后由 Analyst 完成 Analytics/Memory/Strategy/Experiment。
- 最终状态：`completed`。
- ProductionPlan：`prod_de4fa53d39cd8b5b`。
- AgentResult：11 条。
- Handoff：11 条。
- Trace：40 条（包含后续 CLI run/resume 幂等检查事件）。
- Context snapshot：12 个。
- Review round：0；本次脚本初审无需修订。
- Studio QA：PASS。

角色序列：

```text
Researcher
→ Writer
→ Critic(script review)
→ StoryboardDirector
→ Critic(text QA)
→ Designer
→ Voice
→ Editor
→ Critic(final review)
→ Publisher / Human Approval Gate
→ Analyst
```

Publisher 的首个 AgentResult 明确为 blocked/approval_required；存在 ApprovalRecord 后才继续。StudioDirector 没有自动代签或绕过审批。

## Audio Failure Recovery Demo

failure demo run：`20260807_230208_43ee9a2b`

在首次到达 publish review gate 后，将 Audio QA 标记为模拟失败，再执行 Studio resume：

```text
Audio QA fail
  → StudioDirector
  → Voice revision
  → Editor resume
  → Critic final review
  → Publisher package refresh
  → Human Approval Gate
```

结果：

- Researcher：1 次。
- Writer：1 次。
- Voice：2 次。
- Editor：2 次。
- Critic：4 次（初审、Text QA、原最终审查、恢复后最终审查）。
- audio：v2。
- final_video：v2。
- final_review：v2。
- Handoff：14 条。
- Trace：44 条。
- 恢复后状态：`waiting_for_approval`，因为投稿包变更使旧审批不可复用。
- Studio QA：PASS。

这证明恢复没有从 Research 重新开始，也没有复用已经失效的最终审查或投稿审批。

## ProductionPlan 与 Approval Gate

- 所有 LLM/Research/TTS/ASR/Render/Cover provider 都从 `production/production_plan.json` 读取。
- Studio 没有新的独立 provider router。
- Production policy blocker 仍返回 approval_required。
- Publisher 在缺少 ApprovalRecord 时停止；包变化后仍由现有 package hash 校验使审批失效。
- Identity、Experiment、Strategy 与 Publish 的人工审批规则没有降低。
- Studio 不自动提交真实 Bilibili、不自动评论或私信。

## 主要修改文件

- Studio：`alysia/studio/*.py`
- Design integration：`alysia/workers/design.py`、`alysia/workers/__init__.py`、`alysia/workers/publish_package.py`
- 配置/CLI：`alysia/core/config.py`、`alysia/cli.py`、`config.example.yaml`
- 测试：`tests/test_studio.py`
- 文档/版本：`README.md`、`development_report_alpha12.md`、`pyproject.toml`、`alysia/__init__.py`

## 当前限制与瓶颈

1. Ollama、CosyVoice 和 faster-whisper 仍未就绪；真实质量仍受当前 provider 能力限制。
2. Cloud LLM 与 Web Research 仍是占位实现；正式高质量事实链尚未验证。
3. Studio 默认严格串行；alpha12 不做并发性能优化，这是有意限制。
4. Designer 当前只使用模板封面和程序化视觉计划，没有高成本 AI 图像生成。
5. Rule engine 基于 artifact/QA/approval；复杂风格违规目前只形成受控 Critic 建议，不让 LLM 独立路由。
6. Studio adapter 当前调用 Orchestrator 的既有阶段方法；未来可增加稳定的 public stage facade，减少对内部方法名的耦合，但不需要重写流水线。
7. 工作树仍包含 alpha1-alpha11 大量未提交成果；本轮没有替用户提交或清理。

## Alpha13 建议

可以进入 **Autonomous Supervisor + Goal Management + Long-horizon Project Planning**，但继续保持：

- 单一 Supervisor/Director 最终控制权；
- 明确目标层级、deadline、预算、hop/retry 上限；
- 计划与执行分离，长程任务必须可暂停/恢复；
- ProductionPlan、artifact ownership、trace 和 StudioQA 继续作为硬约束；
- 真实发布、身份变更、预算扩大、策略升级和外部通信继续需要 Human Approval；
- 不自动修改自身源码，不引入无限反思或自由多 Agent 对话。
