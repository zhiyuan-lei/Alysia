# Alysia Alpha22 Recovery Inventory

## 1. Recovery scope

- Captured at: `2026-08-09T13:35:47+08:00`
- Repository: `D:\Alysia`
- Recovery source: repository files, Git state, local artifacts, test reports, logs, process/listener state, and local service health only.
- The failed Alpha22 Codex thread was not opened, restored, imported, or used as evidence.
- This pass did not run tests, start services, resume jobs, consume queues, approve content, read credentials, or perform any publication action.
- No reset, clean, checkout, restore, deletion, or overwrite of prior Alpha1-21/Alpha22 work was performed.

## 2. Git recovery baseline

```text
branch=main
HEAD=55da6463f0ff50e5c7e51fb1b9496aca5c8481fa
staged=0
tracked_modified=28
untracked_files_before_recovery_docs=960
untracked_files_after_recovery_docs=962
git_diff_check_exit=0
```

`git diff --stat` reports 28 tracked files with 5,129 insertions and 113 deletions relative to HEAD. The pre-Alpha22 inventory proves the repository was already heavily dirty: 28 tracked modifications and 738 untracked entries existed before Alpha22. Those accumulated Alpha3-21 changes remain protected user work.

The complete pre-Alpha22 status manifest is preserved at:

`docs/alpha22/alpha22_baseline_git_status.txt`

The two additional final untracked files are this recovery inventory and `alpha22_checkpoints/00_recovery.md`; no existing repository file was altered by the recovery pass.

## 3. Alpha22 changed-file inventory

### 3.1 Existing files modified during the Alpha22 time window

The following existing files have post-baseline Alpha22 timestamps and contain Alpha22 integration changes:

```text
alysia/__init__.py
alysia/core/config.py
alysia/core/orchestrator.py
alysia/core/run.py
alysia/planning/loop.py
alysia/control/api.py
alysia/control/service.py
config.example.yaml
pyproject.toml
uv.lock
tests/test_planning.py
tests/test_control_api.py
control-center/package.json
control-center/package-lock.json
control-center/src/App.jsx
control-center/src/components.jsx
control-center/src/pages.jsx
control-center/src/styles.css
docs/phase_execution_ledger.md
```

Alpha22 also updated its own planning files during execution:

```text
.planning/alpha22/task_plan.md
.planning/alpha22/progress.md
.planning/alpha22/findings.md
```

### 3.2 Alpha22 source files added

```text
alysia/creator/__init__.py
alysia/creator/models.py
alysia/creator/store.py
alysia/creator/service.py
alysia/creator/duplicates.py
alysia/creator/bridge.py
alysia/creator/qa.py
alysia/creator/bilibili.py
alysia/creator/evidence.py
alysia/creator/memory.py
tests/test_alpha22_creator.py
tests/fault_injection/test_alpha22_creator_loop.py
```

### 3.3 Alpha22 documentation and evidence added

```text
docs/alpha22/alpha22_baseline_inventory.md
docs/alpha22/alpha22_baseline_git_status.txt
docs/alpha22/alpha22_architecture_inspection.md
docs/alpha22/alpha22_gap_analysis.md
docs/alpha22/alpha22_minimal_implementation_plan.md
docs/alpha22/alpha22_field_run_runbook.md
evaluation/alpha22/alpha22_beta_runs.csv
evaluation/alpha22/alpha22_fault_injection.junit.xml
evaluation/alpha22/alpha22_full_regression.junit.xml
evaluation/alpha22/alpha22_h3_cache_none.junit.xml
evaluation/alpha22/alpha22_h3_cache_none_resources.json
evaluation/alpha22/comfyui_stdout.log
evaluation/alpha22/comfyui_stderr.log
evaluation/alpha22/comfyui_cache_none_stdout.log
evaluation/alpha22/comfyui_cache_none_stderr.log
```

The Control Center production bundle was rebuilt after Alpha22 UI changes:

```text
control-center/dist/index.html
control-center/dist/assets/index-DPFCy5WC.js
control-center/dist/assets/index-zDQwaA_A.css
```

Two completed H3/ComfyUI visual queue jobs and their monitor/result records were also produced during Alpha22. They are runtime evidence, not real CreatorJob or Bilibili Beta evidence.

## 4. Requirement-by-requirement recovery classification

Status vocabulary: `COMPLETED`, `PARTIALLY_COMPLETED`, `NOT_STARTED`, `UNKNOWN`, `BROKEN`.

| Requirement | Recovery status | Evidence and reason |
|---|---|---|
| Baseline inventory | COMPLETED | `docs/alpha22/alpha22_baseline_inventory.md` and full pre-change Git manifest exist. |
| Existing architecture inspection | COMPLETED | `docs/alpha22/alpha22_architecture_inspection.md` exists and maps Alpha18-21 reuse boundaries. |
| Gap analysis / minimal plan | COMPLETED | Both required documents exist. |
| CreatorJob | COMPLETED | Aggregate, stable ID, store, state transitions, revisions, attempts, observations, reflection, memory refs, and tests exist in `alysia/creator/`. Engineering evidence: 12 Alpha22 core tests in the full JUnit report. No persistent field CreatorJob exists yet. |
| Topic Discovery | COMPLETED | Existing CreatorLoop scoring/discovery is bound to a new CreatorJob in `alysia/planning/loop.py`; full regression contains the planning binding test. This is engineering completion only; no real Alpha22 topic run exists. |
| Research / Grounding | COMPLETED | `CreatorRunBridge` maps research sources, claim classifications, uncertainties, grounding status, and stale/conflicted claims. F7 and core QA tests pass. No real research trace has been produced through a field CreatorJob. |
| H3 integration | PARTIALLY_COMPLETED | Real non-mock H3 smoke completed and Visual QA passed. Peak VRAM was 7,708 MB, within the 8,192 MB configured ceiling, but peak system RAM was 26,933 MB, above the 24,576 MB operating budget. |
| ComfyUI integration | PARTIALLY_COMPLETED | Real loopback ComfyUI executed two Alpha22 smoke jobs and produced video/result evidence. Service is currently stopped/unreachable, and the resource-compliance failure remains unresolved. |
| Production Pipeline | PARTIALLY_COMPLETED | Existing production bridge, serialized GPU policy, QA artifacts, and isolated H3 smoke exist. No real CreatorJob has traversed the complete integrated production path, and RAM-budget compliance failed. |
| CreatorQA | COMPLETED | Aggregate content/video/copy/safety/duplicate gate exists and is enforced before REVIEW/APPROVED/PUBLISHED. Tests cover stale facts, insufficient evidence, and state bypass. Engineering completion only. |
| Human Approval | COMPLETED | Alpha20 hash/scope/version approval is integrated with CreatorJob REVIEW -> APPROVED -> PUBLISH_READY; REJECT and REQUEST_REVISION paths exist in backend and Control Center. No real Alpha22 approval record exists. |
| Revision History | COMPLETED | Immutable revision snapshots and incremented revision numbers are implemented and tested. |
| BilibiliPublisher | PARTIALLY_COMPLETED | `prepare/validate/publish/status/fetch_metrics` surface exists. Manual handoff and BV receipt validation are implemented; official API transport is only an injected protocol and intentionally fails closed without an authenticated contract. Zero real receipts exist. |
| Publish State Machine | PARTIALLY_COMPLETED | Required lifecycle and idempotent same-receipt handling are tested. However, the promised explicit retry budget/backoff enforcement is absent from `CreatorJobService.record_publish_failure`; repeated failures can be recorded without a configured maximum. |
| Metrics / ContentObservation | PARTIALLY_COMPLETED | Timestamped observations, explicit availability, evidence path checks, and manual-real API exist. Official Bilibili metric transport and real observations do not exist. |
| CreatorReflection | COMPLETED | Seven-question structured reflection with facts/interpretations/uncertainties separation is implemented and tested. No real reflection artifact exists. |
| Memory Integration | COMPLETED | Compact episodic record is implemented; raw evidence remains outside long-term memory and single-episode semantic promotion is disabled. No real Alpha22 episode exists. |
| F1-F7 | PARTIALLY_COMPLETED | JUnit shows 7/7 passing, but F1/F2 only append synthetic recovery events to a CreatorJob; they do not actually stop ComfyUI or fail an H3 invocation. F3-F7 are deterministic state/unit tests. This does not yet satisfy full runtime fault-injection evidence. |
| Alpha18-21 Regression | PARTIALLY_COMPLETED | Python JUnit shows 356 tests, 0 failures, 0 errors, 1 intentional H3 skip; the skipped H3 test later passed separately. No required `alpha22_regression_report.md` exists, and no preserved post-Alpha22 frontend test report was found. |
| Real Beta Evidence | NOT_STARTED | `workspace/creator_jobs` contains 0 jobs and `alpha22_beta_runs.csv` contains only the header: 0/10 qualified runs. |
| Final Acceptance | NOT_STARTED | No Alpha22 final acceptance/development report exists. Alpha22 PASS or READY_FOR_FIELD_RUN must not be claimed from current evidence. |
| H3/ComfyUI RAM-budget compliance | BROKEN | Recorded 26,933 MB peak exceeds the required 24,576 MB operating budget. |
| Bounded publish retry policy | BROKEN | Attempt records exist, but no retry-budget ceiling or enforced exponential-backoff policy exists on the Alpha22 publication path. |
| Post-change frontend test result | UNKNOWN | Rebuilt bundle and planning notes exist, but no durable post-change Vitest/JUnit/command transcript was found. |
| Official Bilibili authentication/API availability | UNKNOWN | Credentials were not read. Official transport is not implemented/configured in the repository evidence. |

## 5. Preserved test and runtime evidence

```text
evaluation/alpha22/alpha22_fault_injection.junit.xml
  tests=7 failures=0 errors=0 skipped=0

evaluation/alpha22/alpha22_full_regression.junit.xml
  tests=356 failures=0 errors=0 skipped=1
  skip=tests.test_h3_local_integration::test_real_h3_t2v_smoke

evaluation/alpha22/alpha22_h3_cache_none.junit.xml
  tests=1 failures=0 errors=0 skipped=0
  test=real H3 t2v smoke

workspace/h3_smoke_result.json
  mock=false
  generation_status=completed
  visual_qa=PASS
  output=D:\ComfyUI\output\alysia\h3_smoke_20260809_120305\smoke-t2v_00001_.mp4

evaluation/alpha22/alpha22_h3_cache_none_resources.json
  peak_vram_used_mb=7708
  configured_vram_budget_mb=8192
  within_vram_budget=true
  peak_system_ram_used_mb=26933
  configured_ram_budget_mb=24576
  within_ram_budget=false
```

No tests were rerun during recovery because this pass is an inventory only and the historical suite is known to write audit/runtime artifacts.

## 6. Current services, processes, queues, and locks

At recovery capture:

```text
ComfyUI 127.0.0.1:8188 = unavailable
Control Center 127.0.0.1:8765 = unavailable
Ollama 127.0.0.1:11434 = HTTP 200
GPU = RTX 4060 Ti, total 8188 MB, used 738 MB, free 7212 MB
System RAM = total 32610 MB, used 7514 MB, free 25096 MB
```

- No Python/Node process command line matched Alysia, ComfyUI, or the Control Center.
- No listener exists on 8188 or 8765.
- All current visual queue job files are `completed`; both Alpha22 monitor records are `completed`.
- No `.tmp`, `.partial`, `.inprogress`, application lock, retry-queue, or transaction file was found. Package manager lockfiles are not runtime locks.
- Therefore no stale Alpha22 worker/service/lock was identified.

## 7. Pending and half-complete state

No Alpha22 CreatorJob, Alpha22 approval, Alpha22 publication attempt, or Alpha22 retry queue exists.

Pre-existing Alpha21/earlier state remains and must not be mistaken for Alpha22:

```text
run 20260807_225723_122f581b
  current_stage=ready_for_review
  renderer=mock
  llm=mock
  creator_job_id=null
  approval_record=false

run 20260807_230208_43ee9a2b
  current_stage=publish_approval
  creator_job_id=null
  publish_job=job_39b7547104e20751
  publish_job_status=approved
  provider=mock

run 20260809_105526_48c47359
  current_stage=failed
  failed_stage=publish_job
  error=approval_invalid: Alpha21 controlled recovery demo
```

These are protected historical/mock artifacts. They were not resumed or modified.

## 8. Real publication and duplicate-publication risk

- `workspace/creator_jobs`: 0 persistent CreatorJobs.
- `alpha22_beta_runs.csv`: 0 data rows.
- No `platform_content_id`, real BV receipt, or CreatorJob publication audit event was found.
- Recent publication audit records created by regression tests use `provider=mock` and `mock_bv_*` IDs; they are not real Bilibili publications.
- One pre-existing publish job remains `approved`, but its provider is `mock` and it has no CreatorJob or platform content ID.

Conclusion: no evidence of an already-started real Bilibili transaction or immediate real duplicate-publication risk was found. This is not proof about external Bilibili account state because credentials and the platform account were intentionally not inspected. Until a human reconciles external account history with a specific CreatorJob, all real publication actions remain prohibited.

## 9. Recovery point

```text
ALPHA22_RECOVERY_POINT = AFTER_M_MEMORY_INTEGRATION__BEFORE_N_RECOVERY_AND_RESOURCE_ACCEPTANCE
```

Meaning:

- Alpha22 engineering implementation exists through the CreatorJob, Control Center, manual Bilibili handoff, observation, reflection, and episodic-memory surfaces.
- Do not restart Alpha22 from scratch and do not overwrite these files.
- The safest continuation is not field publication. It is to resume at recovery/resource hardening: enforce publish retry budget/backoff, replace shallow F1/F2 with real runtime fault injection, bring the H3/ComfyUI path under the 24 GB RAM operating budget, preserve frontend regression evidence, and generate the missing regression report.
- Only after those gates pass should a human begin new real CreatorJobs and reconcile each manual Bilibili upload before recording a receipt.
- This recovery pass stops here and does not perform those next actions.

## 10. Current acceptance ceiling

Current evidence does not support `PASS` and does not yet support `READY_FOR_FIELD_RUN` because resource compliance and recovery-test completeness remain unresolved. Real Beta count is 0/10. No Alpha23 work is authorized or present.
