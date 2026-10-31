# Alysia v0.1-alpha.21 Development Report

## Status

**DONE** — Alpha21 Control Center 的完整测试、production build、浏览器 Demo A-E、Alpha18/19/20 联动 Gate 与负向安全测试均通过。未进入 Alpha22。

## Repository and worktree preservation

- Repository: `D:\Alysia`
- 开始快照执行了 `git status --short`、`git diff --stat`、`git diff --name-only`：已有 28 个 tracked 文件被修改，tracked diff 为 5,023 insertions / 113 deletions，并存在 Alpha1-20 大量 untracked 成果。
- 结束快照再次执行同样三条命令：仍为相同的 28 个 tracked 文件，tracked diff 为 5,120 insertions / 113 deletions；Alpha1-20 的 untracked 目录和报告仍存在，Alpha21 仅增量增加 `alysia/control/`、`control-center/`、测试、文档与证据。
- 未执行 reset、clean、checkout/restore、stash、rebase、commit、squash 或 amend。

## Baseline and final tests

| Check | Baseline | Final |
|---|---:|---:|
| Full pytest | 322 passed, 1 skipped, 77.93s | **335 passed, 1 skipped, 102.84s** |
| Alpha19 focused | 23 passed | **23 passed, 1.10s** |
| Alpha20 focused | 33 passed | **33 passed, 4.96s** |
| Frontend tests | not present | **6 passed, 1.26s** |
| Frontend production build | not present | **PASS**, 222.44 kB JS / 9.97 kB CSS before gzip |

唯一 skip 是显式 integration：`tests/test_h3_local_integration.py:14`，需要 `ALYSIA_RUN_H3_LOCAL=1` 才加载 42.5GB 本地 H3 stack。默认离线全量测试不会加载它。唯一 warning 是 FastAPI/Starlette `TestClient` 的上游 deprecation warning，不影响 Gate。

## Alpha20 prerequisite and linked gates

- `python -m alysia doctor`: exit 0；12 available / 4 optional missing。GPU 为 RTX 4060 Ti 8188 MiB；Alysia budget 为 VRAM 8192MB、RAM 24GB、sequential GPU。Ollama 可用但 `qwen3.5:4b` 未安装；CUDA toolkit、CosyVoice、faster-whisper 为可选未安装项。
- Alpha18: `eval_879a6ab4d0ede96b5905` vs `baseline_alpha17_75261fe47f27` → **PASS**, promotion allowed, 0 blocking findings。
- Alpha19: 23 focused tests PASS；`evaluation/reliability_demos/alpha21_final/summary.json` → **PASS**，Voice 局部恢复、H3 approved fallback、state backup、render-only retry 全通过。
- Alpha20: 33 focused tests PASS；`evaluation/security_demos/alpha21_final/summary.json` → **PASS**，Writer/Sandbox/invalid approval 均拒绝，valid scoped Mock publish 允许，secret redaction 通过。

## Architecture

- Backend: FastAPI + Uvicorn，本地 adapter 复用既有 Alysia service/use-case；没有在 API 内重写 publish、recovery、evaluation 或 provider 规则。
- Frontend: React + Vite + Lucide，React hooks 管理最小页面状态；无 Electron、UI framework、重型状态管理或 Agent framework。
- Exposure: 固定默认绑定 `127.0.0.1:8765`，Host/Origin 检查、HttpOnly SameSite session cookie、write endpoint CSRF header。
- Security: frontend 不读取 run JSON、本地任意路径或 secret；不直接调用 ComfyUI/H3/provider；没有 publish、shell、system-config endpoint。

## Pages

1. Dashboard：状态、资源、providers、Alpha18/19/20、active runs、failures、pending approvals。
2. Runs：筛选、detail、真实 timeline、artifact/MP4/H3/cover/text/JSON preview、QA、diagnose/recover/resume。
3. Supervisor：goals、plans、blockers。
4. Studio：agents、handoffs、trace。
5. Production：plan、routing、resources、fallback/cache evidence。
6. Visual：ComfyUI/H3 health、visual plans、jobs、clips/QA。
7. Knowledge：claims、sources/status、conflicts、stale/freshness。
8. Analytics / Memory / Experiments：metrics、lessons、strategies/experiments 与 provenance。
9. Approvals：publish/skill/identity 等 pending center，hash/scope/version/risk/context 和二次确认。
10. Skills / Workflows：capability registry、skills、plans/recipes/gaps。
11. Logs / Audit：按真实 audit/failure 数据展示，secret 保持 redacted。

## API summary

共 39 个 `/api` routes：System/health/dashboard 4；Runs/artifacts/recovery 7；Supervisor 3；Studio 2；Production 2；Visual 3；Knowledge 4；Analytics/Memory/Experiments 3；Approvals 4；Capabilities/Skills/Workflows 4；Audit/Errors/Evaluation 3。

所有写 endpoint 只有 run resume/recover 与 approval approve/reject；前者调用 Alpha19 `ReliabilityService`，后者重新校验 Alpha20 immutable approval context 并调用既有 service。不存在 `/api/publish`。

## Browser E2E Demo evidence

- Demo A Dashboard — **PASS**。真实页面显示 ComfyUI/MiniMax H3 `healthy`、Alpha18 `PASS`、Alpha19 `pass`、Alpha20 `secure`、RTX 4060 Ti 963/8192MB、RAM budget 9541/24576MB、disk guard safe。Evidence: `evaluation/control_center/screenshots/demo_a_dashboard_final.png`。
- Demo B Run inspection — **PASS**。打开 testing run `20260807_230208_43ee9a2b`，显示 backend-derived timeline、35+ artifacts，并创建受控 `/api/runs/.../artifacts/final_video` HTML5 video preview。Evidence: `evaluation/control_center/screenshots/demo_b_run_preview.png`。
- Demo C Recovery — **PASS**。隔离 fixture `20260809_105526_48c47359` 显示 FailureRecord；Diagnose 后二次确认 Recover，真实 Alpha19 policy 返回 `escalate_human`，没有越权继续按钮。Evidence: `evaluation/control_center/screenshots/demo_c_recovery.png`。
- Demo D Approval — **PASS**。选择明确标记 `MOCK` 的 pending publish package，二次确认后后端重算当前 hash/scope/version，审批成功；pending 数从 3 降至 2。无 approval/错误 hash 的请求由负向 API 测试拒绝。Evidence: `evaluation/control_center/screenshots/demo_d_approval.png`。
- Demo E Audit — **PASS**。页面显示 Demo C `run.recover` 和 Demo D `control.approval.approve` audit event；API 响应及事件 context 已经 Alpha20 redactor 处理。Evidence: `evaluation/control_center/screenshots/demo_e_audit.png`。
- Laptop check — **PASS**。1366x768 下 Run detail 可用，timeline 使用受控水平滚动，MOCK 标签清楚。Evidence: `evaluation/control_center/screenshots/laptop_1366_run.png`。

浏览器 Demo 使用实际启动的 local Control Center，不是只验证编译。视觉概念和实现对照保存在 `docs/design/alpha21/`；实现只显示真实 backend 数据，不用概念稿中的假数据填充页面。

## Security, reliability, and evaluation integration

- Artifact preview 只接受 run state 已声明、位于 run root 下且扩展名在 preview allowlist 的文件；路径越界测试返回 403。
- Resume 先调用 `reliability.diagnose`；Recover 调用 `prepare_recovery`，只有 policy 允许的 action 才可局部继续。
- Approval endpoint 要求 UI confirmed、CSRF、同源，并重新校验当前 hash/scope/version；consumed/changed/expired approval 无法复用。
- UI 没有 publish provider route；测试明确验证 `/api/publish` 为 404。
- Alpha18 BLOCKED 在组件测试中只读显示；API 没有 evaluation write/override endpoint。
- MOCK/REAL 来源由 backend 推导；testing snapshot 和 provider provenance 均受测试保护。

## Stub audit

对 `alysia/control`、`control-center/src`、`tests/test_control_api.py`、`scripts/alpha21_demo_seed.py` 搜索 `TODO/FIXME/pass/NotImplementedError/placeholder/mock-only`，最终结果为 **NO_MATCHES**。`alpha21_demo_seed.py` 是明确隔离、testing-only 的 E2E fixture，不属于 production path。

## Known limitations

- Control Center 仅为本地工具；CSRF/Origin 保护不等于公网认证或零信任边界。
- Provider registry 显示 warning，因为默认 Ollama 模型未安装；ComfyUI/H3 本机 provider 健康。
- Dashboard 轮询会执行真实 provider/resource health probes，加载时间取决于本机响应。
- Alpha21 不提供任意 ComfyUI workflow editor、credential management、shell console、系统配置或真实平台自动发布。

## Start command

```powershell
Set-Location D:\Alysia\control-center
npm install
npm run build
Set-Location D:\Alysia
uv run python -m alysia control start --open-browser
```

当前验证实例监听 `http://127.0.0.1:8765`。Alpha21 已完成；**没有开始 Alpha22，也没有发布任何真实 Bilibili/Douyin 内容。**
