# Alysia v0.1-alpha.16 开发报告

## 仓库与工作树保护

- 仓库：`D:\Alysia`
- branch：`main`
- alpha16 开始前 tracked diff：22 files、3837 insertions / 89 deletions，另有大量 alpha1-alpha15 untracked 成果。
- 本阶段未执行 `git reset`、`git clean`、`git checkout`、`git stash`、`rebase`、`commit`、`squash` 或历史改动清理。
- `.planning/alpha16/` 单独记录基线、发现和进度；本报告只归因 alpha16 增量。

## alpha15 起点

- 基线测试：201/201 PASS。
- Capability registry：20 项；17 stable、3 experimental。
- Approved skill：`h3_visual_generation` v1 active；v2 disabled。
- Validated recipe：`recipe_a06f7ced1b568b65`；H3 recipe 仍 candidate，resume recipe deprecated。
- `python -m alysia visual doctor`：ComfyUI API timeout，`comfyui_dir` 与 `model_path` 均未配置；alpha16 没有假定 H3 已部署。
- 当前硬件：RTX 4060 Ti，8188 MiB VRAM；simulation resource budget 固定 24GB RAM profile，GPU-heavy 仍串行。

## alpha16 新增能力

- `SimulationScenario`：显式 baseline refs、assumptions、变量、候选动作、horizon、预算、审批与 uncertainty。
- `WorldStateSnapshot`：仅汇总现有 artifacts/doctor/provider health 的可观测状态。
- `CounterfactualCandidateGenerator`：最多 5 个 policy-compliant candidate；禁止明显绕过审批的方案。
- 分层 evaluator：Production、ContentStructure、Risk、Workflow dry-run 与保守 PlatformOutcomeEstimator。
- 统一 `Prediction`：known/derived/simulated/unknown、confidence、evidence、assumption、caveat。
- `CounterfactualComparator`：逐维分数、known fraction、tradeoff、uncertainty、未选原因；近似平局保持 no recommendation。
- `SimulationDecisionPolicy`：默认 recommendation-only；仅低风险内部计划可候选 auto-select。
- 逻辑 dry-run sandbox 与 path guard；不声称 OS 级隔离。
- `SimulationQA`：检查数据标记、uncertainty、unknown、审批、现实隔离、候选上限和有限深度。
- `ExperimentProposal` 与 `SimulationCalibrationRecord`：预测和真实实验分离，误差只生成建议，不自动改代码/参数。
- Supervisor 只读 recommendation 入口；不直接运行模拟 Agent step 或 dispatch。
- CLI：`simulate create/run/compare/show/calibrate/history`。

## alpha16 文件

新增：

- `alysia/schemas/simulation.py`
- `alysia/simulation/*.py`
- `tests/test_simulation.py`
- `workspace/simulation/tasks/demo_a_visual_strategy.json`
- `workspace/simulation/tasks/demo_b_hook.json`
- `workspace/simulation/tasks/demo_c_recipe.json`
- `workspace/simulation/mock_actual_demo.json`
- `development_report_alpha16.md`
- `.planning/alpha16/*`

增量修改：

- `alysia/core/config.py`、`config.example.yaml`
- `alysia/schemas/__init__.py`
- `alysia/supervisor/supervisor.py`
- `alysia/cli.py`
- `alysia/__init__.py`、`pyproject.toml`、`uv.lock`
- `README.md`

这些既有文件在 alpha16 前已含历史未提交修改；alpha16 只增加 simulation/config/CLI/version/documentation 增量。

## Demo A：视频视觉策略

- Scenario：`alpha16_demo_a_visual`
- 候选：Remotion only、Remotion + 2 H3 clips、Remotion + 5 H3 clips。
- 当前 H3 provider unavailable、peak VRAM unknown、无真实 H3 execution metrics；生产时延保持 unknown。
- QA PASS；`real_providers_called=false`、`real_metrics_written=false`。
- 排名：`remotion_only=0.7809`、`h3_two_clips=0.4660`、`h3_five_clips=0.4423`。
- 推荐 `remotion_only`，decision=`recommendation_only`、dispatch=false。H3 方案质量潜力更高，但当前 provider unavailable、资源/时延 unknown、可靠性和 OOM 风险明显更差。

## Demo B：内容结构反事实

- Scenario：`alpha16_demo_b_hook`
- 候选：5s / 8s / 15s hook。
- 现有 episode 均为 testing/mock，不能作为真实平台结果证据；相对平台 outcome 保持 unknown/low confidence。
- Simulation 只建议形成待审批真实实验，不将预测写入 Analytics。
- 三个候选相对分数均为 0.7877，平台 outcome 均为 unknown；比较器输出 `no_recommendation`，要求先做人工批准的真实实验。

## Demo C：Workflow Recipe

- Scenario：`alpha16_demo_c_recipe`
- 当前仓库只有一个 validated recipe；为避免伪造 evidence，Demo C 比较该 recipe 的 fast-draft / standard-quality 两个 dry-run profile。
- 两者都只校验 recipe/registry/contracts，不执行真实 workflow step。
- `fast_draft=0.7849`、`standard_quality=0.7839`；差异不足 0.01，输出 `no_recommendation`。两者 `recipe_status=validated`、`valid=true`、`real_steps_executed=false`。

## Calibration Demo

- 使用 `workspace/simulation/mock_actual_demo.json`，source=`testing`。
- Calibration artifact 与真实 memory 隔离，`applies_automatically=false`。
- Testing actual 下：`risk_score error=-0.06 (under)`，`expected_quality_score error=-0.02 (under)`；`applies_automatically=false`。

## 测试与最终自检

- alpha16 专项：19/19 PASS。
- 最终全量 pytest：220/220 PASS（55.6s）。
- Supervisor/Studio/Workflow/Production/Publish/Feedback 定向回归：95/95 PASS（39s）。
- `python -m alysia doctor`：11 项可用、4 项可选组件未就绪；RTX 4060 Ti 为 8188 MiB。
- `python -m alysia visual doctor`：H3/ComfyUI 仍 unavailable，目录/model 未配置；没有真实 preview。
- Demo A/B/C 均完成 create/run/compare，三个 Simulation QA 均 PASS；history 显示 results/decision 完整。
- `compileall`、`git diff --check` PASS；只有既有 LF/CRLF conversion warning，无 whitespace error。
- 最终 tracked `git diff --stat`：22 files、4000 insertions / 89 deletions。alpha16 新文件保持 untracked 增量，alpha1-alpha15 历史成果仍完整存在。

## Simulation / Reality 隔离与分层结论

- 所有 prediction 都有 estimate type 与 confidence；derived/simulated 带 assumptions，unknown 没有 point/range。
- 模拟 artifacts 只写 `simulations/<scenario_id>/`；真实 `Analytics/Memory` 未被 simulation service 修改。
- Supervisor 只接收 recommendation，不执行 evaluator steps；StudioDirector 仍负责单 content run。
- ProductionPlanner 仍拥有 provider/resource 最终约束；当前 H3 unavailable 会在真实执行前阻断。
- 发布、身份、预算、实验和重大 replan 的 Human Approval Gate 未被绕过。
- Calibration 只记录 error/bias 和建议，不自动修改源码、模型或永久权重。

## 当前限制

1. 不是神经世界模型，也不是 OS 级 sandbox；只做规则化、artifact-backed dry-run。
2. 当前缺少真实 H3 runtime/resource 样本，H3 时延、峰值 RAM/VRAM 与 VisualQA 成功率保持 unknown。
3. 当前无足够真实频道数据，PlatformOutcomeEstimator 不提供有效数值预测。
4. 仓库只有一个 validated recipe；Demo C 不能诚实地比较两个不同 validated recipes。
5. Comparator 权重是可解释默认值；Calibration 只提出建议，不自动更新。
6. 当前最直接瓶颈仍是 ComfyUI/H3 未真实部署，以及缺少真实频道表现与 H3 execution metrics。

## alpha17 建议

进入 **Autonomous Research & Knowledge Maintenance**：持续知识更新、来源可信度、事实版本化与过期检测；仍然禁止无来源事实进入创作，也不允许外部内容自动覆盖已验证知识。
