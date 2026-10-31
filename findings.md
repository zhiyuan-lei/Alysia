# Findings & Decisions

## Alpha.12 Session Start
- 用户要求以单一 `StudioDirector` 将既有模块化流水线包装为九角色 Creator Studio；默认串行，不引入大型 Agent 框架或复杂并发。
- 仓库路径为 `D:\Alysia`；工作树包含 alpha1-alpha11 大量未提交/未跟踪成果，全部视为现有基线并保留。
- alpha11 报告记录最终 `108 passed`、doctor 正常；ProductionPlan、ProviderRouter、ResourceManager、fallback/cache/metrics/quality gate 已存在，alpha12 必须复用。
- alpha11 demo run 为 `20260807_175616_cb2fbe40`；draft/standard/high plan、fallback 和 cache demo 已通过。
- 现有 planning files 已完整记录 alpha11；本轮在顶部追加 alpha12 当前计划，保留历史以便追溯。
- Memory registry 对 Alysia/alpha11 无相关命中，因此本轮以仓库和 alpha11 报告作为事实来源。
- 当前工作树基线全量 pytest 退出码 0；doctor 退出码 0，10 项可用、5 项可选能力未就绪，RTX 4060 Ti 为 8188 MiB。
- 核心编排器仍为 `AlysiaOrchestrator`；Production 层由 `ProductionService -> ProductionPlanner -> ProviderRouter` 组成，Creator Loop 独立管理选题审批。
- 现有角色实现只覆盖 Researcher/Writer/Director/TextCritic 和投稿 metadata agents；Designer、Voice、Editor、Analyst、Publisher 需要做轻量角色适配器，执行逻辑继续委派给 workers/services。
- workers 已清晰覆盖 Voice/Subtitle/AudioQA、Composition/Video/VideoQA、PublishPackage/PublishQA；providers 已按 LLM/Search/TTS/ASR/Video/Cover/Publishing/Feedback/Analytics/Trends 分层，适合 Registry 只声明允许范围而不重建 provider。
- 现有测试按文本、音频、视频、发布、analytics/learning、planning、operations、identity、production 分域，alpha12 可新增独立 `tests/test_studio.py`，避免侵入旧测试。
- `AlysiaOrchestrator` 的 public create/start_planned/resume/render/package/publish_check 已在每个入口调用 `ProductionService.ensure_plan`；Studio 应调用这些入口或现有私有阶段方法的窄适配器，不能另建 provider 选择。
- `RunState.artifacts` 是当前 artifact 引用真相源；StudioContext 可从它同步引用，但 ownership/version 需要放在独立 StudioStore，避免改变旧 RunState schema 和 resume 判定。
- Orchestrator 已按阶段失效下游产物并支持 skip/idempotent；Studio 的 revision request 应先验证 owner，再通过对应现有 force/阶段入口执行，不能直接覆盖别人的文件。
- ProductionPlan 固定 12 个 production stage，ProviderRouter 按显式 quality/task preference、健康、离线、凭证和 VRAM 约束排序；Studio Agent 只能提出 `capability/task_type`，最终 provider 仍读取 plan.selected_provider_per_stage。
- `ProductionService.approve_policy` 拒绝 automation/agent/alysia/system 审核者；Studio 必须把此错误映射为 `approval_required`，不能代签。
- 现有 Worker 接口天然适合角色边界：VoiceWorker 生成 `AudioManifest`，Subtitle/AudioQA 紧随；VideoRender/VideoQA 负责成片；PublishPackage/PublishQA 负责投稿包。Studio 适配器只需协调已有 Orchestrator 阶段。
- AudioQA 已硬性拦截 MockTTS 和持续 tone，SubtitleWorker 已把 ASR 失败显式记录 fallback；Studio QA 还需额外检查 ProductionPlan 的 production/mock provider 语义，不能仅看文件存在。
- `CreatorLoop.approve` 创建 run 后立即由 `ProductionService.plan` 生成计划；`CreatorLoop.start` 只显式启动已批准 slot，不自动渲染/投稿。Studio run 必须接受现有 run_id，不替代选题审批。
- Identity 的 PromptContextBuilder 已统一身份、品牌、策略、实验；Studio ContextSelector 应复用 IdentityService/Memory/Operations 的只读产物，按 role 输出摘要/引用，避免全文历史注入。
- `PublishingService.validate/submit` 要求 REVIEW_READY、QA、包 hash 和 ApprovalRecord；真实 provider 禁止 mock/testing artifacts。PublisherAgent 只能准备/验证或在现有人类批准后提交。
- Studio Context 可直接读取 IdentityStore 当前版本、最多少量 lesson/strategy/experiment 摘要；不需要复制 `PromptContextBuilder` 的完整 rendered prompt。
- LearningPipeline 的 artifact keys 为 analytics_metrics/derived_metrics/content_fingerprint/performance_analysis/lessons/strategy_recommendations/next_experiment；AnalystAgent 可按这些里程碑幂等推进，但在未导入指标时必须返回 blocked 而非补造数据。
- StyleConsistencyReport 没有硬 `passed` 字段，仅包含 score/violations/suggestions/confidence；Studio Critic 将保留其建议性质，只有低分且明确 violation 时才请求对应 owner 修订，不能把任何建议都升级为失败。

# Alpha18 Session Start
- 用户要求只实现 Alpha18，不进入 Alpha19；Alpha1-Alpha17 的全部未提交成果必须增量保留。
- 仓库位于 `D:\Alysia`，开工时工作树有 27 个 tracked 修改以及大量未跟踪 Alpha3-Alpha17 产物；禁止任何清理或历史改写操作。
- 开工 tracked diff stat 为 27 files changed、4513 insertions、100 deletions；完整 status/diff 输出已由本轮工具记录，结束时必须复核。
- 现有 planning files 停留在 Alpha12，仓库已有 Alpha13-Alpha17 报告；本轮在顶部追加 Alpha18 计划，保留旧计划作为历史。
- Alpha17 报告记录专项 25/25、全量 247 PASS + 1 H3 integration SKIP；本轮重新执行得到相同计数，耗时 71.57s，证明开工基线稳定。
- 基线 doctor 退出 0：12 项可用、4 项可选未就绪；RTX 4060 Ti 8188 MiB，Alysia 预算 8192MB VRAM/24GB RAM。未就绪项为 qwen3.5:4b、nvcc、CosyVoice Python、faster-whisper，不阻塞离线 Alpha18。
- 现有 pytest marker 已包含 `integration` 与 `h3_local`；`tests/test_h3_local_integration.py` 仅在 `ALYSIA_RUN_H3_LOCAL=1` 时加载 42.5GB H3 栈，适合扩展而非另建默认重型路径。
- 现有 CLI 使用单文件 Typer 子应用注册；Alpha18 应新增 `eval_app` 并把实现委托给独立 evaluation service，避免在前端复制业务逻辑。
- 历史 stub audit 命中抽象接口、异常标记类、明确禁用的 cloud/Bilibili 路径、视觉 upscale 接口、兼容 placeholder 与容错 `pass`；这些均需在 inventory 中归类，不能擅自修复或归因 Alpha18。
- Alpha18 采用独立 `alysia/evaluation/`，没有重写业务链：13 个注册 case（12 个默认离线 + 1 个显式 H3 integration），覆盖用户指定的 12 类。
- 生成了稳定 golden fixtures：JSON 事实/脚本/分镜/字幕/发布/学习/工作流、真实 Windows SAPI 中文 speech WAV、FFmpeg 可解码视觉/成片以及隔离的 corrupt media。
- 离线评测首个 smoke run 成功：12 cases、22 metrics、status=completed；ASR 文本相似度在未加载 ASR 时明确保存为 unknown/None/confidence=0。
- Script 与 Style 主观指标使用 0-3 离散 rubric，并保存每个 dimension 的理由；不使用 LLM 黑箱小数分。
- Alpha18 专项测试首轮 18/18 PASS。

## Alpha.12 Final Findings
- 最终实现使用唯一 StudioDirector、9 个角色、规则路由、结构化 handoff/result、受控 context、artifact owner/version/revision、JSONL trace 和 StudioQA。
- 完整 demo `20260807_225658_1596ed8c` 最终 completed：11 handoffs、40 trace events、12 context snapshots、Studio QA PASS；Publisher 首次明确 blocked，人工 mock ApprovalRecord 后才继续。
- 修复后的 Audio failure demo `20260807_230208_43ee9a2b`：Researcher/Writer 各 1 次，Voice/Editor 各 2 次，Critic 4 次；audio/final_video/final_review 均 v2；14 handoffs、44 trace events、Studio QA PASS。
- 最终 pytest 集合 129 项，全部通过；doctor 10 项可用、5 项可选能力未就绪；compileall、Remotion check、git diff --check 均通过。
- git status 仍显示 alpha1-alpha11 的大量未提交成果和本轮 alpha12 文件；未清理、重置或提交任何用户工作。


## Alpha.11 Session Start
- 用户要求在 `D:\Alysia` 增量实现 Autonomous Production Optimization，并先验证 alpha10 稳定性。
- 当前 `main` 工作树包含 alpha1-alpha10 大量未提交和未跟踪成果；所有内容视为用户工作，必须保留，不做 reset/clean/checkout。
- 根规划文件仍停留在 alpha8，但仓库已有 `development_report_alpha10.md`、identity、brand voice 与 alpha10 测试；本轮规划已更新为 alpha11。
- 未发现仓库内额外 AGENTS.md/CLAUDE.md；当前用户提供的工作区指令适用。
- alpha11 的关键兼容边界：单总控、默认串行 GPU、人工审批不降低、未知成本/VRAM 不编造、离线测试不调用真实 provider。
- alpha10 报告记录基线 `93 passed`，doctor 正常；当前身份版本 v1，Style QA 是旁路建议，Identity 变更仍需人工批准。
- `AlysiaConfig` 已有 `runtime.sequential_gpu` 和 `resources.gpu_execution/max_concurrent_gpu_models`，alpha11 应兼容扩展而非另建冲突配置。
- 现有 `ResourceManager.phase()` 已支持单 GPU phase 冲突检查、provider unload/cleanup、gc 与可选 `torch.cuda.empty_cache()`；缺少 stage lease、线程 mutex、超时、VRAM probe、OOM 分类和审计事件。
- 现有 provider 通过 `build_*_provider()` 由顶层 config 选择，当前没有统一 capability registry 或 task-aware router。
- Creator Loop 当前人工批准后创建 traceable CREATED run；alpha11 计划门应插在 approved run 进入 create pipeline 前，不能改变选题批准语义。
- README 明确 alpha10 流水线可恢复/可缓存、发布/身份/实验均保留人工门；alpha11 文档必须延续这些边界。
- 当前默认资源顺序已有文档约定（GPU-heavy provider 串行、退出时 unload/cache cleanup），alpha11 需要将约定提升为可审计 ProductionPlan 和 metrics。
- alpha10 基线全量 pytest 通过（93 项进度完成），doctor 退出码 0：10 项可用、5 项可选能力未就绪。
- 实机 doctor 检测到 RTX 4060 Ti、总显存 8188 MiB；配置默认预算应使用用户要求的 7600 MiB，而不是把总显存当成可用预算。
- 当前 Ollama、CosyVoice、faster-whisper 未就绪；SAPI、FFmpeg/ffprobe、Node/npm 可用。Registry health 必须来自 snapshot/静态已知状态，不应把未探测 provider 标成 healthy。
- FFmpeg 在本机由项目的 `find_media_executable()` 从 winget Gyan 路径发现，未必位于 PATH；Capability Registry 必须复用该发现逻辑，否则会错误移除 `render.mock` 降级链。

## Prior Findings

### Alpha.8 / Alpha.7 History

## Alpha.8 Session Start
- 用户要求在现有 `D:\Alysia` 仓库增量实现 publishing + feedback loop，不重建项目。
- 工作树包含 alpha.3-alpha.7 大量未提交成果，必须完整保留。
- Memory registry 无 Alysia/alpha8 相关历史，本轮以仓库和 alpha7 报告为事实来源。
- 初始 `git status` 已记录；未发现仓库内额外 AGENTS/CLAUDE 指令文件。
- 现有 alpha.5 `PublishPackage` 与 `PublishQAWorker` 已提供投稿包、traceability SHA-256 和 pre-publish QA；alpha8 应扩展而非替换。
- 当前 `publish-check` 只推进到 `review_ready`，尚无 PublishJob、approval record、provider 或反馈发布映射。
- 现有发布 QA 的 warnings 在 `qa.strict=false` 时仍可通过；alpha8 validation 需要明确处理 unresolved warnings，并把人工接受记录进审批。
- 最新 alpha7 创建的 run `20260807_201750_f211ca71` 仍为 CREATED；历史 `20260807_175616_cb2fbe40` 已达到 learning/strategy 阶段，更可能是 demo 基础候选。
- 已确认历史 run `20260807_175616_cb2fbe40` 为 `review_ready=true` 且已有 `final.mp4`、封面、metadata、publish package 与 QA，可用于 alpha8 demo。
- 该 run 的 publish QA 有两个未解决 warning：视频仅 82.23 秒（低于 120 秒配置）且没有可发布来源链接。alpha8 validation 不应静默忽略；审批记录需显式接受 warning 后才可提交。
- alpha7 CreatorLoop 当前 stage 只覆盖规划到 queued；alpha8 可兼容扩展 stage literal 与持久化字段，不应改变选题评分或 Research handoff。
- 现有 `VideoMetrics` 没有 `external_id` 与 `comments_summary`；应新增反馈输入 schema，再由 FeedbackMapper 映射到既有 VideoMetrics，避免破坏 alpha6 分析器。
- `MemoryStore` 当前仅管理 episode/lesson/strategy；PublishEpisodeMemory 适合使用独立 `publish_episodes/` 与 index section，避免污染既有 EpisodeMemory 文件格式。
- alpha6 已实现 mock/testing lesson 永久 tentative；FeedbackMapper 必须保持 source 映射，使 mock feedback 进入 testing。
- Bilibili 官方开放平台当前公开说明确有账号授权、视频稿件发布/删除/查询、稿件数据回流等能力，但需要开发者身份认证、创建应用并由关联 UP 主授权。
- 官方公开入口未在无需登录的页面暴露可安全核对的具体上传 endpoint/请求格式；alpha8 不应凭非官方资料猜接口。真实 provider 将只做官方授权环境能力检测并明确安全失败，待用户完成开放平台申请并提供官方应用文档后再启用网络提交。
- 官方隐私政策明确稿件管理和稿件数据能力取决于关联 UP 主授权；因此凭证只能从环境/安全引用注入，仓库不保存 token/cookie。
- PublishJob 使用 run/provider/package_hash 的稳定摘要作为 job_id；同一包重复 submit 可返回同一 submitted job，避免重复投稿。
- ApprovalRecord 绑定完整投稿包 hash 并保存已人工接受的 warnings；包或风险变化后审批自动失效。
- Feedback 幂等摘要刻意排除 collected_at，避免同一平台快照只因采集时间变化而重复清空/重建 Analytics 与 Lessons。

## Repository
- 仓库路径：`D:\Alysia`。
- 工作树已有 alpha.3-alpha.6 大量未提交成果；必须保留并做增量修改。
- 现有根规划文件停留在 alpha.3，本轮更新为 alpha.7 工作记录。
- Memory registry 无 Alysia 相关历史，仓库和 alpha.6 报告是当前事实来源。
- alpha.6 基线为 `55 passed in 19.23s`；doctor 有 10 项可用、5 项可选能力未就绪。
- 历史样本 `20260807_175616_cb2fbe40` 已达到 `strategy_ready`，其 `pipeline_phase=learning_ready`。
- 该样本的 analytics、lessons、strategies、next experiment 均为明确的 testing/mock 来源，不能晋升为真实趋势判断。
- 现有 `RunManager.create()` 只写 topic/config；alpha.7 需要以兼容参数扩展 planning provenance。
- 现有 `MemoryStore` 缺少 list strategies/episodes 方法；只需补只读加载接口。
- alpha7 demo plan 为 `plan_20260807_201716_ad8023ca`，10 个候选、3 个槽位、QA 7/7 通过。
- 批准 `slot_01` 后创建 `20260807_201750_f211ca71`，仍停留在 CREATED，input/run state 均包含 testing provenance。
- 批准后第二次 tick 复用同一 plan，证明计划窗口幂等。

## Requirements Snapshot
- 自主选题输入包括 CreatorProfile、趋势、历史 runs、Lessons/Strategies 和 NextExperiment。
- 评分必须规则化、可调权重、保留 breakdown，LLM 不得单独拍板。
- Creator Loop 默认计划模式、可恢复、幂等，并保留人工批准闸门。
- approved slot 创建 content run 时必须写入 plan/trend/strategy provenance，且正式事实仍走 Research。
- Mock demo 只能标记为 testing，不能进入正式趋势记忆。

## Issues Encountered
- 初次 memory 搜索无命中，组合命令返回非零；无需继续查询 memory。
- 初次嵌套 pwsh 命令发生变量展开；已改用安全引号。
- session-catchup 组合读取超时；已改为分段审计。
- 并行历史 run 审计脚本有空管道语法错误；已拆分命令并成功确认样本。
- 首轮 planning 测试 11/14 通过；3 个审批相关失败来自 PlanStore 未递归序列化 Pydantic 列表，已针对根因修复。
