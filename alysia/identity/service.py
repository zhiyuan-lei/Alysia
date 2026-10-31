from __future__ import annotations

import hashlib
import json
from datetime import datetime

import yaml

from alysia.core.config import AlysiaConfig
from alysia.core.run import RunManager
from alysia.identity.card import IdentityCardGenerator
from alysia.identity.evolution import IdentityEvolutionService
from alysia.identity.prompts import PromptContextBuilder
from alysia.identity.store import IdentityStore
from alysia.identity.style import ContentStyleMemoryBuilder, StyleConsistencyChecker
from alysia.learning.memory import MemoryStore
from alysia.operations import ChannelStore
from alysia.schemas import (
    BrandVoiceProfile,
    CreatorIdentity,
    CreatorProfile,
    IdentityRunCheckReport,
    VisualIdentity,
)
from alysia.schemas import PromptContextArtifact
from alysia.security import SecurityService


class IdentityService:
    def __init__(self, config: AlysiaConfig) -> None:
        self.config = config
        self.store = IdentityStore(config.identity.directory, version_control=config.identity.version_control)
        self.manager = RunManager(config.runtime.runs_dir)
        self.memory = MemoryStore(config.learning.memory_dir)
        self.channels = ChannelStore(config.learning.memory_dir)
        self.security = SecurityService(config)

    def ensure(self) -> CreatorIdentity:
        if not self.config.identity.enabled:
            raise RuntimeError("Identity 系统已在配置中禁用")
        try:
            identity = self.store.load_current()
        except FileNotFoundError:
            identity = self.store.save_initial(self._default_identity())
        self.store.save_card(IdentityCardGenerator().render(identity))
        return identity

    def check_run(self, run_id: str) -> IdentityRunCheckReport:
        identity = self.ensure()
        state = self.manager.load(run_id)
        artifact = self.build_prompt_context(
            state,
            role="check",
            base_task_prompt=f"为主题“{state.topic}”准备创作上下文",
        )
        channel_id = (state.planning_provenance or {}).get("channel_id", self.config.operations.default_channel_id)
        strategies = self.memory.list_strategies(channel_id)
        prompt_path = "identity/prompt_context.check.json"
        errors = [
            f"主题命中身份排除项：{topic}"
            for topic in identity.excluded_topics
            if topic.casefold() in state.topic.casefold()
        ]
        warnings = []
        if all(item.status != "supported" for item in strategies):
            warnings.append("当前频道没有 supported 策略；tentative 项仅作为带状态的审计上下文。")
        stable = {
            "run_id": run_id,
            "identity_version": identity.version,
            "errors": errors,
            "warnings": warnings,
            "prompt_context_digest": artifact.input_digest,
        }
        digest = hashlib.sha256(
            json.dumps(stable, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        report = IdentityRunCheckReport(
            run_id=run_id,
            identity_version=identity.version,
            valid=not errors,
            errors=errors,
            warnings=warnings,
            prompt_context_path=prompt_path,
            input_digest=digest,
        )
        self.manager.write_json(run_id, "identity/identity_check_report.json", report.model_dump(mode="json"))
        return report

    def build_prompt_context(
        self,
        state,
        *,
        role: str,
        base_task_prompt: str,
    ) -> PromptContextArtifact:
        identity = self.ensure()
        channel_id = (state.planning_provenance or {}).get("channel_id", self.config.operations.default_channel_id)
        strategies = self.memory.list_strategies(channel_id)
        experiments = [
            item for item in self.channels.list_experiments(channel_id) if item.status in {"approved", "running"}
        ]
        artifact = PromptContextBuilder().build(
            base_task_prompt=base_task_prompt,
            identity=identity,
            relevant_strategies=strategies,
            experiment=experiments[-1] if experiments else None,
        )
        relative = f"identity/prompt_context.{role}.json"
        self.manager.write_json(state.run_id, relative, artifact.model_dump(mode="json"))
        state.artifacts[f"prompt_context_{role}"] = relative
        self.manager.save(state)
        return artifact

    def style_check(self, run_id: str):
        identity = self.ensure()
        state = self.manager.load(run_id)
        channel_id = (state.planning_provenance or {}).get("channel_id", self.config.operations.default_channel_id)
        style_memory = ContentStyleMemoryBuilder(self.config).refresh(channel_id)
        return StyleConsistencyChecker().check_run(
            self.config,
            run_id,
            identity=identity,
            style_memory=style_memory,
        )

    def evolution(self) -> IdentityEvolutionService:
        self.ensure()
        return IdentityEvolutionService(
            self.store, require_approval=self.config.identity.require_approval,
            security=self.security,
        )

    def _default_identity(self) -> CreatorIdentity:
        profile = self._profile()
        now = datetime.now().astimezone()
        return CreatorIdentity(
            creator_name=profile.creator_name,
            mission_statement="用清晰、可验证的方法解释复杂技术",
            channel_purpose=profile.channel_goal,
            content_philosophy="证据优先，明确区分事实、推断与待验证假设",
            target_audience=profile.target_audience,
            expertise_domains=profile.primary_domains,
            excluded_topics=profile.excluded_domains,
            communication_style=BrandVoiceProfile(
                tone=["理性", "清晰", "克制"],
                sentence_style="短句为主，复杂概念分步解释",
                vocabulary_preferences=["证据", "验证", "边界", "假设"],
                forbidden_phrases=["震惊", "颠覆一切", "百分百", "绝对正确"],
                explanation_depth=self.config.brand_voice.technical_level,
                humor_level=self.config.brand_voice.humor_level,
                technical_level=self.config.brand_voice.technical_level,
                opening_style="问题驱动",
                conclusion_style="总结证据、边界与下一步",
            ),
            visual_identity=VisualIdentity(
                color_theme={"background": "#0A1126", "surface": "#141B37", "accent": "#5BECFF"},
                typography={"heading": "Microsoft YaHei Bold", "body": "Microsoft YaHei"},
                cover_layout=f"left_accent_{self.config.visual_identity.template_version}",
                thumbnail_rules=["标题不超过三行", "保持高对比度", "不使用误导性视觉承诺"],
                scene_preferences=["title", "text", "diagram", "quote", "code", "chart", "image"],
            ),
            narrative_patterns=[
                "problem_solution",
                "myth_breaking",
                "deep_explanation",
                "technology_evolution",
                "experiment_report",
            ],
            values=["准确", "透明", "可验证", "尊重观众"],
            disclosure_policy="明确披露 Alysia 是 AI 视频创作系统，不是真人创作者；不编造个人经历或现实身份。",
            version=1,
            created_at=now,
            updated_at=now,
        )

    def _profile(self) -> CreatorProfile:
        path = self.config.creator.profile_file
        if path.is_file():
            return CreatorProfile.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")) or {})
        return CreatorProfile(
            creator_name=self.config.creator.name,
            channel_goal="用可验证、易理解的中文内容解释 AI 与软件工程",
            primary_domains=["人工智能", "软件工程", "自主智能体"],
            target_audience="对 AI 与工程实践感兴趣的中文观众",
            preferred_formats=["科普解释"],
            originality_requirements="必须提供独立分析",
            source_quality_requirements="关键结论必须可追溯",
        )
