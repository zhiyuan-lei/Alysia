from __future__ import annotations

import os

import pytest

from alysia.core.config import load_config
from alysia.visual import VisualGenerationService


pytestmark = [pytest.mark.integration, pytest.mark.h3_local]


@pytest.mark.skipif(
    os.environ.get("ALYSIA_RUN_H3_LOCAL") != "1",
    reason="set ALYSIA_RUN_H3_LOCAL=1 to load the 42.5 GB local H3 stack",
)
def test_real_h3_t2v_smoke() -> None:
    service = VisualGenerationService(load_config())
    assert service.h3_setup_status()["ready"] is True
    report = service.h3_smoke_test()
    assert report["result"]["mock"] is False
    assert report["qa"]["passed"] is True
    assert report["qa"]["production_eligible"] is True
