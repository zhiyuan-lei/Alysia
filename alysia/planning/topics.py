from __future__ import annotations

import hashlib

from alysia.planning.novelty import find_duplicates, normalize_topic
from alysia.schemas import CreatorProfile, NextExperimentProposal, TopicCandidate, TrendItem


class TopicGenerator:
    def generate(
        self,
        profile: CreatorProfile,
        trends: list[TrendItem],
        history_topics: list[str],
        *,
        candidate_count: int,
        next_experiment: NextExperimentProposal | None = None,
        experiment_ref: str | None = None,
    ) -> list[TopicCandidate]:
        candidates: list[TopicCandidate] = []
        if next_experiment is not None:
            duplicates = find_duplicates(next_experiment.topic, history_topics)
            candidates.append(
                self._candidate(
                    topic=next_experiment.topic,
                    angle=next_experiment.angle,
                    audience=next_experiment.target_audience,
                    why_now="来自 alpha.6 的待验证内容实验，仍需正式 Research 支撑事实。",
                    source_refs=[experiment_ref] if experiment_ref else [],
                    category=self._category(next_experiment.topic, profile),
                    novelty=1 - (duplicates[0].similarity if duplicates else 0),
                    relevance=0.95,
                    evidence=0.65,
                    effort="medium",
                    experiment_link=experiment_ref or "next_experiment",
                    risks=["实验假设置信度有限，不能当作已证实规律"],
                    requires_current_facts=False,
                )
            )

        for trend in trends:
            if len(candidates) >= candidate_count:
                break
            if any(normalize_topic(item.topic) == normalize_topic(trend.topic) for item in candidates):
                continue
            duplicates = find_duplicates(trend.topic, history_topics)
            relevance = 0.9 if trend.category in profile.primary_domains else 0.65
            evidence = min(1.0, trend.confidence * (0.9 if trend.url else 0.65))
            candidates.append(
                self._candidate(
                    topic=trend.topic,
                    angle=f"从{profile.target_audience}最关心的工程问题切入，用案例解释而非罗列观点",
                    audience=profile.target_audience,
                    why_now=f"趋势快照显示该主题近期值得观察；来源：{trend.source}。",
                    source_refs=[trend.id],
                    category=trend.category,
                    novelty=1 - (duplicates[0].similarity if duplicates else 0),
                    relevance=relevance,
                    evidence=evidence,
                    effort="medium",
                    experiment_link=None,
                    risks=["趋势摘要只解释选题时机，脚本事实必须重新调研"],
                )
            )

        domain_index = 0
        while len(candidates) < candidate_count:
            domain = profile.primary_domains[domain_index % len(profile.primary_domains)]
            domain_index += 1
            topic = f"{domain}系统怎样用可恢复检查避免一次失败毁掉整个任务"
            if any(normalize_topic(item.topic) == normalize_topic(topic) for item in candidates):
                topic = f"{domain}工作流的第 {domain_index} 个可靠性检查点"
            duplicates = find_duplicates(topic, history_topics)
            candidates.append(
                self._candidate(
                    topic=topic,
                    angle="以一个最小失败案例展示检测、恢复与复盘",
                    audience=profile.target_audience,
                    why_now="常青候选，用于补足排期；不声称当前热度。",
                    source_refs=[],
                    category=domain,
                    novelty=1 - (duplicates[0].similarity if duplicates else 0),
                    relevance=0.8,
                    evidence=0.35,
                    effort="medium",
                    experiment_link=None,
                    risks=["缺少趋势来源，不能使用时效性标题"],
                    requires_current_facts=False,
                )
            )
        return candidates[:candidate_count]

    @staticmethod
    def _category(topic: str, profile: CreatorProfile) -> str:
        for domain in profile.primary_domains:
            if domain.casefold() in topic.casefold():
                return domain
        return profile.primary_domains[0]

    @staticmethod
    def _candidate(
        *,
        topic: str,
        angle: str,
        audience: str,
        why_now: str,
        source_refs: list[str],
        category: str,
        novelty: float,
        relevance: float,
        evidence: float,
        effort: str,
        experiment_link: str | None,
        risks: list[str],
        requires_current_facts: bool = True,
    ) -> TopicCandidate:
        digest = hashlib.sha256(f"{topic}|{angle}".encode("utf-8")).hexdigest()[:12]
        return TopicCandidate(
            id=f"topic_{digest}",
            topic=topic,
            angle=angle,
            target_audience=audience,
            why_now=why_now,
            source_refs=source_refs,
            category=category,
            novelty_score=max(0, min(1, novelty)),
            relevance_score=relevance,
            evidence_score=evidence,
            expected_effort=effort,
            experiment_link=experiment_link,
            risks=risks,
            requires_current_facts=requires_current_facts,
        )
