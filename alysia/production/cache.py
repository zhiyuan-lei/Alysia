from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from alysia.schemas import CacheEntry

CACHE_ARTIFACT_TYPES = {
    "research",
    "script",
    "storyboard",
    "scene_tts",
    "subtitle_alignment",
    "render_composition",
}


def _normalized_hash(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class ProductionCache:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.index_path = self.root / "index.json"
        self.root.mkdir(parents=True, exist_ok=True)

    def key(
        self,
        *,
        artifact_type: str,
        normalized_input: Any,
        provider_id: str,
        provider_version: str | None,
        config: Any,
    ) -> str:
        payload = {
            "artifact_type": artifact_type,
            "input": _normalized_hash(normalized_input),
            "provider_id": provider_id,
            "provider_version": provider_version,
            "config": _normalized_hash(config),
        }
        return _normalized_hash(payload)

    def put(
        self,
        *,
        artifact_type: str,
        normalized_input: Any,
        provider_id: str,
        provider_version: str | None,
        config: Any,
        artifact_path: Path,
        ttl_hours: int | None = None,
    ) -> CacheEntry:
        if artifact_type not in CACHE_ARTIFACT_TYPES:
            raise ValueError(f"不支持的 production cache artifact_type：{artifact_type}")
        if artifact_type == "research" and ttl_hours is None:
            raise ValueError("Research cache 必须设置 TTL")
        if not artifact_path.is_file():
            raise FileNotFoundError(f"缓存 artifact 不存在：{artifact_path}")
        cache_key = self.key(
            artifact_type=artifact_type,
            normalized_input=normalized_input,
            provider_id=provider_id,
            provider_version=provider_version,
            config=config,
        )
        entry = CacheEntry(
            cache_key=cache_key,
            artifact_type=artifact_type,
            normalized_input_hash=_normalized_hash(normalized_input),
            provider_id=provider_id,
            provider_version=provider_version,
            config_hash=_normalized_hash(config),
            artifact_path=str(artifact_path.resolve()),
            created_at=datetime.now().astimezone(),
            ttl_hours=ttl_hours,
        )
        index = self._load()
        index[cache_key] = entry.model_dump(mode="json")
        self._save(index)
        return entry

    def get(self, cache_key: str, *, now: datetime | None = None) -> CacheEntry | None:
        raw = self._load().get(cache_key)
        if raw is None:
            return None
        entry = CacheEntry.model_validate(raw)
        if not entry.valid or not Path(entry.artifact_path).is_file():
            return None
        now = now or datetime.now().astimezone()
        if entry.ttl_hours is not None and now > entry.created_at + timedelta(hours=entry.ttl_hours):
            return None
        return entry

    def invalidate(self, cache_key: str) -> None:
        index = self._load()
        if cache_key in index:
            index[cache_key]["valid"] = False
            self._save(index)

    def _load(self) -> dict[str, dict[str, Any]]:
        if not self.index_path.is_file():
            return {}
        return json.loads(self.index_path.read_text(encoding="utf-8"))

    def _save(self, payload: dict[str, dict[str, Any]]) -> None:
        temporary = self.index_path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(self.index_path)
