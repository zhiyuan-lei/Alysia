# Phase Execution Ledger

An item may be checked only when its evidence path exists.

## Alpha18

- [x] baseline inventory — `docs/baseline_alpha17_inventory.md`
- [x] implementation — `alysia/evaluation/`
- [x] schemas — `alysia/schemas/evaluation.py`
- [x] benchmark registry — `alysia/evaluation/registry.py`
- [x] golden fixtures — `tests/fixtures/evaluation/`
- [x] scorers — `alysia/evaluation/scorers.py`
- [x] tests — `tests/test_evaluation.py`; 19 focused and 266 full-suite PASS
- [x] CLI — `python -m alysia eval --help`
- [x] baseline snapshot — `evaluation/baselines/baseline_alpha17_75261fe47f27.json`
- [x] regression injection demo — `evaluation/runs/eval_6184e770ede40534c094.json`
- [x] regression gate — `evaluation/gates/baseline_alpha17_75261fe47f27__eval_6184e770ede40534c094.json`
- [x] H3 integration isolation/status — `evaluation/runs/eval_f5dcfc3364068d0b8eff.json`
- [x] regression matrix — `docs/regression_matrix.md`
- [x] full regression — `development_report_alpha18.md#tests-and-checks`
- [x] stub audit — `development_report_alpha18.md#tests-and-checks`
- [x] change review — `docs/reviews/alpha18_change_review.md`
- [x] development report — `development_report_alpha18.md`

## Alpha19

- [x] implementation — `alysia/reliability/`; `alysia/core/io.py`
- [x] schemas/config — `alysia/schemas/reliability.py`; `config.example.yaml`
- [x] tests — `tests/fault_injection/test_reliability.py`; final full-suite evidence in `development_report_alpha19.md`
- [x] CLI — `python -m alysia reliability`; `diagnose`; `recover`; `checkpoints`
- [x] Demo A Voice local recovery — `evaluation/reliability_demos/alpha19_gate/summary.json`
- [x] Demo B H3 approved fallback — `evaluation/reliability_demos/alpha19_gate/summary.json`
- [x] Demo C state backup restore — `evaluation/reliability_demos/alpha19_gate/summary.json`
- [x] Demo D render-only retry — `evaluation/reliability_demos/alpha19_gate/summary.json`
- [x] checkpoint/resume evidence — `tests/fault_injection/test_reliability.py`
- [x] artifact/state integrity — `alysia/reliability/artifacts.py`; `alysia/reliability/checkpoints.py`
- [x] watchdog/resource guards — `alysia/reliability/monitor.py`; `alysia/reliability/resources.py`
- [x] Alpha18 evaluation linkage — `tests/fixtures/evaluation/reliability_recovery.json`
- [x] regression matrix — `docs/regression_matrix.md`
- [x] stub audit — `development_report_alpha19.md#stub-audit`
- [x] change review — `docs/reviews/alpha19_change_review.md`
- [x] development report — `development_report_alpha19.md`

## Alpha20

- [x] implementation — `alysia/security/`, `alysia/publishing/service.py`, governed services/providers
- [x] schemas/config — `alysia/schemas/security.py`, `config/security_policy.yaml`, `config/credential_references.yaml`
- [x] tests — 323 collected; 322 passed, 1 existing explicit H3 integration skip; `tests/test_security.py` 33 passed
- [x] CLI — `python -m alysia security status|permissions|audit|scan|approvals|demo`
- [x] Demo A Writer publish denied — `evaluation/security_demos/alpha20_final/summary.json`
- [x] Demo B Sandbox credential/path denied — `evaluation/security_demos/alpha20_final/summary.json`
- [x] Demo C invalid approval denied — `evaluation/security_demos/alpha20_final/summary.json`
- [x] Demo D valid approval Mock publish — `evaluation/security_demos/alpha20_final/summary.json`
- [x] fake secret leakage demo — `evaluation/security_demos/alpha20_final/fake_secret_redaction.json`
- [x] Alpha18 evaluation linkage — `eval_879a6ab4d0ede96b5905`, Gate PASS, critical regression 0
- [x] Alpha19 reliability linkage — `evaluation/reliability_demos/alpha20_final/summary.json`, 23 focused tests passed
- [x] regression matrix — `docs/regression_matrix.md`, 26 executable invariants
- [x] security review — `docs/security_review_alpha20.md`
- [x] stub audit — explained in `development_report_alpha20.md`; no Alpha20 production security stub
- [x] change review — `docs/reviews/alpha20_change_review.md`
- [x] development report — `development_report_alpha20.md`; status DONE

## Alpha21

- [x] backend API adapter — `alysia/control/api.py`; `alysia/control/service.py`
- [x] local-only server and CLI — `alysia/control/server.py`; `python -m alysia control start`
- [x] frontend pages — `control-center/src/`
- [x] security integration — Alpha20 policy, approval hash/scope/version revalidation, CSRF/origin checks, audit redaction
- [x] recovery integration — Alpha19 `ReliabilityService` diagnose/recover/resume; no force-ignore action
- [x] evaluation integration — Alpha18 gate is rendered read-only
- [x] API tests — `tests/test_control_api.py`
- [x] frontend tests/build — `control-center/src/App.test.jsx`; `control-center/dist/`
- [x] browser Demo A-E — `evaluation/control_center/screenshots/`
- [x] visual concepts and comparison — `docs/design/alpha21/`
- [x] regression matrix — `docs/regression_matrix.md`
- [x] stub audit — `development_report_alpha21.md#stub-audit`
- [x] change review — `docs/reviews/alpha21_change_review.md`
- [x] development report — `development_report_alpha21.md`

## Alpha22

- [x] pre-change baseline — `docs/alpha22/alpha22_baseline_inventory.md`; full status manifest preserved
- [x] architecture inspection — `docs/alpha22/alpha22_architecture_inspection.md`
- [x] gap analysis — `docs/alpha22/alpha22_gap_analysis.md`
- [x] minimal implementation plan — `docs/alpha22/alpha22_minimal_implementation_plan.md`
- [x] CreatorJob aggregate/state/revisions — `alysia/creator/models.py`; `alysia/creator/store.py`; `alysia/creator/service.py`
- [x] topic/research trace and multi-field duplicate detection — `alysia/creator/duplicates.py`; `alysia/creator/bridge.py`
- [x] production/review bridge — existing H3/ComfyUI pipeline mapped through `alysia/creator/bridge.py`
- [x] aggregate CreatorQA — `alysia/creator/qa.py`
- [x] human approval/reject/request-revision — Alpha20 approval path plus Alpha22 Control Center actions
- [x] Bilibili manual handoff adapter — immutable package plus validated real BV receipt; official API mode fails closed without authenticated contract
- [x] timestamped metrics and structured reflection — CreatorJob API/models; unavailable fields remain explicit
- [x] compact episodic memory — `alysia/creator/memory.py`; no single-run semantic promotion
- [x] strict Beta ledger — `evaluation/alpha22/alpha22_beta_runs.csv`; `alysia/creator/evidence.py`
- [x] F1-F7 deterministic tests — `tests/fault_injection/test_alpha22_creator_loop.py`
- [ ] current Alpha18-21 full regression — pending final command evidence
- [ ] live H3/ComfyUI Alpha22 check — pending explicit integration run
- [ ] ten real Bilibili Beta records — 0/10 at engineering stage; must not be synthesized
- [ ] final acceptance report — pending final checks

## Alpha23

Not started. Alpha22 work must not implement Alpha23 long-run/RC scope.
