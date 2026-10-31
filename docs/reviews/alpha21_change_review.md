# Alpha21 Change Review

## 目标

在不复制业务规则的前提下，为 Alpha1-20 的既有能力增加本地可视化控制/观察层；不进入 Alpha22。

## 实际改动

- `alysia/control/`：FastAPI adapter、聚合 facade、本地 server。
- `control-center/`：React/Vite 前端、组件测试和 production build。
- `alysia/cli.py`：新增 `control start`，保留全部既有 CLI。
- `config/security_policy.yaml`：最小权限 `ControlCenterAdapter`。
- `tests/test_control_api.py`：路径、secret、恢复、审批和绕过负向测试。
- `scripts/alpha21_demo_seed.py`：隔离的 Alpha19 恢复 UI 测试 fixture。
- README、ledger、regression matrix、设计概念和浏览器证据。

## 无关改动

未清理或重写 Alpha1-20；未修改系统网络、代理、驱动、CUDA；未进入真实平台运营。开始前已有的大量未提交改动全部保留。

## 新依赖

- Python：FastAPI、Uvicorn。
- Frontend：React、Vite、Lucide；Vitest/Testing Library/jsdom 仅用于测试。
- 未引入 Electron、大型 UI framework、重型状态管理或新的 Agent 框架。

## API、schema 与 config 变化

- 新增 `/api/*` 只读和受控写 adapter；没有 `/api/publish` 或任意 shell/config endpoint。
- 新增本地 CSRF cookie/header 和 Origin/Host 检查；默认只绑定 `127.0.0.1`。
- 未修改既有 artifact、approval、recovery 或 evaluation schema。

## Security 与 reliability 风险复核

- Artifact 内容只能来自 run state 中已声明且位于 run root 内的白名单扩展。
- Write endpoint 既要求 UI 二次确认，也重新走 PolicyEnforcer/Approval 或 RecoveryPolicy。
- Approval approve/reject 产生脱敏 audit event；secret 由 Alpha20 Redactor 清洗。
- UI 不直接调用 provider，无法手动覆盖 Alpha18 gate，也不提供 force-ignore recovery。

## UI 限制

- Desktop-first；小于 1080px 不在 Alpha21 支持范围。
- 本地 session/CSRF 不是公网认证方案。
- 页面显示当前已有 artifact 数据；缺失数据使用 empty state，不生成假生产数据。
- 不支持任意 ComfyUI workflow 编辑、系统设置或凭证管理。

## Alpha22 前置依赖

Alpha21 工程 Gate 全通过后，Alpha22 仍需要独立的真实 Bilibili 10-video field protocol 和人工发布/数据证据；Control Center 完成不等于真实运营完成。
