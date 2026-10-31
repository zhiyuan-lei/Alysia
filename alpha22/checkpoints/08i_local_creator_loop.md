# Alpha22 本地创作闭环实测（2026-10-02）

## 范围

新增 CLI `alysia local-create` 与控制中心“本地创作”页，共用 `LocalCreatorService`。用户自己填写每镜头提示词、参考图或受信任的 ComfyUI API 工作流、配音文案；Alysia 串行生成、SAPI 配音、Remotion 剪辑、VideoQA 检查并进入本地人工审看。没有 Bilibili LIVE 发布。

## 真实 H3 → 配音 → 剪辑

- 输入：`alpha22/field_smoke/local_creator/h3_real_smoke_spec.json`，使用已有参考图，但本轮由新 CLI 入口重新运行 H3 推理，**没有复用旧视频片段**。
- 任务：`local_20261002_103801_fe05a505`，状态 `COMPLETE` / `review_ready`。
- H3：固定 staged I2V，1280×720、24fps、90 帧、3.75 秒。四阶段全部 `PASS`；0.5 秒间隔采样的整卡 VRAM 峰值 4676 MiB，整机 RAM 峰值 12653 MiB，低于 7.5 GiB 运行时显存停止线和 24 GiB RAM 包络。分阶段耗时约 1103.6 秒。
- SAPI：真实旁白 WAV，4.3745 秒；最终 MP4 4.583333 秒，1280×720、24fps、H.264/AAC、48kHz 双声道，完整解码 QA `PASS`。音轨 volumedetect 均值 -21.1 dB、峰值 -1.5 dB，不是静音。
- 成片：`D:\Alysia\workspace\local_creator\local_20261002_103801_fe05a505\output\final.mp4`；2,180,425 字节；SHA-256 `aac46ca6ba532ba0495cc9d8255361a14a95fe812956f20c91f7711e46dc638e`。
- 原始测量和阶段日志：该任务的 `h3/blue_blossoms/wallpaper_20261002_103801_39f0dc3f/summary.json` 及每阶段日志；最终状态、哈希、QA 位于 `state.json`。

## ComfyUI API → 配音 → 剪辑

- ComfyUI 监听本机 `127.0.0.1:8188`，先确认空队列。校准图仅使用内置 `EmptyImage`、`RepeatImageBatch`、`PrimitiveStringMultiline`、`CreateVideo`、`SaveVideo`，输出 320×180/24fps/1 秒纯色视频；不加载 H3 模型。重启为正常低显存服务（未禁用自定义节点）后的校准结果见 `alpha22/field_smoke/local_creator/comfyui_cpu_video_calibration.json`：采样整卡 VRAM 基线/峰值均 792 MiB，增量 0 MiB；在任务元数据中用最低 1 MiB 的保守正数录入预算。该采样无法证明复杂工作流的峰值。
- CLI 任务：`local_20261002_110715_c5fbb0be`，`COMPLETE`，来源是 ComfyUI API 真实视频，不是 mock。其成片 QA `PASS`。
- 控制中心真实 HTTP+CSRF 提交任务：`local_20261002_111540_b7cd9cb0`，`COMPLETE` / QA `PASS`；`GET /api/local-create/jobs` 可查，视频 GET 返回 200 `video/mp4`。它证明网页后端可发起并追踪同一工作流，前端表单另由 Vitest 检查。
- 正常低显存 ComfyUI 服务（已加载本机自定义节点）复验 CLI 任务 `local_20261002_112220_8fc1d8c8`，同样 `COMPLETE` / QA `PASS`；复验后 ComfyUI `/system_stats` 与控制中心 `/api/health` 均可达、队列为空。
- 上述 ComfyUI 工作流将自写 `prompt` 绑定到字符串节点，作用于输出文件名前缀；**它不是语义提示词驱动的画面生成**。真实 ComfyUI 内 H3 T2V 节点图没有在 6 GiB 预算下重新通过，不得据此改成 PASS。

## 回归与边界

- 本轮完整 `uv run pytest -q --disable-warnings` exit 0；控制中心 Vitest 7 项通过，Vite build 通过；新代码 `py_compile` 和 `git diff --check` 通过。
- ComfyUI 自定义 API 工作流要求 `SaveVideo`、用户 prompt 文本绑定、同配置测得的增量峰值 <=6144 MiB；提交前 ResourceGuard、空队列门槛，运行时按 7.5 GiB 整卡 VRAM / 24 GiB RAM 采样并请求中断。监控为采样式，不是瞬时硬限制。
- 旧版 ComfyUI H3 一次性 T2V 峰值约 7678 MiB，依旧不符合 6 GiB 单任务预算。当前 PASS 指 staged H3 单图视频链路和通用 ComfyUI API 视频链路，不能外推到任意 ComfyUI/H3 工作流或内容审美。
- 保留原 BLOCKED 证据；未执行 git reset/clean/restore/checkout/stage/commit。
