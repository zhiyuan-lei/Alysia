from __future__ import annotations

from alysia.core.config import AlysiaConfig
from alysia.core.run import RunManager
from alysia.production import ProductionService
from alysia.studio.ownership import ARTIFACT_OWNERS
from alysia.studio.protocol import StudioQAReport, StudioState
from alysia.studio.trace import StudioTraceStore


class StudioQA:
    def __init__(self, config: AlysiaConfig) -> None:
        self.config = config
        self.manager = RunManager(config.runtime.runs_dir)

    def run(self, run_id: str, store: StudioTraceStore, studio_state: StudioState) -> StudioQAReport:
        run_state = self.manager.load(run_id)
        handoffs = store.handoffs()
        artifacts = store.artifacts()
        revisions = store.revisions()
        errors: list[str] = []
        warnings: list[str] = []

        incomplete_handoffs = [
            item.handoff_id for item in handoffs if item.status in {"pending", "accepted"}
        ]
        if self.config.studio.require_handoff_records and studio_state.agent_hops and not handoffs:
            errors.append("Studio 执行过角色跳转但没有 handoff records")
        if incomplete_handoffs:
            errors.append("存在未完成 handoff：" + ", ".join(incomplete_handoffs))

        ownership_errors = [
            f"{item.kind}:{item.owner_agent_id}!={ARTIFACT_OWNERS.get(item.kind)}"
            for item in artifacts
            if ARTIFACT_OWNERS.get(item.kind) != item.owner_agent_id
        ]
        if self.config.studio.enforce_artifact_ownership and ownership_errors:
            errors.append("artifact owner 错误：" + ", ".join(ownership_errors))

        duplicate_versions = []
        seen: set[tuple[str, int]] = set()
        for item in artifacts:
            key = (item.kind, item.version)
            if key in seen:
                duplicate_versions.append(f"{item.kind}@v{item.version}")
            seen.add(key)
        if duplicate_versions:
            errors.append("artifact version 重复：" + ", ".join(duplicate_versions))

        if studio_state.review_rounds > self.config.studio.max_review_rounds:
            errors.append("review loop 超过 max_review_rounds")
        if studio_state.agent_hops > self.config.studio.max_agent_hops:
            errors.append("agent hops 超过 max_agent_hops")
        unresolved_revisions = [item.request_id for item in revisions if item.status in {"pending", "accepted"}]
        if studio_state.status == "completed" and unresolved_revisions:
            errors.append("completed Studio 仍有未解决 revision：" + ", ".join(unresolved_revisions))
        if studio_state.escalation is not None and studio_state.status == "completed":
            errors.append("completed Studio 仍包含未解决 escalation")

        required_by_run = {
            "text": ["research", "script", "storyboard", "text_qa"],
            "audio": ["audio", "subtitles", "audio_qa"],
            "video": ["final_video", "video_qa"],
            "package": ["publish_package", "publish_qa"],
        }
        available = {item.kind for item in artifacts}
        missing = []
        if run_state.text_pipeline_completed:
            missing.extend(item for item in required_by_run["text"] if item not in available)
        if run_state.audio_pipeline_completed:
            missing.extend(item for item in required_by_run["audio"] if item not in available)
        if run_state.video_pipeline_completed:
            missing.extend(item for item in required_by_run["video"] if item not in available)
        if run_state.package_pipeline_completed:
            missing.extend(item for item in required_by_run["package"] if item not in available)
        if missing:
            errors.append("缺少与 run milestone 对应的 Studio artifact：" + ", ".join(sorted(set(missing))))

        mock_provider_misuse = False
        try:
            plan = ProductionService(self.config).load_plan(run_id)
            selected = set(plan.selected_provider_per_stage.values())
            mock_provider_misuse = (
                self.config.publishing.provider != "mock"
                and any(".mock" in item for item in selected)
            )
        except FileNotFoundError:
            warnings.append("run 尚无 ProductionPlan，无法完成 mock provider 审计")
        if mock_provider_misuse:
            errors.append("真实 publishing 配置下 ProductionPlan 包含 mock provider")

        checks = {
            "handoffs_complete": not incomplete_handoffs,
            "artifact_owners_valid": not ownership_errors,
            "artifact_versions_unique": not duplicate_versions,
            "review_round_within_limit": studio_state.review_rounds <= self.config.studio.max_review_rounds,
            "agent_hops_within_limit": studio_state.agent_hops <= self.config.studio.max_agent_hops,
            "required_artifacts_present": not missing,
            "no_unresolved_escalation_on_complete": not (
                studio_state.status == "completed" and studio_state.escalation is not None
            ),
            "mock_provider_not_in_real_publish": not mock_provider_misuse,
        }
        report = StudioQAReport(
            run_id=run_id,
            passed=not errors,
            checks=checks,
            errors=errors,
            warnings=warnings,
            metrics={
                "handoff_count": len(handoffs),
                "artifact_count": len(artifacts),
                "result_count": len(store.results()),
                "trace_event_count": len(store.trace_records()),
                "review_rounds": studio_state.review_rounds,
                "agent_hops": studio_state.agent_hops,
            },
        )
        store.save_qa(report)
        return report
