# Alysia v0.1-alpha.11 开发报告

生成日期：2026-08-07（Asia/Shanghai）

## 结果

alpha11 已在不重写 alpha1-alpha10 流水线、不降低内容/发布/身份/实验人工审批门槛的前提下，加入可解释、可审计的 Autonomous Production Optimization：

```text
APPROVED_TOPIC / direct create
  → ProductionProfile + Constraints
  → Provider Capability Registry
  → Task-aware Provider Router
  → ranked ProductionPlan + alternatives
  → policy / cloud cost gate
  → serial ResourceManager execution
  → explicit fallback records
  → execution_metrics.json
  → existing QA + ProductionQualityGate
  → production_report.json
```

仓库路径：`D:\Alysia`。

## Alpha10 状态确认

开发前完整审计 alpha10 报告、README、Creator Identity/Brand Voice、Creator Loop、ResourceManager、LLM/TTS/ASR/Video/Research/Cover provider、config 与 tests。

基线结果：93 项测试通过；`python -m alysia doctor` 正常完成。现有工作树包含 alpha1-alpha10 大量未提交成果，本轮全部保留，没有 reset、clean、checkout 或重建仓库。

## 新增能力

### 1. Production Profile 与约束

新增 `ProductionConstraints` / `ProductionProfile`，支持 draft/standard/high、7600 MiB 本地预算、可选 cloud cost/wall time、local/cloud/fallback/offline policy、串行 GPU、reproducibility priority 和 provider allow/deny list。

### 2. Provider Capability Registry

统一登记 LLM、Research、TTS、ASR、Render、Cover、metadata 与 QA provider。Capability 包含任务、位置、显存声明、unload、时延/质量/成本等级、网络/凭证要求和健康状态。未知 benchmark、成本和显存保持 `unknown/null`。

当前实时状态：

- SAPI、FFmpeg/ffprobe、Node/npm、Remotion：可用。
- RTX 4060 Ti：可用，doctor 报告总显存 8188 MiB；计划预算仍固定为 7600 MiB。
- Ollama、CosyVoice、faster-whisper、nvcc：缺失或未就绪。
- Cloud LLM、Web Research：现有代码仍为显式占位，因此 Registry 标记 unavailable。

### 3. Planner、Router 与 Optimization Engine

ProductionPlanner 按 stage 输出 provider、顺序、fallback、资源/成本说明、quality tradeoff、reasons、warnings、policy blockers 和 ranked alternatives。ProviderRouter 使用配置化 quality/task preference 与显式权重；历史 metrics 至少积累 3 次后才会影响失败 provider 排名，单次失败不会永久改变全局策略。

### 4. Execution、Resource 与 Fallback

ResourceManager 新增 acquire/release、单 GPU-heavy mutex、timeout、unload/cleanup、gc/可选 CUDA cache 清理、`nvidia-smi` VRAM probe 和 OOM 分类，不实现多 GPU 或复杂并发。

Orchestrator 在 direct create、planned start、resume、render、package 与 publish-check 前确保 ProductionPlan 存在并通过 policy gate；按 stage provider_id 配置现有 worker。Fallback 不静默，写入 original choice、failure reason、fallback choice 和 quality impact。ASR 内部 CUDA→CPU 或 deterministic fallback 同样记录。

### 5. Metrics、Cache、Cost 与 Quality Gate

- `execution_metrics.json` 记录 stage 时间、provider、success/failure、retry、可测时才记录的 peak VRAM、规模、cost status、cache hit 与 fallback。
- Production Cache 的稳定 key 覆盖 Research、Script、Storyboard、scene TTS、subtitle alignment 和 render composition；Research 强制 TTL。
- CostEstimator 不硬编码 API 单价；本地 energy/electricity cost 与缺证据 cloud cost 保持 unknown。
- ProductionQualityGate 复用已有 QA。draft 允许更多 warning；standard 要求已到达阶段的 QA 通过；high 对 review-ready 内容增加 Style QA，且 retry budget 有上限。

### 6. CLI 与 Creator Loop

新增：

```powershell
python -m alysia production plan RUN_ID --quality draft|standard|high
python -m alysia production status RUN_ID
python -m alysia production report RUN_ID
python -m alysia production approve-policy RUN_ID --approved-by HUMAN
```

Creator Loop 的 approved slot 创建 content run 后立即写入 ProductionPlan。若设置 `max_cloud_cost` 且 cloud 成本未知，计划被阻止并要求明确人工确认；不会修改全局预算，也不会替代原有 Topic、内容或发布审批。

## 主要修改文件

- Schema：`alysia/schemas/production.py`、`alysia/schemas/__init__.py`
- Production：`alysia/production/registry.py`、`router.py`、`planner.py`、`executor.py`、`metrics.py`、`cache.py`、`cost.py`、`quality.py`、`service.py`
- 集成：`alysia/core/resources.py`、`orchestrator.py`、`alysia/planning/loop.py`、`alysia/workers/subtitle.py`、`alysia/providers/asr/faster_whisper.py`
- CLI/配置：`alysia/cli.py`、`alysia/core/config.py`、`config.example.yaml`
- 测试：`tests/test_production.py`
- 文档/版本：`README.md`、`development_report_alpha11.md`、`pyproject.toml`、`alysia/__init__.py`

## 测试

alpha11 新增 15 个离线测试，对应要求的 constraints、registry、plan、offline exclusion、VRAM rejection、serial GPU、quality routing、fallback、cache key/TTL、metrics、unknown cost、quality gate、Creator Loop plan gate 和 optimizer idempotency。

最终全量结果：`108 passed in 33.73s`。

Remotion smoke test：`npm run check` 通过，发现 `VideoComposition`（1920x1080、30fps）。

## Demo

demo run：`20260807_175616_cb2fbe40`（review-ready，主题“为什么AI Agent还不是AGI？”）。

| Profile | Plan ID | TTS | Render | 主要差异 |
|---|---|---|---|---|
| draft | `prod_c7f7531949b8791f` | `tts.mock` | `render.mock` | 最快、可复现，仅适合测试/draft |
| standard | `prod_c08275429621d7ae` | `tts.sapi` | `render.mock` | 尊重该历史 run 的当前 renderer 配置 |
| high | `prod_cf4a8eebc9ac66b0` | `tts.sapi` | `render.remotion` | 更高视频质量并启用 high QA |

由于真实 Research、Ollama 和 Cloud LLM 均未就绪，三档都选择 `research.mock` / `llm.mock` 并保留 warning，没有假装成正式事实来源或高质量模型。

### Fallback demo

在 high plan 中模拟 `render.remotion` 失败：

```text
render.remotion
  → failure: demo simulated Remotion failure
  → render.mock
  → quality impact: high → low
```

执行成功；metrics 共 13 条 stage 记录、1 条 fallback，未发生静默降级。

### Cache demo

- Executor simulation：Research、Script 两个 stage 命中 cache。
- Production Cache index：Research 与 Script 二次 lookup 均命中。
- Research entry：TTL=24 小时。
- 索引：`workspace/production_cache/index.json`。

### Quality / Report

- high ProductionQualityGate：PASS。
- `production report` CLI：PASS。
- demo bottleneck（mock simulation）：Storyboard 约 0.016 秒；该数字只描述 mock simulation，不是模型 benchmark。
- 所有 cost 输出：unknown，未伪造 API 单价或本地电费。

## 已知限制与当前瓶颈

1. Ollama 未安装，无法验证本地 LLM 的真实显存、时延或输出质量。
2. Cloud LLM 与 Web Research 仍是占位实现，无法形成正式高质量脚本/事实链。
3. CosyVoice 与 faster-whisper 未安装；当前正式可用音频路径是 SAPI + deterministic subtitle timing。
4. `peak_vram_mb` 需要连续采样才可信；当前只有前后 probe 能力，因此 peak 保持 null。
5. Cache index 已覆盖目标 artifact type，但现有 VoiceWorker 自有 scene cache 与统一 ProductionCache 尚未完全合并迁移。
6. Planner 使用声明能力和透明启发式排序，不是硬件 benchmark；历史样本不足时不自动改变 ranking。
7. 工作树仍包含 alpha1-alpha10 原有大量未提交文件；本轮没有替用户提交或清理。

## Alpha12 建议

可以进入 **Multi-Agent Creator Studio**，但继续使用单总控编排器：Researcher、Writer、Designer、Editor、Analyst、Producer 作为明确角色/worker，由一个 Director/Orchestrator 串行调度 GPU-heavy 工作。先建立角色输入输出 contract、共享 ProductionPlan 与统一审计，再考虑有限并行；不要过早引入大型 Agent 框架、自治源码修改或复杂并发。
