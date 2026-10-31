from __future__ import annotations

from alysia.studio.protocol import AgentProfile


class AgentRegistry:
    def __init__(self, profiles: list[AgentProfile] | None = None) -> None:
        self._profiles: dict[str, AgentProfile] = {}
        for profile in profiles or self.default_profiles():
            self.register(profile)

    def register(self, profile: AgentProfile) -> None:
        if profile.agent_id in self._profiles:
            raise ValueError(f"重复 agent_id：{profile.agent_id}")
        self._profiles[profile.agent_id] = profile

    def get(self, agent_id: str) -> AgentProfile:
        try:
            return self._profiles[agent_id]
        except KeyError as exc:
            raise KeyError(f"未注册 Studio Agent：{agent_id}") from exc

    def list(self) -> list[AgentProfile]:
        return list(self._profiles.values())

    def assert_can_produce(self, agent_id: str, artifact_kind: str) -> None:
        profile = self.get(agent_id)
        if artifact_kind not in profile.produced_artifacts:
            raise PermissionError(f"{agent_id} 无权产出 {artifact_kind}")

    def assert_provider_allowed(self, agent_id: str, provider_id: str) -> None:
        profile = self.get(agent_id)
        allowed = profile.allowed_providers
        if provider_id not in allowed and not any(
            item.endswith(".*") and provider_id.startswith(item[:-1]) for item in allowed
        ):
            raise PermissionError(f"{agent_id} 不允许使用 provider {provider_id}")

    def available_skills(self, agent_id: str, skill_registry) -> list:
        """Studio 只能看到 SkillRegistry 中 active 且已批准注册的技能。"""
        self.get(agent_id)
        return skill_registry.available(agent_id)

    @staticmethod
    def default_profiles() -> list[AgentProfile]:
        return [
            AgentProfile(
                agent_id="researcher",
                role="ResearcherAgent",
                capabilities=["source_research", "fact_summary"],
                accepted_inputs=["topic", "planning_provenance"],
                produced_artifacts=["research"],
                required_context=["goal", "constraints", "production_plan_id"],
                allowed_tools=["research_worker"],
                allowed_providers=["research.*"],
                quality_responsibilities=["source_traceability", "fact_inference_separation"],
                escalation_rules=["provider_failure", "insufficient_sources"],
            ),
            AgentProfile(
                agent_id="writer",
                role="WriterAgent",
                capabilities=["script_writing", "script_revision"],
                accepted_inputs=["research", "revision_request"],
                produced_artifacts=["script", "metadata"],
                required_context=["creator_identity", "brand_voice", "strategy_refs", "experiment_refs"],
                allowed_tools=["writer_agent"],
                allowed_providers=["llm.*"],
                quality_responsibilities=["brand_voice", "narrative_clarity", "source_references"],
                escalation_rules=["unresolved_fact_question", "review_round_limit"],
            ),
            AgentProfile(
                agent_id="storyboard_director",
                role="StoryboardDirectorAgent",
                capabilities=["storyboard", "narrative_pacing"],
                accepted_inputs=["script"],
                produced_artifacts=["storyboard"],
                required_context=["creator_identity", "brand_voice", "constraints"],
                allowed_tools=["director_agent"],
                allowed_providers=["llm.*"],
                quality_responsibilities=["section_coverage", "duration", "visual_type_safety"],
                escalation_rules=["script_invalid", "duration_conflict"],
            ),
            AgentProfile(
                agent_id="designer",
                role="DesignerAgent",
                capabilities=["design_plan", "template_cover", "asset_plan"],
                accepted_inputs=["script", "storyboard"],
                produced_artifacts=["design_plan", "design_assets", "visual_plan", "visual_assets", "publish_cover"],
                required_context=["creator_identity", "brand_voice", "constraints"],
                allowed_tools=["cover_worker", "asset_planner", "visual_planner", "visual_generation_queue"],
                allowed_providers=["cover.*", "visual.*"],
                quality_responsibilities=["visual_identity", "cover_safety", "asset_traceability"],
                escalation_rules=["asset_missing", "style_violation", "cost_approval_required"],
            ),
            AgentProfile(
                agent_id="voice",
                role="VoiceAgent",
                capabilities=["tts", "subtitle_alignment", "audio_qa"],
                accepted_inputs=["storyboard"],
                produced_artifacts=["audio", "subtitles", "audio_qa"],
                required_context=["constraints", "production_plan_id"],
                allowed_tools=["voice_worker", "subtitle_worker", "audio_qa_worker"],
                allowed_providers=["tts.*", "asr.*", "subtitle.*", "deterministic.*"],
                quality_responsibilities=["real_speech_gate", "subtitle_semantics", "audio_sync"],
                escalation_rules=["provider_failure", "audio_qa_failure"],
            ),
            AgentProfile(
                agent_id="editor",
                role="EditorAgent",
                capabilities=["composition", "render", "video_qa"],
                accepted_inputs=["storyboard", "design_plan", "visual_assets", "audio", "subtitles"],
                produced_artifacts=["composition", "final_video", "video_qa"],
                required_context=["constraints", "production_plan_id"],
                allowed_tools=["video_worker", "video_qa_worker"],
                allowed_providers=["render.*"],
                quality_responsibilities=["decodability", "av_sync", "format_compliance"],
                escalation_rules=["render_failure", "video_qa_failure", "audio_qa_failure"],
            ),
            AgentProfile(
                agent_id="critic",
                role="CriticAgent",
                capabilities=["fact_review", "logic_review", "style_review", "risk_review"],
                accepted_inputs=["research", "script", "storyboard", "final_video", "qa_reports"],
                produced_artifacts=["script_review", "text_qa", "final_review", "revision_request"],
                required_context=["creator_identity", "brand_voice", "constraints"],
                allowed_tools=["text_critic", "style_checker", "qa_readers"],
                allowed_providers=["deterministic.*", "llm.*"],
                quality_responsibilities=["cross_stage_consistency", "risk_escalation"],
                escalation_rules=["review_round_limit", "unresolved_qa_failure"],
            ),
            AgentProfile(
                agent_id="analyst",
                role="AnalystAgent",
                capabilities=["analytics", "memory", "experiments"],
                accepted_inputs=["analytics", "feedback", "content_fingerprint"],
                produced_artifacts=["analytics", "memory", "strategy", "experiment"],
                required_context=["strategy_refs", "experiment_refs", "constraints"],
                allowed_tools=["learning_pipeline", "operations_service"],
                allowed_providers=["analytics.*", "feedback.*", "deterministic.*"],
                quality_responsibilities=["evidence_confidence", "mock_data_boundary"],
                escalation_rules=["insufficient_data", "strategy_approval_required"],
            ),
            AgentProfile(
                agent_id="publisher",
                role="PublisherAgent",
                capabilities=["publish_package", "publish_validation", "publish_job"],
                accepted_inputs=["final_video", "video_qa", "publish_cover", "research", "script"],
                produced_artifacts=["publish_package", "publish_qa", "publish_validation", "publish_job"],
                required_context=["approvals", "constraints", "production_plan_id"],
                allowed_tools=["publish_package_worker", "publishing_service"],
                allowed_providers=["publishing.*", "cover.*", "deterministic.*"],
                quality_responsibilities=["approval_gate", "package_hash", "mock_publish_boundary"],
                escalation_rules=["approval_required", "publish_validation_failure"],
            ),
        ]
