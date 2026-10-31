from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

from alysia.knowledge.conflicts import ConflictDetector
from alysia.knowledge.models import EvidenceSource, KnowledgeClaim, normalize_claim_key, stable_id
from alysia.knowledge.service import KnowledgeService
from alysia.core.run import RunManager
from alysia.schemas.script import Script, ScriptSection


def _official(source_id: str, title: str, url: str, *, published_at: datetime) -> EvidenceSource:
    return EvidenceSource(
        source_id=source_id,
        url=url,
        title=title,
        publisher="MiniMax 官方文档（离线 fixture）",
        domain="minimax.io",
        published_at=published_at,
        retrieved_at=datetime.now().astimezone(),
        source_type="official",
        freshness_class="current",
        evidence_origin="manual",
        citation_note="alpha17 offline fixture；只验证知识管线行为",
    )


def demo_a_supersession(service: KnowledgeService, *, run_root: Path | None = None) -> dict[str, object]:
    now = datetime.now().astimezone()
    store = service.store
    source_v1 = store.add_source(_official("demo-a-source-v1", "模型 v1 文档", "https://www.minimax.io/docs/demo-v1", published_at=now - timedelta(days=30)))
    key = "demo-model-max-duration"
    old_id = "demo-a-claim-v1"
    new_id = "demo-a-claim-v2"
    old = KnowledgeClaim(
        claim_id=old_id, statement="该模型 v1 最大视频时长为 10 秒。", normalized_key=key,
        topic="Demo A", domain="model_version", claim_type="time_sensitive", status="verified",
        confidence=0.95, last_verified_at=now - timedelta(days=30), evidence_refs=[source_v1.source_id],
        version=1, freshness_policy_days=14,
    )
    store.add_claim(old)
    old_run = (run_root or service.config.runtime.runs_dir) / "alpha17_demo_a_old_run"
    snapshot = store.snapshot_run(old_run, [old])
    source_v2 = store.add_source(_official("demo-a-source-v2", "模型 v2 文档", "https://www.minimax.io/docs/demo-v2", published_at=now))
    new = KnowledgeClaim(
        claim_id=new_id, statement="该模型 v2 最大视频时长为 15 秒。", normalized_key=key,
        topic="Demo A", domain="model_version", claim_type="time_sensitive", status="verified",
        confidence=0.97, last_verified_at=now, evidence_refs=[source_v2.source_id],
        version=2, freshness_policy_days=14,
    )
    old, new = store.supersede(old_id, new)
    snapshot_payload = json.loads(Path(snapshot["claims_used"]).read_text(encoding="utf-8"))
    return {
        "old_claim_status": old.status,
        "new_claim_status": new.status,
        "new_supersedes": new.supersedes_claim_id,
        "old_snapshot_statement": snapshot_payload[0]["statement"],
        "old_snapshot_preserved": snapshot_payload[0]["status"] == "verified",
        "new_current": new.status == "verified" and new.version == 2,
    }


def demo_b_conflict(service: KnowledgeService) -> dict[str, object]:
    now = datetime.now().astimezone()
    store = service.store
    source_a = store.add_source(_official("demo-b-source-a", "技术参数 A", "https://www.minimax.io/docs/demo-param-a", published_at=now))
    source_b = EvidenceSource(
        source_id="demo-b-source-b", url="https://community.example.invalid/demo-param-b",
        title="社区参数记录 B", publisher="社区记录", domain="community.example.invalid",
        published_at=now, retrieved_at=now, source_type="community", freshness_class="current",
        evidence_origin="manual", reliability_notes=["需要官方资料复核"],
    )
    store.add_source(source_b)
    key = "demo-b-technical-parameter"
    claim_a = KnowledgeClaim(
        claim_id="demo-b-claim-a", statement="技术参数为 24。", normalized_key=key,
        topic="Demo B", domain="software", claim_type="time_sensitive", status="provisional",
        confidence=0.65, last_verified_at=now, evidence_refs=[source_a.source_id], freshness_policy_days=14,
    )
    claim_b = KnowledgeClaim(
        claim_id="demo-b-claim-b", statement="技术参数为 32。", normalized_key=key,
        topic="Demo B", domain="software", claim_type="time_sensitive", status="provisional",
        confidence=0.4, last_verified_at=now, evidence_refs=[source_b.source_id], freshness_policy_days=14,
    )
    store.add_claim(claim_a)
    store.add_claim(claim_b)
    conflicts = ConflictDetector(store).detect_for(claim_b)
    task = service.research_tasks.create("Demo B 技术参数的当前官方值是什么？", required_evidence_quality="primary", freshness_requirement_days=14)
    return {
        "conflict_ids": [item.conflict_id for item in conflicts],
        "claim_a_status": store.get_claim(claim_a.claim_id).status,
        "claim_b_status": store.get_claim(claim_b.claim_id).status,
        "writer_must_hedge": True,
        "research_task_id": task.task_id,
        "required_evidence_quality": task.required_evidence_quality,
    }


def demo_c_stale_block(service: KnowledgeService) -> dict[str, object]:
    now = datetime.now().astimezone()
    store = service.store
    source = store.add_source(_official("demo-c-source", "API 价格旧快照", "https://www.minimax.io/docs/demo-pricing", published_at=now - timedelta(days=10)))
    claim = KnowledgeClaim(
        claim_id="demo-c-stale-pricing", statement="该 API 当前价格为每次 1 元。",
        normalized_key="demo-c-api-pricing", topic="Demo C", domain="pricing",
        claim_type="time_sensitive", status="verified", confidence=0.9,
        last_verified_at=now - timedelta(days=10), evidence_refs=[source.source_id], freshness_policy_days=3,
    )
    store.add_claim(claim)
    script = Script(
        title="过期知识阻塞演示", hook="价格是否还是原来的值？", thesis="可变事实必须重新验证。",
        target_audience="测试", target_duration_sec=30,
        sections=[ScriptSection(id="facts", purpose="说明价格", narration=claim.statement, key_visual_hint="价格卡片", claim_refs=[claim.claim_id])],
        conclusion="完成验证后恢复。",
    )
    before = service.grounding.check(script, run_id="alpha17_demo_c", factual_section_ids={"facts"})
    maintenance = service.maintenance.tick(priority_topics=["Demo C"])
    gap = service.gaps.create(
        "Demo C API 当前价格是多少？", affected_topics=["Demo C"], affected_runs=["alpha17_demo_c"],
        urgency="critical", required_source_types=["official", "primary"], current_evidence=[source.source_id],
    )
    return {
        "blocked": not before.passed,
        "stale_claim_refs": before.stale_claim_refs,
        "reverification_tasks": maintenance.task_ids,
        "knowledge_gap_id": gap.gap_id,
        "resume_from": "writing",
        "restart_full_pipeline": False,
    }


def demo_d_h3_observation(service: KnowledgeService, evidence_path: Path = Path("evaluation/capability_evaluation_h3_runtime.json")) -> dict[str, object]:
    payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    evidence = payload["evidence"]
    source = EvidenceSource(
        source_id="local-h3-runtime-20260808",
        url="https://localhost.invalid/alysia/h3-runtime-observation/20260808",
        title="Alysia 本机 H3 runtime observation",
        publisher="Alysia local benchmark",
        domain="local_system",
        retrieved_at=datetime.fromisoformat(payload["generated_at"]),
        source_type="primary",
        freshness_class="observed_snapshot",
        content_hash=stable_id("sha", json.dumps(payload, sort_keys=True)),
        access_note=str(evidence_path),
        citation_note="单机运行观测，不可外推为全局模型性能",
        evidence_origin="system_observation",
        observation_scope="current_machine",
    )
    service.store.add_source(source)
    statement = (
        f"在当前本机观测中，H3 {evidence['resolution']} / {evidence['duration_sec']} 秒 / "
        f"{evidence['steps']} steps 的 provider wall time 为 {evidence['alysia_provider_wall_time_sec']} 秒，"
        f"峰值 VRAM {evidence['peak_vram_used_mb']} MB。"
    )
    claim = KnowledgeClaim(
        claim_id="local-h3-capability-observation-20260808",
        statement=statement,
        normalized_key=normalize_claim_key("current-machine-h3-runtime-profile"),
        topic="H3 local capability", domain="local_capability_observation",
        claim_type="historical", status="verified", confidence=0.99,
        last_verified_at=source.retrieved_at, evidence_refs=[source.source_id],
        scope="current_machine", conditions=["RTX 4060 Ti", "Alysia provider", evidence["resolution"]],
    )
    service.store.add_claim(claim)
    return {
        "claim_id": claim.claim_id,
        "status": claim.status,
        "scope": claim.scope,
        "source_origin": source.evidence_origin,
        "observation_scope": source.observation_scope,
        "global_fact": claim.scope == "global",
        "provider": evidence["real_provider"],
        "mock": evidence["mock"],
    }


def demo_grounding_run(service: KnowledgeService) -> dict[str, object]:
    h3 = demo_d_h3_observation(service)
    claim = service.store.get_claim(str(h3["claim_id"]))
    manager = RunManager(service.config.runtime.runs_dir)
    state = manager.create("alpha17 H3 本机观测 grounding demo", service.config.model_dump(mode="json"))
    script = Script(
        title="H3 本机能力观测", hook="本机实测与公共事实有什么区别？",
        thesis="单机 benchmark 只能说明其明确条件下的本机表现。", target_audience="开发者",
        target_duration_sec=30,
        sections=[ScriptSection(
            id="local-observation", purpose="报告本机观测", narration=claim.statement,
            key_visual_hint="本机资源卡片", claim_refs=[claim.claim_id],
        )],
        conclusion="该观测不外推为所有机器或模型版本的全局性能。",
        source_refs=claim.evidence_refs,
    )
    manager.write_json(state.run_id, "script.json", script.model_dump(mode="json"))
    manager.write_text(state.run_id, "script.md", script.to_markdown())
    state.artifacts.update({"script": "script.json", "script_markdown": "script.md"})
    manager.save(state)
    report = service.grounding.check(script, run_id=state.run_id, factual_section_ids={"local-observation"})
    service.grounding.save(report, manager.run_dir(state.run_id))
    service.store.snapshot_run(manager.run_dir(state.run_id), [claim])
    return {"run_id": state.run_id, "passed": report.passed, "citation_coverage": report.citation_coverage}
