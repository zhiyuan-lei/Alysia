# Alysia v0.1-alpha.8 开发报告

生成日期：2026-08-07（Asia/Shanghai）

## 结果

仓库路径：`D:\Alysia`

本阶段已完成默认需要人工批准、离线可测且可审计的发布与反馈闭环：

```text
REVIEW_READY
  → publish review
  → ApprovalRecord(package_hash + accepted_warnings)
  → PublishJob
  → validate
  → Mock submit / Bilibili safe boundary
  → external_id
  → FEEDBACK_WAITING
  → Manual / Mock feedback
  → FeedbackMapper
  → existing VideoMetrics + Analytics
  → PublishEpisodeMemory + tentative Lessons
  → LEARNING
```

系统默认不自动登录、不保存密码/cookie/token、不无人审核发布、不自动评论或私信。

## Alpha.7 前置状态

- alpha.8 开始前全量基线：`70 passed in 21.49s`。
- `python -m alysia doctor` 通过：10 项可用，5 项可选能力缺失/未就绪。
- 复用历史 `review_ready` run：`20260807_175616_cb2fbe40`。
- 该 run 已有 final.mp4、封面、metadata、publish package、video QA 与 publish QA。
- 现有 publish QA 有两项 warning：视频短于配置目标时长、没有可发布来源链接；alpha.8 审批已显式记录接受，未静默忽略。
- alpha.3-alpha.7 的既有未提交成果全部保留，未重建项目。

## 新增能力

- `ApprovalRecord`、`PublishJob`、`PublishValidationReport` 结构化 schema。
- 稳定 job_id 和完整投稿包 SHA-256；同一 run/provider/package 重复 submit 不重复创建投稿。
- `BasePublishingProvider`、`MockPublishingProvider`、`BilibiliPublishingProvider`。
- `publish review/approve/validate/submit/status` CLI。
- validation 检查 review_ready、video/publish QA、视频、封面、metadata、mock/testing 产物、warning 接受情况、审批存在性与包哈希一致性。
- 凭证只从环境变量读取；错误消息自动 redact，不把凭证写入 repo、logs 或 run artifacts。
- `FeedbackRecord`、`CommentInsight`、`PublishEpisodeMemory`。
- `BaseFeedbackProvider`、`ManualFeedbackProvider`、`MockFeedbackProvider`、`BilibiliFeedbackProvider`。
- `FeedbackMapper` 将反馈规范化为现有 `VideoMetrics`，复用 alpha.6 Analytics/LearningPipeline。
- feedback digest、run_id/external_id 映射和重复导入幂等。
- 评论仅进行轻量规则提取：常见主题、正负信号、问题和内容请求；不自动回复。
- Memory 新增 `publish_episodes/`；来源严格区分 `real|mock|manual`。
- Creator Loop stage 扩展为 `review_ready → publish_approval → publish_job → feedback_waiting → learning`。

## 主要修改文件

- Schema：`alysia/schemas/publishing.py`、`alysia/schemas/feedback.py`、`alysia/schemas/__init__.py`
- 发布：`alysia/publishing/*`、`alysia/providers/publishing/*`
- 反馈：`alysia/feedback/*`、`alysia/providers/feedback/*`
- 状态/配置：`alysia/core/config.py`、`alysia/core/run.py`、`alysia/core/state.py`
- 复用学习闭环：`alysia/learning/pipeline.py`、`alysia/learning/memory.py`
- Creator Loop schema：`alysia/schemas/planning.py`
- CLI：`alysia/cli.py`
- 配置：`config.example.yaml`、`.gitignore`
- 测试：`tests/test_publishing_feedback.py`、`tests/test_state.py`、`tests/helpers.py`
- 文档/版本：`README.md`、`development_report_alpha8.md`、`pyproject.toml`、`alysia/__init__.py`

## 测试

alpha.8 新增 8 个离线测试场景，覆盖：

1. PublishJob/ApprovalRecord schema。
2. 发布验证与 approval required。
3. Mock submit 与重复提交幂等。
4. Bilibili 缺凭证安全失败且不发网络请求。
5. Manual feedback JSON 导入与 run/external_id 校验。
6. Feedback 映射、重复导入幂等与 PublishEpisodeMemory。
7. Mock feedback 不产生 supported lesson。
8. Creator Loop 人工门及发布阶段迁移。

阶段中间全量回归：`78 passed in 27.22s`。最终测试结果见“最终自检”。

## 完整 Mock Demo

- demo run_id：`20260807_175616_cb2fbe40`
- publish job id：`job_a48cf2db364cbddd`
- package hash：`6898422397f46d500dbb3f1ee1a88009b1e9685ed91431cf5ce0d809c0cc1220`
- approval：`approved_by=human`，记录 3 项已查看 warning
- provider：`mock`
- mock external_id：`mock_bv_7f9619297c94ab45`
- feedback digest：`c7664c4ea6cfd7373067970afa29be2729330ed8abcf93c2be18577b71661750`
- feedback source：`mock`
- 最终 milestone：`memory_updated`
- publish episode memory：1 条
- 与 demo run 相关 lessons：2 条，`supported=0`

实际执行：

```powershell
python -m alysia publish review 20260807_175616_cb2fbe40
python -m alysia publish approve 20260807_175616_cb2fbe40
python -m alysia publish validate 20260807_175616_cb2fbe40
python -m alysia publish submit 20260807_175616_cb2fbe40 --provider mock
python -m alysia publish status job_a48cf2db364cbddd
python -m alysia feedback import 20260807_175616_cb2fbe40 --provider mock
python -m alysia analyze 20260807_175616_cb2fbe40
python -m alysia learn 20260807_175616_cb2fbe40
```

重复执行 submit、feedback import、analyze、learn 后：

- job_id 与 external_id 不变。
- feedback digest 不变。
- publish episode 仍为 1 条。
- 没有新增或晋升 supported lesson。
- 命令均直接复用既有状态/产物。

## Bilibili Provider 当前能力与限制

[哔哩哔哩开放平台官方文档](https://open.bilibili.com/doc) 当前公开说明包含账号授权、视频稿件发布/删除/查询和稿件数据能力；使用这些能力需要完成开发者身份认证、创建应用并取得关联 UP 主授权。

alpha.8 已实现 provider contract、凭证环境检测、人工审批、可恢复 job、错误安全落盘和 credential redaction，但没有凭非官方资料猜测具体上传 endpoint。当前无需登录即可访问的官方页面未提供可供本机无授权验证的完整上传请求契约，因此：

- 缺少 `BILIBILI_CLIENT_ID`、`BILIBILI_CLIENT_SECRET` 或 `BILIBILI_ACCESS_TOKEN` 时立即安全失败。
- 即使环境变量存在，在当前应用的官方接口文档尚未核验前仍安全失败，不发网络请求。
- 不使用网页自动登录、浏览器 cookie、二维码登录或非官方逆向接口替代。
- 后续需由用户完成开放平台入驻/应用授权，并提供该应用可见的官方接口文档，再实现真实网络提交与只读反馈。

## 当前限制

- 历史 demo 包含 mock LLM/Research 产物，只允许 Mock submit，真实 provider validation 会拒绝。
- 手工反馈只支持单条 JSON/CSV；没有后台定时轮询。
- CommentInsight 是透明规则，不做情感模型推断，也不读取原始评论账号或隐私信息。
- Feedback schema 不猜测 impressions、CTR、平均观看时长或完播率；缺失数据保持 `null`。
- 发布审批接受 warning 是显式命令行为；包内容变化会使审批失效。
- 不自动投稿、评论、私信、修改账号资料或保存凭证。

## Alpha.9 建议

建议进入 **Alysia v0.1-alpha.9：Official App Onboarding + Publish Sandbox + Operational Review UI**：

1. 完成 Bilibili 开放平台开发者认证、应用创建、关联 UP 主授权和官方沙盒接入。
2. 根据该应用可见的官方文档实现 OAuth/token 引用与 token refresh adapter；凭证仍只进系统安全存储或进程环境。
3. 在官方沙盒中验证分片上传、投稿回执、失败重试、幂等键和稿件状态查询。
4. 为 review/approval 做本地只读 UI，突出来源缺失、AI 披露、版权、时长与 mock 产物风险。
5. 增加定时、只读反馈采集，但仍保留人工发布门和禁止自动评论/私信。

## 最终自检

- `python -m compileall -q alysia`：通过。
- `pytest`：`78 passed in 32.12s`。
- `python -m alysia doctor`：通过；10 项可用，5 项可选能力缺失/未就绪。
- `python -m alysia publish --help`：review/approve/validate/submit/status 均可见。
- `python -m alysia feedback --help`：import 可见。
- 完整 mock publish/feedback/analyze/learn：通过。
- 重复 submit/import/analyze/learn：job、external_id、feedback digest 与 memory 数量保持幂等。
- 凭证扫描：`runs/`、`workspace/`、`memory/` 未发现 access token、client secret、cookie 或 password 字样。
- `git diff --check`：通过；仅有 Windows autocrlf 提示，无 whitespace error。
- `git status --short`：已执行；保留 alpha.3-alpha.7 既有未提交成果及本轮 alpha.8 改动，未清理或覆盖用户工作。
