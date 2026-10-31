from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from alysia.core.config import AlysiaConfig
from alysia.schemas import WorkflowApprovalPolicy, WorkflowBudgetPolicy, WorkflowTask

from .executors import ExecutorSpec, WorkflowExecutionError, WorkflowExecutorRegistry, _declarative_adapter
from .service import WorkflowService


def visual_enhancement_demo(config: AlysiaConfig) -> dict:
    service = WorkflowService(config)
    task = WorkflowTask(
        task_id="demo_visual_enhancement",
        objective="对已有视频 run 的 3 个关键 scene 做 H3 视觉增强并完成 QA",
        inputs=["storyboard"], desired_outputs=["video_qa_report"],
        constraints=["3 scenes", "offline", "mock allowed", "sequential gpu"],
        quality_target="standard", execution_mode="testing",
        budget_policy=WorkflowBudgetPolicy(max_local_vram_mb=7600, allow_unknown_resources=True),
        approval_policy=WorkflowApprovalPolicy(require_human_approval=True, allow_mock_artifacts=True),
        context_refs=["alpha13.5:H3LocalVisualSkill"],
        success_criteria=["status:completed", "artifact:video_qa_report", "qa:video_qa_report"],
    )
    plan = service.plan(task)
    validation = service.validate(plan.workflow_id)
    state = service.run(plan.workflow_id)
    return {
        "workflow_id": plan.workflow_id, "run_id": plan.run_id,
        "validation": validation.model_dump(mode="json"), "state": state.model_dump(mode="json"),
        "report": service.report(plan.workflow_id),
    }


def capability_gap_demo(config: AlysiaConfig) -> dict:
    service = WorkflowService(config)
    task = WorkflowTask(
        task_id="demo_editable_vector_infographic",
        objective="自动生成高质量可编辑矢量信息图",
        inputs=["research"], desired_outputs=["editable_vector_infographic"],
        constraints=["offline", "no unknown code"], execution_mode="testing",
        success_criteria=["artifact:editable_vector_infographic"],
    )
    plan = service.plan(task)
    validation = service.validate(plan.workflow_id)
    return {
        "workflow_id": plan.workflow_id, "status": service.store.load_plan(plan.workflow_id).status,
        "unresolved_gaps": plan.unresolved_gaps, "gap_links": plan.gap_links,
        "validation": validation.model_dump(mode="json"),
    }


def recipe_learning_demo(config: AlysiaConfig) -> dict:
    service = WorkflowService(config)
    workflows: list[str] = []
    recipe_ids: list[str] = []
    for index in range(1, 5):
        task = WorkflowTask(
            task_id=f"demo_recipe_learning_{index}",
            objective="从 storyboard 选择关键视觉场景",
            inputs=["storyboard"], desired_outputs=["selected_scenes"],
            constraints=["offline", "deterministic"], execution_mode="testing",
            success_criteria=["status:completed", "artifact:selected_scenes"],
            approval_policy=WorkflowApprovalPolicy(allow_mock_artifacts=True),
        )
        plan = service.plan(task)
        service.validate(plan.workflow_id)
        service.run(plan.workflow_id)
        plan = service.store.load_plan(plan.workflow_id)
        workflows.append(plan.workflow_id)
        if plan.recipe_id:
            recipe_ids.append(plan.recipe_id)
    recipes = service.recipes.list()
    return {
        "workflow_ids": workflows,
        "validated_recipes": [item.recipe_id for item in recipes if item.status == "validated"],
        "fourth_recipe_id": service.store.load_plan(workflows[-1]).recipe_id,
        "recipe_ids": recipe_ids,
    }


def failure_repair_resume_demo(config: AlysiaConfig) -> dict:
    service = WorkflowService(config)
    task = WorkflowTask(
        task_id="demo_workflow_resume",
        objective="从 storyboard 选择关键视觉场景并验证 resume",
        inputs=["storyboard"], desired_outputs=["selected_scenes"], execution_mode="testing",
        constraints=["offline"], success_criteria=["status:completed", "artifact:selected_scenes"],
        approval_policy=WorkflowApprovalPolicy(allow_mock_artifacts=True),
    )
    plan = service.plan(task)
    service.validate(plan.workflow_id)
    broken = WorkflowExecutorRegistry.controlled_defaults()
    broken.register(ExecutorSpec("scene_selection", "production", "capability", _always_fail))
    original_rounds = service.config.workflow.max_repair_rounds
    service.config.workflow.max_repair_rounds = 0
    failed = service.run(plan.workflow_id, executors=broken)
    service.config.workflow.max_repair_rounds = original_rounds
    resumed = service.resume(plan.workflow_id, executors=WorkflowExecutorRegistry.controlled_defaults())
    return {
        "workflow_id": plan.workflow_id, "failed_status": failed.status,
        "resumed_status": resumed.status, "attempts": resumed.steps[plan.steps[0].step_id].attempts,
    }


def _always_fail(context):
    raise WorkflowExecutionError("controlled demo failure")
