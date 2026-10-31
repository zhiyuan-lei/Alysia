# Alpha22 Bilibili Field Run Runbook

## Safety boundary
- Public publication is always a human action until an authenticated, reviewed Bilibili Open Platform transport is configured.
- A prepared local package is never PUBLISHED.
- Do not place cookies, tokens, client secrets, or Authorization headers in the run directory, CreatorJob, logs, prompts, memory, screenshots, or CSV.
- Do not count mock/testing/dry-run jobs.

## One real CreatorJob

1. Start the local services needed by the selected production plan. Heavy GPU stages remain serial.
2. Create a CreatorLoop plan from real/manual/web trend sources and approve one PlanSlot.
3. Run/resume the bound content run until `review_ready`.
4. In Control Center, open Creator Beta and inspect:
   - topic and research/claim trace;
   - script and final media artifacts in the bound Run detail;
   - aggregate CreatorQA and underlying grounding/video/publish QA;
   - title, description, tags, thumbnail, video, risk, and package metadata.
5. Choose exactly one:
   - APPROVE: Alpha20 revalidates scope/hash/version and creates `publish/bilibili_handoff.json`;
   - REJECT: enter a reason; the CreatorJob becomes BLOCKED and cannot publish;
   - REQUEST_REVISION: enter a reason; revision N is snapshotted and revision N+1 returns to DRAFT.
6. For an approved `PUBLISH_READY` job, a human uploads the immutable video/package to Bilibili.
7. Save a non-secret platform receipt or screenshot inside the bound run directory, for example:
   `runs/<run_id>/publish/bilibili_receipt.json`.
8. Record the real BV identifier, canonical URL, publication time, recorder, and evidence path through:
   `POST /api/creator-jobs/<job_id>/record-publication`.
   The service validates the BV form, URL/ID match, evidence existence, human actor, QA, approval, and real provenance before PUBLISHED.
9. At each observation time, save the platform evidence inside the run directory and call:
   `POST /api/creator-jobs/<job_id>/observations`.
   Every metric must be either a non-negative value with `available` or null with `unavailable`.
10. Record CreatorReflection through:
    `POST /api/creator-jobs/<job_id>/reflection`.
    Facts, interpretations, uncertainties, evidence, and next changes are separate.
11. Call the memory endpoint to write one compact episodic record. Raw comments/metrics/research remain outside long-term memory.
12. Save a self-contained evidence summary in the run directory and call the Beta evidence endpoint. The CSV row is upserted by job_id.

## Qualification rule
A row counts only when it is:
- real, non-testing, non-dry-run;
- Bilibili and PUBLISHED with a validated BV receipt;
- CreatorQA PASS;
- accompanied by at least one timestamped observation (values may all be explicitly unavailable);
- accompanied by a reflection;
- backed by an existing non-empty evidence path.

Until 10 qualified rows exist, Alpha22 is not PASS.

## Official API mode
Bilibili's public Open Platform states that video management and data-return capabilities exist, but the detailed contracts require developer identity verification, application setup, and UP authorization. The code therefore exposes an injectable official transport boundary and fails closed when it is absent; it does not guess endpoints or automate browser cookies.

