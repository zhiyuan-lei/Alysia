# 本地创作：视频、配音、剪辑

从 Alysia CLI 或控制中心的“本地创作”页提交同一份创作任务。每个镜头由用户填写画面提示词和配音文案，最多 5 个镜头；Alysia 串行生成画面，用本机 SAPI 配音、Remotion 剪辑和 VideoQA 检查，产物只进入本地人工审看，不自动发布。

## 启动与使用

在 `D:\Alysia` 中运行：

```powershell
uv run python -m alysia control start --open-browser
```

自定义 ComfyUI API 工作流还需要本机 ComfyUI 服务。若尚未运行，可在另一 PowerShell 窗口启动（仅监听本机）：

```powershell
Set-Location D:\ComfyUI
.\.venv\Scripts\python.exe main.py --listen 127.0.0.1 --port 8188 --lowvram --disable-auto-launch
```

打开“本地创作”，选择视频后端，填写镜头 ID、提示词、配音文案和输入。提交后可在同页查看阶段、失败原因和完成后的 MP4；服务器中断后可恢复任务。CLI 使用相同后端：

```powershell
uv run python -m alysia local-create run D:\Alysia\alpha22\field_smoke\local_creator\h3_real_smoke_spec.json
uv run python -m alysia local-create list
uv run python -m alysia local-create status <run_id>
uv run python -m alysia local-create resume <run_id>
```

任务状态保存在 `D:\Alysia\workspace\local_creator\<run_id>\state.json`，成片为 `output\final.mp4`。恢复时会校验已完成片段和配音的 SHA-256；H3 分阶段中断时，会在参考图与提示词未变化的前提下恢复已完成阶段。CLI 的 `run` 为同步命令，控制中心在后台执行；不要同时向另一个入口重复提交同一任务。

## 两种视频后端

- `h3_staged_i2v`：选择本机参考图，填写动作提示词。调用本机 MiniMax H3 的已验证分阶段单图工作流，固定输出 1280×720、24fps、90 帧（3.75 秒）。可自写提示词，但不能在此模式任意更换节点图。一次只处理一个镜头，6 GiB 为任务提交预检上限，7.5 GiB 为采样式整卡显存停止线，RAM 包络保持 24 GiB。
- `comfyui_api`：粘贴受信任的 ComfyUI API-format JSON 节点图。必须有 `_alysia.api_format=true`、`prompt` 节点图、`SaveVideo` 节点，以及经同一配置实测的 `_alysia.measured_peak_vram_mb`（1–6144 MiB）。必须通过 `_alysia.bindings.prompt` 将用户提示词绑定到现有的文本输入，如 `"prompt": "12.inputs.text"`；还可绑定 `seed`、`length`、`duration_sec`、`width`、`height`、`steps`、`filename_prefix` 等值。ComfyUI 必须已在配置的本机 API 地址运行，队列为空。Alysia 会按估计峰值预检，并对运行时整卡显存 7.5 GiB / 系统 RAM 24 GiB 进行采样监控；采样不是硬实时保证。

ComfyUI 工作流的峰值字段是用户提供的测量证据，不是 Alysia 自动推断。不要把旧版 H3 一次性 T2V 工作流（历史峰值约 7678 MiB）误填为 6 GiB 以下；该旧路径仍未通过此硬件包络。自定义工作流中的节点可能调用本机插件或读取文件，只提交你信任的节点图。

每个镜头的旁白由真实 SAPI 合成；无声视频与配音会按镜头顺序组装、加字幕并导出 1280×720 H.264/AAC MP4。VideoQA 仅验证工程属性（流、时长、解码等），不等同于内容质量审查。输出仍需人看画面、听声音。

## 状态口径

`COMPLETE` 表示该任务的最终 MP4 通过基础 QA，**不表示**所有后端和任意工作流都已验证。`FAILED` 会保留已完成片段和错误，检查原因后点“恢复”或运行 CLI `resume`。H3 长镜头可能需要较长时间；运行期间不要并发启动其它 GPU 工作负载。绝不自动执行 Bilibili LIVE 发布。
