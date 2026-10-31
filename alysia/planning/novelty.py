from __future__ import annotations

import re

from alysia.schemas import DuplicateCandidate


def normalize_topic(value: str) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", value.casefold())


def topic_tokens(value: str) -> set[str]:
    normalized = normalize_topic(value)
    ascii_words = set(re.findall(r"[a-z0-9]+", value.casefold()))
    chinese = "".join(re.findall(r"[\u4e00-\u9fff]", normalized))
    bigrams = {chinese[index : index + 2] for index in range(max(0, len(chinese) - 1))}
    return ascii_words | bigrams


def topic_similarity(left: str, right: str) -> float:
    left_normalized = normalize_topic(left)
    right_normalized = normalize_topic(right)
    if not left_normalized or not right_normalized:
        return 0.0
    if left_normalized == right_normalized:
        return 1.0
    left_tokens = topic_tokens(left)
    right_tokens = topic_tokens(right)
    union = left_tokens | right_tokens
    return len(left_tokens & right_tokens) / len(union) if union else 0.0


def find_duplicates(topic: str, history_topics: list[str], *, threshold: float = 0.45) -> list[DuplicateCandidate]:
    matches = [
        DuplicateCandidate(candidate_topic=topic, existing_topic=existing, similarity=topic_similarity(topic, existing))
        for existing in history_topics
    ]
    return sorted(
        (match for match in matches if match.similarity >= threshold),
        key=lambda match: match.similarity,
        reverse=True,
    )
