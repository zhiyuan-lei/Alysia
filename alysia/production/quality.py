from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from alysia.core.run import RunManager
from alysia.schemas import ProductionPlan, ProductionQualityGateReport

_QA_ARTIFACTS = {
    "text": "text_qa_report.json",
    "audio": "audio_qa_report.json",
    "video": "qa/video_qa_report.json",
    "publish": "publish/publish_qa_report.json",
}


class ProductionQualityGate:
    def __init__(self, manager: RunManager) -> None:
        self.manager = manager

    def evaluate(self, run_id: str, plan: ProductionPlan) -> ProductionQualityGateReport:
        state = self.manager.load(run_id)
        run_dir = self.manager.run_dir(run_id)
        errors = list(plan.policy_blockers)
        warnings = list(plan.warnings)
        checked: list[str] = []
        expected = []
        if state.text_pipeline_completed:
            expected.append(_QA_ARTIFACTS["text"])
        if state.audio_pipeline_completed:
            expected.append(_QA_ARTIFACTS["audio"])
        if state.video_pipeline_completed:
            expected.append(_QA_ARTIFACTS["video"])
        if state.package_pipeline_completed or state.review_ready:
            expected.append(_QA_ARTIFACTS["publish"])
        for relative in expected:
            path = run_dir / relative
            checked.append(relative)
            if not path.is_file():
                errors.append(f"缺少既有 QA：{relative}")
                continue
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload.get("passed") is not True:
                errors.append(f"既有 QA 未通过：{relative}")
            qa_warnings = payload.get("warnings") or []
            warnings.extend(f"{relative}: {item}" for item in qa_warnings)

        if plan.profile.quality_target == "high" and state.review_ready:
            style_path = run_dir / "qa" / "style_consistency_report.json"
            checked.append("qa/style_consistency_report.json")
            if not style_path.is_file():
                errors.append("high profile 的 review-ready 内容缺少二次 Style QA")
            elif json.loads(style_path.read_text(encoding="utf-8")).get("violations"):
                errors.append("high profile 的 Style QA 存在 violation")
        if plan.profile.quality_target == "draft":
            errors = [item for item in errors if "policy" in item.lower() or "人工确认" in item]
        report = ProductionQualityGateReport(
            run_id=run_id,
            plan_id=plan.plan_id,
            quality_target=plan.profile.quality_target,
            passed=not errors,
            errors=sorted(set(errors)),
            warnings=sorted(set(warnings)),
            checked_qa_artifacts=checked,
            retry_budget=plan.profile.max_retries_per_stage,
            checked_at=datetime.now().astimezone(),
        )
        self.manager.write_json(run_id, "production/quality_gate_report.json", report.model_dump(mode="json"))
        return report
