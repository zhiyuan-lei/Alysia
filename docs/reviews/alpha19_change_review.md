# Alpha19 Change Review

## 目标

在不清理、不提交、不覆盖 Alpha1-18 既有未提交成果的前提下，为 Alysia 增加统一故障分类、有限恢复策略、checkpoint/resume、原子状态写入、artifact integrity、长任务 watchdog、资源守卫和局部恢复证据。范围严格止于 Alpha19；未实现 Alpha20 权限或安全架构。

## 实际改动

- 新增 `alysia/reliability/`：FailureStore、RecoveryPolicyEngine、CheckpointManager、ArtifactIntegrityChecker、LongRunningTaskMonitor、ResourceGuard、FaultInjector、ReliabilityService 与四个离线 demo。
- 新增 `alysia/schemas/reliability.py` 和 `alysia/core/io.py`，统一 schema 与 Windows 优先的 atomic write/有限备份。
- 将 Run、Workflow、Studio trace、Supervisor、Visual queue、Publish job、Knowledge index 接入原子写入、备份恢复或 integrity 检查。
- 将 Orchestrator、WorkflowRuntime、Visual、Voice、Subtitle、Remotion/FFmpeg 接入 checkpoint、失败记录、heartbeat、资源守卫与有限恢复。
- 扩展 CLI、Alpha18 evaluation registry/scorer/gate、regression matrix、测试、fixture 和文档。

## 无关改动审查

没有主动清理或重构 Alpha1-18 的邻近代码；每处既有模块修改均用于接入 Alpha19 的持久化、监控、恢复或回归保护。没有删除既有 tracked/untracked 成果，没有执行 reset、clean、checkout/restore、stash、rebase、commit、squash 或 amend。

## 新依赖

无新增第三方依赖。资源检测、媒体探测和真实 ComfyUI 轮询复用现有 Python 标准库、`nvidia-smi`、FFmpeg/ffprobe 与既有 HTTP/provider 能力。

## Schema、配置与 CLI 变化

- Schema：`FailureRecord`、`RecoveryDecision`、`CheckpointRecord`、`ArtifactIntegrityRecord`、`LongRunningTaskRecord`、`ResourceGuardResult`、`RecoveryMetrics`。
- 配置：新增 `reliability` 段；重试、恢复轮数、backoff、backup、hash 和磁盘/RAM/VRAM 阈值均可配置。fault injection 在 production 默认关闭。
- CLI：`reliability status|failures|demo`、`diagnose`、`recover`、`checkpoints`。`recover` 在资源/审批/人工条件不满足时只报告，不越权继续。

## 恢复风险

- H3 真实大模型不会进入默认测试；默认 demo 使用 integration-safe OOM 注入，并实际验证批准的低资源/Remotion fallback、VisualQA 和质量影响记录。真实部署路径由显式 integration 测试与 ComfyUI health/history 轮询保护。
- Artifact dependency invalidation 依赖现有 stage/owner 映射；新增阶段时必须同步登记 owner 和下游依赖。
- 小型状态只保留有限历史；当前与备份同时损坏时会明确升级人工，而不是猜测状态。
- 原子替换可防止半写 JSON，但无法替代磁盘/文件系统级备份。

## 未覆盖风险

- 未执行默认全模型 H3 推理，因为会加载本机约 42.5 GB 模型栈；保持显式 integration marker。
- 未模拟真实断电和操作系统进程被强杀，只覆盖可重复的进程失败、超时、状态截断、artifact 损坏、资源不足和 provider 故障。
- 未实现跨机器分布式锁或多节点恢复；Alysia v0.1 当前是单机执行模型。

## Alpha20 前置依赖

Alpha19 只提供可审计的 failure/recovery 记录。Alpha20 若开始，可消费这些记录建立权限与审计策略，但不得把 Alpha19 的 fault injection、fallback 或 recover CLI 当成授权机制。Alpha20 尚未开始。
