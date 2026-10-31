from __future__ import annotations

from alysia.studio.protocol import ArtifactRef, RevisionRequest, stable_studio_id
from alysia.studio.registry import AgentRegistry
from alysia.studio.trace import StudioTraceStore


ARTIFACT_OWNERS: dict[str, str] = {
    "research": "researcher",
    "script": "writer",
    "metadata": "writer",
    "storyboard": "storyboard_director",
    "design_plan": "designer",
    "design_assets": "designer",
    "publish_cover": "designer",
    "audio": "voice",
    "subtitles": "voice",
    "audio_qa": "voice",
    "composition": "editor",
    "final_video": "editor",
    "video_qa": "editor",
    "script_review": "critic",
    "text_qa": "critic",
    "final_review": "critic",
    "revision_request": "critic",
    "analytics": "analyst",
    "memory": "analyst",
    "strategy": "analyst",
    "experiment": "analyst",
    "publish_package": "publisher",
    "publish_qa": "publisher",
    "publish_validation": "publisher",
    "publish_job": "publisher",
}


class ArtifactCatalog:
    def __init__(self, store: StudioTraceStore, registry: AgentRegistry) -> None:
        self.store = store
        self.registry = registry

    def latest(self, kind: str) -> ArtifactRef | None:
        matches = [item for item in self.store.artifacts() if item.kind == kind and item.active]
        return max(matches, key=lambda item: item.version) if matches else None

    def available_kinds(self) -> set[str]:
        return {item.kind for item in self.store.artifacts() if item.active}

    def invalidate(self, kinds: list[str]) -> None:
        for item in self.store.artifacts():
            if item.kind in kinds and item.active:
                item.active = False
                self.store.save_artifact(item)

    def register(
        self,
        *,
        run_id: str,
        agent_id: str,
        kind: str,
        path: str,
        source_run_artifact: str | None = None,
        summary: str = "",
        testing: bool = False,
        revision_request: RevisionRequest | None = None,
    ) -> ArtifactRef:
        expected_owner = ARTIFACT_OWNERS.get(kind)
        if expected_owner != agent_id:
            raise PermissionError(f"{kind} 的 owner 必须是 {expected_owner}，不能由 {agent_id} 直接写入")
        self.registry.assert_can_produce(agent_id, kind)
        current = self.latest(kind)
        if current is not None and kind == "revision_request":
            current = None
        if current is not None:
            if revision_request is None:
                if current.path == path:
                    return current
                raise PermissionError(f"修改已有 {kind} 必须提供 revision request")
            if revision_request.owner_agent_id != agent_id or revision_request.artifact_kind != kind:
                raise PermissionError("revision request 与 artifact owner/kind 不一致")
            if revision_request.status != "accepted":
                raise PermissionError("revision request 尚未 accepted")
        previous = self.latest(kind)
        all_previous = [item for item in self.store.artifacts() if item.kind == kind]
        version = 1 if not all_previous else max(item.version for item in all_previous) + 1
        if current is not None and revision_request is not None:
            current.active = False
            self.store.save_artifact(current)
        artifact = ArtifactRef(
            artifact_id=stable_studio_id("artifact", run_id, kind, str(version), path),
            kind=kind,
            path=path,
            owner_agent_id=agent_id,
            version=version,
            source_run_artifact=source_run_artifact,
            summary=summary,
            testing=testing,
        )
        self.store.save_artifact(artifact)
        if revision_request is not None:
            revision_request.status = "completed"
            revision_request.completed_artifact_id = artifact.artifact_id
            self.store.save_revision(revision_request)
        return artifact

    def request_revision(
        self,
        *,
        run_id: str,
        artifact_kind: str,
        requested_by: str,
        reason: str,
        acceptance_criteria: list[str],
    ) -> RevisionRequest:
        current = self.latest(artifact_kind)
        owner = ARTIFACT_OWNERS.get(artifact_kind)
        if owner is None:
            raise KeyError(f"未定义 artifact owner：{artifact_kind}")
        request = RevisionRequest(
            request_id=stable_studio_id(
                "revision", run_id, artifact_kind, str((current.version if current else 0) + 1), reason
            ),
            artifact_kind=artifact_kind,
            artifact_id=current.artifact_id if current else None,
            requested_by=requested_by,
            owner_agent_id=owner,
            reason=reason,
            acceptance_criteria=acceptance_criteria,
        )
        self.store.save_revision(request)
        return request

    def accept_revision(self, request_id: str, *, agent_id: str) -> RevisionRequest:
        request = next((item for item in self.store.revisions() if item.request_id == request_id), None)
        if request is None:
            raise FileNotFoundError(f"找不到 revision request：{request_id}")
        if request.owner_agent_id != agent_id:
            raise PermissionError("只有 artifact owner 可以接受 revision request")
        request.status = "accepted"
        self.store.save_revision(request)
        return request
