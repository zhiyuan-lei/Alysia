# Alpha20 Security Review

## Scope and status

This review covers Alysia v0.1-alpha.20 application-level permissions, approval binding, credential references, audit/redaction, logical path/tool/network policy and the protected publish path. It is an engineering review of the implemented controls, not a professional penetration test, formal verification, zero-trust certification or OS sandbox assessment.

## Threat assumptions

- Agents, workflow steps and approved skills can be buggy, over-broad or attempt an action outside their role.
- Stale or incorrectly scoped human approvals may be replayed against a different action, subject, artifact, version or provider.
- Provider errors, logs and artifacts may accidentally contain tokens, cookies or authorization headers.
- Relative paths, Windows drive paths or symbolic links may be used to attempt writes outside a logical skill workspace.
- Network-capable adapters may be pointed at loopback or private-network targets that are inappropriate for their role.
- A local user with filesystem or process control is outside the trusted application boundary and can alter configuration, code or the audit log.

## Protected assets

- Publish packages, approval records, PublishJob state and provider submit calls.
- Creator identity versions, budget change decisions and skill registration approvals.
- Credential references and runtime-resolved secret values.
- Run/workflow artifacts and skill sandbox write roots.
- Local process execution allowlist, public-network access and local ComfyUI/H3 GPU execution.
- Security decisions and redacted application audit evidence.

## Trust boundaries

1. Human approval boundary: an approval must bind action type, subject, artifact/package SHA-256, exact scope, version/nonce and optional expiry. Consumption records prevent reuse by another job.
2. Agent boundary: the role matrix in `config/security_policy.yaml` is authoritative; prompt instructions are not authorization.
3. Provider boundary: publish credentials are resolved from `CredentialReference` only after `READ_CREDENTIAL_REF`; production Bilibili adapters no longer read environment variables directly.
4. Skill boundary: `SkillSandbox` is limited by active-skill state, path guards, credential/network denial and a logical executable allowlist.
5. Network boundary: Researcher public access, explicitly approved APIs and local loopback adapters are separate categories. Private/link-local/reserved IPs are denied by default.
6. Recovery boundary: permission/policy denial is non-retryable; invalid approval or missing credentials escalates rather than relaxing policy.

## Permission model

The model defines 12 permissions: `READ_ARTIFACT`, `WRITE_ARTIFACT`, `NETWORK_PUBLIC`, `GPU_EXECUTE`, `EXECUTE_LOCAL_TOOL`, `PUBLISH`, `READ_CREDENTIAL_REF`, `MODIFY_IDENTITY`, `MODIFY_BUDGET`, `APPROVE_SKILL`, `MODIFY_POLICY` and `SYSTEM_CONFIG`.

The configured matrix contains 15 roles/adapters, including every required Studio role, Supervisor, SkillSandbox, WorkflowRuntime and ComfyUI/H3. Missing actor/permission pairs are denied. `SYSTEM_CONFIG` is hard-denied in the engine even if a future policy file is misconfigured; Alpha20 exposes it to no agent or skill.

`Supervisor` may propose publish/identity/budget/skill/policy changes, but those permissions resolve to `require_approval`. `WriterAgent` cannot publish or modify identity/budget. `PublisherAgent` can publish only with a valid approval and may resolve an approved credential reference, but cannot modify identity, budget or system configuration. `SkillSandbox` cannot read credentials, publish, use network by default or execute an unapproved skill.

## Approval hardening

`ApprovalRecord` now includes `approval_id`, `action_type`, `subject_id`, approval timestamps, optional expiry, package/config hash, scope, nonce, version and consumption fields. `ApprovalValidator` rejects missing approvals, non-human approvers, action/subject/hash/scope mismatch, expiry and replay. A consumed approval can resume the same idempotent PublishJob, but cannot authorize a different consumption reference.

Publish order is: validation PASS -> policy `PUBLISH` check -> scoped approval validation -> approval consumption -> credential reference resolution when required -> provider call -> audit. The Mock provider uses the same permission path. Real providers still reject mock/testing artifacts.

## Credential handling

`config/credential_references.yaml` contains metadata and environment key names only. It contains no secret values. Runtime resolution requires `READ_CREDENTIAL_REF`; providers receive an in-memory mapping and must not persist it. `os_store_ref` remains an explicit unsupported interface in Alpha20 and fails closed. Browser cookies, browser automation login and cookie extraction are not implemented.

`Redactor` removes configured environment secret values, authorization/bearer values and common token/key/cookie/session fields from strings and structured audit context. `SecretScanner` scans text logs, run artifacts, reports and config snapshots when directed by CLI and reports only redacted excerpts.

## Audit

`audit/audit_log.jsonl` is a logically append-only application audit. Every event records actor, action, resource, permission, decision, optional approval/correlation/run/workflow reference, result and redacted context. Writes use Alpha19 atomic replace plus limited backups. This improves crash consistency but is not cryptographically chained, immutable or tamper-proof.

## Sandbox, path, tool and network controls

- `PathGuard` resolves Windows-compatible absolute paths, rejects explicit `..`, enforces allowed roots after resolution and rejects configured credential/source roots.
- `SkillSandbox` writes only below its sandbox root and rejects unapproved execution.
- The executable allowlist recognizes ffmpeg/ffprobe, the approved Python environment, Node/npm/npx/Remotion contexts. It does not pass arbitrary commands to a shell.
- ComfyUI API calls are network calls to an allowed local-loopback adapter; GPU execution is separately checked before generation.
- Research public URLs are allowed only for ResearcherAgent. Private, link-local and reserved literal IP targets are denied. The policy does not bypass robots.txt, authentication or paywalls.

## Security and reliability integration

`FailureCategory` includes `permission_denied`, `approval_invalid`, `credential_unavailable` and `policy_violation`. Permission and policy violations terminate without retry. Invalid approval and unavailable credentials require human intervention. RecoveryPolicy cannot reinterpret these failures as transient provider errors or retry them indefinitely.

## Known gaps and what is not protected

- No OS process sandbox, container, Windows integrity level, filesystem ACL isolation, firewall rule or network namespace is created.
- A local administrator or process with repository write access can alter policy, code, credentials in process memory or the application audit log.
- Audit is not signed, remotely replicated or tamper-evident.
- DNS rebinding and hostname resolution to private addresses are not fully prevented because Alpha20 avoids network DNS resolution during policy checks; literal private IPs are blocked.
- Existing trusted internal subprocess call sites are not all moved behind one OS broker. The Alpha20 allowlist governs SkillSandbox/Workflow generic execution, while established FFmpeg/SAPI/doctor paths retain their existing typed adapters.
- Secret scanning is heuristic and limited to text files up to 2 MiB; it does not inspect binary media, process memory, swap, external service logs or deleted files.
- `os_store_ref` is metadata-only; Windows Credential Manager integration is deferred.
- Bilibili upload remains a safe-fail adapter until an authorized official request contract is configured. Alpha20 does not automate login or obtain cookies.

These limitations are intentional and must not be described as zero-trust or production-grade hostile-code isolation.
