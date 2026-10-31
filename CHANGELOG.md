# 变更记录

版本号沿用 `pyproject.toml` 中的 `version`。本项目在 `v0.1.0-beta.1` 之前是逐阶段推进的 alpha，每个阶段的能力边界以对应的 `development_report_alpha*.md` 为准。

## 未发布

- 修复 `tests/helpers.py` 未隔离 `workflow.recipe_dir` 的问题：此前跑测试会写入仓库内 `memory/workflows/`，把 `git status` 弄脏。
- 修复 `tests/helpers.py` 未隔离 `visual_generation.queue_dir` 与 `production.cache_dir` 的问题：并发跑两个 pytest 会共用一个 `workspace/visual_queue`，后启动的进程看到前一个的在跑 job，导致 3 个 studio 测试报出与被测行为无关的失败。
- 修复 `tests/test_visual_generation.py` 依赖本机真实显存的问题：GPU 被 ComfyUI 占用时会误报 4 个失败；现固定显存/内存快照，结果与机器负载无关。
- 修复 `tests/test_audio_pipeline.py` 假定系统装有中文 SAPI 语音的问题：纯英文语音对中文文本只切出一段，`>= 5` 时间戳断言会失败；改为断言时间戳存在、单调不减且落在音频时长内。
- 修复 `EvaluationStore._write` 在 Windows 上写出 CRLF 的问题：入库产物是 LF，每次评测重写都会把 `evaluation/` 变成 git diff。改为显式 `newline="\n"`。
- `config.example.yaml` 的 `project.root` 改为相对路径 `.`，clone 到任意目录都能直接用示例配置。
- 新增 GitHub Actions CI、Dependabot、issue/PR 模板与行为准则。

## v0.1.0-alpha.22 — 真实创作者闭环 Beta

- 新增 CreatorJob 聚合、状态机、修订链与去重（`alysia/creator/`）。
- 新增聚合式 CreatorQA 与人工审批/退回路径。
- 新增 Bilibili 手工交付适配器：不可变投稿包 + 校验过的真实 BV 回执；官方 API 模式在缺少已认证契约时安全失败。
- 新增带时间戳的指标、结构化复盘与简要情景记忆；不使用单轮结果直接晋升语义。
- 新增严格 Beta 台账（`evaluation/alpha22/alpha22_beta_runs.csv`）。
- 现场证据与资源策略记录见 `alpha22/`。

## v0.1.0-alpha.21 — Control Center

- FastAPI adapter + React/Vite 前端，只监听 `127.0.0.1:8765`。
- 审批、恢复、评测 gate 全部复用后端既有边界；UI 不能把 `BLOCKED` 改成 `PASS`。

## v0.1.0-alpha.20 — 安全与治理

- 应用层最小权限、审批绑定、凭证引用、脱敏审计。
- 路径 / 工具 / 网络三段策略，发布 Gate 与 Mock、真实 provider 共用。

## v0.1.0-alpha.19 — 可靠性与恢复

- 故障注入、本地续跑、部分恢复与结构化失败记录。

## v0.1.0-alpha.18 — 评测与回归智能

- 版本化离线基准、基线/候选对比与阻断式晋升 gate。

## v0.1.0-alpha.2 … alpha.17

选题、研究取证、脚本、分镜、配音、剪辑、质检、投稿包、学习闭环、自主选题、发布反馈、长期运营、创作者身份、生产优化、Creator Studio、长期 Supervisor、本地生成视觉、能力缺口与 Skill、Workflow 学习、反事实模拟、证据化知识维护。逐阶段说明见对应 `development_report_alpha*.md`。

## v0.1.0-alpha.2

首个可运行的文本创作流水线（`create` → `text_ready`）。
