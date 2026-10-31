from __future__ import annotations

import hashlib
import json
from datetime import datetime

from alysia.schemas.visual import SceneVisualPlan, VisualGenerationJob


def build_visual_job(
    run_id: str,
    scene: SceneVisualPlan,
    provider: str,
    workflow_id: str,
    retry_limit: int = 1,
) -> VisualGenerationJob:
    stable = {
        "run_id": run_id, "scene": scene.model_dump(mode="json"),
        "provider": provider, "workflow_id": workflow_id, "workflow_version": "1",
    }
    encoded = json.dumps(stable, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    now = datetime.now().astimezone()
    return VisualGenerationJob(
        job_id=f"vjob_{digest[:16]}", run_id=run_id, scene=scene, provider=provider,
        workflow_id=workflow_id, workflow_version="1", max_retries=retry_limit,
        cache_key=digest, created_at=now, updated_at=now,
    )
