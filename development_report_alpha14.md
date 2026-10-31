# Alysia v0.1-alpha.14 开发报告

## 工作树保护与阶段边界

- 仓库：`D:\Alysia`
- alpha14 开始前，alpha13.5 已独立完成 163/163 全量回归、CLI demo 和 `development_report_alpha13_5.md`。
- 工作树仍包含 alpha1-alpha13 的历史未提交成果和 alpha13.5 增量；本阶段继续在当前工作树上增量开发。
- 没有执行 `git reset`、`git clean`、`git checkout`、`git stash`、`rebase`、`commit`、`squash` 或其他清理/提交操作。
- 没有把 alpha1-alpha13 的历史文件归因于 alpha14，也没有自动修改核心源码作为“自我进化”。

## 实现结果

alpha14 建立了受控的 Self-Evaluation + Capability Gap + Skill Acquisition Pipeline：

- CapabilityRegistry：从现有 agents/workers/providers/visual/studio/supervisor 建立 15 项初始能力；记录 owner、实现引用、成熟度、限制、前置条件与评测套件。
- SelfEvaluationEngine：输入 QA、Studio failure、Supervisor failure、Production metrics、人工 evidence/manual rating，分别输出 observed failure、cause hypothesis 和 capability gap。
- CapabilityGapDetector：没有 evidence 时不创建 gap；保存 evidence run/id、影响 agent、严重度、频率、workaround、置信度。
- SkillProposal：强制 `sandbox_required=true`、`approval_required=true`，记录接口、工具/provider、风险、资源成本和评测计划。
- Skill pipeline：`PROPOSED → DESIGNED → SANDBOX_READY → TESTING → EVALUATED → WAITING_APPROVAL → APPROVED → REGISTERED`，并支持 FAILED/REJECTED 语义。
- SkillSandbox：实现逻辑 path guard、网络/凭证/核心源码写入限制；明确不声称提供 OS 级隔离。
- SkillEvaluator：只运行受信任的声明式 functional/quality/regression/resource/security 检查，不导入或执行 proposal 提供的未知代码。
- SkillRegistry：只有通过评测、经过独立 review、由 `human:*` 显式批准的 skill 可注册；支持版本、disable、deprecated 和 rollback。
- Studio AgentRegistry 只能读取 active registered skills；未批准 proposal 不可见。
- ProductionPlanner 可读取 required skill 与 resource requirements；未批准/不可用 skill 会形成 policy blocker。
- Supervisor/Alysia 使用非 `human:*` 身份审批时硬失败，不能自行批准 skill。

## 本阶段新增文件

- `alysia/schemas/capability.py`
- `alysia/capabilities/*.py`
- `evaluation/capability_evidence_alpha14.json`
- `tests/test_capabilities.py`
- `development_report_alpha14.md`
- `workspace/capabilities/*` 与 `workspace/sandbox/skills/*`（CLI demo 状态）

## 本阶段增量修改的既有文件

- `alysia/core/config.py`、`config.example.yaml`
- `alysia/schemas/__init__.py`、`alysia/schemas/production.py`
- `alysia/production/planner.py`
- `alysia/studio/registry.py`
- `alysia/cli.py`
- `README.md`
- `alysia/__init__.py`、`pyproject.toml`（最终版本标记为 alpha14）

这些文件在 alpha14 之前已有大量未提交内容；本报告只归因上述 capability/skill 增量。

## Capability 与 Gap

- 初始 Capability 数量：15。
- stable：12；experimental：3（TTS、Subtitle Alignment、本地 H3）。
- evidence：2 条显式历史/阶段证据，并从现有历史 Studio/Production trace 中读取到 3 条失败证据，共 5 条；collector 还支持 QA、Supervisor 和 manual review 文件。
- detected gaps：
  1. `gap_b42ef506ef4c`：真实中文旁白与语音可识别性门禁不足；critical；frequency=2；confidence=0.65。
  2. `gap_52ee90e52df2`：本地 H3 尚缺真实模型 smoke test 与资源基线；medium；frequency=1；confidence=0.55。
  3. `gap_cb50c278cf9b`：历史 Studio/Production 中 3 条尚未映射到具体能力的 `unknown_runtime` 失败；high；frequency=3；confidence=0.75，等待人工分类。
- 自评明确把测试音误入成片作为 observed failure，把“mock promotion gate 缺失”保留为 cause hypothesis，不混为事实。

## Demo A：历史 Voice/Subtitle 问题

- 从 `historical_audio_noise_alpha5_1` 证据检测到 audio gap。
- 生成 `real_tts_speech_gate` SkillProposal。
- 提案接口：`validate(script, wav, asr_transcript) -> SpeechGateReport`。
- 当前状态：`PROPOSED`。
- 未执行、未评测、未批准、未注册；Studio AgentRegistry 中不可用。

## Demo B：alpha13.5 H3 capability

- `h3_visual_generation` 完成 functional/quality/regression/resource/security 五类声明式离线评测，score=1.0。
- 资源峰值保持 `unknown`；评测没有冒充真实 H3 模型运行。
- CLI 经过 `human:alpha14-reviewer` review，再由 `human:alpha14-demo-v1` 显式批准注册 v1。
- 生成 v2，经过独立 review/approve 后注册；v1 自动 deprecated。
- 演示 disable v2，然后 rollback 到 v1。
- 最终 registry：v1=`active`，v2=`disabled`；rollback 已验证。
- Capability `visual_h3_local` 仍保持 `experimental`，直到真实 ComfyUI/H3 smoke 和资源基线完成。

## 测试与验收

- alpha14 专项：16/16 PASS。
- Supervisor + Studio + Capability + Production gate 回归：73/73 PASS。
- 最终全量：179/179 PASS，约 58 秒。
- `python -m alysia doctor`：成功；11 项可用、4 项可选组件未就绪。
- 已执行：`capability list/evaluate`、`gaps list`、`skill propose/test/review/approve/disable/rollback`。
- Human Approval、Studio、Supervisor 与 Production policy gate 均通过回归。

## 安全边界

- 未从互联网下载或执行任何 skill 代码。
- 未自动 `pip install`。
- Skill sandbox 默认无网络、无凭证、不可修改核心源码。
- 当前只实现逻辑 sandbox + path/capability guard，不声称提供 OS 级隔离。
- 不自动批准、发布、评论、私信，不绕过现有 Human Approval Gate。

## 当前限制

1. SkillEvaluator 是声明式离线评测器，不是通用第三方代码执行器；这是 alpha14 的安全设计。
2. OS 级进程、网络和系统调用隔离尚未实现；高风险 skill 仍不应执行。
3. Capability 与证据映射当前以可审计规则为主，未知失败会归入 `unknown_runtime`，需要人工复核。
4. H3 v1 active 代表接口、队列、安全和 Mock pipeline 已获 demo 审批，不代表真实 H3 画质/显存/速度已验证。
5. 实际 CosyVoice/faster-whisper 未安装，Audio gap 仍保持开放提案状态。

## alpha15 建议

建议进入 **Governed Skill Runtime + Real Provider Qualification**：

- 先在独立 ComfyUI 环境完成真实 H3 3–5 秒 smoke test，补齐真实 VRAM/RAM/耗时与 workflow provenance；
- 对 CosyVoice/faster-whisper 建立真实语音回听、相似度和 production gate 评测；
- 为 approved skill 增加进程级 resource/time limit 与更强隔离；
- 继续要求人类批准，禁止从互联网自动下载并执行未知技能。
