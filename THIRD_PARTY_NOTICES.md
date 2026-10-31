# 第三方组件与许可声明

本仓库自身以 [MIT License](LICENSE) 发布。以下第三方组件随仓库分发，各自保留原始许可与版权声明。

| 组件 | 位置 | 许可 | 版权 |
| --- | --- | --- | --- |
| bilibili-mcp | `tools/bilibili-mcp/` | MIT | Copyright (c) 2026 AGI_Ananas |
| Remotion 模板 | `video/remotion/` | 依赖本身遵循各自许可 | 见 `video/remotion/package.json` 依赖清单 |

## 未随仓库分发的内容

以下内容因体积或敏感性不在仓库内，使用时需自行获取并遵守其许可：

- **MiniMax H3 模型权重**：`models/` 下的 `.safetensors` 文件不随仓库提供。模型来自 `Comfy-Org/MiniMax-H3`，适用 `minimax-h3-community-license-agreement`，使用前请阅读原始协议。
- **文本编码器与 VAE**：同上，属于模型资产，需自行下载并校验。
- **第三方字体与素材**：渲染模板若引用系统字体（如 Microsoft YaHei），不随仓库分发字体文件；商用前请确认字体授权。

## 前端依赖

`control-center/` 与 `video/remotion/` 的 `node_modules` 不入库，由 `package.json` / `package-lock.json` 还原。依赖许可以各自包为准。

## 报告许可问题

如你认为本仓库某处使用第三方素材的方式不当，请发邮件或在仓库 issue 中说明具体路径与依据，我们会核对并处理。
