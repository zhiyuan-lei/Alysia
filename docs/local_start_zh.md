# 本机打开 Alysia 与 ComfyUI

Alysia 当前是运行在本机的网页控制中心，不是独立的 Windows `.exe`。ComfyUI 是另一项本机网页服务，可以单独打开；两者均只监听 `127.0.0.1`，不需要先打开 Codex。

## 双击打开

在文件资源管理器进入 `D:\Alysia`：

1. 双击 `打开Alysia.cmd`：启动或复用 Alysia 控制中心，并打开 `http://127.0.0.1:8765/`。左侧“本地创作”可填写 H3/ComfyUI 任务。
2. 双击 `打开ComfyUI.cmd`：启动或复用 ComfyUI，并打开 `http://127.0.0.1:8188/`。可单独使用 ComfyUI，不必先打开 Alysia。

这两个入口不会重复启动已就绪的服务，不会结束占用端口的未知程序，也不会开机自启动。ComfyUI 使用现有 `D:\ComfyUI` 环境和 `--lowvram` 配置；启动不会自动加载 H3 模型。首次启动可能需要几十秒。若服务已运行，双击只会打开网页。

## 手动启动

若要看实时终端日志，可在两个 PowerShell 7 窗口分别运行：

```powershell
Set-Location D:\Alysia
.\.venv\Scripts\python.exe -m alysia control start --open-browser
```

```powershell
Set-Location D:\ComfyUI
.\.venv\Scripts\python.exe main.py --listen 127.0.0.1 --port 8188 --lowvram --disable-auto-launch
```

第二条命令启动后，可在浏览器手动访问 `http://127.0.0.1:8188/`。不用同时执行双击入口和对应手动命令；如果服务已运行，访问网址即可。ComfyUI 的自定义 API 工作流需要 8188 服务；Alysia 的已验证分阶段 H3 单图模式使用本机 ComfyUI 环境，但不依赖网页 API 一直运行。

## 中文界面与故障位置

Alysia 控制中心导航、常用页面、状态、审批与本地创作操作采用简体中文；任务 ID、API/模型名、原始 JSON 和第三方 ComfyUI 界面保留原文，避免改变技术含义。`打开*.cmd` 通过 PowerShell 7 启动，不修改系统执行策略。若启动失败，窗口会显示原因，日志在 `D:\Alysia\workspace\launcher_logs\`。遇到“端口已被其他程序占用”时，请先确认占用者；入口不会自动结束进程。
