from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from time import monotonic
from typing import Any

from alysia.core.resources import ResourceManager
from alysia.production.cost import CostEstimator
from alysia.production.metrics import ExecutionMetricsStore
from alysia.production.registry import ProviderCapabilityRegistry
from alysia.schemas import FallbackRecord, ProductionPlan, StageExecutionMetric


class ProductionExecutor:
    """执行已声明 handler 的轻量计划；用于离线模拟和可审计 worker 编排。"""

    def __init__(
        self,
        registry: ProviderCapabilityRegistry,
        resources: ResourceManager,
        metrics: ExecutionMetricsStore,
    ) -> None:
        self.registry = registry
        self.resources = resources
        self.metrics = metrics
        self.cost = CostEstimator()

    def execute(
        self,
        plan: ProductionPlan,
        handlers: dict[str, Callable[[str], Any]],
        *,
        cache_hits: set[str] | None = None,
    ) -> dict[str, Any]:
        outputs: dict[str, Any] = {}
        cache_hits = cache_hits or set()
        for stage in plan.stages:
            if stage.stage_id in cache_hits:
                now = datetime.now().astimezone()
                capability = self.registry.get(stage.selected_provider)
                self.metrics.record_stage(
                    StageExecutionMetric(
                        stage_id=stage.stage_id,
                        start_time=now,
                        end_time=now,
                        elapsed_sec=0,
                        provider=stage.selected_provider,
                        success=True,
                        cache_hit=True,
                        estimated_cost=self.cost.estimate(capability),
                        actual_cost=self.cost.estimate(capability),
                    )
                )
                outputs[stage.stage_id] = "cache_hit"
                continue
            choices = [stage.selected_provider, *stage.fallback_chain]
            last_error: Exception | None = None
            for index, provider_id in enumerate(choices):
                handler = handlers.get(provider_id)
                if handler is None:
                    last_error = RuntimeError(f"没有为 {provider_id} 注册执行 handler")
                    continue
                capability = self.registry.get(provider_id)
                started_at = datetime.now().astimezone()
                start = monotonic()
                try:
                    with self.resources.phase(
                        stage.stage_id,
                        provider=handler,
                        gpu_heavy=capability.gpu_heavy,
                        timeout_sec=plan.profile.max_wall_time_sec,
                    ):
                        outputs[stage.stage_id] = handler(stage.stage_id)
                    ended_at = datetime.now().astimezone()
                    self.metrics.record_stage(
                        StageExecutionMetric(
                            stage_id=stage.stage_id,
                            start_time=started_at,
                            end_time=ended_at,
                            elapsed_sec=monotonic() - start,
                            provider=provider_id,
                            success=True,
                            retry_count=index,
                            fallback_used=index > 0,
                            estimated_cost=self.cost.estimate(capability),
                            actual_cost=self.cost.estimate(capability),
                        )
                    )
                    break
                except Exception as exc:
                    last_error = exc
                    ended_at = datetime.now().astimezone()
                    self.metrics.record_stage(
                        StageExecutionMetric(
                            stage_id=stage.stage_id,
                            start_time=started_at,
                            end_time=ended_at,
                            elapsed_sec=monotonic() - start,
                            provider=provider_id,
                            success=False,
                            failure_reason=str(exc),
                            retry_count=index,
                            fallback_used=index > 0,
                            estimated_cost=self.cost.estimate(capability),
                            actual_cost=self.cost.estimate(capability),
                        )
                    )
                    if index + 1 < len(choices):
                        fallback = choices[index + 1]
                        impact = (
                            f"quality {capability.expected_quality_class} → "
                            f"{self.registry.get(fallback).expected_quality_class}"
                        )
                        self.metrics.record_fallback(
                            FallbackRecord(
                                stage_id=stage.stage_id,
                                original_choice=provider_id,
                                failure_reason=str(exc),
                                fallback_choice=fallback,
                                quality_impact=impact,
                                occurred_at=ended_at,
                            )
                        )
            else:
                assert last_error is not None
                raise last_error
        return outputs
