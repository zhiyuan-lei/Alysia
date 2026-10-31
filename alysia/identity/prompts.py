from __future__ import annotations

import hashlib
import json
from typing import Any

from alysia.schemas import CreatorIdentity, PromptContextArtifact


class PromptContextBuilder:
    """统一组装身份、品牌、策略和实验上下文，不改写基础任务 Prompt。"""

    def build(
        self,
        *,
        base_task_prompt: str,
        identity: CreatorIdentity,
        relevant_strategies: list[Any] | None = None,
        experiment: Any | None = None,
    ) -> PromptContextArtifact:
        strategies = [self._dump(item) for item in (relevant_strategies or [])]
        experiment_data = self._dump(experiment) if experiment is not None else None
        identity_data = identity.model_dump(mode="json")
        brand_voice = identity.communication_style.model_dump(mode="json")
        stable_input = {
            "base_task_prompt": base_task_prompt,
            "creator_identity": identity_data,
            "brand_voice": brand_voice,
            "relevant_strategies": strategies,
            "content_experiment": experiment_data,
        }
        digest = hashlib.sha256(
            json.dumps(stable_input, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
        rendered = self._render(base_task_prompt, identity, strategies, experiment_data)
        return PromptContextArtifact(
            identity_version=identity.version,
            base_task_prompt=base_task_prompt,
            creator_identity=identity_data,
            brand_voice=brand_voice,
            relevant_strategies=strategies,
            content_experiment=experiment_data,
            rendered_context=rendered,
            input_digest=digest,
        )

    @staticmethod
    def _dump(value: Any) -> dict[str, Any]:
        if hasattr(value, "model_dump"):
            return value.model_dump(mode="json")
        if not isinstance(value, dict):
            raise TypeError("Prompt context 项必须是 dict 或 Pydantic model")
        return dict(value)

    @staticmethod
    def _render(
        base_task_prompt: str,
        identity: CreatorIdentity,
        strategies: list[dict[str, Any]],
        experiment: dict[str, Any] | None,
    ) -> str:
        voice = identity.communication_style
        strategy_lines = [
            f"- [{item.get('status', 'unknown')}] {item.get('rule') or item.get('proposed_change') or item}"
            for item in strategies
        ] or ["- 无相关策略；不要补造。"]
        experiment_line = (
            json.dumps(experiment, ensure_ascii=False, sort_keys=True)
            if experiment is not None
            else "无已批准内容实验。"
        )
        return "\n".join(
            [
                "## Base Task Prompt",
                base_task_prompt,
                "",
                "## Creator Identity",
                f"名称：{identity.creator_name}（AI 视频创作系统，不是真人）",
                f"使命：{identity.mission_statement}",
                f"频道用途：{identity.channel_purpose}",
                f"目标观众：{identity.target_audience}",
                f"专业领域：{'、'.join(identity.expertise_domains)}",
                f"排除主题：{'、'.join(identity.excluded_topics) or '无'}",
                f"身份披露：{identity.disclosure_policy}",
                "",
                "## Brand Voice",
                f"语气：{'、'.join(voice.tone)}",
                f"句式：{voice.sentence_style}",
                f"技术深度：{voice.technical_level}",
                f"解释深度：{voice.explanation_depth}",
                f"幽默程度：{voice.humor_level}",
                f"禁用表达：{'、'.join(voice.forbidden_phrases) or '无'}",
                "",
                "## Relevant Strategy",
                *strategy_lines,
                "策略只作为带状态的证据建议；tentative 不得当成永久规则。",
                "",
                "## Content Experiment",
                experiment_line,
                "未获人工批准的实验不得改变内容生产或频道方向。",
            ]
        )
