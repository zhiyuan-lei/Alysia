# Alysia v0.1-alpha.20 Development Report

## 结论

**状态：DONE。** Alpha20 的应用层最小权限、审批绑定、凭证引用、脱敏审计、路径/工具/网络策略和发布 Gate 已实现并通过最终 Gate。未进入 Alpha21。

## 仓库与工作树保护

- 仓库：`D:\Alysia`
- 开始前已执行并记录：`git status --short`、`git diff --stat`、`git diff --name-only`。
- 开始快照为 Alpha1-19 的大量既有未提交成果；tracked diff 摘要为约 4860 insertions / 110 deletions，且包含既有大量 untracked 阶段产物。
- 结束快照：28 个 tracked 文件处于修改状态，tracked diff 为 5023 insertions / 113 deletions；大量既有 untracked 成果仍在，新增 Alpha20 文件均为增量内容。
- 结束检查未发现 deleted path；原 tracked 修改路径仍存在。
- 本阶段未执行 reset、clean、checkout/restore、stash、rebase、commit、squash 或 amend。

## Alpha19 前置 Gate

- 基线全量 pytest：290 collected，289 passed，1 skipped，约 82.5 秒。
- Alpha18 基线 Gate：`eval_160f3bc5f319c192188c`，comparison `cmp_50bacfb952d45c31`，PASS，critical regression=0。
- Alpha19 reliability status：0 failures；关键恢复回归 23 passed。
- `doctor` 可执行并返回 0；可选缺口为未安装 Qwen 模型、nvcc、CosyVoice Python 和 faster-whisper，不构成 Alpha20 blocker。

## 实现摘要

- 统一 12 项 Permission 与默认 deny 的 `PermissionPolicyEngine`。
- 配置化 15 个角色/adapter 的最小权限矩阵；`SYSTEM_CONFIG` 对 Agent/Skill 硬拒绝。
- `PermissionDecision` 与结构化 security error；deny/require_approval 不调用下游 provider。
- ApprovalRecord 绑定 action、subject、scope、artifact/config hash、version/nonce、expiry 和 consumption reference，阻断跨动作、跨包与 replay。
- `CredentialReference` 只保存 env/os-store/manual 引用元数据；运行时解析需要 `READ_CREDENTIAL_REF`。
- SecretScanner/Redactor 覆盖 Authorization/Bearer、API key、token、cookie/session 和测试 `.env` 值。
- `audit/audit_log.jsonl` 为应用层逻辑 append-only 审计，使用 Alpha19 原子写入 helper；不宣称 tamper-proof。
- SkillSandbox/Workflow 增加 path guard、approved-skill 检查和逻辑工具 allowlist；Research、approved API 与 ComfyUI loopback 使用网络策略。
- Publish、Identity、Budget、Skill、Policy 变更进入统一策略/审批层；MockPublishingProvider 与正式路径共用 Gate。
- Alpha19 FailureCategory 增加 permission_denied、approval_invalid、credential_unavailable、policy_violation，避免安全失败无限重试。

## 测试结果

- 最终全量 pytest：323 collected，322 passed，1 skipped，81.88 秒，exit 0。
- Alpha20 离线安全测试：33 passed。
- 新增 skip：0。
- 唯一 skip 为既有真实 H3 integration；需显式 `ALYSIA_RUN_H3_LOCAL=1` 才加载 42.5 GB 本地模型栈。
- Alpha19 fault/recovery 回归：23 passed。
- `git diff --check`：无 whitespace error；仅既有 Windows LF/CRLF 提示。

## Security Demos

- Demo A：WriterAgent publish -> DENY；provider_called=false；PASS。
- Demo B：SkillSandbox credential lookup 与 `..` path traversal -> DENY；PASS。
- Demo C：旧/错误 package hash approval -> DENY；provider_called=false；PASS。
- Demo D：PublisherAgent + 合法 scoped approval + Mock provider -> ALLOW；provider_called=true；PASS。
- 证据：`evaluation/security_demos/alpha20_final/summary.json`。

## Secret leakage 与 Audit

- 测试用 fake secret 的原值仅存在于测试 fixture，不在报告或运行产物中回显。
- 生成 evidence 与 audit 中 raw fake secret 搜索结果：0；`[REDACTED]` 存在。
- fake secret 证据：`evaluation/security_demos/alpha20_final/fake_secret_redaction.json`。
- demo audit：6 events，覆盖 deny、require_approval 和 allow；raw fake secret=false。
- 应用 audit 检查时共 139 events；raw fake secret=false。
- security scan fixture：2 files、4 findings，报告仅含 redacted excerpt。

## Alpha18 Evaluation 联动

- 最终 evaluation：`eval_879a6ab4d0ede96b5905`。
- comparison：`cmp_1bff98bfb375ecd5`，对比 `baseline_alpha17_75261fe47f27`。
- Gate：PASS；promotion_allowed=true；blocking findings=0；critical regression=0。
- 受保护安全指标均为 1.0：unauthorized_action_block_rate、approval_scope_integrity、secret_redaction_success、audit_event_coverage、sandbox_escape_block_rate。
- Research/render/publish 等既有可比较指标无 critical regression；离线 ASR 指标继续显式 unknown，不伪造结果。

## Alpha19 Reliability 联动

- `evaluation/reliability_demos/alpha20_final/summary.json`：PASS。
- Voice 失败仅重做 Voice/Subtitle/Editor；H3 OOM 使用批准的低资源/Remotion fallback；损坏 state 从 backup 恢复；FFmpeg 失败只重跑 Render。
- permission/policy violation 不重试；invalid approval/credential unavailable 等待人工。
- publish resume 保持幂等，不重复提交。

## CLI

- `python -m alysia security status`
- `python -m alysia security permissions`
- `python -m alysia security audit [--run-id]`
- `python -m alysia security scan <path_or_run>`
- `python -m alysia security approvals [subject]`
- `python -m alysia security demo --evidence-dir <dir>`

CLI 不输出 secret 值。最终 status：enabled=true、default_deny=true、policy_version=alpha20.1、roles=15、permissions=12、SYSTEM_CONFIG open=false。

## Stub Audit

Alpha20 security production path 没有未实现 stub。扫描命中项均已人工分类：

- `alysia/security/credentials.py`、`alysia/publishing/service.py`、`alysia/workflow/executors.py` 的 `pass` 是 exception class body，不是实现缺口。
- provider `base.py` 的 `NotImplementedError` 是抽象接口契约。
- Cloud LLM 与 Bilibili analytics placeholder 是 Alpha2/Alpha6 既有、明确 safe-fail 的未实现 provider，不在 Alpha20 production security path。

因此 Stub Audit 不构成 blocker。

## 已知安全限制

- 仅应用层控制，不是 OS sandbox、容器、ACL/firewall 隔离或零信任系统。
- Audit 未签名、未远端复制，不防本机管理员篡改。
- DNS rebinding 未完全解决；当前阻断 literal private/link-local/reserved IP。
- SecretScanner 是启发式文本扫描，不覆盖二进制、内存、swap 或外部服务日志。
- `os_store_ref` 在 Alpha20 仅定义引用，解析会 fail closed；未接 Windows Credential Manager。
- 已有 typed FFmpeg/SAPI/doctor subprocess 尚未统一迁移到一个 OS broker；通用 Skill/Workflow 执行已受 allowlist 控制。
- Bilibili 正式 provider 在官方授权请求契约未配置时继续 safe-fail；不抓取 cookie、不自动登录。

完整边界见 `docs/security_review_alpha20.md`。

## Blockers / 未完成项

- Alpha20 Gate blocker：无。
- 上述限制属于已记录的非目标，不影响 Alpha20 DONE，也不得被描述为生产级 hostile-code isolation。
- Alpha21 Control Center：未开始。

## 证据与文档

- `docs/security_review_alpha20.md`
- `docs/reviews/alpha20_change_review.md`
- `docs/regression_matrix.md`
- `docs/phase_execution_ledger.md`
- `evaluation/security_demos/alpha20_final/summary.json`
- `evaluation/reliability_demos/alpha20_final/summary.json`
- `evaluation/runs/eval_879a6ab4d0ede96b5905.json`
- `evaluation/comparisons/cmp_1bff98bfb375ecd5.json`
