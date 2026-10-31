"""Verify real SAPI + Remotion + QA using a previously generated real H3 clip.

This does not claim a new H3 inference or a working ComfyUI service.
"""
from __future__ import annotations

import json
from pathlib import Path
import shutil

from alysia.core.config import load_config
from alysia.local_creator import LocalCreatorService, _hash_file


def main() -> None:
    existing = Path(
        "alpha22/field_smoke/h3_blink_720p/run_20261001_233242/H3_motion_720p_TEST_ONLY.mp4"
    ).resolve()
    reference = Path(
        "alpha22/field_smoke/h3_blink_720p/run_20261001_233242/reference_canvas.png"
    ).resolve()
    if not existing.is_file() or not reference.is_file():
        raise FileNotFoundError("此前真实 H3 视频或参考图不存在")
    service = LocalCreatorService(load_config())
    job = service.submit({
        "title": "本地闭环 CPU 阶段验证",
        "scenes": [{"scene_id": "scene_1", "backend": "h3_staged_i2v",
                    "reference_image": str(reference),
                    "prompt": "少女轻轻眨眼，花瓣飘落，头发和衣袖微动。",
                    "narration": "花瓣轻轻飘落，少女眨了眨眼。"}],
    })
    run_id = job["run_id"]
    target = service._dir(run_id) / "clips" / "scene_1.mp4"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(existing, target)
    state = service.status(run_id)
    state["clips"]["scene_1"] = {
        "path": str(target), "sha256": _hash_file(target),
        "duration_sec": service._video_duration(target),
        "backend": "existing_real_h3_artifact_reused_for_cpu_smoke",
        "source": str(existing),
    }
    service._save(state)
    result = service.run(run_id)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["status"] != "COMPLETE":
        raise RuntimeError(result["error"])


if __name__ == "__main__":
    main()
