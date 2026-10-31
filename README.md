# Alysia

Alysia 是面向 B 站的自主创作者系统：把选题、研究取证、脚本、分镜、配音、剪辑、质检与投稿准备串成一条可恢复的流水线，并在审核与发布两处保留人工闸门。当前版本 `v0.1.0-alpha.22`。

它的目标不是生成看起来热闹的 AI 视频，而是产出**依据可查、失败可续、边界清楚**的内容。系统默认只做到投稿准备包，真实发布需要具名的人工确认。

- 许可：[MIT](LICENSE)
- 参与开发：[CONTRIBUTING.md](CONTRIBUTING.md)
- 安全问题：[SECURITY.md](SECURITY.md)
- 本地启动：[docs/local_start_zh.md](docs/local_start_zh.md)

## 安装与最小验证

```powershell
git clone <your-fork-url> alysia
Set-Location alysia
uv sync --extra dev --python 3.11
uv run python -m alysia doctor
uv run python -m alysia create "为什么AI Agent还不是AGI？" --provider mock
```

不需要 GPU、模型权重或平台凭证就能跑通 mock 文本链路；本地音视频、H3 生成与真实投稿属于可选能力，按 `doctor` 的实时结果逐步补齐。

## 当前能力

当前已打通可恢复、可缓存的文本、音频与视频流水线：

```text
中文 Topic
  → ResearchResult
  → EvidenceSource normalization
  → Claim extraction + verification + conflict/freshness checks
  → versioned KnowledgeStore
  → Writer grounding + per-run knowledge snapshot
  → Script
  → Storyboard
  → Text QA
  → milestone: text_ready
  → Scene TTS
  → narration.wav + audio_manifest.json
  → deterministic subtitles
  → Audio QA
  → milestone: audio_ready
  → composition.json
  → Mock / Remotion Render
  → FFmpeg H264/AAC normalize
  → ffprobe + decode QA
  → milestone: video_ready
  → Title + Description + Tags + Template Cover
  → publish package + traceability metadata
  → Pre-Publish QA
  → milestone: review_ready
  → Human Review
  → Manual / Mock Analytics Import
  → Content Fingerprint + Derived Metrics
  → Performance Analysis
  → Episode + Tentative Lessons
  → Strategy Recommendation + Next Experiment
  → milestone: strategy_ready
  → Trend Snapshot + Historical Runs + Memory
  → Topic Candidates + Explicit Weighted Scoring
  → Editorial Review + Planning QA
  → 7-day Content Plan
  → Human Approval Gate
  → traceable CREATED run
  → REVIEW_READY + Publish Review
  → ApprovalRecord + package hash
  → PublishJob + Mock / Bilibili adapter
  → FEEDBACK_WAITING
  → Manual / Mock feedback ingestion
  → existing Analytics + Memory/Lessons
  → Channel Memory + Multi-video Analysis
  → Audience Model + Controlled Experiments
  → Evidence-linked Strategy Evolution
  → Long-term Creator Dashboard
  → Versioned Creator Identity + Brand Voice
  → Prompt Context Assembly + Style Consistency QA
  → Explainable ProductionPlan + Provider Routing
  → Sequential GPU Resource Gate + Audited Fallback
  → Execution Metrics + Cache + Cost/Quality Report
  → StudioDirector + Role Registry
  → Controlled Context + Handoff + Artifact Ownership
  → Sequential Agent Results + Trace + Studio QA
```

- 每一步均使用 Pydantic schema 校验结构化输出。
- 每一步完成后写入 `run_state.json` 和对应 artifact。
- `resume` 默认跳过已完成且产物仍存在的阶段；`--force` 可重新执行。
- Mock provider 完全离线，可用于测试和演示。
- Ollama provider 支持结构化输出，但不会自动安装 Ollama 或下载模型。
- Text QA 只做主题、结构、引用、重复和时长的启发式检查，不声称替代事实核查。
- 默认使用 Windows SAPI 中文语音并记录词级起始时间；MockTTS 只供离线测试，默认无法通过正式 Audio QA。
- Voice Worker 按 scene 缓存音频；输入 hash 未变化时不重复调用 TTS。
- `voice --force` 会在状态中使旧字幕与 Audio QA 失效（不删除文件），下一次 resume 会安全重建下游产物。
- 旁白固定为 PCM16、mono；默认 24000Hz，scene 之间插入可配置短停顿。
- 字幕保留 Storyboard 原始文字；SAPI 使用 TTS 词时间戳对齐，其他 provider 可回退到确定性时长分配。
- faster-whisper 仅作为可选时间校准器；不可用时自动保留 deterministic 主路径。
- Audio QA 检查可解码性、时长、静音、clipping、持续测试音/稳定噪声、manifest、字幕边界和文本覆盖，但不声称是广播级响度检测。
- Storyboard、音频 manifest 与字幕会确定性转换为 30fps composition 时间线。
- Remotion 模板支持 Title、Text、Image、Diagram、Quote、Code 与 Chart scene；图片缺失时使用 placeholder。
- FFmpeg 将 renderer 中间产物统一规范化为 1080p、H264、48kHz stereo AAC，并通过 ffprobe 与完整解码检查。
- `render` 从 `audio_ready` 直接生成 `final.mp4`；成功后只标记 `video_ready`，不会提前标记整项任务 completed。
- `package` 从 `video_ready` 生成 5 种可解释标题候选、简介、章节、标签、模板封面和投稿元数据。
- 标题规则禁止虚假承诺、绝对化表达和无依据数字；最终候选仍需人工审核。
- 简介只引用已有 Research 来源；`.invalid`、`.test` 与 localhost 测试地址不会进入可发布链接。
- `publish-check` 校验视频及其 alpha.4 QA、标题、简介来源字段、标签和封面，并只推进到 `review_ready`。
- 发布包记录输入 artifact 和 SHA-256，便于追溯到 Research、Script、Storyboard 与 final.mp4。
- alpha6 可通过 JSON/CSV 离线导入单条视频的指标，缺失字段保持 `null`，不会补造数据。
- 每个派生指标都记录值、公式、实际输入和缺失输入；无法计算时值为 `null`。
- Content Fingerprint 只读取现有 run artifacts，记录标题风格、hook、字幕密度、叙事速度、视觉类型、来源和包装特征，不调用 LLM 猜测。
- Performance Analysis 明确区分事实、低置信度假设、异常和缺失数据，不把单条视频的相关性写成因果关系。
- 长期记忆使用可审计 JSON：episode、lesson、strategy 和 index；同一 run 重复 `learn` 不会重复增加证据或置信度。
- 单条视频只形成 `tentative` lesson；至少两个独立真实 run 支持且置信度达到阈值后才可变为 `supported`。相反证据可在后续版本将其降级或标记 `rejected`。
- Mock/testing 指标会永久标记为测试来源，绝不晋升为正式 `supported` lesson。
- 策略只输出带 evidence、confidence、risk 与 test plan 的建议，不自动修改配置、源码或启动下一条 create 任务。
- Creator Profile 以可审计 YAML 固定频道目标、领域、受众、格式、风险与来源要求，不依赖隐式 prompt。
- Trend Provider 支持离线 Mock、手工 JSON/CSV 和显式公共 JSON feed；缺失热度保持 `null`，相同来源/主题会去重。
- Topic Candidate 同时参考趋势、历史主题和 alpha.6 Next Experiment；评分由配置权重计算并保存完整 breakdown。
- Editorial Board 是单编排器中的 Scout/Editor/Critic 逻辑，不启动并发多 Agent runtime。
- Content Plan 会分散同类主题，并持久化为 JSON/Markdown；Creator Loop 的单次 tick 在计划窗口内幂等。
- 所有计划默认进入 Human Approval Gate。只有显式 `plan approve` 才创建 `CREATED` content run，仍不会自动制作或发布。
- Mock trend 计划强制 `testing=true`；其批准 run 也保留 testing provenance，不能冒充真实平台趋势。
- PublishJob 持久化 draft/approved/submitting/submitted/failed/cancelled 状态；同一包重复提交保持幂等。
- 所有 submit 都要求人工 ApprovalRecord，审批绑定完整投稿包 SHA-256；包变化后必须重新审批。
- 发布验证同时检查 video/publish QA、视频、封面、metadata、mock 产物、未接受 warning 与审批状态。
- 默认 `publishing.provider=mock`；Bilibili provider 只读取环境注入的官方开放平台凭证，不保存密码、cookie 或 token。
- Feedback 支持 Manual JSON/CSV、Mock 与 Bilibili 接口边界，并保持 run_id/external_id 映射与幂等。
- 评论只生成轻量 CommentInsight，不自动回复；发布记忆明确标记 real/mock/manual。
- Mock feedback 映射为 testing，不能把 lesson 晋升为 supported。
- 每个 `channel_id` 独立保存频道定位、发布历史、受众假设、案例、实验和长期策略；不共享 Creator Loop 状态。
- 跨视频分析显式输出指标样本数、最佳/最弱 run、前后窗口变化、内容疲劳信号和主题生命周期；缺失数据不会被补造。
- Audience Model 只使用聚合内容指标与 CommentInsight，描述主题、格式和观看行为信号，不建立个人画像。
- Experiment Manager 使用 draft → human-approved → running → completed 生命周期；同一实验一次只改变一个变量并记录 control variables。
- 策略证据链为 `strategy → experiments → metrics → confidence`；至少两个合格的非测试正向实验才可升级为 `supported`。
- Creator Dashboard 是幂等 JSON 快照，汇总频道状态、近期表现、当前实验、待验证策略和下一步建议。
- Creator Loop 记录 `observe → analyze → experiment → create → publish → learn`，但创建、发布和实验仍保留人工门。
- Creator Identity 使用 YAML 当前版本和不可覆盖历史快照，明确 Alysia 是 AI 视频创作系统，不模拟真人身份或个人经历。
- Brand Voice、Visual Identity 和叙事模式均为配置；Writer/Director 的最终 prompt context 由统一 Builder 组装并保存到 run 中。
- Content Style Memory 只从 alpha9 的非测试成功案例提取观察；单条视频最多形成 tentative 规则，至少两个独立 run 和受控实验关联才可能成为 supported 风格信号。
- Style Consistency QA 只生成建议，不修改脚本、身份、频道方向或 pipeline milestone。
- Identity Change Proposal 默认 pending；只有明确人工审核者批准后才会创建新身份版本。
- alpha12 的 Agent 是职责/推理角色，不是独立进程；Researcher、Writer、StoryboardDirector、Designer、Voice、Editor、Critic、Publisher、Analyst 均由唯一 StudioDirector 串行调度。
- Agent 只能接收 ContextSelector 按角色裁剪的上下文；大文件正文留在 artifact 中，StudioContext 只保存引用、版本、摘要、约束、审批与决策。
- 每次角色切换必须形成结构化 AgentHandoff，每个角色必须返回 AgentResult；自由聊天式辩论、递归调用和无限反思均不支持。
- ArtifactCatalog 强制 owner/version/revision request。修改他人产物必须回到 owner，Audio QA fail 会定点返回 Voice，再从 Editor 继续，不重跑 Researcher/Writer。
- Studio 继续读取 alpha11 ProductionPlan 选择 provider；Agent 无权自行选择昂贵模型，也无权绕过发布、身份、实验或成本审批。

## 快速开始

```powershell
Set-Location <clone-dir>
uv sync --extra dev --python 3.11
uv run python -m alysia --help
uv run python -m alysia doctor
uv run python -m alysia create "为什么AI Agent还不是AGI？" --provider mock
uv run python -m alysia resume RUN_ID --tts-provider sapi --asr-provider none
uv run python -m alysia render RUN_ID --renderer remotion
uv run python -m alysia package RUN_ID --generator template
uv run python -m alysia publish-check RUN_ID
uv run python -m alysia analytics template RUN_ID
uv run python -m alysia analytics import RUN_ID --file metrics.json
uv run python -m alysia analyze RUN_ID
uv run python -m alysia learn RUN_ID
uv run python -m alysia strategy RUN_ID
uv run python -m alysia creator-loop tick
uv run python -m alysia plan show PLAN_ID
uv run python -m alysia plan approve PLAN_ID SLOT_ID
uv run python -m alysia publish review RUN_ID
uv run python -m alysia publish approve RUN_ID
uv run python -m alysia publish validate RUN_ID
uv run python -m alysia publish submit RUN_ID --provider mock
uv run python -m alysia feedback import RUN_ID --provider mock
uv run python -m alysia operations refresh --channel main
uv run python -m alysia operations dashboard --channel main
uv run python -m alysia identity show
uv run python -m alysia identity check RUN_ID
uv run python -m alysia style check RUN_ID
uv run python -m alysia production plan RUN_ID --quality standard
uv run python -m alysia production status RUN_ID
uv run python -m alysia production report RUN_ID
uv run python -m alysia identity propose
uv run python -m alysia experiment create "缩短开场是否提升留存" --variable hook_length_sec --metric completion_rate --controls topic,title_style
uv run pytest
```

也可以直接使用虚拟环境中的解释器：

```powershell
.\.venv\Scripts\python.exe -m alysia doctor
.\.venv\Scripts\python.exe -m alysia create "为什么AI Agent还不是AGI？" --provider mock
.\.venv\Scripts\python.exe -m pytest
```

## CLI

```powershell
# 创建并运行到 text_ready
python -m alysia create "主题" --provider mock

# 查看状态
python -m alysia status RUN_ID

# 从 text_ready 幂等恢复到 audio_ready；若开始时已是 audio_ready，则推进到 video_ready
python -m alysia resume RUN_ID --tts-provider sapi --asr-provider none

# 明确重跑当前可恢复阶段
python -m alysia resume RUN_ID --force

# 从 audio_ready 渲染真实、可检查的简化视频（测试默认使用 mock）
python -m alysia render RUN_ID --renderer mock

# 使用 Remotion 模板渲染；--force 会重新生成视频和视频 QA
python -m alysia render RUN_ID --renderer remotion --force

# 从 video_ready 生成投稿前内容包和 1280x720 确定性模板封面
python -m alysia package RUN_ID --generator template

# 使用离线 Mock 封面生成器（测试用途）
python -m alysia package RUN_ID --generator mock --force

# 执行发布前 QA；通过后只进入 review_ready 人工审核门
python -m alysia publish-check RUN_ID

# 只生成或重做真实中文旁白；mock 仅用于测试
python -m alysia voice RUN_ID --tts-provider sapi

# 从已有 audio manifest 生成字幕、QA，并标记 audio_ready
python -m alysia subtitle RUN_ID --asr-provider none

# 查看音频里程碑和关键产物
python -m alysia audio-status RUN_ID

# 列出本地任务
python -m alysia runs

# 生成手工指标模板；所有未知平台字段均为 null
python -m alysia analytics template RUN_ID

# 离线导入一条 JSON/CSV 指标记录
python -m alysia analytics import RUN_ID --file metrics.json

# 依次生成表现分析、长期记忆、策略与下一实验
python -m alysia analyze RUN_ID
python -m alysia learn RUN_ID
python -m alysia strategy RUN_ID

# 审计长期 lesson
python -m alysia memory list
python -m alysia memory show LESSON_ID

# 生成趋势导入模板并导入 JSON/CSV 快照
python -m alysia trends template
python -m alysia trends import --file trends.json

# 显式创建新计划，或执行幂等的单次 Creator Loop tick
python -m alysia plan create
python -m alysia creator-loop tick
python -m alysia creator-loop status

# 查看并人工批准/拒绝槽位；批准只创建 traceable run，不自动投稿
python -m alysia plan show PLAN_ID
python -m alysia plan approve PLAN_ID SLOT_ID
python -m alysia plan reject PLAN_ID SLOT_ID

# 只有 approved slot 才能由用户显式启动现有文本创作管线
python -m alysia creator-loop run PLAN_ID SLOT_ID

# 人工审核、批准、验证并创建 Mock PublishJob
python -m alysia publish review RUN_ID
python -m alysia publish approve RUN_ID
python -m alysia publish validate RUN_ID
python -m alysia publish submit RUN_ID --provider mock
python -m alysia publish status JOB_ID

# 导入只读反馈，再复用 alpha6 的 analyze/learn
python -m alysia feedback import RUN_ID --provider mock
python -m alysia analyze RUN_ID
python -m alysia learn RUN_ID

# 查看身份、历史和 run 级 Prompt Context 审计
python -m alysia identity show
python -m alysia identity history
python -m alysia identity check RUN_ID

# 只读 Style QA；报告写入 runs/<run_id>/qa/
python -m alysia style check RUN_ID

# 创建待人工批准的身份提案；不会自动修改当前身份
python -m alysia identity propose

# Multi-Agent Creator Studio：角色、执行、状态、trace 与幂等恢复
python -m alysia studio agents
python -m alysia studio run RUN_ID
python -m alysia studio status RUN_ID
python -m alysia studio trace RUN_ID
python -m alysia studio resume RUN_ID
```

单次任务保存在 `runs/<run_id>/`，主要产物包括：

```text
input.json
run_state.json
research.md
sources.json
script.md
script.json
storyboard.json
metadata.json
text_qa_report.json
audio/scenes/scene_001.wav
audio/narration.wav
audio/audio_manifest.json
subtitles/subtitles.srt
subtitles/subtitles.json
audio_qa_report.json
video/composition.json
video/assets_manifest.json
video/render_config.json
video/render_result.json
output/final.mp4
qa/video_qa_report.json
publish/cover.png
publish/title.txt
publish/description.md
publish/tags.json
publish/metadata.json
publish/publish_package.json
publish/publish_qa_report.json
analytics/metrics_template.json
analytics/metrics.json
analytics/derived_metrics.json
analytics/content_fingerprint.json
analytics/performance_analysis.json
analytics/lessons.json
analytics/strategy_recommendations.json
analytics/next_experiment.json
analytics/learning_qa_report.json
publish/approval_record.json
publish/publish_job.json
publish/publish_validation_report.json
feedback/feedback.json
feedback/comment_insight.json
feedback/mapping.json
identity/prompt_context.writer.json
identity/prompt_context.director.json
identity/prompt_context.check.json
identity/identity_check_report.json
qa/style_consistency_report.json
production/production_plan.json
production/plans/draft.json
production/plans/standard.json
production/plans/high.json
production/execution_metrics.json
production/quality_gate_report.json
production/production_report.json
studio/studio_state.json
studio/studio_trace.jsonl
studio/handoffs.json
studio/decisions.json
studio/agent_results.json
studio/artifacts.json
studio/revision_requests.json
studio/studio_qa_report.json
studio/context_snapshots/context.v0001.json
logs/events.jsonl
```

## Autonomous Production Optimization

alpha11 在现有单总控编排器前增加 ProductionPlan。每个直接创建或经 Creator Loop 人工批准的 run 都会先根据任务阶段、quality target、7600 MiB 本地显存预算、provider 健康状态、网络/凭证约束、历史可靠性和成本证据生成计划。计划保存 selected provider、执行顺序、fallback chain、资源/成本说明、质量权衡、warnings、policy blockers 和排序后的 alternatives；选择理由不是黑箱结果。

三档 profile 的意图如下：

- `draft`：优先低时延、可复现的本地/mock 路径，允许更多 warning，但不能绕过需要人工确认的策略 blocker。
- `standard`：优先尊重当前已配置 provider，并要求已经到达的 text/audio/video/publish QA 全部通过。
- `high`：优先更高质量能力和二次 Style QA，但仍受 `max_retries_per_stage` 限制，不会无限修复。

Provider Capability Registry 统一登记 LLM、Research、TTS、ASR、Render、Cover 与确定性 QA/metadata worker。能力只记录声明或安全探测到的信息；显存、成本或 benchmark 无证据时保持 `null/unknown`。当前 cloud LLM 和 Web Research 仍是显式占位，因此健康状态为 unavailable，不会被计划选中。

RTX 4060 Ti 默认执行顺序是 `LLM → unload → TTS → unload → ASR → unload → visual(optional) → render`。ResourceManager 使用单 GPU-heavy mutex、阶段 acquire/release、provider unload/cleanup、可选 CUDA cache 清理、`nvidia-smi` 前后探测、timeout 与 OOM 分类；不实现多 GPU 或 GPU-heavy 并发。

Fallback 不允许静默发生。每次降级记录 original choice、failure reason、fallback choice 和 quality impact。Remotion 可以在健康检查确认 FFmpeg 可用时降级到现有 `MockVideoRenderer` 的简化 FFmpeg 渲染；ASR CUDA/模型失败可回退 CPU 或确定性字幕时间，但必须写入 fallback 审计。

Execution Metrics 位于 `runs/<run_id>/production/execution_metrics.json`，包含 stage 时延、provider、成功/失败、retry、可测时才记录的 peak VRAM、输入/输出规模、cost status、cache hit 和 fallback。成本只允许 `known`、`estimated_with_source` 或 `unknown`；本地执行不会伪造电费，cloud provider 未返回可验证 usage/price 时也不会估价。

Production Cache 使用 normalized input、provider/version 和 config 的稳定哈希，覆盖 Research、Script、Storyboard、scene TTS、subtitle alignment 和 render composition。Research 强制 TTL；默认 `research_cache_ttl_hours=24`，不会永久复用时效性资料。

```powershell
python -m alysia production plan RUN_ID --quality draft
python -m alysia production plan RUN_ID --quality standard
python -m alysia production plan RUN_ID --quality high
python -m alysia production status RUN_ID
python -m alysia production report RUN_ID
```

如果设置了 `max_cloud_cost`，而入选 cloud provider 的成本无法由可验证来源证明不超预算，计划会进入 policy blocker。只有显式的人类审核者可以运行 `production approve-policy RUN_ID --approved-by NAME` 接受该次计划风险；该操作不修改全局预算，也不替代内容或发布审批。

## Multi-Agent Creator Studio

alpha12 在既有 Orchestrator 外增加兼容包装层，不重写 Topic → Video → Publish。`StudioDirector` 是唯一总控，根据 pipeline phase、required artifacts、QA、ProductionPlan 与 approval state 规则化选择下一角色；LLM 只能提供建议，不能覆盖硬路由。默认 `studio.mode=sequential`，最多 2 轮 review、20 次 agent hop，达到上限后停止并升级 Human Review。

角色与执行层严格分离：Agent 定义职责、输入、产物、质量责任和升级规则；Worker/Provider 继续执行调研、LLM、TTS、字幕、渲染、封面、发布和分析。Designer 使用确定性模板封面；Publisher 复用 Designer-owned cover，并只在现有 Human Approval Gate 之后验证或创建 PublishJob。

每次切换都保存 `AgentHandoff`，每次执行都保存 `AgentResult`。Artifact owner 固定为 Researcher→research、Writer→script、StoryboardDirector→storyboard、Designer→design/cover、Voice→audio/subtitles、Editor→final.mp4、Critic→review、Publisher→publish package、Analyst→analytics/memory/strategy。修订创建新 version，不直接覆盖他人 ownership 记录。

`studio trace` 读取 `runs/<run_id>/studio/studio_trace.jsonl`，可看到路由原因、handoff、输入 artifact、fallback、QA 返工与 escalation；token、secret、password、cookie、authorization 和 API key 字段会被脱敏。StudioQA 检查交接完整性、owner/version、循环上限、required artifact、未解决 escalation 和 mock provider 的真实发布误用。

## Autonomous Supervisor 与长期计划

alpha13 在 Creator Studio 外增加长期治理层，但不改变单条内容流水线：

```text
AutonomousSupervisor（长期 Goal / Plan / Project）
  → CreatorLoop（选题计划、人工内容批准、run 创建）
  → StudioDirector（单个 run 的角色路由与产物恢复）
  → Agents / Workers / Providers
```

Supervisor 管多个连续内容项目的优先级、依赖、预算、风险和 review point；StudioDirector 仍只管理一个 run。Supervisor 不直接调用 Writer、Voice、Renderer 或 Publisher，也不能替人批准发布、身份重大变化、预算超限或重大 replan。

- `Goal`：显式长期目标，包含日期范围、可测量指标、预算、审批策略和停止条件；可以 active、paused、blocked、completed 或 cancelled。
- `LongHorizonPlan`：Goal 的版本化执行方案，包含 milestones、projects、dependency graph、review points、resource budget 和 risk register。
- `ContentProject`：由多个相关 run、experiment 和 publishing activity 组成的系列或 campaign；它不是单个 Agent task。
- `ReplanProposal`：保存新版本计划和影响，但不会覆盖当前计划；默认等待人工批准。

Supervisor 采用单次 tick，不启动后台 daemon。每次 tick 最多执行 `supervisor.max_actions_per_tick` 个高层动作、最多派发 `max_dispatches_per_tick` 个 run；达到日/周 run、cloud cost、失败次数或 active project 限制时自动暂停或要求批准。

```powershell
python -m alysia supervisor goals
python -m alysia supervisor plan demo_goal
python -m alysia supervisor tick
python -m alysia supervisor status
python -m alysia supervisor blockers
python -m alysia supervisor review demo_goal
python -m alysia supervisor qa
python -m alysia supervisor goal-status GOAL_ID paused
python -m alysia supervisor approve-run PLANNED_RUN_ID --approved-by HUMAN_NAME
python -m alysia supervisor replan GOAL_ID --reason "provider unavailable"

# 完全离线的四期系列、hook 实验、blocker、budget pause 与 replan 演示
python -m alysia supervisor demo
```

长期产物默认保存到 `supervisor/`：

```text
supervisor/
├── goals/
├── plans/<goal_id>/
├── projects/
├── reviews/
├── replans/
├── supervisor_state.json
├── supervisor_trace.jsonl
└── supervisor_qa_report.json
```

Cross-run Context 只选取频道定位、supported lessons/strategies、active experiments、当前 identity 摘要和生产健康摘要；不会把全部历史或大文件正文塞给下游 Agent。

长期记忆位于：

```text
memory/
├── episodes/<run_id>.json
├── publish_episodes/<run_id>.json
├── lessons/<lesson_id>.json
├── strategies/<strategy_id>.json
├── channels/<channel_id>/
│   ├── channel_memory.json
│   ├── multi_video_analysis.json
│   ├── audience_model.json
│   ├── content_style_memory.json
│   ├── dashboard.json
│   └── experiments/<experiment_id>.json
└── index.json
```

身份与品牌资产位于：

```text
identity/
├── creator_identity.yaml
├── identity_card.md
├── history/creator_identity.v0001.yaml
└── proposals/identity_change_*.json
```

## Personality + Brand Identity

`CreatorIdentity` 是可配置、可审计的创作身份，不是对真实人类的模拟。当前身份包含使命、频道用途、内容哲学、目标观众、专业领域、排除主题、Brand Voice、Visual Identity、叙事模式、价值观和披露政策。`identity show` 在首次运行时创建 v1，并同步生成只包含安全配置字段的 `identity_card.md`。

Writer 和 Director 不各自硬编码人格。Orchestrator 使用 `PromptContextBuilder` 统一组合基础任务 Prompt、当前 Creator Identity、Brand Voice、带状态的相关 Strategy 和已人工批准/运行中的 Experiment，并将输入摘要及最终上下文保存为 `runs/<run_id>/identity/prompt_context.<role>.json`。tentative 策略会保留状态标签，不能被解释为永久规则。

`style check` 是旁路审计，不改变任何 pipeline milestone。它读取 Script、Storyboard、投稿标题/封面 metadata 和 Creator Identity，输出 `StyleConsistencyReport`。Visual Identity v1 与 alpha5 模板封面 metadata 对接，但颜色和字体当前只作为配置，不会触发 AI 图片生成或强制重绘旧封面。

身份演进采用 `Observation → Proposal → Human Approval → New Version`。`identity propose` 只写 pending proposal；系统身份、Alysia、agent 或 automation 不能作为审核者。旧历史文件不会被覆盖，过期版本 proposal 也不能应用。

## Long-term Creator Operations

`operations refresh` 只汇总已经存在的 run、Analytics、Feedback、Memory 和 Experiment 证据。旧 run 没有频道来源时只归入 `operations.default_channel_id`；新 Content Plan 和 run 会显式携带 `channel_id`。不同频道的长期状态和 Creator Loop 状态文件相互隔离，但不会触发真实账号登录或批量操作。

实验默认是 `draft`。必须显式执行 `experiment approve --approved-by HUMAN` 后，才能用 `experiment assign` 分配 control/treatment run；两组达到最小样本数且 Analytics 来源与分配来源一致后，才能 `experiment evaluate`。评估只写结果与证据，不自动修改配置、脚本或全频道策略。

Dashboard 的结论是运营辅助信号：内容疲劳与主题生命周期均使用透明启发式阈值，并附 run 证据；样本不足时输出 `insufficient`，不会输出伪精确结论。

alpha.7 规划产物位于：

```text
plans/<plan_id>/
├── creator_profile.json
├── trends.json
├── topic_candidates.json
├── topic_scores.json
├── editorial_decision.json
├── content_plan.json
├── content_plan.md
└── planning_qa_report.json
```

## Autonomous Topic Selection

`Trend Research` 只回答“为什么现在值得考虑这个主题”，不是脚本事实库。候选被人工批准后，新 run 仍从现有 Research 阶段开始；趋势摘要不会直接被当成脚本事实。`input.json` 与 `run_state.json` 会记录 plan、slot、趋势来源、关联实验、testing 标记和 Research handoff。

选题总分由配置中的显式权重计算：频道相关性、新鲜度、受众匹配、相对历史的新颖性、证据质量、制作可行性和实验价值提供正分；重复与风险提供惩罚。命中 excluded domain、与近期历史高度重复、或时效性论证证据过弱会被 Critic 直接淘汰。LLM 不能单独黑箱决定选题。

Creator Loop 默认 `enabled: false`、`require_human_approval: true`。显式调用 `creator-loop tick` 只执行一次规划；在 `planning_interval_hours` 内再次 tick 会复用当前计划。应用不会修改 Windows Task Scheduler，也不会后台常驻。

## Analytics 与学习边界

指标比例统一使用 `0..1`，例如 CTR 4.2% 写作 `0.042`。模板不会填写任何未知值；派生指标只有在所需输入齐全且分母有效时才计算。`PerformanceAnalysis` 中的 `facts` 只来自导入值或显式公式，`hypotheses` 必须附证据、置信度和“相关不等于因果”的声明。

Lesson 状态含义：

- `tentative`：单样本或证据不足的候选经验。
- `supported`：至少两个独立真实 run 支持，且置信度达到门槛；仍不等于因果定律。
- `rejected`：预留给后续相反证据审查；alpha6 不会无依据自动拒绝 lesson。

`strategy` 的定位是设计下一次可验证实验，默认建议未来 3 条相近内容一次只改变一个变量。它不会自动修改全局配置，也不会自动开始制作或投稿。

## Trend 与 Research 的边界

- Trend：公开快照、手工导入或 mock 测试信号，用于选题时机和候选排序。
- Research：候选获批后重新执行的正式资料收集，用于支撑脚本事实。
- MockTrendProvider：只用于离线测试，计划与 run 永久保留 testing 标记。
- WebTrendProvider：只读取显式配置的公共 JSON feed；不登录平台、不抓取账号数据、不猜测缺失热度。

## 配置

按需复制示例文件，真实配置和密钥不会被 Git 跟踪：

```powershell
Copy-Item config.example.yaml config.yaml
Copy-Item .env.example .env
```

`config.example.yaml` 中的文本阶段配置：

```yaml
llm:
  provider: mock           # mock | ollama | cloud（占位）
  model: qwen3.5:4b
  base_url: http://127.0.0.1:11434

content:
  language: zh-CN
  min_duration_sec: 120
  max_duration_sec: 300
  default_duration_sec: 180

research:
  provider: mock           # web 目前只有接口骨架
  max_sources: 5

runtime:
  retries: 1
  runs_dir: runs
  sequential_gpu: true

tts:
  provider: sapi
  language: zh-CN
  voice: default
  speed: 1.0
  sample_rate: 24000
  pause_between_scenes_ms: 250
  allow_test_tone: false

asr:
  enabled: false
  provider: faster-whisper
  model: small
  device: cuda
  compute_type: int8_float16
  local_files_only: true

subtitle:
  max_chars_per_line: 22
  min_duration_sec: 0.8
  max_duration_sec: 6.0
  deterministic_default: true
  font_size: 54
  position: bottom
  max_width: 0.82

video:
  renderer: remotion       # mock | remotion
  width: 1920
  height: 1080
  fps: 30
  codec: h264
  audio_codec: aac

render:
  temp_dir: video/temp
  output_dir: output
  remotion_dir: video/remotion
  ffmpeg_path: null
  ffprobe_path: null

publish:
  title_candidates: 5
  cover:
    width: 1280
    height: 720
    format: png
  tags:
    max_count: 10

publishing:
  provider: mock
  require_approval: true
  save_credentials: false
  workspace_dir: workspace/publishing

feedback:
  provider: manual

security:
  redact_credentials: true

qa:
  strict: false

learning:
  memory_dir: memory

identity:
  enabled: true
  require_approval: true
  version_control: true
  directory: identity

brand_voice:
  technical_level: medium
  humor_level: low
  evidence_priority: high

visual_identity:
  template_version: v1
```

使用本地 Ollama 时，将 `llm.provider` 改为 `ollama`，或为单次创建传入 `--provider ollama`。必须先自行确认 Ollama 服务和指定模型已经存在；Alysia 不会自动下载模型。正式发布内容前还需要真实的 Research provider，Mock 来源只用于离线验收。

使用 CosyVoice 时，必须先在隔离环境中准备兼容的 `cosyvoice` 包和本地模型目录，再将 `tts.provider` 设为 `cosyvoice`、配置 `tts.model_dir`。Alysia 不会自动下载模型。faster-whisper 同样是可选项，默认 `local_files_only: true`；缺少包、模型或 CUDA 时，不影响 deterministic 字幕。

## 字幕对齐策略

- `tts`（SAPI 默认）：字幕文字来自 Storyboard narration，边界使用真实 TTS 词时间戳；不会产生 ASR 识别错字。
- `deterministic`（回退）：provider 没有词时间戳时，按实际 scene 音频时长切句和分配时间。
- `asr`（可选增强）：faster-whisper 只校准 scene 内的语音边界，不覆盖脚本文字。校准失败时记录日志并回退到 deterministic。

## RTX 4060 Ti 8GB 资源策略

Alysia alpha11 默认以 7600 MiB 作为本地计划预算，并串行执行 GPU-heavy provider。进入 TTS 或 ASR 阶段时记录资源 phase，退出时调用 provider 的 `unload/cleanup`，并在 torch 可用时清理 CUDA cache。`nvidia-smi` 只记录真实探测值；没有连续采样时 `peak_vram_mb` 保持 `null`。视频阶段使用 Remotion、CPU/FFmpeg 编码，不引入 ComfyUI 或 AI 视频模型。

## Remotion 与 FFmpeg

Remotion 位于 `video/remotion`，只负责把 `video/composition.json` 渲染成中间 MP4。Python worker 随后调用 FFmpeg 做尺寸、帧率、H264/AAC、响度与 faststart 规范化，最后由 ffprobe 解析流信息并执行完整解码检查。

```powershell
Set-Location .\video\remotion
npm install
npm run check
```

工具发现顺序为：配置中的显式路径、当前 PATH、winget 的 Gyan.FFmpeg 安装目录。因此新终端尚未刷新 PATH 时，Alysia 仍可找到已经安装的 FFmpeg。

## 当前明确不支持

- Bilibili 网页自动登录、cookie 投稿或未经官方应用授权的真实提交
- 自动回复评论或私信
- 未配置公开 WebSearchAdapter 时的自动联网 Research；Alysia 不自行登录、绕过 robots/认证/付费墙
- Cloud LLM 实际 API 接入
- 自动安装 CosyVoice、faster-whisper 或大型本地模型
- 专业广播级响度标准化与母带处理
- 自动绕过人工审核门；`review_ready` 不等于 `published`
- 未经官方授权的 B 站 Analytics 自动访问、登录或账号抓取
- 根据一次视频自动强制更改创作策略
- 根据单个实验自动升级为 supported 策略，或让 mock/testing 实验进入正式证据链
- 跨频道共享运营记忆、实验状态或 Creator Loop 状态
- 自动修改 Alysia 自身源码或无人工触发地后台启动创作循环
- 自动修改 Creator Identity、Brand Voice 或频道方向
- 编造个人经历、现实身份或冒充真人创作者
- 将单条视频风格或 mock/testing 结果升级为永久品牌规则
- 无人工批准直接创建真实内容任务
- 将 mock trend 或搜索摘要当作真实平台趋势、正式事实或发布依据

## 待补齐的外部工具

环境诊断以 `python -m alysia doctor` 的实时结果为准。

- FFmpeg/ffprobe 已安装；`doctor` 会显示发现到的实际二进制路径。
- 安装并启动 Ollama 后运行 `ollama list` 验证。
- 后续需要本地文本模型时，再按需运行 `ollama pull qwen3.5:4b`；本轮不会自动下载模型。
- Remotion 依赖与 Headless Shell 已安装；首次在新机器运行时可能需要下载浏览器运行时。

## 目录说明

- `alysia/core`：配置、Run 持久化、状态与编排
- `alysia/agents`：Researcher、Writer、Director、TextCritic、Title、Description 与 Tag
- `alysia/workers`：音频、composition、FFmpeg 后处理、投稿包与音视频/发布前 QA
- `alysia/providers`：LLM、Research、TTS、ASR、Video、Cover、Analytics 与 Trend provider
- `alysia/analytics`：派生指标、内容指纹与表现分析
- `alysia/learning`：长期记忆、Lesson、Strategy、Planner 与 Learning QA
- `alysia/planning`：Creator Loop、候选生成、规则评分、去重、Editorial Board、排期、审批与 Planning QA
- `alysia/publishing`：PublishJob、人工审批、包哈希、验证、状态持久化与安全提交
- `alysia/feedback`：反馈导入、CommentInsight、VideoMetrics 映射与幂等回流
- `alysia/operations`：频道记忆、跨视频分析、受众模型、实验管理、策略证据链与 Dashboard
- `alysia/identity`：版本化身份、Brand Voice、Style Memory、Style QA、叙事库、Prompt Context 与变更审批
- `alysia/studio`：单 Director、Agent Registry、受控 Context、Handoff、Result、Ownership、Trace、规则路由与 Studio QA
- `alysia/knowledge`：Evidence/Claim 分离、来源评分、验证、冲突、TTL、版本替代、Grounding、Knowledge QA 与维护任务
- `alysia/schemas`：Research、Script、Storyboard、Audio、Video、Publish、Analytics、Learning、Planning 与 QA 结构化模型
- `alysia/prompts`：各角色独立 prompt
- `video/remotion`：React + Remotion 程序化视频模板
- `skills/narrative`、`identity`、`memory`、`evaluation`：叙事模板、身份历史、长期记忆与评测
- `assets`、`runs`、`plans`、`knowledge`、`workspace/trends`、`workspace/publishing`：静态素材、内容 run、规划产物、证据化知识、趋势快照与 PublishJob

第一阶段环境检测见 `setup_report.md`；alpha.2 文本实现见 `development_report_alpha2.md`；alpha.3 音频实现见 `development_report_alpha3.md`；alpha.4 视频实现见 `development_report_alpha4.md`；投稿包见 `development_report_alpha5.md`；学习闭环见 `development_report_alpha6.md`；自主选题见 `development_report_alpha7.md`；发布反馈闭环见 `development_report_alpha8.md`；长期运营层见 `development_report_alpha9.md`；创作者身份与品牌层见 `development_report_alpha10.md`；生产优化层见 `development_report_alpha11.md`；Creator Studio 见 `development_report_alpha12.md`；长期 Supervisor 见 `development_report_alpha13.md`；本地生成视觉见 `development_report_alpha13_5.md`；Capability/Skill 见 `development_report_alpha14.md`；Workflow 学习见 `development_report_alpha15.md`；反事实模拟见 `development_report_alpha16.md`；证据化知识维护见 `development_report_alpha17.md`；统一回归评测见 `development_report_alpha18.md`。

## Bilibili 官方能力边界

[哔哩哔哩开放平台](https://open.bilibili.com/doc) 当前公开说明包含账号授权、视频稿件发布/删除/查询和稿件数据能力，但要求开发者身份认证、应用接入与关联 UP 主授权。alpha.8 不猜测登录后才可核验的上传 endpoint，也不使用网页自动登录；`BilibiliPublishingProvider` 与 `BilibiliFeedbackProvider` 在凭证或已核验官方请求契约缺失时会安全失败且不发出网络请求。
## alpha13.5：Local Generative Visual Engine

Alysia 现支持按镜头把视觉任务路由到 Remotion、静态资源或本地 ComfyUI/MiniMax H3。H3 仅用于受预算约束的重点动态镜头，GPU-heavy job 默认串行，原生音轨默认丢弃，主旁白和字幕仍由既有链路负责。

```powershell
python -m alysia visual doctor
python -m alysia visual h3-setup-status
python -m alysia visual h3-smoke-test
python -m alysia visual plan <run_id>
python -m alysia visual generate <run_id> --provider comfyui-h3
python -m alysia visual status <run_id>
```

真实运行配置采用 RTX 4060 Ti 8 GB VRAM + 24 GB RAM 保守预算，当前机器检测事实另见 `config/current_machine_profile.yaml`。2026-08-08 的首次 T2V 实测为 608x352、73 帧、6 steps、170.81 秒，峰值 VRAM 7678 MiB、系统 RAM 使用 25918.8 MiB，VisualQA PASS；因此 H3 capability 仍保持 experimental。Mock 视觉产物只验证工作流，不能进入 production review。完整部署与限制见 `setup_h3_local.md` 和 `development_report_alpha13_5_runtime.md`。

### 动态壁纸制作（单图 H3 视频）

这是独立于上述一次性 ComfyUI 队列的本地视觉工作流：以单张参考图和动作提示词生成 1280×720、90 帧、24 fps 的 MP4，首尾参考帧保持一致。H3 依次执行参考帧、文本/图像编码、采样、解码四个独立 GPU 阶段；提交前仍以实测增量显存通过 6144 MiB 预算预检，运行时对整卡显存按 7680 MiB（7.5 GiB）采样停止阈值及系统 RAM 24 GiB 上限监测。采样阈值不是驱动级硬限额。生成结果标记为待人工审看，不会自动发布。

```powershell
python -m alysia visual dynamic-wallpaper --image "C:/path/reference.png" --prompt-file "C:/path/motion-prompt.txt"
python -m alysia visual dynamic-wallpaper-resume "workspace/dynamic_wallpaper/wallpaper_<run_id>"
```

也可用 `--prompt "动作描述"` 代替 `--prompt-file`。每次运行在 `workspace/dynamic_wallpaper/` 下保存 `job.json`、`summary.json`、分阶段日志和最终 `dynamic_wallpaper_720p.mp4`；失败时保留这些记录以供排查和恢复。此配置仅对已验证的 MiniMax H3 模型及本机 ComfyUI 动态加载环境有效。

## alpha14：Capability Gap 与受控 Skill Acquisition

Alysia 可以从 QA、trace、执行指标和人工证据中识别能力缺口并生成 SkillProposal。新 skill 只能在逻辑 sandbox 中完成声明式评测，经独立 review 和 `human:*` 显式批准后，才会进入版本化 SkillRegistry。

```powershell
python -m alysia capability list
python -m alysia capability evaluate
python -m alysia gaps list
python -m alysia skill propose <gap_id>
python -m alysia skill test <skill_id>
python -m alysia skill review <skill_id>
python -m alysia skill approve <skill_id> --approved-by human:<name>
python -m alysia skill disable <skill_id>
python -m alysia skill rollback <skill_id> <version>
```

alpha14 不会自动下载未知代码、安装任意包、修改核心源码或批准自身 skill。

## alpha15：Capability Composition 与 Adaptive Workflow Learning

alpha15 在 alpha14 的受控 Skill Registry 外增加一个独立 workflow 层，用于把已经存在且允许执行的能力组合成有限 DAG。四个概念的边界如下：

- **Capability**：Alysia 现有 Agent、Worker、Provider 或治理层已经实现并登记的能力，包含 input/output contract、owner、成熟度、资源和 policy 限制。
- **Skill**：为能力缺口提出、在 sandbox 中评测并由人类批准注册的版本化能力；只有 active/registered 版本可被组合。
- **Workflow**：针对某个有明确成功标准的任务，由当前受信任能力临时组成的执行计划；它不是新代码。
- **Recipe**：多次成功 workflow 的程序性记忆，保存步骤模板、能力版本和 evidence runs；单次成功只能成为 candidate，默认三次独立成功后才 validated。

分层保持不变：Supervisor 决定长期“做什么”，WorkflowPlanner 决定“已批准能力如何组合”，StudioDirector 负责单条内容 run，ProductionPlanner 决定 provider/资源，SkillRegistry 决定 skill 是否可用。WorkflowRuntime 不能代替这些层审批或直接选择未知 provider。

Workflow 先通过规则化 CapabilityMatcher，再由 WorkflowPlanner 反向解析 desired outputs。WorkflowValidator 在执行前检查 registry 状态、input/output contract、DAG cycle、step/skill hop 上限、资源预算、mock/production 隔离和 publish/identity/budget approval points。未解决产物 contract 会进入 `blocked_waiting_capability`，并链接回 alpha14 CapabilityGap/SkillProposal；不会联网寻找或执行未知实现。

```powershell
python -m alysia workflow plan --task <task.json_or_task_id>
python -m alysia workflow validate <workflow_id>
python -m alysia workflow run <workflow_id>
python -m alysia workflow resume <workflow_id>
python -m alysia workflow status <workflow_id>
python -m alysia workflow report <workflow_id>
python -m alysia workflow qa <workflow_id>
python -m alysia workflow recipes
python -m alysia workflow recipe-show <recipe_id>

# 完全离线的 alpha15 演示
python -m alysia workflow demo-a
python -m alysia workflow demo-repair
python -m alysia workflow demo-b
python -m alysia workflow demo-c
```

每个 workflow 的可恢复状态和审计产物保存在：

```text
runs/<run_id>/workflow/
├── workflow_plan.json
├── workflow_state.json
├── step_results.jsonl
├── workflow_trace.jsonl
├── workflow_validation_report.json
├── workflow_evaluation_report.json
└── workflow_qa_report.json
```

执行默认严格顺序；已完成且 artifact 仍存在的 step 会幂等复用。失败只对当前 step 进行有限 retry、选择 contract 兼容的 active fallback、返回 artifact owner、跳过 optional step、人工升级或创建 capability gap，不从头重跑，也不允许无限 repair loop。

成功组合写入 `memory/workflows/`。Recipe retrieval 会重新检查 capability maturity 和 active skill version；版本变化、skill disable/deprecate 或 provenance 缺失会阻止复用。alpha15 的 meta-learning 只调整 recipe confidence、候选排序和 workflow 建议，不自动修改 prompt、provider、核心源码或永久策略。

## alpha16：World State Snapshot 与反事实模拟

alpha16 的 `WorldStateSnapshot` 只是 Alysia 当前可观测 artifact 的轻量快照，不是完整或真实的“世界模型”。它只读取现有 channel memory、goal、identity、experiment、provider health、doctor 与 execution metrics；来源缺失时保留 missing/unknown，不由模型补值。

Simulation 与现实数据严格分开：

- `known` 必须有 evidence ref；`derived` / `simulated` 必须记录 assumption；`unknown` 不得包含伪造 point/range。
- dry-run 不调用真实 publish、评论、私信或 H3 preview，不写真实 Analytics/Memory。
- PlatformOutcomeEstimator 只有足够真实历史数据时才允许宽区间相对估计；不会预测精确播放量、粉丝数或收益。
- Calibration 只把 prediction 与后续 actual artifact 比较，记录 error/bias 和 confidence/weight 建议；不会自动修改 estimator 源码或永久参数。

CounterfactualPlanner 对同一 objective 生成 2-5 个候选，并分别评估 production、content structure、risk、workflow recipe 和保守 platform outcome。比较结果包含逐维 score breakdown、dominant tradeoffs、uncertainty 与未选原因，而不是只输出黑箱总分。

```powershell
python -m alysia simulate create --task workspace/simulation/tasks/demo_a_visual_strategy.json
python -m alysia simulate run alpha16_demo_a_visual
python -m alysia simulate compare alpha16_demo_a_visual
python -m alysia simulate show alpha16_demo_a_visual
python -m alysia simulate calibrate alpha16_demo_a_visual --actual workspace/simulation/mock_actual_demo.json
python -m alysia simulate history
```

逻辑沙箱只写 `simulations/<scenario_id>/`：

```text
scenario.json
world_state_snapshot.json
candidates.json
simulation_results.json
comparison.json
decision.json
simulation_qa_report.json
trace.jsonl
```

这不是 OS 级安全隔离。路径 guard 只约束 simulation artifact 根目录；真实执行仍交给现有 StudioDirector、ProductionPlanner 与 Publisher。默认决策策略为 conservative：只有低风险、无发布/预算超限/身份变更/重大 replan 且 scenario 明确允许的内部计划，才可标记 `auto_select`；Supervisor 集成仍只消费 recommendation，不直接执行模拟步骤。所有发布、身份、预算和重大 replan 继续要求既有 Human Approval Gate。

## alpha17：Autonomous Research & Knowledge Maintenance

alpha17 把 Research 产物拆成两个不同对象：`EvidenceSource` 描述来源与获取条件，`KnowledgeClaim` 描述可被验证、冲突、过期和替代的陈述。Source 不等于 Fact；模型记忆、趋势、模拟、评论或 mock fixture 都不能单独晋升为 verified fact。

边界如下：

- **Trend**：回答“为什么现在做”，只用于选题线索。
- **Research**：围绕具体问题收集来源与候选 claim，受 max sources/rounds 和 stop condition 限制。
- **Knowledge**：只保存通过来源策略的 verified/provisional claim，并保留证据、scope、时间、TTL、冲突和版本。
- **Simulation**：永远写入 simulation artifacts，不写事实库。
- **Feedback/Comments**：只进入受众与内容 insight，不作为权威事实。

可变事实按领域采用不同 freshness 默认值。software/model version、pricing/API rules、current roles 与 stable definition 的 TTL 独立配置；到期后产生 `ReverificationTask`，关键 stale/conflicted claim 会使 Grounding/Knowledge QA 失败。更新可变事实时创建新 claim，并把旧 claim 标记为 superseded，不覆盖旧视频保存的来源快照。

每个使用知识的正式 run 保存：

```text
runs/<run_id>/knowledge/
├── claims_used.json
├── source_snapshot.json
├── grounding_report.json
└── knowledge_qa_report.json
```

StudioContext 只通过 `KnowledgeContextSelector` 提供与 topic/role 相关、仍然新鲜的 claim，不把整个知识库塞入 prompt。Supervisor 只能检查 readiness、创建 KnowledgeGap；Workflow 可以组合受控 Research/Verification/Writer adapter；ProductionPlanner 仍只负责 provider/resource，发布审批门保持不变。

```powershell
python -m alysia knowledge status
python -m alysia knowledge claims --topic "H3 local capability"
python -m alysia knowledge sources --claim <claim_id>
python -m alysia knowledge conflicts
python -m alysia knowledge stale
python -m alysia knowledge verify <claim_id>
python -m alysia knowledge tick
python -m alysia research task "某项当前技术参数是什么？" --quality primary --freshness-days 14
python -m alysia grounding check <run_id>

# 完全离线、可重复的 alpha17 验收
python -m alysia knowledge demo-a  # supersession + old snapshot
python -m alysia knowledge demo-b  # 来源冲突 + primary research task
python -m alysia knowledge demo-c  # stale 阻塞 + reverify/resume
python -m alysia knowledge demo-d  # H3 本机 observation，不外推为全局事实
```

Demo A/B/C 的故意冲突、过期值与离线 fixture 只写入 `workspace/knowledge_demos/alpha17/`，不会污染主知识库；Demo D 则把真实本机 H3 observation 写入主库，并以 `scope=current_machine` 限制其适用范围。

`WebResearchProvider` 只接受显式注入的公开 `WebSearchAdapter`，负责捕获 published/retrieved time、domain/type 与 content hash；未配置 adapter 时安全失败，不执行浏览器登录或受限访问。

## alpha18：Autonomous Evaluation Benchmarking + Regression Intelligence

alpha18 增加独立的 `alysia.evaluation` 层，不改写 Research、Studio、Supervisor、Workflow、Publishing 或 H3 业务实现。版本化 registry 默认运行 12 个完全离线的 golden benchmark，并把本地 H3/ComfyUI smoke 保留为第 13 个显式 integration case。

统一评测产物保存到：

```text
evaluation/
├── runs/<evaluation_id>.json
├── baselines/<baseline_id>.json
├── comparisons/<comparison_id>.json
└── gates/<baseline_id>__<evaluation_id>.json
```

EvaluationRun 使用源码、配置、测试 manifest 与 golden fixtures 的 SHA-256 fingerprint，不要求也不会创建 Git commit。未知指标（例如默认离线环境未加载 ASR）必须保存为 `value=null`、`measurement_type=unknown`、`confidence=0`；主观 Script/Style 指标只使用带维度理由的离散 rubric。

```powershell
python -m alysia eval list
python -m alysia eval baseline-create --version alpha17
python -m alysia eval run --label candidate
python -m alysia eval compare <baseline_id> <evaluation_id>
python -m alysia eval report <evaluation_id>
python -m alysia eval gate <evaluation_id> --baseline-id <baseline_id>

# 故意注入隔离字幕回归，证明 promotion gate 会 BLOCKED
python -m alysia eval run --label regression-demo --inject-regression subtitle_timing

# 只有显式 integration 才会加载本地 H3
python -m alysia eval run --label h3-integration --integration
```

`EvaluationGate` 只输出 `PASS`、`PASS_WITH_WARNINGS` 或 `BLOCKED` 与证据，不自动回滚代码。Research grounding、stale/conflicted knowledge、真实语音/测试 tone、字幕时间、render decode、publish approval、approved-skill-only、Supervisor 预算/动作限制和 provider resource policy 是受保护 invariant；major/critical regression 会阻止 capability/version promotion。

## alpha19：Reliability, Recovery & Fault Tolerance

alpha19 为 Run、Workflow、Studio、Supervisor、Visual 与 Publishing 增加统一的故障记录和有限恢复策略。失败会归类为 timeout、OOM、provider/network、artifact/state corruption、资源压力、TTS/ASR、H3/ComfyUI、render、approval/cancellation 等类别，并保存证据、重试次数、fallback、质量影响和最终状态。RecoveryPolicyEngine 只会在配置的次数和 recovery rounds 内选择重试、退避、批准过的 fallback、checkpoint 恢复、artifact owner 回退、暂停等待资源、人工升级或终止，不会无限循环或静默降质。

关键 JSON/text 状态采用 temp file、flush/fsync 和 atomic replace，并为小型状态保留有限 `.bak1/.bak2` 历史。Run、Workflow、Supervisor、Visual job、Publish job 与 Knowledge index 在当前文件损坏时会尝试最近有效副本；副本也损坏时停止并要求人工处理。CheckpointManager 为 Research、Script、Storyboard、Voice、Subtitle、Visual、Render、Publish、Workflow、Studio 和 Supervisor 保存 started/succeeded/failed 状态与 artifact integrity，resume 只复用完整、可解析/可解码的产物。

长任务通过 heartbeat/timeout 监控。ComfyUI 使用真实 queue/history API 轮询；FFmpeg、Remotion、TTS、ASR 和 provider call 会记录任务状态。重型阶段执行前通过可配置 ResourceGuard 检查磁盘、系统 RAM、NVIDIA VRAM 与 ComfyUI 健康状态；资源不足默认暂停，不删除用户文件。H3 OOM 只允许按 ProductionPlan 先尝试一次低资源 profile，再使用明确批准的 Remotion/static fallback 或升级人工，且必须记录质量影响。

```powershell
python -m alysia reliability status
python -m alysia reliability failures [run_id]
python -m alysia diagnose <run_id>
python -m alysia recover <run_id>
python -m alysia checkpoints <run_id>

# 仅测试证据目录中启用故障注入；production 配置保持关闭
python -m alysia reliability demo --evidence-dir evaluation/reliability_demos/alpha19_gate
```

Voice 恢复只使 Voice、依赖音频时间的 Subtitle 和 Editor 失效；Render 恢复保留 composition/audio/assets；Workflow resume 不重复完成的 step；Supervisor dispatch 与 Publish job 保持幂等。MockTTS production block、发布审批、Knowledge freshness、approved skill 和 Supervisor limits 均继续由 Alpha18 regression gate 保护。

## alpha20：Security, Permission & Governance

alpha20 在 provider/tool 真正执行之前应用统一的默认拒绝权限模型。`config/security_policy.yaml` 配置 Supervisor、Studio 角色、SkillSandbox、WorkflowRuntime 和 provider adapter 的最小权限；`SYSTEM_CONFIG` 对所有 Agent/Skill 硬拒绝。发布、身份、预算、技能和策略变更必须使用与 action、subject、artifact/config hash、scope、version/nonce 和有效期绑定的人工审批，审批不能跨动作、跨版本或跨发布包复用。

凭证只以 `CredentialReference` 元数据存在于仓库，运行时解析还需 `READ_CREDENTIAL_REF`。浏览器 Cookie 抓取和自动登录不在 alpha20 范围内。安全日志写入 `audit/audit_log.jsonl`，上下文会先做 token、cookie、Authorization 和环境变量 secret 脱敏；该日志是应用层逻辑 append-only 记录，不是防篡改审计系统。

SkillSandbox/Workflow 的通用工具执行受 approved-skill、路径和逻辑 allowlist 约束；Research 公网、已批准 API 与 ComfyUI loopback 使用独立网络策略。该实现不创建 OS 级 sandbox、防火墙或零信任边界，完整限制见 `docs/security_review_alpha20.md`。

```powershell
python -m alysia security status
python -m alysia security permissions
python -m alysia security audit --run-id <run_id>
python -m alysia security scan <path_or_run>
python -m alysia security approvals [subject]

# 仅使用测试凭证和 Mock provider 生成本地安全证据
python -m alysia security demo --evidence-dir evaluation/security_demos/alpha20_gate
```

任何 permission/policy deny 都不会调用下游 provider，也不会被 Alpha19 RecoveryPolicy 当作可重试 provider 错误；缺少审批或凭证时会安全等待人工处理。MockPublishingProvider 与正式 provider 共用同一发布 Gate。

## alpha21：Alysia Control Center

alpha21 将既有 CLI、service、run artifact、Alpha18 评测、Alpha19 恢复和 Alpha20 安全门整合为本地可视化控制中心。React/Vite 前端只调用 FastAPI adapter；它不直接读取 `runs/*.json`、不连接 ComfyUI/H3、不持有凭证，也没有直接 publish 或任意 shell 入口。

```powershell
# 首次安装和构建前端
Set-Location control-center
npm install
npm run test -- --run
npm run build
Set-Location ..

# 一条命令启动后端和静态前端，固定监听 127.0.0.1:8765
uv run python -m alysia control start --open-browser
```

页面包括 Dashboard、Runs/安全 artifact 预览、Supervisor、Studio、Production、Visual/H3、Knowledge、Analytics/Memory/Experiments、统一 Approvals、Skills/Workflows 和 Logs/Audit。资源面板复用 Alpha19 doctor/resource guard，当前生产预算显示 RTX 4060 Ti 8GB 与 24GB RAM；物理内存探测值另行标注。

Resume/Recover 只能调用 Alpha19 `RecoveryPolicy`，没有“忽略完整性继续”按钮。Approve/Reject 会在后端重新校验 Alpha20 scope、package/config hash、version 和当前状态；localhost 不构成信任边界。写请求还要求同源和本地 CSRF session token。该保护只面向本机控制台，不应被视为完整公网部署安全方案。

Alpha18 gate 状态只读显示，UI 无法把 `BLOCKED` 改成 `PASS`。REAL、MOCK、SIMULATION provenance 必须显式展示。alpha21 不包含真实 Bilibili/Douyin 连续运营；该工作属于 Alpha22。

Alpha22 的“本地创作”页与 `alysia local-create` CLI 共用本机 H3/ComfyUI、SAPI、Remotion、VideoQA 任务服务。自写提示词与工作流、运行约束及恢复方法见 [本地创作使用说明](docs/local_creator.md)；本地成片不会自动发布。

Windows 可分别双击仓库根目录的 `打开Alysia.cmd`、`打开ComfyUI.cmd`，独立启动或打开两个本机网页服务；简体中文界面和手动启动方式见 [本机启动说明](docs/local_start_zh.md)。
