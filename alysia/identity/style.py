from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from typing import Any

from alysia.core.config import AlysiaConfig
from alysia.core.run import RunManager
from alysia.operations import ChannelStore, OperationsService
from alysia.schemas import (
    ContentStyleMemory,
    ContentStyleRule,
    CreatorIdentity,
    Script,
    Storyboard,
    StyleConsistencyReport,
    StyleEvidence,
)


class ContentStyleMemoryBuilder:
    """仅从 alpha9 的非测试成功案例提取风格观察。"""

    def __init__(self, config: AlysiaConfig) -> None:
        self.config = config
        self.manager = RunManager(config.runtime.runs_dir)
        self.store = ChannelStore(config.learning.memory_dir)
        self.operations = OperationsService(config)

    def refresh(self, channel_id: str) -> ContentStyleMemory:
        dashboard = self.operations.refresh(channel_id)
        experiments = self.store.list_experiments(channel_id)
        assigned = {
            assignment.run_id: experiment.id
            for experiment in experiments
            if experiment.status == "completed"
            for assignment in experiment.assignments
            if assignment.source not in {"mock", "testing"}
        }
        published_sources = {item.run_id: item.source for item in dashboard.channel_state.published_topics}
        observations: list[StyleEvidence] = []
        for case in dashboard.channel_state.success_cases:
            source = published_sources.get(case.run_id)
            if source is None or source in {"mock", "testing"}:
                continue
            try:
                state = self.manager.load(case.run_id)
                script = Script.model_validate(self.manager.read_json(case.run_id, state.artifacts["script"]))
                storyboard = Storyboard.model_validate(self.manager.read_json(case.run_id, state.artifacts["storyboard"]))
                metadata = self._optional_json(case.run_id, state.artifacts.get("publish_metadata"))
                fingerprint = self._optional_json(case.run_id, state.artifacts.get("content_fingerprint"))
            except (FileNotFoundError, KeyError, ValueError):
                continue
            observations.append(
                StyleEvidence(
                    run_id=case.run_id,
                    experiment_id=assigned.get(case.run_id),
                    metrics=case.metrics,
                    title_pattern=self._title_pattern(metadata, script.title),
                    opening_pattern=self._opening_pattern(script.hook),
                    video_structure=[section.purpose for section in script.sections],
                    visual_style=list(dict.fromkeys(scene.visual_type.value for scene in storyboard.scenes)),
                    subtitle_style=self._subtitle_style(state.config_snapshot),
                    narrative_pacing=self._narrative_pacing(fingerprint),
                    source=source,
                )
            )
        stable = [item.model_dump(mode="json") for item in sorted(observations, key=lambda item: item.run_id)]
        digest = hashlib.sha256(
            json.dumps(stable, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
        existing = self.store.load_style_memory(channel_id)
        if existing and existing.source_digest == digest:
            return existing
        memory = ContentStyleMemory(
            channel_id=channel_id,
            observations=observations,
            rules=self._derive_rules(observations),
            source_digest=digest,
            updated_at=datetime.now().astimezone(),
        )
        self.store.save_style_memory(memory)
        return memory

    def _optional_json(self, run_id: str, relative: str | None) -> dict[str, Any]:
        return self.manager.read_json(run_id, relative) if relative else {}

    @staticmethod
    def _title_pattern(metadata: dict[str, Any], fallback: str) -> str:
        primary = metadata.get("primary_title") or fallback
        for candidate in metadata.get("title_candidates", []):
            if candidate.get("title") == primary:
                return str(candidate.get("style") or "未分类")
        if "？" in primary or "?" in primary:
            return "问题型"
        if re.search(r"\d", primary):
            return "数字型"
        return "陈述型"

    @staticmethod
    def _opening_pattern(hook: str) -> str:
        if "？" in hook or "?" in hook:
            return "问题驱动"
        if re.search(r"\d", hook):
            return "数据开场"
        return "直接陈述"

    @staticmethod
    def _subtitle_style(snapshot: dict[str, Any]) -> str:
        subtitle = snapshot.get("subtitle", {})
        position = subtitle.get("position", "unknown")
        lines = subtitle.get("max_chars_per_line", "unknown")
        return f"position={position};max_chars_per_line={lines}"

    @staticmethod
    def _narrative_pacing(fingerprint: dict[str, Any]) -> str:
        value = fingerprint.get("narration_speed_chars_per_sec")
        if value is None:
            return "unknown"
        speed = float(value)
        if speed < 3:
            return "slow"
        if speed > 5:
            return "fast"
        return "medium"

    @staticmethod
    def _derive_rules(observations: list[StyleEvidence]) -> list[ContentStyleRule]:
        dimensions: dict[str, list[tuple[str, StyleEvidence]]] = defaultdict(list)
        for item in observations:
            dimensions["title_pattern"].append((item.title_pattern, item))
            dimensions["opening_pattern"].append((item.opening_pattern, item))
            dimensions["video_structure"].append((" → ".join(item.video_structure), item))
            dimensions["visual_style"].append((" + ".join(item.visual_style), item))
            dimensions["subtitle_style"].append((item.subtitle_style, item))
            dimensions["narrative_pacing"].append((item.narrative_pacing, item))
        rules: list[ContentStyleRule] = []
        for dimension, values in sorted(dimensions.items()):
            counts = Counter(value for value, _ in values if value and value != "unknown")
            for value, count in sorted(counts.items()):
                evidence = [item for candidate, item in values if candidate == value]
                run_ids = sorted({item.run_id for item in evidence})
                experiment_ids = sorted({item.experiment_id for item in evidence if item.experiment_id})
                rules.append(
                    ContentStyleRule(
                        dimension=dimension,
                        value=value,
                        evidence_run_ids=run_ids,
                        experiment_ids=experiment_ids,
                        metrics={item.run_id: item.metrics for item in evidence},
                        confidence=min(0.85, 0.25 + count * 0.2),
                        status="supported" if len(run_ids) >= 2 and experiment_ids else "tentative",
                    )
                )
        return rules


class StyleConsistencyChecker:
    def check_run(
        self,
        config: AlysiaConfig,
        run_id: str,
        *,
        identity: CreatorIdentity,
        style_memory: ContentStyleMemory | None = None,
    ) -> StyleConsistencyReport:
        manager = RunManager(config.runtime.runs_dir)
        state = manager.load(run_id)
        script = Script.model_validate(manager.read_json(run_id, state.artifacts["script"]))
        storyboard = Storyboard.model_validate(manager.read_json(run_id, state.artifacts["storyboard"]))
        metadata_relative = state.artifacts.get("publish_metadata")
        metadata = manager.read_json(run_id, metadata_relative) if metadata_relative else {}
        title = str(metadata.get("primary_title") or script.title)
        report = self.check(
            run_id=run_id,
            script=script,
            storyboard=storyboard,
            title=title,
            cover_metadata=metadata,
            identity=identity,
            style_memory=style_memory,
        )
        manager.write_json(run_id, "qa/style_consistency_report.json", report.model_dump(mode="json"))
        return report

    def check(
        self,
        *,
        run_id: str,
        script: Script,
        storyboard: Storyboard,
        title: str,
        cover_metadata: dict[str, Any],
        identity: CreatorIdentity,
        style_memory: ContentStyleMemory | None = None,
    ) -> StyleConsistencyReport:
        voice = identity.communication_style
        text = " ".join(
            [title, script.hook, script.thesis, script.conclusion]
            + [section.narration for section in script.sections]
            + [scene.screen_text for scene in storyboard.scenes]
        )
        normalized = _normalize(text)
        matched: list[str] = []
        violations: list[str] = []
        suggestions: list[str] = []
        checks = 0

        checks += 1
        excluded = [item for item in identity.excluded_topics if _normalize(item) in normalized]
        if excluded:
            violations.append(f"内容命中身份排除主题：{'、'.join(excluded)}")
        else:
            matched.append("未命中身份配置中的排除主题")

        checks += 1
        if _domain_matches(text, identity.expertise_domains):
            matched.append("主题与频道专业领域相符")
        else:
            violations.append("主题与已配置的频道专业领域缺少明确关联")

        checks += 1
        audience_tokens = _meaningful_tokens(identity.target_audience)
        if any(token in _normalize(script.target_audience) for token in audience_tokens):
            matched.append("脚本目标观众与 Creator Identity 一致")
        else:
            suggestions.append("核对脚本目标观众与频道身份是否一致")

        checks += 1
        forbidden = [phrase for phrase in voice.forbidden_phrases if phrase.casefold() in text.casefold()]
        if forbidden:
            violations.append(f"使用 Brand Voice 禁用表达：{'、'.join(forbidden)}")
        else:
            matched.append("未使用 Brand Voice 禁用表达")

        checks += 1
        technical_markers = sum(text.casefold().count(marker) for marker in ("ai", "agent", "agi", "模型", "系统", "验证"))
        required = {"low": 0, "medium": 2, "high": 5}[voice.technical_level]
        if technical_markers >= required:
            matched.append(f"技术表达密度符合 {voice.technical_level} 级别")
        else:
            suggestions.append(f"当前技术表达可能低于 {voice.technical_level} 级别")

        checks += 1
        if "问题" in voice.opening_style and not ("？" in script.hook or "?" in script.hook):
            suggestions.append("Brand Voice 偏好问题驱动开场，当前 Hook 未使用问题句")
        else:
            matched.append("开场形式符合 Brand Voice")

        checks += 1
        if script.conclusion.strip():
            matched.append("包含与 Brand Voice 兼容的明确结论")
        else:
            violations.append("缺少结论")

        checks += 1
        preferred = set(identity.visual_identity.scene_preferences)
        used = {scene.visual_type.value for scene in storyboard.scenes}
        outside = sorted(used - preferred) if preferred else []
        if outside:
            suggestions.append(f"分镜包含非首选视觉类型：{'、'.join(outside)}")
        else:
            matched.append("分镜视觉类型符合 Visual Identity 偏好")

        checks += 1
        if cover_metadata.get("primary_title"):
            matched.append("封面/投稿 metadata 含可审计主标题")
        else:
            suggestions.append("当前 run 尚无完整封面 metadata，视觉规范检查置信度降低")

        if style_memory:
            supported = [item for item in style_memory.rules if item.status == "supported"]
            if supported:
                suggestions.append("存在跨视频 supported 风格规则；建议由人工结合报告逐项复核，不自动应用。")
            elif style_memory.observations:
                suggestions.append("当前风格记忆只有 tentative 观察，不能作为永久品牌规则。")
            else:
                suggestions.append("暂无非测试成功案例；本次只检查静态身份与 Brand Voice 配置。")

        total_findings = len(matched) + len(violations) + len(suggestions)
        score = round(max(0.0, 1.0 - (len(violations) * 1.0 + len(suggestions) * 0.25) / checks), 3)
        confidence = round(min(0.95, 0.45 + min(checks, total_findings) * 0.05), 3)
        stable_input = {
            "script": script.model_dump(mode="json"),
            "storyboard": storyboard.model_dump(mode="json"),
            "title": title,
            "cover_metadata": cover_metadata,
            "identity": identity.model_dump(mode="json"),
            "style_memory_digest": style_memory.source_digest if style_memory else None,
        }
        digest = hashlib.sha256(
            json.dumps(stable_input, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
        return StyleConsistencyReport(
            run_id=run_id,
            identity_version=identity.version,
            matched_elements=matched,
            violations=violations,
            suggestions=suggestions,
            score=score,
            confidence=confidence,
            input_digest=digest,
        )


def _normalize(value: str) -> str:
    return re.sub(r"\W+", "", value, flags=re.UNICODE).casefold()


def _meaningful_tokens(value: str) -> list[str]:
    normalized = _normalize(value)
    known = [item for item in ("人工智能", "软件工程", "技术", "中文", "观众", "ai") if item in normalized]
    return known or [normalized]


def _domain_matches(text: str, domains: list[str]) -> bool:
    normalized = _normalize(text)
    aliases = {"人工智能": ["人工智能", "ai", "agent", "agi"], "自主智能体": ["智能体", "agent"]}
    for domain in domains:
        candidates = aliases.get(domain, [domain])
        if any(_normalize(candidate) in normalized for candidate in candidates):
            return True
    return False
