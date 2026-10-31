from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from alysia.core.io import atomic_write_json

from alysia.knowledge.models import (
    EvidenceSource,
    KnowledgeClaim,
    KnowledgeConflict,
    KnowledgeGap,
    ResearchTask,
    ReverificationTask,
    knowledge_now,
    stable_id,
)


class KnowledgeStore:
    """透明 JSON 知识库；保存历史版本，不依赖向量数据库。"""

    _DIRS = ("claims", "sources", "topics", "conflicts", "snapshots", "tasks", "gaps")

    def __init__(self, root: Path = Path("knowledge")) -> None:
        self.root = root.resolve()
        for name in self._DIRS:
            (self.root / name).mkdir(parents=True, exist_ok=True)
        if not self.index_path.is_file():
            self._write(self.index_path, self._empty_index())

    @property
    def index_path(self) -> Path:
        return self.root / "index.json"

    @staticmethod
    def _empty_index() -> dict[str, Any]:
        return {"version": 1, "sources": [], "claims": [], "conflicts": [], "topics": {}, "updated_at": None}

    @staticmethod
    def _safe_id(identifier: str) -> str:
        if not identifier or Path(identifier).name != identifier:
            raise ValueError("knowledge identifier 格式无效")
        return identifier

    def add_source(self, source: EvidenceSource) -> EvidenceSource:
        path = self.root / "sources" / f"{self._safe_id(source.source_id)}.json"
        if path.is_file():
            existing = EvidenceSource.model_validate(self._read(path))
            if existing.model_dump(mode="json") != source.model_dump(mode="json"):
                self._snapshot("source", source.source_id, existing.model_dump(mode="json"))
        self._write(path, source.model_dump(mode="json"))
        self._index_add("sources", source.source_id)
        return source

    def get_source(self, source_id: str) -> EvidenceSource:
        return EvidenceSource.model_validate(self._read(self.root / "sources" / f"{self._safe_id(source_id)}.json"))

    def list_sources(self) -> list[EvidenceSource]:
        return [EvidenceSource.model_validate(self._read(path)) for path in sorted((self.root / "sources").glob("*.json"))]

    def add_claim(self, claim: KnowledgeClaim) -> KnowledgeClaim:
        path = self.root / "claims" / f"{self._safe_id(claim.claim_id)}.json"
        if path.is_file():
            existing = KnowledgeClaim.model_validate(self._read(path))
            if existing.model_dump(mode="json") != claim.model_dump(mode="json"):
                self._snapshot("claim", claim.claim_id, existing.model_dump(mode="json"))
        self._write(path, claim.model_dump(mode="json"))
        index = self._index()
        if claim.claim_id not in index["claims"]:
            index["claims"].append(claim.claim_id)
        topic_ids = index["topics"].setdefault(claim.topic, [])
        if claim.claim_id not in topic_ids:
            topic_ids.append(claim.claim_id)
        index["updated_at"] = knowledge_now().isoformat()
        self._write(self.index_path, index)
        self._write(self.root / "topics" / f"{self._topic_slug(claim.topic)}.json", {"topic": claim.topic, "claim_ids": topic_ids})
        return claim

    def get_claim(self, claim_id: str) -> KnowledgeClaim:
        return KnowledgeClaim.model_validate(self._read(self.root / "claims" / f"{self._safe_id(claim_id)}.json"))

    def list_claims(self, topic: str | None = None) -> list[KnowledgeClaim]:
        claims = [KnowledgeClaim.model_validate(self._read(path)) for path in sorted((self.root / "claims").glob("*.json"))]
        return [item for item in claims if topic is None or item.topic == topic]

    def active_claims(self, topic: str | None = None) -> list[KnowledgeClaim]:
        inactive = {"retracted", "superseded"}
        return [item for item in self.list_claims(topic) if item.status not in inactive]

    def supersede(self, old_claim_id: str, new_claim: KnowledgeClaim) -> tuple[KnowledgeClaim, KnowledgeClaim]:
        old = self.get_claim(old_claim_id)
        if new_claim.claim_id == old.claim_id:
            raise ValueError("新旧 claim_id 必须不同")
        old.status = "superseded"
        old.updated_at = knowledge_now()
        new_claim.supersedes_claim_id = old.claim_id
        new_claim.version = max(new_claim.version, old.version + 1)
        self.add_claim(old)
        self.add_claim(new_claim)
        return old, new_claim

    def add_conflict(self, conflict: KnowledgeConflict) -> KnowledgeConflict:
        path = self.root / "conflicts" / f"{self._safe_id(conflict.conflict_id)}.json"
        self._write(path, conflict.model_dump(mode="json"))
        self._index_add("conflicts", conflict.conflict_id)
        return conflict

    def list_conflicts(self, *, open_only: bool = False) -> list[KnowledgeConflict]:
        items = [KnowledgeConflict.model_validate(self._read(path)) for path in sorted((self.root / "conflicts").glob("*.json"))]
        return [item for item in items if not open_only or item.resolution_status in {"open", "needs_primary_source"}]

    def add_task(self, task: ReverificationTask | ResearchTask) -> ReverificationTask | ResearchTask:
        path = self.root / "tasks" / f"{self._safe_id(task.task_id)}.json"
        self._write(path, task.model_dump(mode="json"))
        return task

    def list_tasks(self) -> list[ReverificationTask | ResearchTask]:
        output: list[ReverificationTask | ResearchTask] = []
        for path in sorted((self.root / "tasks").glob("*.json")):
            payload = self._read(path)
            model = ReverificationTask if "claim_id" in payload else ResearchTask
            output.append(model.model_validate(payload))
        return output

    def add_gap(self, gap: KnowledgeGap) -> KnowledgeGap:
        self._write(self.root / "gaps" / f"{self._safe_id(gap.gap_id)}.json", gap.model_dump(mode="json"))
        return gap

    def list_gaps(self) -> list[KnowledgeGap]:
        return [KnowledgeGap.model_validate(self._read(path)) for path in sorted((self.root / "gaps").glob("*.json"))]

    def snapshot_run(self, run_dir: Path, claims: list[KnowledgeClaim]) -> dict[str, str]:
        knowledge_dir = run_dir / "knowledge"
        knowledge_dir.mkdir(parents=True, exist_ok=True)
        source_ids = sorted({ref for claim in claims for ref in claim.evidence_refs})
        sources = [self.get_source(source_id) for source_id in source_ids]
        claims_path = knowledge_dir / "claims_used.json"
        sources_path = knowledge_dir / "source_snapshot.json"
        self._write(claims_path, [item.model_dump(mode="json") for item in claims])
        self._write(sources_path, [item.model_dump(mode="json") for item in sources])
        return {"claims_used": claims_path.as_posix(), "source_snapshot": sources_path.as_posix()}

    def status(self) -> dict[str, Any]:
        claims = self.list_claims()
        conflicts = self.list_conflicts(open_only=True)
        return {
            "root": str(self.root),
            "sources": len(self.list_sources()),
            "claims": len(claims),
            "verified": sum(item.status == "verified" for item in claims),
            "provisional": sum(item.status == "provisional" for item in claims),
            "stale": sum(item.status == "stale" for item in claims),
            "conflicted": sum(item.status == "conflicted" for item in claims),
            "open_conflicts": len(conflicts),
            "tasks": len(self.list_tasks()),
            "gaps": len(self.list_gaps()),
        }

    def _index_add(self, key: str, value: str) -> None:
        index = self._index()
        if value not in index[key]:
            index[key].append(value)
        index["updated_at"] = knowledge_now().isoformat()
        self._write(self.index_path, index)

    def _index(self) -> dict[str, Any]:
        return self._read(self.index_path) if self.index_path.is_file() else self._empty_index()

    def _snapshot(self, kind: str, identifier: str, payload: Any) -> None:
        stamp = knowledge_now().strftime("%Y%m%dT%H%M%S%f")
        self._write(self.root / "snapshots" / f"{kind}_{identifier}_{stamp}.json", payload)

    @staticmethod
    def _topic_slug(topic: str) -> str:
        return stable_id("topic", topic)

    @staticmethod
    def _read(path: Path) -> Any:
        if not path.is_file():
            raise FileNotFoundError(path)
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _write(path: Path, payload: Any) -> None:
        atomic_write_json(path, payload, backup_count=2 if path.name == "index.json" else 0)
