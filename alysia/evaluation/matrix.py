from __future__ import annotations


REGRESSION_MATRIX = [
    {"invariant": "topic_research_script_storyboard", "tests": ["tests/test_orchestrator_text_pipeline.py"], "evaluation_cases": ["research_grounding.core", "script_quality.core", "storyboard_coverage.core"]},
    {"invariant": "mock_tts_production_block", "tests": ["tests/test_audio_pipeline.py::test_audio_qa_rejects_mock_tone"], "evaluation_cases": ["voice_intelligibility.core"]},
    {"invariant": "subtitle_semantic_timing", "tests": ["tests/test_audio_pipeline.py"], "evaluation_cases": ["subtitle_sync_semantic_split.core"]},
    {"invariant": "remotion_ffmpeg_render", "tests": ["tests/test_video_pipeline.py"], "evaluation_cases": ["render_stability.core"]},
    {"invariant": "h3_comfyui_health", "tests": ["tests/test_h3_local_integration.py"], "evaluation_cases": ["visual_h3_artifact_validity.offline", "visual_h3_artifact_validity.integration"]},
    {"invariant": "publish_approval", "tests": ["tests/test_workflow.py::test_publish_approval_gate_preserved", "tests/test_publishing_feedback.py"], "evaluation_cases": ["publish_package_correctness.core", "supervisor_workflow_reliability.core"]},
    {"invariant": "analytics_memory_mock_isolation", "tests": ["tests/test_analytics_learning.py", "tests/test_publishing_feedback.py"], "evaluation_cases": ["analytics_learning_correctness.core"]},
    {"invariant": "trend_simulation_feedback_knowledge_isolation", "tests": ["tests/test_knowledge.py::test_trend_not_promoted_to_fact", "tests/test_knowledge.py::test_simulation_not_promoted_to_fact", "tests/test_knowledge.py::test_feedback_not_promoted_to_fact"], "evaluation_cases": ["knowledge_freshness_conflict.core", "analytics_learning_correctness.core"]},
    {"invariant": "identity_approval", "tests": ["tests/test_identity.py"], "evaluation_cases": ["brand_style_consistency.core"]},
    {"invariant": "skill_approval", "tests": ["tests/test_capabilities.py"], "evaluation_cases": ["supervisor_workflow_reliability.core"]},
    {"invariant": "workflow_approved_skill_only", "tests": ["tests/test_workflow.py::test_unapproved_skill_not_eligible"], "evaluation_cases": ["supervisor_workflow_reliability.core"]},
    {"invariant": "supervisor_budget_action_limits", "tests": ["tests/test_supervisor.py::test_budget_policy"], "evaluation_cases": ["supervisor_workflow_reliability.core"]},
    {"invariant": "knowledge_stale_claim_blocking", "tests": ["tests/test_knowledge.py::test_stale_claim_blocked_in_script"], "evaluation_cases": ["knowledge_freshness_conflict.core"]},
    {"invariant": "production_provider_resource_constraints", "tests": ["tests/test_production.py"], "evaluation_cases": ["supervisor_workflow_reliability.core"]},
    {"invariant": "voice_failure_local_recovery", "tests": ["tests/fault_injection/test_reliability.py::test_audio_repair_regenerates_subtitle_only_downstream"], "evaluation_cases": ["fault_recovery_reliability.core"]},
    {"invariant": "h3_failure_local_recovery", "tests": ["tests/fault_injection/test_reliability.py::test_h3_mock_oom_uses_approved_fallback"], "evaluation_cases": ["fault_recovery_reliability.core"]},
    {"invariant": "render_failure_local_recovery", "tests": ["tests/fault_injection/test_reliability.py::test_ffmpeg_failure_render_only_retry"], "evaluation_cases": ["fault_recovery_reliability.core"]},
    {"invariant": "state_corruption_recovery", "tests": ["tests/fault_injection/test_reliability.py::test_corrupt_state_restores_backup"], "evaluation_cases": ["fault_recovery_reliability.core"]},
    {"invariant": "duplicate_publish_prevention", "tests": ["tests/fault_injection/test_reliability.py::test_publish_job_not_duplicated_after_resume"], "evaluation_cases": ["fault_recovery_reliability.core"]},
    {"invariant": "security_default_deny", "tests": ["tests/test_security.py::test_permission_default_deny"], "evaluation_cases": ["security_governance.core"]},
    {"invariant": "security_writer_cannot_publish", "tests": ["tests/test_security.py::test_writer_cannot_publish"], "evaluation_cases": ["security_governance.core"]},
    {"invariant": "security_sandbox_no_credentials", "tests": ["tests/test_security.py::test_skill_sandbox_cannot_read_credentials"], "evaluation_cases": ["security_governance.core"]},
    {"invariant": "security_approval_hash_scope", "tests": ["tests/test_security.py::test_approval_package_hash_mismatch", "tests/test_security.py::test_approval_action_scope"], "evaluation_cases": ["security_governance.core"]},
    {"invariant": "security_audit_redaction", "tests": ["tests/test_security.py::test_security_audit_redacts_credentials"], "evaluation_cases": ["security_governance.core"]},
    {"invariant": "security_publish_policy_gate", "tests": ["tests/test_security.py::test_publish_mock_also_uses_policy_gate"], "evaluation_cases": ["security_governance.core", "publish_package_correctness.core"]},
    {"invariant": "security_governed_changes", "tests": ["tests/test_security.py::test_identity_change_requires_approval", "tests/test_security.py::test_budget_change_requires_approval", "tests/test_security.py::test_skill_approval_requires_correct_scope"], "evaluation_cases": ["security_governance.core"]},
]


def matrix_invariant_ids() -> set[str]:
    return {item["invariant"] for item in REGRESSION_MATRIX}
