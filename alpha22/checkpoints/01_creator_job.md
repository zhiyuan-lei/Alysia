# Alpha22 Checkpoint 01 — CreatorJob

## Status

PASS

## Files changed

- `alysia/creator/models.py`
- `alysia/creator/store.py`
- `alysia/creator/service.py`
- `alysia/creator/__init__.py`
- `tests/test_creator_job.py`
- `tests/test_alpha22_creator.py`（仅将旧状态断言同步为规范名称）
- `alpha22/README.md`
- `alpha22/checkpoints/00_baseline.md`
- `alpha22/checkpoints/01_creator_job.md`

## Implementation

- 复用现有 Pydantic v2 `CreatorJob`，保留既有 Creator/Run/evidence 字段与接口。
- `job_id` 改为模型必填；`CreatorJob.new()` 生成稳定的 `creator_<16 hex>` UUID-derived ID。持久化数据缺失或空 ID 会被拒绝，不会静默生成新身份。
- 显式定义审批状态：`DRAFT`、`REVIEW`、`APPROVED`、`REJECTED`、`REVISION_REQUIRED`。
- 显式定义发布状态：`NOT_READY`、`PUBLISH_READY`、`PUBLISHING`、`PUBLISHED`、`FAILED`。
- 增加经 Pydantic 重新验证的审批与发布转换；审批不能跳过 REVIEW，APPROVED 必须记录 `human:` actor 与时间。
- 模型级不变量拒绝未 APPROVED 的 `PUBLISH_READY/PUBLISHING/PUBLISHED`，并拒绝缺失平台回执字段的 PUBLISHED 状态。

## Persistence

- 复用 `alysia.core.io` 的原子 JSON 写入、备份和恢复读取。
- `CreatorJobStore.create()` 防止覆盖已有 job。
- `save()` 在落盘前重新验证模型。
- `load()` 从 JSON 恢复并验证模型。
- `update()` 拒绝身份/版本保留字段被覆盖，自动递增 `current_revision`，在写入新版本前保存旧 JSON snapshot，并把 snapshot 路径、原因、操作者和时间写入 revision history。

## State transitions

```text
DRAFT → REVIEW → APPROVED
               ↘ REJECTED
               ↘ REVISION_REQUIRED → DRAFT

APPROVED → PUBLISH_READY → PUBLISHING → PUBLISHED
                                      ↘ FAILED
```

核心 gate 位于模型层，绕过 service 直接反序列化非法状态也会失败。本步骤未实现或触发任何真实发布动作。

## Tests

执行：

```text
uv run pytest tests/test_alpha22_creator.py tests/test_creator_job.py -q
```

覆盖：create、save/load、serialize/deserialize、missing ID、approval transition、invalid publish transition、PUBLISHED receipt validation、versioned update 与 revision snapshot。

## Test result

```text
18 passed
Exit code: 0
```

第二次回归无 warning。未运行 GPU、ComfyUI、H3、浏览器或真实平台操作。

## Known limitations

- JSON store 面向本地单进程工作流；本步骤未增加多进程锁或数据库事务。
- `CreatorJob.status` 作为既有兼容总状态继续保留；审批与发布 gate 由新的专用 Enum 字段负责。
- 仅运行 CreatorJob 定向及既有 Creator 兼容测试，未重跑全仓库测试。
- Topic Discovery、Research/Grounding、production、Publisher、metrics、reflection、memory learning 和 Beta field run 均未进入本步骤。

## Git diff summary

- 起始与结束 tracked diff 均为：28 files changed, 5,129 insertions, 113 deletions。
- `alysia/creator/` 与 `tests/test_alpha22_creator.py` 在本步骤开始前已是 untracked；Git 无法用普通 tracked diff 将其中本次增量与既有内容分离，因此本 checkpoint 明确列出触及文件。
- 新增 `alpha22/` 与 `tests/test_creator_job.py`，当前均为 untracked；未 stage、未 commit。
- 未清理或修改来源不明的 Alpha1–21 成果。

## Next safe step

仅推荐：Alpha22 Step 2 — Topic Discovery + Research/Grounding。当前 checkpoint 完成后停止，不自行执行 Step 2。

