from __future__ import annotations

import re

from alysia.schemas import CandidateCapability, ProductionConstraints, WorkflowTask

from .contracts import RegistryView


class CapabilityMatcher:
    def match(
        self,
        task: WorkflowTask,
        registry: RegistryView,
        constraints: ProductionConstraints | None = None,
    ) -> list[CandidateCapability]:
        constraints = constraints or ProductionConstraints(
            quality_target=task.quality_target,
            max_local_vram_mb=task.budget_policy.max_local_vram_mb,
            max_cloud_cost=task.budget_policy.max_cloud_cost,
            max_wall_time_sec=task.budget_policy.max_wall_time_sec,
        )
        terms = set(re.findall(r"[a-zA-Z0-9_]+", task.objective.lower()))
        required = set(task.desired_outputs)
        candidates: list[CandidateCapability] = []
        for item in registry.all():
            matched_outputs = required & set(item.produced_outputs)
            matched_tags = terms & set(item.tags)
            matched_inputs = set(task.inputs) & set(item.accepted_inputs)
            status_ok = item.status not in {"deprecated", "disabled", "rolled_back"}
            if item.source_type == "skill":
                status_ok = item.status == "active"
            resource_ok, resource_notes = self._resource_eligible(task, item.resource_requirements, constraints)
            contract_ok = bool(item.produced_outputs) and "contract_not_declared" not in item.policy_restrictions
            eligible = status_ok and resource_ok and contract_ok
            maturity_score = 1.0 if item.maturity == "stable" else 0.65
            if item.source_type == "skill" and item.status == "active":
                maturity_score = 0.95
            score = min(1.0, (
                0.45 * (len(matched_outputs) / max(1, len(required)))
                + 0.15 * (len(matched_inputs) / max(1, len(item.accepted_inputs)))
                + 0.10 * min(1.0, len(matched_tags) / 2)
                + 0.20 * maturity_score
                + 0.10 * float(resource_ok)
            ))
            risks = list(item.policy_restrictions)
            if not status_ok:
                risks.append(f"状态不可执行：{item.status}")
            if not contract_ok:
                risks.append("缺少受信任 input/output contract")
            candidates.append(CandidateCapability(
                candidate_id=item.implementation_id, source_type=item.source_type,
                version=item.version, status=item.status, match_score=round(score, 4),
                matched_requirements=sorted(matched_outputs | matched_inputs | matched_tags),
                missing_requirements=sorted(required - set(item.produced_outputs)),
                prerequisites=list(item.prerequisites), accepted_inputs=list(item.accepted_inputs),
                produced_outputs=list(item.produced_outputs), owner_agent=item.owner_agent,
                execution_layer=item.execution_layer, resource_notes=resource_notes,
                risk_notes=risks, confidence=maturity_score, eligible=eligible,
            ))
        return sorted(candidates, key=lambda item: (item.eligible, item.match_score, item.confidence), reverse=True)

    @staticmethod
    def _resource_eligible(task: WorkflowTask, resource: dict, constraints: ProductionConstraints) -> tuple[bool, list[str]]:
        notes: list[str] = []
        eligible = True
        peak = resource.get("peak_vram_mb")
        if isinstance(peak, (int, float)):
            notes.append(f"peak_vram_mb={peak}")
            if peak > constraints.max_local_vram_mb:
                eligible = False
                notes.append("超过 max_local_vram_mb")
        elif resource.get("gpu_heavy"):
            notes.append("peak_vram_mb=unknown")
            if task.execution_mode == "production" and not task.budget_policy.allow_unknown_resources:
                eligible = False
                notes.append("production 禁止未知 GPU 资源预算")
        if resource.get("sequential_gpu_required"):
            notes.append("继承 alpha11 sequential GPU policy")
        return eligible, notes
