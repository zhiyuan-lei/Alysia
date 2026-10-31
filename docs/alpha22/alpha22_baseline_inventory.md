# Alysia Alpha22 Baseline Inventory

## Capture scope

- Captured at: 2026-08-09T11:18:29.6149583+08:00
- Repository: `D:\Alysia`
- Access alias: `<local-checkout>` (directory junction)
- This inventory was captured before the first Alpha22 repository write.
- Secret handling: credential values were neither read nor recorded; only file existence, ignore status, paths, sizes, and hashes were captured.

## Git baseline

- Branch: `main`
- HEAD: `55da6463f0ff50e5c7e51fb1b9496aca5c8481fa`
- HEAD time: `2026-08-07T17:57:53+08:00`
- HEAD subject: `feat: add alpha.2 text creation pipeline`
- Configured remote names: none
- Existing tracked modifications: 28
- Existing untracked entries in full `git status --short -uall`: 738
- Existing planning pointer: `.planning/.active_plan = alpha19`
- Full pre-change manifest: `docs/alpha22/alpha22_baseline_git_status.txt`

The dirty tree contains the accumulated Alpha3–21 implementation, tests, reports, evidence, runtime outputs, and generated media. Alpha22 must not reset, clean, overwrite, or delete these assets.

## Alpha21 artifacts

```text
development_report_alpha21.md	8281	2026-08-09T11:08:51.4171175+08:00	2DABBF8E72420144A41765692014875F493BAF54A74D0A9E59CF64B4964317E6
docs\design\alpha21\approval-center-concept.png	1380992	2026-08-09T10:30:12.4342573+08:00	314CA23D6C7DF691C516953DB51F176777800EC64549198EC33780060F652836
docs\design\alpha21\dashboard-concept.png	1198843	2026-08-09T10:28:10.7928066+08:00	2275D4F74B42A5DAC90E388E07B1D16CF31514445D388BD3323CEA985DF7E97B
docs\design\alpha21\run-detail-concept.png	1317232	2026-08-09T10:29:11.8878503+08:00	04DDAE9C0B017FEA3F7F5CA59235786DAFFB9B54DC42AF9E8ADE2C7592ADE0D2
docs\reviews\alpha21_change_review.md	2388	2026-08-09T11:00:58.6196042+08:00	1CB0A6F825DEFBFCDF17D01D23F94D96F027B7C90C6848F3B1782DC90D29420B
scripts\alpha21_demo_seed.py	1899	2026-08-09T10:55:12.0711980+08:00	817F1CA8E0CD4B4A6A6AF2C3A41E8CB7EE2904EC211EED1A291045B907E0E8E7
===CONFIG_HASHES===
config\creator_profile.yaml	729	A7D0EBA137FF3BFC17626421F0A1AFB1B2A292CC574A2A74E65BA5CD81E620A9
config\credential_references.yaml	283	92E377CE937B8A150233372D5B7A7A0FA7104A5FA99A8CA640822211CFB162B8
config\current_machine_profile.yaml	768	CA32814A12479A3215A082E820DDDB634C7910EAF85057B6FE4696D52DF481B9
config\security_policy.yaml	2348	280A8C77A7000BBAD393A0C81C8F966B0EB6A67236390F15F4BAEBC910335609
config.example.yaml	8133	6B02E4BF75E032C96997725D0AE985C4129A1F0BD350CFA6A4CAA057E6CF5F7C
.env.example	105	76634A8D33665E9D0476D79D59E474757EC8E2A3477E8E7F148CC43B616027DC
===SECRET_PRESENCE===
dot_env_exists=False
dot_env_ignored=True
```

## Hardware and storage snapshot

The physical machine reports about 31.85 GiB visible RAM, but Alpha22 will continue to enforce the user-specified 24 GB RAM operational budget and 8 GB VRAM budget.

```text
captured_at=2026-08-09T11:18:29.6149583+08:00
gpu=NVIDIA GeForce RTX 4060 Ti, 8188, 963, 6987, 596.21
total_ram_gib=31.85
free_ram_gib=21.78
disk_C_used_gib=93.88;free_gib=56.13
disk_D_used_gib=559.99;free_gib=243.57
disk_R_used_gib=0.02;free_gib=0.04
disk_Temp_used_gib=93.88;free_gib=56.13
===PROCESSES===
pid=1460;name=node.exe;path=C:\Program Files\nodejs\node.exe
pid=1776;name=node_repl.exe;path=<codex-runtime>
pid=3420;name=node.exe;path=C:\Program Files\nodejs\node.exe
pid=5080;name=python.exe;path=D:\Alysia\.venv\Scripts\python.exe
pid=5320;name=node.exe;path=C:\Program Files\nodejs\node.exe
pid=6364;name=node.exe;path=C:\Program Files\nodejs\node.exe
pid=6608;name=node_repl.exe;path=<codex-runtime>
pid=7308;name=node.exe;path=C:\Program Files\nodejs\node.exe
pid=7628;name=node.exe;path=C:\Program Files\nodejs\node.exe
pid=8180;name=node.exe;path=C:\Program Files\nodejs\node.exe
pid=9164;name=node.exe;path=C:\Program Files\nodejs\node.exe
pid=9960;name=node.exe;path=C:\Program Files\nodejs\node.exe
pid=13568;name=node.exe;path=C:\Program Files\nodejs\node.exe
pid=15848;name=ollama.exe;path=<ollama>
pid=16160;name=ollama app.exe;path=<ollama> app.exe
pid=16852;name=node.exe;path=C:\Program Files\nodejs\node.exe
pid=18168;name=node.exe;path=C:\Program Files\nodejs\node.exe
pid=18244;name=node_repl.exe;path=<codex-runtime>
pid=18584;name=node.exe;path=C:\Program Files\nodejs\node.exe
pid=18840;name=node.exe;path=C:\Program Files\nodejs\node.exe
pid=19408;name=node_repl.exe;path=<codex-runtime>
pid=20052;name=node.exe;path=<codex-runtime>
pid=20868;name=node.exe;path=C:\Program Files\nodejs\node.exe
pid=21220;name=node_repl.exe;path=<codex-runtime>
pid=21408;name=python.exe;path=<local-path>
pid=22152;name=node.exe;path=C:\Program Files\nodejs\node.exe
pid=22752;name=node.exe;path=C:\Program Files\nodejs\node.exe
pid=22952;name=node.exe;path=C:\Program Files\nodejs\node.exe
pid=23048;name=node.exe;path=C:\Program Files\nodejs\node.exe
pid=23388;name=node.exe;path=C:\Program Files\nodejs\node.exe
===LISTENERS===
address=127.0.0.1;port=11434;pid=15848
address=127.0.0.1;port=53647;pid=16160
address=127.0.0.1;port=8765;pid=21408
```

## Current local services and model inventory

At capture time, Ollama responded on loopback, while ComfyUI did not respond on `127.0.0.1:8188`. All configured H3 model files and the Alysia workflow directory existed. Presence is not equivalent to a passing live integration test.

```text
comfyui_http=unavailable:HttpRequestException
ollama_http=200
path_exists=D:\ComfyUI;type=directory
path_exists=D:\ComfyUI\models\diffusion_models\minimax_h3_fl2va_pruned_int8_convrot.safetensors;type=file;size=20970379616;sha256=E889202C41DAFB67B10D67B97F0D8541508036A6090AF23425A5C2615D03C47A
path_exists=D:\ComfyUI\models\text_encoders\qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors;type=file;size=15687142551;sha256=35A88D51044231FE332301D7A62AA81E3F2CBA62FEBEB446E2C1E3E0EF76F2C6
path_exists=D:\ComfyUI\models\vae\minimax_h3_video_vae_fp16.safetensors;type=file;size=5207808496;sha256=7C1F131492E7EDDACAAC9069A61B81BDD39DE5CC96561E677C5EAB1CDCE5E522
path_exists=D:\ComfyUI\models\vae\minimax_h3_audio_vae_fp32.safetensors;type=file;size=605254808;sha256=8E505D95DD1561D47ABD43D4238FD40D9BB1AE9E147ED0A4CBA778D76AE4DB48
path_exists=D:\Alysia\workflows\comfyui\h3;type=directory
```

## Current configuration inventory

Configuration file contents were not copied into this baseline. Hashes above make later drift auditable. `.env` did not exist and is ignored by Git.

Known non-secret local configuration references already present in the repository include:

- ComfyUI base URL: `http://127.0.0.1:8188`
- ComfyUI directory: `D:\ComfyUI`
- H3 workflow directory: `workflows\comfyui\h3`
- H3 diffusion model: `D:\ComfyUI\models\diffusion_models\minimax_h3_fl2va_pruned_int8_convrot.safetensors`
- Ollama base URL: `http://127.0.0.1:11434`

## Baseline conclusions

1. The repository is valid and contains the expected Alpha18–21 lineage, but nearly all post-Alpha2 work is uncommitted.
2. Alpha22 must be implemented surgically on top of this dirty baseline, with every new file attributable to the phase.
3. H3 weights are present; ComfyUI is currently stopped or unreachable, so live H3 production cannot be claimed from this snapshot.
4. No real Beta publication evidence has been counted at baseline.
5. The baseline itself does not authorize publishing or reading platform credentials.
