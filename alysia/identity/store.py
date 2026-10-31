from __future__ import annotations

import json
from pathlib import Path

import yaml

from alysia.schemas import CreatorIdentity, IdentityChangeProposal


class IdentityStore:
    """保存当前创作者身份、不可覆盖的历史版本和待审批提案。"""

    def __init__(self, root: Path, *, version_control: bool = True) -> None:
        self.root = root.resolve()
        self.history_dir = self.root / "history"
        self.proposals_dir = self.root / "proposals"
        self.current_path = self.root / "creator_identity.yaml"
        self.card_path = self.root / "identity_card.md"
        self.version_control = version_control

    def save_initial(self, identity: CreatorIdentity) -> CreatorIdentity:
        if self.current_path.is_file():
            return self.load_current()
        initial = identity.model_copy(update={"version": 1})
        self._save_identity(initial)
        return initial

    def save_new_version(self, identity: CreatorIdentity) -> CreatorIdentity:
        current = self.load_current()
        changed = identity.model_copy(
            update={
                "version": current.version + 1,
                "created_at": current.created_at,
            }
        )
        self._save_identity(changed)
        return changed

    def load_current(self) -> CreatorIdentity:
        if not self.current_path.is_file():
            raise FileNotFoundError(f"Creator Identity 不存在：{self.current_path}")
        return CreatorIdentity.model_validate(yaml.safe_load(self.current_path.read_text(encoding="utf-8")) or {})

    def list_history(self) -> list[CreatorIdentity]:
        if not self.history_dir.is_dir():
            return []
        return [
            CreatorIdentity.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")) or {})
            for path in sorted(self.history_dir.glob("creator_identity.v*.yaml"))
        ]

    def save_card(self, content: str) -> Path:
        self.root.mkdir(parents=True, exist_ok=True)
        self._atomic_write(self.card_path, content.rstrip() + "\n")
        return self.card_path

    def save_proposal(self, proposal: IdentityChangeProposal) -> Path:
        path = self.proposals_dir / f"{proposal.id}.json"
        encoded = json.dumps(proposal.model_dump(mode="json"), ensure_ascii=False, indent=2, default=str) + "\n"
        path.parent.mkdir(parents=True, exist_ok=True)
        self._atomic_write(path, encoded)
        return path

    def load_proposal(self, proposal_id: str) -> IdentityChangeProposal:
        if not proposal_id or Path(proposal_id).name != proposal_id:
            raise ValueError("proposal_id 格式无效")
        path = self.proposals_dir / f"{proposal_id}.json"
        if not path.is_file():
            raise FileNotFoundError(f"找不到 Identity proposal：{proposal_id}")
        return IdentityChangeProposal.model_validate_json(path.read_text(encoding="utf-8"))

    def _save_identity(self, identity: CreatorIdentity) -> None:
        payload = yaml.safe_dump(
            identity.model_dump(mode="json"),
            allow_unicode=True,
            sort_keys=False,
        )
        self.root.mkdir(parents=True, exist_ok=True)
        self._atomic_write(self.current_path, payload)
        if self.version_control:
            history = self.history_dir / f"creator_identity.v{identity.version:04d}.yaml"
            if history.exists():
                existing = CreatorIdentity.model_validate(yaml.safe_load(history.read_text(encoding="utf-8")) or {})
                if existing != identity:
                    raise FileExistsError(f"身份历史版本已存在且内容不同：v{identity.version}")
            else:
                history.parent.mkdir(parents=True, exist_ok=True)
                self._atomic_write(history, payload)

    @staticmethod
    def _atomic_write(path: Path, content: str) -> None:
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(content, encoding="utf-8", newline="\n")
        temporary.replace(path)
