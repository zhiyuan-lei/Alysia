# Alpha17 Baseline Inventory

Generated for Alpha18. Repository: `D:\Alysia`. This is an inventory, not a cleanup list.

## Worktree and baseline

- Branch: `main`.
- Start tracked diff: 27 files changed, 4513 insertions, 100 deletions, plus substantial untracked Alpha3-Alpha17 artifacts.
- Baseline pytest: 247 passed, 1 skipped in 71.57s. The only skip is the explicit local H3 integration test guarded by `ALYSIA_RUN_H3_LOCAL=1`.
- Baseline doctor: exit 0; 12 available, 4 optional missing/not ready.
- Hardware detected: NVIDIA GeForce RTX 4060 Ti, 8188 MiB; configured budget 8192 MiB VRAM / 24 GB RAM; sequential GPU required.
- Optional components not ready: Ollama `qwen3.5:4b`, CUDA Toolkit `nvcc`, CosyVoice Python, faster-whisper. SAPI, FFmpeg/ffprobe, Node/npm, Git and the GPU are available.

## Alpha reports

Present: Alpha2 through Alpha17, including separate Alpha13.5 design/runtime reports. No `development_report_alpha1.md` exists. Alpha17 is the authoritative immediate baseline report.

## CLI commands

Top-level production flow: `create`, `status`, `resume`, `render`, `package`, `publish-check`, `voice`, `subtitle`, `audio-status`, `runs`, `analyze`, `learn`, `strategy`, `doctor`.

Grouped commands: `analytics`, `memory`, `trends`, `plan`, `creator-loop`, `publish`, `feedback`, `operations`, `experiment`, `identity`, `style`, `production`, `studio`, `supervisor`, `visual`, `capability`, `gaps`, `skill`, `workflow`, `simulate`, `knowledge`, `research`, `grounding`.

Alpha18 will add `eval` without changing the semantics of existing commands.

## Modules

- Agents: 8 files (`researcher`, `writer`, `director`, `critic`, title/description/tags plus exports).
- Providers: 51 files covering LLM, search, TTS, ASR, cover, video, visual/ComfyUI/H3, analytics, feedback, trends and publishing.
- Workers: 13 files covering text, voice/WAV/audio QA, subtitle, composition, video/render QA, cover/package and publish QA.
- Schemas: 21 files covering research, script, storyboard, audio, video, visual, QA, publish/publishing, analytics, learning, planning, operations, identity, production, supervisor, capability, workflow and simulation.
- Knowledge: 16 files for source/claim models, extraction, verification, conflict, freshness, grounding, QA, maintenance, context, store and service.
- Studio: 10 files; Supervisor: 9; Workflow: 15; Production: 10; Publishing: 4.

## QA and evaluation before Alpha18

Existing deterministic QA includes text, audio/speech-tone guard, subtitle validation, video decode/format, visual artifact/provenance, publish package, planning, learning, knowledge, simulation, studio, supervisor and workflow QA.

Existing evaluation is capability- and workflow-specific (`alysia/capabilities/evaluation.py`, `alysia/workflow/evaluation.py`). There is no unified versioned benchmark registry, worktree-based EvaluationRun, baseline snapshot, cross-version RegressionEngine or global promotion gate.

## Tests

There are 27 test modules before Alpha18. Major categories: schemas/text pipeline, audio/subtitle, video/render, publish/publishing/feedback, analytics/learning/operations/planning, identity, production, studio, supervisor, capabilities/skills, workflow, simulation, knowledge and H3 integration.

## H3 / ComfyUI health path

- Provider adapter: `alysia/providers/visual/comfyui.py` and `h3.py`.
- Provider registry/health: `alysia/providers/visual/registry.py`.
- Planning/queue/service/QA: `alysia/visual/`.
- Real machine evidence: `evaluation/capability_evaluation_h3_runtime.json`.
- Existing explicit integration test: `tests/test_h3_local_integration.py`, marker `integration` + `h3_local`, environment gate `ALYSIA_RUN_H3_LOCAL=1`.
- Default pytest must not load the 42.5 GB local H3 stack.

## Existing mock-only or intentionally unavailable paths

- Mock LLM/search/TTS/ASR/video/visual/analytics/feedback/trends/publishing/cover providers support offline deterministic tests. Their outputs must remain testing/mock and must not enter real Analytics/Memory or production review.
- `alysia/providers/analytics/bilibili.py` is an explicit no-login contract placeholder for manual import.
- `alysia/providers/llm/cloud.py` explicitly raises `NotImplementedError`; cloud LLM was intentionally outside earlier alpha scope.
- Abstract provider methods in visual/trends/studio protocols intentionally raise `NotImplementedError` or use `pass` in exception marker classes.
- `alysia/visual/upscale.py` exposes an unimplemented abstract/provider boundary; current configured `ffmpeg` path is implemented elsewhere. This is historical and is not changed in Alpha18.
- Remotion image placeholder behavior is a deliberate fallback when an image asset is absent, not an Alpha18 implementation stub.

## Existing TODO / FIXME / stubs

No TODO/FIXME tokens were found in production Python during the baseline scan. Historical stub-like hits fall into these groups:

1. Empty exception marker classes: orchestrator, learning, operations, production, publishing and workflow.
2. Abstract protocol/provider methods: visual base, feedback/publishing/trend bases and Studio agent interface.
3. Explicitly unsupported integrations: cloud LLM and direct Bilibili analytics.
4. Optional feature boundary: visual upscale provider.
5. Defensive exception swallowing with comments/logging: orchestrator, planning, simulation, subtitle and visual QA.
6. Deliberate media placeholder fields/documentation.

Alpha18 must not remove or silently reinterpret these historical items. Its final stub audit will compare only Alpha18-added/modified production paths and document any new hit.

## Baseline conclusion

Alpha17 is stable enough to serve as the first Alpha18 baseline: all 247 offline tests pass, the one heavy H3 test is explicitly isolated, doctor exits successfully, and the missing capability is the unified evaluation/regression layer rather than a broken production pipeline.
