# Alysia 本地 ComfyUI + MiniMax H3 实测部署

本页记录 `2026-08-08` 当前机器上的真实部署结果，不是面向任意硬件的通用教程。

## 当前机器与运行预算

- GPU：NVIDIA GeForce RTX 4060 Ti，8188 MiB 可检测 VRAM。
- Alysia 运行预算：24 GB RAM、8192 MB nominal VRAM、GPU-heavy provider 严格串行。
- Windows 实际检测：34,193,965,056 bytes（31.85 GiB）物理内存。
- Pagefile：2048 MB；部署没有自动修改系统虚拟内存。
- 当前覆盖配置见 `config/current_machine_profile.yaml`。历史报告中的 32 GB 检测记录保留原样。

## 已安装组件

- ComfyUI：`D:\ComfyUI`
- ComfyUI version：0.31.0
- ComfyUI commit：`dd79c643a95402136a75a28f6187d843bcf457ed`
- 独立 Python：3.12.12，位于 `D:\ComfyUI\.venv`
- PyTorch：2.13.0+cu130；`torch.cuda.is_available() == True`
- comfyui-workflow-templates：0.11.37
- comfy-kitchen：0.2.28
- comfy-aimdo：0.4.13
- 未安装第三方 custom node；H3 使用 ComfyUI 原生节点。

启动参数：

```powershell
Set-Location D:\ComfyUI
.\.venv\Scripts\python.exe main.py `
  --listen 127.0.0.1 `
  --port 8188 `
  --lowvram `
  --disable-pinned-memory `
  --disable-async-offload `
  --reserve-vram 1 `
  --disable-auto-launch
```

API health：`GET http://127.0.0.1:8188/system_stats`。

## 模型来源与文件

来源：`Comfy-Org/MiniMax-H3`，revision `eb8a16107c595128b3a578f82d2ce2f75920c355`。模型页声明使用 `minimax-h3-community-license-agreement`；实际使用前仍应阅读仓库中的完整协议。

| 模型 | 本地路径 | bytes |
|---|---|---:|
| FL2VA pruned INT8 ConvRot | `D:\ComfyUI\models\diffusion_models\minimax_h3_fl2va_pruned_int8_convrot.safetensors` | 20,970,379,616 |
| Qwen3-VL 32B NVFP4 AWQ encoder | `D:\ComfyUI\models\text_encoders\qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors` | 15,687,142,551 |
| Video VAE FP16 | `D:\ComfyUI\models\vae\minimax_h3_video_vae_fp16.safetensors` | 5,207,808,496 |
| Audio VAE FP32 | `D:\ComfyUI\models\vae\minimax_h3_audio_vae_fp32.safetensors` | 605,254,808 |

下载清单和 SHA-256 校验结果：`D:\ComfyUI\alysia_h3_model_manifest.json`。四个文件均已通过大小与 SHA-256 校验。

## Workflow

- 官方 UI 模板快照：`D:\ComfyUI\alysia_workflows`
- 来源 commit：`Comfy-Org/workflow_templates@ab972e047428bd02b274de70ae6d6bba1573f9e1`
- Alysia 可提交的 T2V API workflow：`workflows/comfyui/h3/t2v.json`
- I2V/R2V 官方模板已下载，但 Alysia API 绑定与真实运行尚未验证；R2V 还需要另一套 ref2va diffusion 权重。

## 首次真实 T2V smoke test

- Prompt：银色小机器人在霓虹工作室缓慢行走，侧向跟拍，无文字或水印。
- 分辨率：608x352。
- 帧数/FPS：73 / 24，实际 3.042 秒。
- Steps：6；seed：20260808。
- ComfyUI 执行时间：170.81 秒。
- 峰值 VRAM：7678 MiB。
- 峰值系统 RAM 使用：25918.8 MiB。
- 最低可用 RAM：6691.1 MiB。
- OOM/process kill：无。
- 输出：`D:\ComfyUI\output\alysia_h3_smoke\t2v_608x352_73f_6steps_00001_.mp4`。
- VisualQA：PASS；duration=3.042、608x352、black_ratio=0、freeze_ratio=0、production_eligible=true。

首个监控脚本曾因 ComfyUI 0.31 `SaveVideo` 在 history 中使用 `images` 字段承载 MP4 而产生 false negative；实际 history 状态为 success、文件存在，解析器已经修复。

## 24 GB 预算结论

此配置能在当前实际 31.85 GiB 机器上运行，但首次实测系统 RAM 使用峰值约 25.3 GiB，已经超过指定的 24 GB 运行预算。由此不能声称“24 GB RAM 已稳定验证”。Alysia 仍按 24 GB 做保守预算，并默认：

- draft：禁用 H3。
- standard：最多 3 个镜头、建议总计不超过 18 秒。
- high：最多 5 个镜头、建议总计不超过 30 秒。
- 所有 H3 job 串行；运行前释放其他 GPU provider；完成后调用 ComfyUI `/free`。
- 默认 608x352、3 秒 smoke profile；正式镜头再按实测逐步提高。

若机器真实只有 24 GB 物理内存，当前 2 GB pagefile 很可能成为明显风险。项目不会自动修改 pagefile；建议先升级到至少 32 GB，长镜头或更高分辨率更适合 48/64 GB。

## 常用命令

```powershell
Set-Location D:\Alysia
.\.venv\Scripts\python.exe -m alysia visual doctor
.\.venv\Scripts\python.exe -m alysia visual h3-setup-status
.\.venv\Scripts\python.exe -m alysia visual h3-smoke-test
.\.venv\Scripts\python.exe -m alysia visual generate <run_id> --provider comfyui-h3
```

真实集成测试默认跳过大型模型：

```powershell
$env:ALYSIA_RUN_H3_LOCAL='1'
.\.venv\Scripts\python.exe -m pytest tests\test_h3_local_integration.py -m h3_local
```
