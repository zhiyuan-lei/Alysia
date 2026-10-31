# Alpha22 — Real Creator Loop Beta

Alpha22 采用小步、checkpoint 驱动的执行方式。本目录保存阶段边界与可恢复的实施记录；代码、测试、checkpoint 和 Git diff 共同构成项目状态。

当前只完成 Step 1：CreatorJob 领域模型、状态约束、JSON persistence 与定向单元测试。

后续真实发布必须遵守：

```text
Human Approval
→ PUBLISH_READY
→ Explicit Publish Action
```

测试、dry-run、mock、假 content ID 或合成 metrics 均不得计为真实发布。针对 RTX 4060 Ti 8GB 与 24GB RAM，后续重型生成任务默认串行，不并发加载 ComfyUI heavy workflow 与 MiniMax H3 heavy model。

