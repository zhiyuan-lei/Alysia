# Alysia alpha13.5 Runtime Deployment Report

## 结果

alpha13.5 已从 Mock/adapter 状态推进到真实本地 T2V 可运行状态：

- ComfyUI 0.31.0 原生 H3 节点已部署并通过 API health。
- 官方 Comfy-Org H3 T2V 量化模型组已下载并完成 SHA-256 校验。
- Alysia T2V workflow 已转换为真实 API format，可注入 prompt、seed、duration、resolution、steps 与模型配置。
- `ComfyUIProvider` 能提交、轮询、收集 MP4、保存 prompt id，并识别新版 `SaveVideo` 输出。
- ResourceManager 记录 VRAM/RAM 前后状态；ComfyUI provider 完成后调用 `/free` 卸载模型。
- VisualQA 对首个真实 MP4 通过解码、时长、黑帧、冻结帧与 provenance 检查。

## 当前机器覆盖

- 配置预算：RTX 4060 Ti / 8192 MB VRAM / 24 GB RAM / 串行 GPU。
- Windows 检测事实：8188 MiB VRAM、31.85 GiB physical RAM、2 GB pagefile。
- 旧 alpha13.5 报告中的 32 GB 检测记录未被改写；当前覆盖位于 `config/current_machine_profile.yaml`。

## 来源与版本

- ComfyUI：`D:\ComfyUI`，version 0.31.0，commit `dd79c643a95402136a75a28f6187d843bcf457ed`。
- Workflow source：`Comfy-Org/workflow_templates@ab972e047428bd02b274de70ae6d6bba1573f9e1`。
- Model source：`Comfy-Org/MiniMax-H3@eb8a16107c595128b3a578f82d2ce2f75920c355`。
- Python 3.12.12；PyTorch 2.13.0+cu130；CUDA runtime 13.0。
- 未安装第三方 custom node，未修改驱动、系统 CUDA、代理、Windows Update 或 pagefile。

## 首次真实 smoke test

| 项目 | 实测 |
|---|---|
| mode | T2V |
| prompt | small silver robot in a neon-lit workshop |
| resolution | 608x352 |
| duration | 73 frames / 24 fps = 3.042 s |
| steps | 6 |
| generation wall time | 170.81 s |
| peak VRAM used | 7678 MiB |
| peak system RAM used | 25918.8 MiB |
| minimum available RAM | 6691.1 MiB |
| OOM | no |
| output | `D:\ComfyUI\output\alysia_h3_smoke\t2v_608x352_73f_6steps_00001_.mp4` |
| VisualQA | PASS |

VisualQA metrics：duration 3.042、width 608、height 352、freeze_ratio 0、black_ratio 0、provenance complete、production eligible。

## Alysia Provider API 验收

`python -m alysia visual h3-smoke-test` 又通过 Alysia 的 `ComfyUIProvider/H3LocalProvider` 提交了一次独立真实 job：

- run_id：`h3_smoke_20260808_174552`
- ComfyUI prompt_id：`da674ae1-7779-4b7b-aa57-fdc3464ea896`
- Provider generation_time：105.75 秒。
- 输出：`D:\ComfyUI\output\alysia\h3_smoke_20260808_174552\smoke-t2v_00001_.mp4`。
- VisualQA：PASS，production_eligible=true。
- ResourceManager before/after：VRAM 959→2909 MiB、RAM 10661→25089 MiB；连续峰值以首次监控 smoke 的 7678/25918.8 MiB 为准。
- provider release 后显存回落至约 1 GiB，验证了 ComfyUI `/free` 释放路径。

## 限制与降级

1. 实测 RAM 峰值超过 24 GB 预算，因此 capability 仍保持 experimental，不能直接提升 stable。
2. T2V 已真实验证；I2V/R2V 只有官方 UI 模板，尚未完成 Alysia API 集成测试。
3. R2V 需要额外 ref2va diffusion 权重，本轮未下载，避免无必要增加约 20 GB。
4. H3 原生音频未用作主旁白；本次 workflow 不解码音频，VoiceAgent/字幕链路保持不变。
5. 当前 pagefile 仅 2 GB；项目没有自动修改系统设置。

## 自动化验收

- 默认全量 `pytest` 不加载大型模型，回归测试通过，H3 本地测试按设计跳过。
- 显式设置 `ALYSIA_RUN_H3_LOCAL=1` 后执行 `tests/test_h3_local_integration.py`：`1 passed in 168.01s`。
- 该集成测试通过 Alysia provider 提交真实 T2V job，并验证输出 MP4 与 VisualQA。

## 推荐默认预算

- draft：0 个 H3 镜头。
- standard：1–3 个，建议总计 <=18 秒。
- high：最多 5 个，建议总计 <=30 秒；仍需人工提高生产时间预算。
- 以上是初始策略，不是绝对硬件上限；后续根据独立任务样本调整。

## 工作树保护

本阶段只在现有工作树上增量修改。没有执行 reset、clean、checkout 覆盖、stash、rebase、commit、squash 或清理；alpha1–16 的既有未提交成果保持原样。
