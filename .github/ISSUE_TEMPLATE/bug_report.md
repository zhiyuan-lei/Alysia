---
name: 缺陷报告
about: 报告可复现的错误行为
title: "[bug] "
labels: bug
---

## 发生了什么

<!-- 一句话说明现象。 -->

## 期望行为

<!-- 你认为正确的结果是什么。 -->

## 复现步骤

```powershell
# 从干净仓库开始的最小命令序列
```

## 实测输出

```text
<!-- 贴关键报错或状态。不要贴真实凭证、cookie、模型权重路径。 -->
```

## 环境

- 操作系统：
- Python：`python --version`
- 安装方式：`uv sync --extra dev` / 其他
- `python -m alysia doctor` 的结论摘要（例如"12 项可用，4 项缺失"）：
- 相关组件（可多选）：文本流水线 / 音频 / 视频渲染 / H3 视觉 / Control Center / 发布 `发布包` / 其他

## 附加上下文

<!-- 截图、run_id、日志片段。runs/ 与 workspace/ 不入库，请只贴必要片段。 -->
