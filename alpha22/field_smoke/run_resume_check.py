from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime
from pathlib import Path

import httpx

from alysia.core.io import atomic_write_json
from alysia.creator import (
    ComfyUIProductionAdapter,
    ProductionArtifactRegistry,
    ProductionOrchestrator,
    ProductionPlan,
    ProductionPlanStore,
    ProductionStatus,
    ProductionTask,
    ProductionTaskStatus,
    ProductionTaskType,
    ResourceClass,
)


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "comfyui" / "TEST_ONLY_comfyui_stage_a.png"


def relevant_history_count() -> int:
    payload = httpx.get("http://127.0.0.1:8188/history", timeout=5).json()
    return sum(
        1
        for item in payload.values()
        if "TEST_ONLY_comfyui_stage_a" in json.dumps(item.get("prompt", []), ensure_ascii=False)
    )


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    plans = ProductionPlanStore(ROOT / "resume" / "plans")
    artifacts = ProductionArtifactRegistry(ROOT / "resume" / "artifacts", probe_media=False)
    artifact_path = artifacts.task_dir("creator_alpha22_step8", "comfyui") / SOURCE.name
    shutil.copy2(SOURCE, artifact_path)
    manifest = artifacts.register(
        job_id="creator_alpha22_step8",
        task_id="comfyui",
        artifact_type="IMAGE",
        path=artifact_path,
        metadata={"test_only": True, "provider": "REAL_COMFYUI"},
    )
    plan = ProductionPlan(
        production_id="production_2222222222222222",
        job_id="creator_alpha22_step8",
        creator_plan_id="creator_plan_alpha22_step8",
        tasks=[
            ProductionTask(
                task_id="comfyui",
                task_type=ProductionTaskType.IMAGE,
                status=ProductionTaskStatus.SUCCEEDED,
                output_refs=[manifest.artifact_id],
                resource_class=ResourceClass.GPU_HEAVY,
                attempt_count=1,
            )
        ],
        status=ProductionStatus.SUCCEEDED,
    )
    plans.save(plan)
    adapter = ComfyUIProductionAdapter.from_config(
        base_url="http://127.0.0.1:8188",
        workflow_dir=ROOT / "comfyui" / "workflows",
        output_dir=Path(r"D:\ComfyUI\output"),
        timeout_sec=5,
        job_timeout_sec=30,
    )
    before_hash = sha256(artifact_path)
    before_mtime = artifact_path.stat().st_mtime_ns
    before_history = relevant_history_count()
    resumed = ProductionOrchestrator(
        adapters={ProductionTaskType.IMAGE: adapter},
        store=plans,
        artifacts=artifacts,
        preflight=lambda task: None,
    ).resume(plan.production_id)
    after_history = relevant_history_count()
    after_hash = sha256(artifact_path)
    after_mtime = artifact_path.stat().st_mtime_ns
    payload = {
        "result": "PASS",
        "checked_at": datetime.now().astimezone().isoformat(),
        "production_id": resumed.production_id,
        "adapter": "REAL_COMFYUI_ADAPTER",
        "task_status": resumed.task("comfyui").status.value,
        "artifact_id": manifest.artifact_id,
        "artifact_path": str(artifact_path),
        "artifact_valid": artifacts.valid(resumed.task("comfyui").output_refs),
        "hash_before": before_hash,
        "hash_after": after_hash,
        "mtime_before_ns": before_mtime,
        "mtime_after_ns": after_mtime,
        "comfyui_invocation_count_before": before_history,
        "comfyui_invocation_count_after": after_history,
        "successful_real_task_regenerated": False,
    }
    if (
        resumed.status != ProductionStatus.SUCCEEDED
        or before_hash != after_hash
        or before_mtime != after_mtime
        or before_history != after_history
    ):
        payload["result"] = "FAIL"
        payload["successful_real_task_regenerated"] = True
    atomic_write_json(ROOT / "resume" / "resume_result.json", payload, backup_count=1)
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
