# Alysia v0.1-alpha.13.5 开发报告

## 仓库与工作树保护

- 仓库：`D:\Alysia`
- 分支：`main`
- 开始时已跟踪差异：22 个文件，3306 insertions、89 deletions。
- 开始时还存在 alpha1-alpha13 的大量未跟踪目录、测试、报告和运行数据。
- 本阶段没有执行 `git reset`、`git clean`、`git checkout`、`git stash`、`rebase`、`commit`、`squash` 或其他清理/提交操作。
- alpha1-alpha13 的历史未提交成果全部保留；本报告只把下面列出的增量归入 alpha13.5。

## 本阶段结果

已完成 Local Generative Visual Engine 的可测试地基：

- Visual provider 抽象、registry、Mock provider、ComfyUI adapter 和 MiniMax H3 local workflow adapter。
- 规则化 VisualPlanner：Remotion、静态图、H3 T2V/I2V/R2V 路由；默认 3–8 秒重点镜头；限制镜头数量和总生成秒数。
- 结构化 H3VisualPrompt，单独保存 prompt JSON，并预留 character/reference/wardrobe/identity constraints。
- 持久化 VisualJobQueue，状态包含 pending/running/completed/failed/cancelled；GPU-heavy job 串行、可恢复、可缓存。
- ResourceManager 增加已注册 GPU provider 的显式 unload/cleanup 支持，并记录 H3 前后真实 `nvidia-smi` 快照。
- NoOp 与 FFmpeg scale fallback；未强制部署第二个大型超分模型。
- VisualQA：存在性、ffprobe 解码、时长、分辨率、基础黑帧/冻结检测、provenance 和 mock production gate。
- Editor/Composition/Remotion 支持混合静态资源和 H3 clip；H3 音轨默认静音，主旁白和字幕继续使用现有链路。
- alpha11 ProductionPlanner 增加 `visual_generation` stage；H3 声明为 local/high-latency/GPU-heavy，显存需求保持 unknown，不伪造峰值。
- Designer 生成混合视觉计划；实际 H3 生成仍可由明确 CLI 触发。

## 本阶段新增文件

- `alysia/schemas/visual.py`
- `alysia/providers/visual/*.py`
- `alysia/visual/*.py`
- `workflows/comfyui/h3/{t2v,i2v,reference}.json`
- `tests/test_visual_generation.py`
- `setup_h3_local.md`
- `development_report_alpha13_5.md`
- `runs/demo_alpha13_5/*`（离线验收 run）

## 本阶段增量修改的既有文件

- `alysia/core/config.py`、`config.example.yaml`
- `alysia/core/resources.py`
- `alysia/schemas/__init__.py`、`alysia/schemas/production.py`
- `alysia/production/{planner,registry,router}.py`
- `alysia/studio/{agents,registry}.py`
- `alysia/workers/composition.py`
- `video/remotion/src/components.jsx`
- `alysia/cli.py`
- `alysia/__init__.py`、`pyproject.toml`

这些文件中的 alpha1-alpha13 原有未提交内容不属于本阶段；本轮只在其基础上追加上述视觉能力。

## 环境检查

- Python 3.11.14、Node.js 24.16.0、npm 11.13.0、FFmpeg/FFprobe 9.0 可用。
- GPU：NVIDIA GeForce RTX 4060 Ti，8188 MiB VRAM；visual doctor 时空闲约 7252 MiB。
- RAM：34,193,965,056 bytes（约 32 GB）。
- D 盘可用约 308 GB。
- 未发现本机 ComfyUI；Alysia `.venv` 未安装 torch；`model_path` 未配置。
- 未修改系统代理、显卡驱动、CUDA、Windows Update。

## 测试与验收

- alpha13.5 专项：13/13 PASS。
- Production/Studio/Video/CLI 回归：46/46 PASS。
- 阶段全量回归：163/163 PASS，约 52 秒。
- `python -m alysia doctor`：命令成功；11 项可用、4 项可选组件未就绪。
- `python -m alysia visual doctor`：Mock provider 可用；ComfyUI-H3 因 API 不可达和未配置 model_path 而明确 unavailable。

## Demo run

- run_id：`demo_alpha13_5`
- 路由：`scene-title=remotion`、`scene-h3=h3_t2v`、`scene-diagram=remotion`。
- H3 预算：最多 4 个镜头/30 秒；本次使用 1 个镜头/8 秒。
- Mock clip：1920x1080、8.0 秒，可解码，black_ratio=0、freeze_ratio=0，provenance 完整。
- Mock VisualQA：工程检查 PASS，但 `production_eligible=false`；manifest 明确禁止进入 production review。
- 队列恢复：重复 generate 不增加 attempts，复用既有 result。

## 真实 H3 smoke test

未执行。原因是本机尚未发现 ComfyUI、H3 权重或可用真实 API-format workflow。根据任务边界，本轮没有自动下载大型模型或第三方未知代码。安装与 3–5 秒低分辨率 smoke test 步骤见 `setup_h3_local.md`。

## 已知限制

1. 仓库提供的 workflow JSON 是带 `_alysia` 注入契约的占位模板，不是特定 H3 节点版本的可执行工作流。
2. ComfyUI adapter 已实现提交、轮询、history 输出收集，但只有配置真实 workflow/模型后才可验证节点字段映射。
3. VisualQA 是工程级启发式检查，不包含语义相关性或审美评分。
4. Python 线程内 GPU job 严格串行；没有声称提供跨进程/OS 级分布式锁。
5. 32 GB RAM + 8 GB VRAM 的真实速度和峰值必须在安装后实测；报告不引用未经本机验证的模型峰值。
