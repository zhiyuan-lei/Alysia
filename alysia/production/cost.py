from __future__ import annotations

from typing import Any

from alysia.schemas import CostValue, ProviderCapability


class CostEstimator:
    """只接受 provider 可验证 usage/price 证据；不内置 API 单价。"""

    def estimate(
        self,
        capability: ProviderCapability,
        provider_usage: dict[str, Any] | None = None,
    ) -> CostValue:
        usage = provider_usage or {}
        if all(key in usage for key in ("actual_amount", "currency", "billing_source")):
            return CostValue(
                status="known",
                amount=float(usage["actual_amount"]),
                currency=str(usage["currency"]),
                source=str(usage["billing_source"]),
                details="由 provider 返回的账单证据记录",
            )
        if all(key in usage for key in ("estimated_amount", "currency", "price_source")):
            return CostValue(
                status="estimated_with_source",
                amount=float(usage["estimated_amount"]),
                currency=str(usage["currency"]),
                source=str(usage["price_source"]),
                details="由 provider usage 与显式价格来源计算",
            )
        if capability.local_or_cloud in {"local", "mock"}:
            return CostValue(
                status="unknown",
                details="runtime 可记录；energy/electricity cost 未知",
            )
        return CostValue(status="unknown", details="provider 未返回可验证 usage/price 来源")
