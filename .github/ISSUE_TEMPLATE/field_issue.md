---
name: 现场问题（H3 / ComfyUI / 平台对接）
about: 真实运行环境下的故障，通常与显存、模型或外部服务有关
title: "[field] "
labels: field
---

## 出错环节

<!-- 例如：H3 t2v 生成、ComfyUI 提交、SAPI 配音、Remotion 渲染、投稿包校验。 -->

## 关键产物

- run_id：
- 相关 JSON 路径（相对路径即可，例如 `runs/<run_id>/reliability/resource_guards/*.json`）：
- `resource_guards` 里的 `status` 与 `reasons`：

## 资源快照

```text
GPU：
VRAM total / used / free：
系统 RAM available：
磁盘剩余：
```

获取方式：`python -m alysia doctor`，或对应 `resource_guards` 文件里的 `observed_values`。

## 已排除的可能

<!-- 例如"确认 ComfyUI 在 8188 端口可用"、"确认权重文件存在"。没做过的检查也请写明未执行。 -->

## 附加上下文
