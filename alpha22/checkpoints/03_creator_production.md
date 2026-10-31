# Alpha22 Checkpoint 03 — CreatorPlan + Production Orchestration

## Status

PASS

## CreatorPlan architecture

- Existing `CreatorPlan` is extended with `plan_id`, `job_id`, CreatorJob revision, script sections, production directions, metadata drafts, grounding references, uncertainty references, requirements, cost status, and timestamps.
- `CreatorPlanBuilder` requires a non-empty CreatorJob topic and grounded claims, unless the plan is explicitly `creative_only`.
- Factual `CreatorScriptSection` records claim refs; conflicting, insufficient, and unverified claim IDs remain in `uncertainty_refs`.

## ProductionPlan architecture

- `ProductionPlan` contains bound job/CreatorPlan IDs, lightweight DAG tasks, dependencies, resource requirements, artifact targets, persisted status, and timestamps.
- `ProductionTask` supports VOICE/IMAGE/VIDEO/COMPOSITE/THUMBNAIL/METADATA, dependency refs, four resource classes, bounded attempts, lifecycle timestamps, errors, and metadata.
- `ProductionOrchestrator` supports start, resume, cancel, status, dependency resolution, upstream blocking, persistence after execution, and explicit force regeneration.

## Adapters reused

- `ComfyUIProductionAdapter` delegates workflow loading, parameter binding, submit/poll/wait, cancellation, and result parsing to the existing `ComfyUIProvider`.
- `H3ProductionAdapter` delegates to the existing `MiniMaxH3LocalProvider`, which already reuses ComfyUI and `H3VisualConfig`.
- Adapter metadata stores only provider/workflow refs, workflow hash, and scene ID; full workflow JSON and private configuration are not copied into CreatorJob or manifests.

## Resource policy

- Existing `ResourceManager` provides the shared GPU mutex, provider cleanup, CUDA cache release, OOM detection, and real-or-unavailable VRAM snapshots.
- GPU_HEAVY concurrency is 1 by default. H3 and ComfyUI heavy work cannot acquire the same manager concurrently.
- Default preflight reuses `ResourceGuard`; resource failure maps to `RESOURCE_EXHAUSTED`, leaves a persisted recoverable plan, and always releases the lock.

## Retry and idempotency strategy

- Retry policy is configured and capped at three attempts, with bounded backoff.
- Transient timeout/provider and resource failures are retryable; permanent request/artifact validation failures are terminal.
- Resume skips SUCCEEDED tasks only when every registered artifact is still VALID and hash-consistent.
- Explicit `force_regenerate` resets only named tasks and their attempt budget; no heavy regeneration occurs implicitly.

## Artifact strategy

- `ProductionArtifactRegistry` confines paths beneath the configured artifact root and isolates by job/task.
- Manifests record artifact/job/task IDs, type, path, time, size, SHA-256, status, and redacted metadata.
- Statuses are VALID/PARTIAL/INVALID/MISSING. Empty, corrupt, missing, hash-changed, or failed partial outputs are not treated as valid.
- Production defaults to existing media probing; fake integration fixtures may explicitly disable media probing and are not Beta evidence.

## CreatorJob integration

- `CreatorProductionIntegrator` only accepts VALID artifacts bound to the same job.
- Updates script, title/description/tags, visual/audio plans, video, and thumbnail through versioned `CreatorJobStore.update()`.
- Approval remains DRAFT and publish remains NOT_READY after production.

## Tests executed

```text
uv run pytest tests/test_creator_production.py -q
uv run pytest tests/test_alpha22_creator.py tests/test_creator_job.py tests/test_topic_research.py tests/test_creator_production.py tests/test_production.py tests/test_visual_generation.py -q
```

## Test results

- Step 3 focused: `17 passed`.
- Step 1–3 plus directly relevant existing Production/Visual regression: `88 passed`.
- Exit code 0; no warnings.

## Real smoke test status

NOT_EXECUTED. No local H3/ComfyUI health call, service start, model load, GPU generation, or formal content production was performed. Contract tests used fake provider/process boundaries only.

## Known limitations

- Orchestration is synchronous and single-process; it is not a distributed scheduler.
- Cancel is cooperative through the existing provider cancellation interface and cannot preempt arbitrary blocking third-party code beyond its timeout boundary.
- Force regeneration targets named tasks; downstream invalidation must be requested explicitly in this minimal version.
- H3/ComfyUI were contract-tested but not exercised against the real local services.
- Full repository tests and final F1–F7 acceptance were not run.

## Files changed

- `alysia/creator/models.py`
- `alysia/creator/bridge.py`
- `alysia/creator/production.py`
- `alysia/creator/__init__.py`
- `tests/test_creator_production.py`
- `alpha22/checkpoints/03_creator_production.md`

## Git diff summary

- Tracked baseline remains 28 modified files with 5,129 insertions and 113 deletions.
- Creator and checkpoint paths were already untracked aggregates; ordinary tracked diff cannot isolate their per-step lines. This checkpoint lists every Step 3 file touched.
- `tests/test_creator_production.py` is newly untracked.
- No reset, clean, restore, checkout, stage, commit, or deletion was performed.

## Next safe step

Only recommend: Alpha22 Step 4 — CreatorQA + Human Review Gate. Stop after this checkpoint; do not execute Step 4 automatically.

