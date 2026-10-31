# Alpha18 Regression Matrix

The executable mapping lives in `alysia/evaluation/matrix.py`; this document is its human-readable index.

| Core invariant | Existing regression evidence | Alpha18 evaluation case |
|---|---|---|
| Topic to Research to Script to Storyboard | `tests/test_orchestrator_text_pipeline.py` | `research_grounding.core`, `script_quality.core`, `storyboard_coverage.core` |
| MockTTS production block / real-provider guard | `tests/test_audio_pipeline.py::test_audio_qa_rejects_mock_tone` | `voice_intelligibility.core` |
| Subtitle semantic/timing QA | `tests/test_audio_pipeline.py` | `subtitle_sync_semantic_split.core` |
| Remotion/FFmpeg render | `tests/test_video_pipeline.py` | `render_stability.core` |
| H3/ComfyUI provider health | `tests/test_h3_local_integration.py` | offline artifact case plus explicit integration case |
| Publish approval gate | `tests/test_workflow.py::test_publish_approval_gate_preserved`, `tests/test_publishing_feedback.py` | publish package + workflow reliability |
| Analytics/Memory real-vs-mock isolation | `tests/test_analytics_learning.py`, `tests/test_publishing_feedback.py` | `analytics_learning_correctness.core` |
| Trend/Simulation/Feedback/Knowledge isolation | three origin-boundary tests in `tests/test_knowledge.py` | knowledge + analytics isolation |
| Identity approval | `tests/test_identity.py` | `brand_style_consistency.core` |
| Skill approval | `tests/test_capabilities.py` | workflow reliability |
| Workflow approved-skill-only | `tests/test_workflow.py::test_unapproved_skill_not_eligible` | workflow reliability |
| Supervisor budget/action limits | `tests/test_supervisor.py::test_budget_policy` | workflow reliability |
| Knowledge stale claim blocking | `tests/test_knowledge.py::test_stale_claim_blocked_in_script` | knowledge freshness/conflict |
| Production provider/resource constraints | `tests/test_production.py` | workflow reliability |
| Voice failure local recovery | `tests/fault_injection/test_reliability.py::test_audio_repair_regenerates_subtitle_only_downstream` | `fault_recovery_reliability.core` |
| H3 failure approved fallback | `tests/fault_injection/test_reliability.py::test_h3_mock_oom_uses_approved_fallback` | `fault_recovery_reliability.core` |
| Render failure render-only retry | `tests/fault_injection/test_reliability.py::test_ffmpeg_failure_render_only_retry` | `fault_recovery_reliability.core` |
| State corruption backup recovery | `tests/fault_injection/test_reliability.py::test_corrupt_state_restores_backup` | `fault_recovery_reliability.core` |
| Duplicate publish prevention | `tests/fault_injection/test_reliability.py::test_publish_job_not_duplicated_after_resume` | `fault_recovery_reliability.core` |
| Security default deny / SYSTEM_CONFIG hard deny | `tests/test_security.py::test_permission_default_deny`, `tests/test_security.py::test_system_config_denied_for_agents` | `security_governance.core` |
| Writer cannot publish | `tests/test_security.py::test_writer_cannot_publish` | `security_governance.core` |
| SkillSandbox cannot read credentials or escape root | `tests/test_security.py::test_skill_sandbox_cannot_read_credentials`, `tests/test_security.py::test_skill_cannot_write_outside_sandbox`, `tests/test_security.py::test_path_traversal_rejected` | `security_governance.core` |
| Approval action/scope/hash/expiry/replay integrity | `tests/test_security.py::test_approval_action_scope`, `tests/test_security.py::test_approval_package_hash_mismatch`, `tests/test_security.py::test_approval_replay_rejected`, `tests/test_security.py::test_expired_approval_rejected` | `security_governance.core` |
| Audit coverage and secret redaction | `tests/test_security.py::test_audit_event_on_deny`, `tests/test_security.py::test_audit_event_on_allow`, `tests/test_security.py::test_security_audit_redacts_credentials` | `security_governance.core` |
| Publish policy gate, including Mock provider | `tests/test_security.py::test_publish_requires_valid_approval`, `tests/test_security.py::test_publish_mock_also_uses_policy_gate` | `security_governance.core` |
| Identity/budget/skill changes require scoped approval | `tests/test_security.py::test_identity_change_requires_approval`, `tests/test_security.py::test_budget_change_requires_approval`, `tests/test_security.py::test_skill_approval_requires_correct_scope` | `security_governance.core` |
| Control Center cannot bypass publish approval | `tests/test_control_api.py::test_api_approval_uses_policy_gate`, `tests/test_control_api.py::test_api_publish_cannot_bypass_gate` | `security_governance.core` |
| Control Center cannot expose credentials | `tests/test_control_api.py::test_api_no_secret_fields`, `tests/test_control_api.py::test_api_audit_redacted` | `security_governance.core` |
| Artifact preview is confined to declared run artifacts | `tests/test_control_api.py::test_api_artifact_path_guard`, `tests/test_control_api.py::test_api_bad_run_id` | `security_governance.core` |
| Control Center recovery uses Alpha19 service | `tests/test_control_api.py::test_api_resume_uses_recovery_service` | `fault_recovery_reliability.core` |
| Evaluation gate remains read-only in UI | `control-center/src/App.test.jsx` blocked-gate case; no evaluation write endpoint exists | `security_governance.core` |
| Mock/real provenance is explicit | `tests/test_control_api.py::test_api_testing_provenance_is_explicit`, `control-center/src/App.test.jsx` | `analytics_learning_correctness.core` |

Alpha18's core matrix test verifies that every row has an existing test file and registered evaluation case. Security promotion is blocked unless all five protected security metrics equal 1.0. H3 remains explicit integration and is never loaded by the default offline suite.
