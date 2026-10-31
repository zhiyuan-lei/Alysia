"""Create an isolated failure fixture for the Alpha21 Recovery UI smoke demo.

The generated run is explicitly marked testing and exercises the real Alpha19
FailureStore and RecoveryPolicy. It does not publish or call a provider.
"""

from __future__ import annotations

import json

from alysia.core.config import load_config
from alysia.core.run import RunManager
from alysia.core.state import Stage
from alysia.reliability import ReliabilityService


def main() -> None:
    config = load_config()
    manager = RunManager(config.runtime.runs_dir)
    for directory in manager.runs_dir.iterdir():
        if not directory.is_dir():
            continue
        try:
            existing = manager.load(directory.name)
        except (OSError, ValueError):
            continue
        if existing.config_snapshot.get("alpha21_demo") == "recovery":
            failures = ReliabilityService(config, manager=manager).failures(existing.run_id).list(run_id=existing.run_id)
            print(json.dumps({"run_id": existing.run_id, "failure_id": failures[-1].failure_id}, ensure_ascii=False))
            return

    state = manager.create(
        "Alpha21 Control Center recovery smoke fixture",
        {"testing": True, "alpha21_demo": "recovery", "environment": "MOCK"},
    )
    reliability = ReliabilityService(config, manager=manager)
    failure, decision = reliability.record_exception(
        RuntimeError("approval_invalid: Alpha21 controlled recovery demo"),
        state=state,
        stage=Stage.PUBLISH_JOB.value,
        provider=None,
        retry_count=0,
    )
    state.fail_stage(Stage.PUBLISH_JOB, RuntimeError(failure.message))
    manager.save(state)
    print(
        json.dumps(
            {"run_id": state.run_id, "failure_id": failure.failure_id, "decision": decision.action},
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
