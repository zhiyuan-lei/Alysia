# 安全策略

Alysia 会在本机运行模型、执行 FFmpeg/Remotion 渲染、读写本地状态，并可选地对接内容平台。它的安全边界值得单独说明，也欢迎你报告问题。

## 报告漏洞

请通过 GitHub 的 Private vulnerability reporting（仓库 Security 标签页 → "Report a vulnerability"）提交，不要开公开 issue，也不要在讨论区贴利用细节。

报告里请包含：

- 受影响的版本或提交号；
- 复现步骤与最小样例；
- 实际影响（能否读到本地文件、能否发出未授权请求、能否绕过人工闸门等）；
- 你希望的处理方式（仅告知 / 需要修复协调）。

一般会在 7 天内给出初步回应。修复发布前请保留细节，给我们协调时间。

## 支持范围

仅当前 `main` 分支的最新提交在支持范围内。历史 alpha 报告与 checkpoint 是开发记录，不作为安全承诺。

## 已知的设计边界

这些不是缺陷，而是项目有意保留的限制：

- **本地控制中心不是公网服务。** FastAPI adapter 只监听 `127.0.0.1`，写请求要求同源与本地 CSRF token。把它暴露到公网属于部署错误，不在支持范围内。
- **凭证不落库。** 平台凭证通过环境变量或本地凭据文件提供，不写入 run 状态、日志或产物；发布包必须是不含机密的快照。
- **发布需要两道闸。** 审核通过（APPROVED / PUBLISH_READY）与真实发布确认是两次独立动作，后者要求具名 `human:<identifier>`、时间戳、请求 ID 与修订号。
- **自定义 ComfyUI 工作流被视作可信输入。** 工作流节点可能调用本机插件或读取文件；Alysia 只做显存与队列预检，不审计节点图内部行为。只提交你自己信任的节点图。
- **模型与第三方素材的许可证由使用者负责。** 仓库不附带模型权重；MiniMax H3 等模型有各自的许可协议，使用前请阅读原始条款。

## 安全相关代码位置

| 关注点 | 位置 |
| --- | --- |
| 凭证读取与脱敏 | `alysia/security/` |
| 权限与策略判定 | `alysia/security/policy.py`、`alysia/security/tools.py` |
| 审批与审计 | `alysia/security/approvals.py`、`alysia/security/audit.py` |
| 发布闸门与包哈希 | `alysia/publishing/` |
| 控制中心鉴权与 CSRF | `alysia/control/api.py` |
| 资源预算与中断 | `alysia/reliability/` |
| 密钥扫描示例 | `evaluation/security_demos/` |

## 加固建议

部署到共享机器或多用户环境时，至少做到：

1. 只在本机回环地址提供服务，通过 SSH 隧道访问，不要做反向代理暴露；
2. 用独立系统账户运行，限制工作目录权限；
3. 定期检查 `audit/` 与 `supervisor/` 日志是否被误加入版本控制；
4. 升级依赖后重跑 `tests/test_security.py` 与 `tests/test_control_api.py`。
