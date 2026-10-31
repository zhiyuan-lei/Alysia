# Alpha20 Change Review

## Goal

Add enforceable application-level least privilege, scoped human approvals, credential references, redacted audit evidence and security gates without entering Alpha21 or replacing Alpha1-19 work.

## Changed areas

- New `alysia/security/` policy, approval, credential, audit, redaction, path, tool, network, service and demo modules.
- New `alysia/schemas/security.py`; additive ApprovalRecord and FailureCategory fields.
- Security configuration and auditable role/credential metadata under `config/`.
- Enforcement at PublishingService, IdentityEvolutionService, SkillAcquisitionService, WorkflowRuntime, Web/Trend/Ollama adapters and ComfyUI/H3 adapter.
- Alpha18 security benchmark and regression matrix rows.
- Offline security tests, fake-secret fixtures and Demo A-D evidence.
- CLI `security status|permissions|audit|scan|approvals|demo`.

## Unrelated changes

No unrelated cleanup, refactor, formatting sweep, dependency upgrade, model download or Alpha21 UI work was performed. Existing Alpha1-19 uncommitted files were not reset, restored, stashed, committed or removed.

## Dependencies

No new package dependency was added. The implementation uses existing Pydantic, PyYAML and standard-library primitives.

## Schema, config and CLI changes

- `ApprovalRecord` remains backward-loadable through defaults while adding action/subject/scope/expiry/replay fields.
- `FailureCategory` adds four explicit security failures.
- `SecurityConfig` adds enabled/default-deny policy, metadata files, audit location and tool allowlist.
- The Alpha18 registry advances to `alpha20.1` with five protected security metrics.
- Six read-only/control security CLI surfaces and one offline demo command are added.

## Regression risk review

- Publish idempotency: consumed approvals permit only the same deterministic job ID; duplicate provider submit remains prevented.
- Existing approvals: new approvals are provider-scoped; old deserialized records receive safe defaults but may require re-approval when their scope does not match the provider.
- Network adapters: only production constructors inject SecurityService; direct unit-test adapters remain injectable and offline.
- H3: health/generation calls now check loopback/GPU permissions but retain the existing explicit-integration test boundary.
- Recovery: security denials cannot enter retry loops.
- Audit writes add small atomic I/O before sensitive actions; they do not alter run artifacts.

## Risks not fully covered

The residual risks and non-claims are listed in `docs/security_review_alpha20.md`, especially OS isolation, audit tamper resistance, DNS rebinding, heuristic secret detection and remaining trusted typed subprocess adapters.

## Alpha21 prerequisites

Alpha21 may display decisions and approvals only through these security services. It must not duplicate policy logic in the UI, display secret values, mutate policy without approval or treat audit JSONL as tamper-proof. Alpha21 was not implemented in this change.
